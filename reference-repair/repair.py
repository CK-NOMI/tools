import base64, io, json, subprocess, tempfile, uuid
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from PIL import Image, ImageDraw
from pptx import Presentation
from pptx.util import Pt
from object_engine import scene, apply_v2
ROOT=Path(__file__).parent

def decode(s): return base64.b64decode(s.split(',')[-1],validate=True)
def render(path, folder, w, h):
    subprocess.run(['soffice','-env:UserInstallation='+ (folder/'profile').as_uri(),'--headless','--convert-to','pdf','--outdir',str(folder),str(path)],check=True,capture_output=True,timeout=90)
    subprocess.run(['pdftoppm','-scale-to-x',str(w),'-scale-to-y',str(h),'-png',str(folder/(path.stem+'.pdf')),str(folder/'slide')],check=True,timeout=90)
    return sorted(folder.glob('slide-*.png'),key=lambda p:int(p.stem.split('-')[-1]))
def objects(p):
    return [[dict(id=s.shape_id,name=s.name,text=s.text if s.has_text_frame else '',type=str(s.shape_type),box=[s.left/p.slide_width,s.top/p.slide_height,s.width/p.slide_width,s.height/p.slide_height]) for s in sl.shapes] for sl in p.slides]
def apply(source,operations,out):
    p=Presentation(source)
    for op in operations:
        sl=p.slides[int(op['slide'])]; tree=sl.shapes._spTree
        kind=op['kind']
        if kind=='patch':
            b=op['box']; img=Image.open(io.BytesIO(decode(op['png']))).convert('RGBA')
            if not (0<=b[0]<=1 and 0<=b[1]<=1 and 0<b[2]<=1.000001-b[0] and 0<b[3]<=1.000001-b[1]): raise ValueError('invalid patch box')
            if op.get('protect'):
                mask=img.getchannel('A'); d=ImageDraw.Draw(mask)
                for s in sl.shapes:
                    if s.has_text_frame and s.text.strip():
                        x,y,w,h=s.left/p.slide_width,s.top/p.slide_height,s.width/p.slide_width,s.height/p.slide_height
                        d.rectangle(((x-b[0])/b[2]*img.width,(y-b[1])/b[3]*img.height,(x+w-b[0])/b[2]*img.width,(y+h-b[1])/b[3]*img.height),fill=0)
                img.putalpha(mask)
            buf=io.BytesIO();img.save(buf,format='PNG');buf.seek(0)
            sh=sl.shapes.add_picture(buf,*[round(v*scale) for v,scale in zip(b,[p.slide_width,p.slide_height,p.slide_width,p.slide_height])]);sh.name='Reference repair '+str(op.get('label','patch'))
            if op.get('behind'):
                anchor=next((s for s in sl.shapes if s.shape_id==op.get('anchor')),None)
                if anchor is not None: tree.remove(sh._element);tree.insert(tree.index(anchor._element),sh._element)
        else:
            s=next((s for s in sl.shapes if s.shape_id==op['id']),None)
            if s is None: raise ValueError('object not found: '+str(op['id']))
            e=s._element
            if kind=='delete': tree.remove(e)
            elif kind=='front': tree.remove(e);tree.append(e)
            elif kind=='back': tree.remove(e);tree.insert(2,e)
            elif kind=='layout':
                if 'box' in op: s.left,s.top,s.width,s.height=[round(v*scale) for v,scale in zip(op['box'],[p.slide_width,p.slide_height,p.slide_width,p.slide_height])]
                if 'font' in op and s.has_text_frame:
                    for para in s.text_frame.paragraphs:
                        for run in para.runs: run.font.size=Pt(op['font'])
                if 'text' in op and s.has_text_frame: s.text=op['text']
            else: raise ValueError('unknown operation')
    p.save(out)

class Handler(BaseHTTPRequestHandler):
    def send(self,data,typ='application/json'):
        self.send_response(200);self.send_header('Content-Type',typ);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_GET(self):
        if self.path=='/': self.send((ROOT/'v2.html').read_bytes(),'text/html; charset=utf-8')
        elif self.path=='/legacy': self.send((ROOT/'index.html').read_bytes(),'text/html; charset=utf-8')
        elif self.path=='/v2.js': self.send((ROOT/'v2.js').read_bytes(),'application/javascript; charset=utf-8')
        elif self.path=='/sample':
            deck=ROOT/'samples'/'city.pptx'; ref=ROOT/'samples'/'city.png'
            if not deck.is_file() or not ref.is_file():
                self.send(json.dumps({'available':False}).encode())
            else:
                self.send(json.dumps({'available':True,'pptx':'data:application/vnd.openxmlformats-officedocument.presentationml.presentation;base64,'+base64.b64encode(deck.read_bytes()).decode(),'reference':'data:image/png;base64,'+base64.b64encode(ref.read_bytes()).decode()}).encode())
        else: self.send_error(404)
    def do_POST(self):
        try:
            n=int(self.headers['Content-Length']);
            if n>100_000_000: raise ValueError('payload too large')
            req=json.loads(self.rfile.read(n))
            with tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp);source=folder/'input.pptx';source.write_bytes(decode(req['pptx']));p=Presentation(source)
                if self.path=='/v2/inspect':
                    w=1600;h=round(w*p.slide_height/p.slide_width);pages=render(source,folder,w,h)
                    self.send(json.dumps(dict(width=w,height=h,width_pt=p.slide_width/12700,scene=scene(p),pages=['data:image/png;base64,'+base64.b64encode(x.read_bytes()).decode() for x in pages])).encode())
                elif self.path in ('/v2/export','/v2/preview'):
                    out=folder/'repaired-v2.pptx';apply_v2(source,req['transactions'],out)
                    if self.path=='/v2/export': self.send(out.read_bytes(),'application/vnd.openxmlformats-officedocument.presentationml.presentation')
                    else:
                        w=1600;h=round(w*p.slide_height/p.slide_width);pages=render(out,folder,w,h)
                        self.send(json.dumps(dict(pages=['data:image/png;base64,'+base64.b64encode(x.read_bytes()).decode() for x in pages])).encode())
                elif self.path=='/inspect':
                    w=1600;h=round(w*p.slide_height/p.slide_width);pages=render(source,folder,w,h)
                    self.send(json.dumps(dict(width=w,height=h,objects=objects(p),pages=['data:image/png;base64,'+base64.b64encode(x.read_bytes()).decode() for x in pages])).encode())
                elif self.path in ('/export','/preview'):
                    out=folder/'repaired.pptx';apply(source,req['ops'],out)
                    if self.path=='/export': self.send(out.read_bytes(),'application/vnd.openxmlformats-officedocument.presentationml.presentation')
                    else:
                        w=1600;h=round(w*p.slide_height/p.slide_width);pages=render(out,folder,w,h);self.send(json.dumps(dict(pages=['data:image/png;base64,'+base64.b64encode(x.read_bytes()).decode() for x in pages])).encode())
                else: self.send_error(404)
        except Exception as e:
            self.send_error(400,str(e))
if __name__=='__main__': ThreadingHTTPServer(('127.0.0.1',8765),Handler).serve_forever()
