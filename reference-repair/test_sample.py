"""Reproduce the sample repair using the same operation engine as the UI."""
import argparse, base64, io, json, time
from pathlib import Path
from PIL import Image, ImageDraw
from pptx import Presentation
from repair import apply, render
import numpy as np

def main():
    ap=argparse.ArgumentParser();ap.add_argument('pptx',type=Path);ap.add_argument('png',type=Path);ap.add_argument('out',type=Path);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    w,h=1648,928; ref=Image.open(a.png).convert('RGBA').resize((w,h),Image.Resampling.LANCZOS);p=Presentation(a.pptx);ops=[]
    def delete(i):ops.append(dict(kind='delete',slide=0,id=i))
    def layout(i,b=None,font=None):
        o=dict(kind='layout',slide=0,id=i)
        if b:o['box']=[b[0]/w,b[1]/h,b[2]/w,b[3]/h]
        if font:o['font']=font
        ops.append(o)
    def patch(box,im,label,anchor=None):
        x,y,r,b=box;buf=io.BytesIO();im.save(buf,format='PNG');ops.append(dict(kind='patch',slide=0,box=[x/w,y/h,(r-x)/w,(b-y)/h],png=base64.b64encode(buf.getvalue()).decode(),label=label,behind=anchor is not None,anchor=anchor,protect=False))
    start=time.perf_counter()
    # Sample-specific manual decisions: retain background, cards, connectors and all text.
    for i in [3,4,5,6,7,8,21]:delete(i)
    # The data-center label is misplaced. Restore its underlying dark panel and text at reference position.
    layout(9,(1099,350,142,34));layout(32,(1101,350,140,32),13)
    # Exclude interiors of existing cards and the building sign from source to prevent baked duplicate text.
    bg=ref.crop((0,130,w,721));alpha=bg.getchannel('A');d=ImageDraw.Draw(alpha)
    for x,y,r,b in [(45,148,350,262),(535,148,831,263),(1153,148,1450,263),(44,582,334,696),(644,582,933,696),(1302,582,1604,696)]:
        d.rounded_rectangle((x+2,y-130+2,r-2,b-130-2),radius=23,fill=0)
    d.rectangle((1099,350-130,1241,384-130),fill=0);bg.putalpha(alpha);patch((0,130,w,721),bg,'city scene',10)
    for box,label in [((60,167,138,240),'green building'),((550,161,632,240),'solar'),((1170,171,1242,241),'monitor'),((56,607,134,675),'bicycle'),((661,602,728,675),'tree'),((1317,608,1390,670),'people'),((50,753,123,828),'gear'),((609,753,680,828),'cloud'),((1179,754,1246,830),'growth')]:
        im=ref.crop(box);arr=np.array(im);# sample icons sit on light backgrounds; reject light pixels while retaining colored edges
        rgb=arr[:,:,:3].astype(int);chroma=rgb.max(2)-rgb.min(2);arr[:,:,3]=np.where((rgb.min(2)>210)&(chroma<48),0,255).astype('uint8');patch(box,Image.fromarray(arr),label)
    layout(35,font=17.25);layout(36,(154,200,191,50),11.4);layout(33,font=30);layout(47,(199,753,278,44),20);layout(49,(702,753,322,44),20)
    out=a.out/'repaired.pptx';apply(a.pptx,ops,out);elapsed=time.perf_counter()-start
    for n,f in [('before',a.pptx),('after',out)]:
        folder=a.out/n;folder.mkdir(exist_ok=True);r=render(f.resolve(),folder.resolve(),w,h);Image.open(r[0]).save(a.out/(n+'.png'))
    before=Presentation(a.pptx);after=Presentation(out)
    def texts(p):return {s.shape_id:s.text for s in p.slides[0].shapes if s.has_text_frame and s.text.strip()}
    assert texts(before)==texts(after)
    arr=np.asarray(ref.convert('RGB'),dtype=np.float32)
    def mae(n):return float(np.abs(np.asarray(Image.open(a.out/(n+'.png')).convert('RGB'),dtype=np.float32)-arr).mean())
    report=dict(operations=len(ops),objects_before=len(before.slides[0].shapes),objects_after=len(after.slides[0].shapes),text_objects=len(texts(after)),texts_identical=True,mae_before=mae('before'),mae_after=mae('after'),engine_seconds=elapsed)
    print(json.dumps(report,indent=2));(a.out/'report.json').write_text(json.dumps(report,indent=2))
if __name__=='__main__':main()
