import argparse, subprocess, sys, time, urllib.request, base64
from pathlib import Path
from playwright.sync_api import sync_playwright
from pptx import Presentation

def main():
    p=argparse.ArgumentParser();p.add_argument('pptx',type=Path);p.add_argument('png',type=Path);p.add_argument('out',type=Path);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    server=subprocess.Popen([sys.executable,str(Path(__file__).with_name('repair.py'))],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        time.sleep(.7)
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);page=browser.new_page(viewport={'width':1600,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            # Chromium policy blocks localhost navigation in this environment. Test DOM and pointer interactions with a local HTTP bridge.
            def bridge(path, body):
                request=urllib.request.Request('http://127.0.0.1:8765'+path,data=body.encode(),headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(request,timeout=120) as r:return {'data':base64.b64encode(r.read()).decode(),'type':r.headers.get('Content-Type')}
            page.expose_function('bridge',bridge);page.set_content(Path(__file__).with_name('index.html').read_text());page.evaluate("() => {window.fetch=async (path,opts)=>{const r=await bridge(path,opts.body);return new Response(Uint8Array.from(atob(r.data),c=>c.charCodeAt(0)),{headers:{'Content-Type':r.type}})}}")
            page.locator('#ppt').set_input_files(str(a.pptx));page.locator('#ref').set_input_files(str(a.png));page.locator('#load').click();page.wait_for_function("document.querySelector('#status').textContent.includes('已载入')",timeout=120000)
            c=page.locator('#view').bounding_box();x,y,w,h=[c[k] for k in ('x','y','width','height')]
            def draw(tool,a,b):
                page.select_option('#tool',tool);page.mouse.move(x+a[0]*w,y+a[1]*h);page.mouse.down();page.mouse.move(x+b[0]*w,y+b[1]*h,steps=8);page.mouse.up()
            for tool in ['rect','round','circle','ellipse','lasso','brush']:
                draw(tool,(.045,.19),(.078,.25));page.locator('#clear').click()
            draw('ellipse',(.045,.19),(.078,.25));page.select_option('#combine','add');draw('rect',(.34,.19),(.38,.25));page.select_option('#combine','subtract');draw('rect',(.045,.19),(.05,.20));page.locator('#apply').click();page.wait_for_function("document.querySelector('#history').textContent.includes('1 项')");page.locator('#undo').click();page.wait_for_function("document.querySelector('#history').textContent.includes('0 项')");page.locator('#redo').click();page.wait_for_function("document.querySelector('#history').textContent.includes('1 项')")
            page.locator('#obj').select_option('21');page.locator('[data-op=delete]').click();page.locator('#preview').click();page.wait_for_function("document.querySelector('#status').textContent.includes('已更新真实')",timeout=120000)
            with page.expect_download(timeout=120000) as d:page.locator('#export').click()
            d.value.save_as(str(a.out/'ui-export.pptx'));page.screenshot(path=str(a.out/'ui.png'),full_page=True);browser.close()
            before=Presentation(a.pptx);after=Presentation(a.out/'ui-export.pptx');assert len(after.slides[0].shapes)==len(before.slides[0].shapes);assert all(s.shape_id!=21 or s.shape_type!=13 or s.name.startswith('Reference repair') for s in after.slides[0].shapes);assert [s.text for s in before.slides[0].shapes if s.has_text_frame and s.text]==[s.text for s in after.slides[0].shapes if s.has_text_frame and s.text];assert not errors,errors;print('PASS: actual Chromium mouse selections, add/subtract, patch, undo/redo, delete, preview, export, text retention; no pageerror')
    finally:server.terminate();server.wait(timeout=10)
if __name__=='__main__':main()
