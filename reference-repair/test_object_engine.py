"""Synthetic export/read-back regression for the v2 object engine."""
import io
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from pptx import Presentation
from pptx.util import Inches, Pt
from object_engine import scene, apply_v2, uri

def asset(rgb):
    b=io.BytesIO()
    Image.new("RGB",(50,25),rgb).save(b,format="PNG")
    return b.getvalue()

class ObjectEngineTest(unittest.TestCase):
    def test_transaction_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/"input.pptx"
            out=Path(tmp)/"output.pptx"
            p=Presentation()
            sl=p.slides.add_slide(p.slide_layouts[6])
            pic=sl.shapes.add_picture(io.BytesIO(asset("red")), Inches(1), Inches(1), Inches(2), Inches(1))
            text=sl.shapes.add_textbox(Inches(3), Inches(1), Inches(2), Inches(1))
            run=text.text_frame.paragraphs[0].add_run();run.text="Before";run.font.size=Pt(24);run.font.bold=True
            a,b=str(pic.shape_id),str(text.shape_id)
            p.save(src); original=src.read_bytes()
            data=scene(Presentation(src))[0]["objects"]
            self.assertEqual([o["kind"] for o in data],["picture","text"])
            self.assertTrue(data[0]["asset"].startswith("data:image/png"))
            def op(kind,ident,**kw): return dict(kind=kind,id=ident,slide=0,**kw)
            txs=[dict(ops=[op("replace",a,box=[.1,.1,.2,.2],asset=uri(asset("blue"))),
                           op("text",b,text="After"),
                           op("insert","patch-1",box=[.5,.5,.2,.2],asset=uri(asset("green")))]),
                 dict(ops=[op("layout","patch-1",box=[.4,.4,.3,.2]),op("back","patch-1")])]
            apply_v2(src,txs,out)
            self.assertEqual(src.read_bytes(),original)
            q=Presentation(out); shapes=list(q.slides[0].shapes)
            self.assertEqual(len(shapes),3)
            self.assertEqual(shapes[0].name,"Reference recovery patch-1")
            self.assertAlmostEqual(shapes[0].left/q.slide_width,.4,places=5)
            self.assertEqual(Image.open(io.BytesIO(shapes[1].image.blob)).getpixel((0,0)),(0,0,255,255))
            self.assertEqual(shapes[2].text,"After")
            self.assertEqual(shapes[2].text_frame.paragraphs[0].runs[0].font.size.pt,24)
            self.assertTrue(shapes[2].text_frame.paragraphs[0].runs[0].font.bold)
            # Replay before the second transaction simulates undo.
            apply_v2(src,txs[:1],out)
            q=Presentation(out)
            self.assertEqual(q.slides[0].shapes[-1].name,"Reference recovery patch-1")

if __name__=="__main__":
    unittest.main()
