"""Object editing and reference recovery for the v2 workspace.
The original PPTX is never mutated. IDs are slide-scoped, and new IDs are
mapped to shapes during replay. The browser preview is deliberately approximate;
LibreOffice remains the authoritative renderer.
"""
import base64
import io
import math
from PIL import Image
from pptx import Presentation
from pptx.util import Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.enum.text import PP_ALIGN

def uri(blob, mime="image/png"):
    return "data:" + mime + ";base64," + base64.b64encode(blob).decode()

def decode(value):
    return base64.b64decode(value.split(",", 1)[-1], validate=True)

def color(value, fallback=None):
    try:
        return "#" + str(value.rgb)
    except (AttributeError, TypeError, ValueError):
        return fallback

def fill(shape):
    try:
        return color(shape.fill.fore_color)
    except (AttributeError, TypeError, ValueError):
        return None

def first_style(s):
    p = s.text_frame.paragraphs[0]
    f = p.runs[0].font if p.runs else p.font
    return dict(font=f.name or "", size=f.size.pt if f.size else 18,
                bold=bool(f.bold), italic=bool(f.italic),
                color=color(f.color, "#222222"),
                align={PP_ALIGN.CENTER:"center", PP_ALIGN.RIGHT:"right"}.get(p.alignment,"left"))

def picture(s):
    try:
        im = Image.open(io.BytesIO(s.image.blob)).convert("RGBA")
        w,h = im.size
        l,t,r,b = [float(getattr(s,"crop_"+k,0)) for k in ("left","top","right","bottom")]
        box = (round(w*l),round(h*t),round(w*(1-r)),round(h*(1-b)))
        if box[2]>box[0] and box[3]>box[1]:
            im=im.crop(box)
        out=io.BytesIO(); im.save(out,format="PNG")
        return uri(out.getvalue())
    except (AttributeError, ValueError, OSError):
        return None

def scene(p):
    pages=[]
    for sl in p.slides:
        result=[]
        for s in sl.shapes:
            typ=s.shape_type
            kind="picture" if typ==MSO_SHAPE_TYPE.PICTURE else ("text" if s.has_text_frame else "unsupported")
            # Keep unknown shapes in the scene as selectable placeholders; never
            # flatten them into the slide or silently change their native type.
            o=dict(id=str(s.shape_id), name=s.name, kind=kind,
                   box=[s.left/p.slide_width,s.top/p.slide_height,s.width/p.slide_width,s.height/p.slide_height],
                   rotation=float(s.rotation or 0), fill=fill(s))
            if kind=="picture":
                o["asset"]=picture(s)
            if kind=="text":
                o.update(text=s.text, **first_style(s))
            try:
                o["line"]=color(s.line.color)
            except (AttributeError, TypeError, ValueError):
                pass
            result.append(o)
        bg=fill(sl.background)
        pages.append(dict(background=bg or "#ffffff",objects=result))
    return pages

def checked_box(b):
    if not isinstance(b,list) or len(b)!=4:
        raise ValueError("invalid box")
    b=[float(v) for v in b]
    if not all(math.isfinite(v) for v in b) or b[2]<=0 or b[3]<=0 or any(abs(v)>10 for v in b):
        raise ValueError("invalid object geometry")
    return b

def dimensions(p,b):
    return [round(v*k) for v,k in zip(checked_box(b),(p.slide_width,p.slide_height,p.slide_width,p.slide_height))]

def patch(sl,p,op):
    im=Image.open(io.BytesIO(decode(op["asset"]))).convert("RGBA")
    buf=io.BytesIO();im.save(buf,format="PNG");buf.seek(0)
    s=sl.shapes.add_picture(buf,*dimensions(p,op["box"]))
    s.name="Reference recovery "+str(op["id"])
    s.rotation=float(op.get("rotation",0))
    return s

def apply_v2(source,transactions,out):
    p=Presentation(source)
    maps=[{str(s.shape_id):s for s in sl.shapes} for sl in p.slides]
    for tx in transactions:
        for op in tx["ops"]:
            i=int(op["slide"])
            sl=p.slides[i]; m=maps[i]; tree=sl.shapes._spTree
            k=op["kind"]; ident=str(op["id"])
            if k in ("insert","replace"):
                if k=="insert" and ident in m: raise ValueError("duplicate object")
                old=m.get(ident)
                if k=="replace" and (old is None or old.shape_type!=MSO_SHAPE_TYPE.PICTURE):
                    raise ValueError("only picture objects can be replaced")
                new=patch(sl,p,op)
                if old is not None:
                    pos=tree.index(old._element)
                    tree.remove(new._element);tree.insert(pos,new._element);tree.remove(old._element)
                m[ident]=new
                continue
            s=m.get(ident)
            if s is None: raise ValueError("missing object "+ident)
            e=s._element
            if k=="delete":
                tree.remove(e);del m[ident]
            elif k=="front":
                tree.remove(e);tree.append(e)
            elif k=="back":
                tree.remove(e);tree.insert(2,e)
            elif k=="layout":
                s.left,s.top,s.width,s.height=dimensions(p,op["box"])
                rot=float(op.get("rotation",s.rotation or 0))
                if not math.isfinite(rot): raise ValueError("invalid rotation")
                s.rotation=rot%360
            elif k=="text":
                if not s.has_text_frame: raise ValueError("not a text object")
                tf=s.text_frame
                # Editing text preserves the first run's style, not arbitrary
                # mixed formatting. Existing paragraphs are retained when possible.
                if "text" in op:
                    lines=str(op["text"]).split("\n")
                    for n,line in enumerate(lines):
                        para=tf.paragraphs[n] if n<len(tf.paragraphs) else tf.add_paragraph()
                        runs=para.runs
                        if runs:
                            runs[0].text=line
                            for run in runs[1:]: run.text=""
                        else:
                            para.add_run().text=line
                    for para in list(tf.paragraphs)[len(lines):]:
                        para._p.getparent().remove(para._p)
                for para in tf.paragraphs:
                    if "align" in op: para.alignment={"left":PP_ALIGN.LEFT,"center":PP_ALIGN.CENTER,"right":PP_ALIGN.RIGHT}[op["align"]]
                    for run in para.runs:
                        f=run.font
                        if "size" in op: f.size=Pt(float(op["size"]))
                        if "font" in op and op["font"]: f.name=str(op["font"])
                        if "color" in op: f.color.rgb=RGBColor.from_string(op["color"].lstrip("#").upper())
                        if "bold" in op: f.bold=bool(op["bold"])
                        if "italic" in op: f.italic=bool(op["italic"])
            else: raise ValueError("unknown v2 operation "+k)
    p.save(out)
