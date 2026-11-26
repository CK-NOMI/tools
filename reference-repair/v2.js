"use strict";
const $=id=>document.getElementById(id), board=$("board"), sceneEl=$("scene");
let source=null, meta=null, pg=0, refs={}, txs=[], cursor=0, selected=null, mode="select", drag=null, draft=null, candidate=null, busy=false, exactPages=null, repairTarget=null;
const copy=x=>JSON.parse(JSON.stringify(x)), setStatus=x=>$("status").textContent=x;
const activeTx=()=>txs.slice(0,cursor), op=(kind,id,fields={})=>({kind,id,slide:pg,...fields});
const currentPage=()=>meta?.scene[pg];
function objects(){
  if(!meta)return [];
  const arr=copy(currentPage().objects);
  for(const tx of activeTx())for(const o of tx.ops){
    if(o.slide!==pg)continue;
    const i=arr.findIndex(a=>a.id===o.id);
    if(o.kind==="insert")arr.push({id:o.id,name:"原图取件",kind:"picture",box:o.box,asset:o.asset,rotation:o.rotation||0});
    else if(i>=0){
      if(o.kind==="delete")arr.splice(i,1);
      else if(o.kind==="front")arr.push(arr.splice(i,1)[0]);
      else if(o.kind==="back")arr.unshift(arr.splice(i,1)[0]);
      else if(o.kind==="replace")arr[i]={...arr[i],box:o.box,asset:o.asset,rotation:o.rotation||0};
      else if(o.kind==="layout")Object.assign(arr[i],{box:o.box,rotation:o.rotation??arr[i].rotation});
      else if(o.kind==="text"){const {kind,id,slide,...fields}=o;Object.assign(arr[i],fields);}
    }
  }
  if(draft){const a=arr.find(a=>a.id===draft.id);if(a)a.box=draft.box;}
  return arr;
}
const chosen=()=>objects().find(a=>a.id===selected);
function geometry(el,b){Object.assign(el.style,{left:b[0]*100+"%",top:b[1]*100+"%",width:b[2]*100+"%",height:b[3]*100+"%"});}
function live(){ $("exact").hidden=true;$("mode").textContent="编辑预览（近似）"; }
function draw(){
  sceneEl.replaceChildren();$("selection").replaceChildren();
  if(!meta)return;
  sceneEl.style.background=currentPage().background;
  const arr=objects(), factor=board.clientWidth/meta.width_pt;
  for(const a of arr){
    const el=document.createElement("div");el.className="object"+(a.kind==="unsupported"||a.kind==="picture"&&!a.asset?" unsupported":"");el.dataset.id=a.id;geometry(el,a.box);el.style.transform="rotate("+a.rotation+"deg)";el.title=a.name;
    if(a.kind==="picture"&&a.asset){const img=document.createElement("img");img.src=a.asset;img.draggable=false;el.append(img);}
    else if(a.kind==="text"){
      el.textContent=a.text||"";el.style.background=a.fill||"transparent";if(a.line)el.style.border="1px solid "+a.line;
      Object.assign(el.style,{display:"block",fontFamily:a.font||"sans-serif",fontSize:(a.size*factor)+"px",fontWeight:a.bold?"bold":"normal",fontStyle:a.italic?"italic":"normal",color:a.color,textAlign:a.align,lineHeight:"1.15"});
    }else el.textContent=a.name;
    sceneEl.append(el);
  }
  const a=arr.find(o=>o.id===selected);
  if(a&&mode==="select"&&$("exact").hidden){
    const outline=document.createElement("div");outline.className="outline";geometry(outline,a.box);outline.style.transform="rotate("+a.rotation+"deg)";
    if(a.rotation%360===0)for(const [x,y,dir] of [[0,0,"nw"],[50,0,"n"],[100,0,"ne"],[0,50,"w"],[100,50,"e"],[0,100,"sw"],[50,100,"s"],[100,100,"se"]]){
      const h=document.createElement("div");h.className="handle";h.dataset.handle=dir;h.style.left=x+"%";h.style.top=y+"%";h.style.cursor=dir+"-resize";outline.append(h);
    }
    $("selection").append(outline);
  }
  if(drag?.kind==="region"&&drag.box){const r=document.createElement("div");r.className="region";geometry(r,drag.box);$("selection").append(r);}
  $("overlay").hidden=!refs[pg];if(refs[pg])$("overlay").src=refs[pg].src;
}
function panel(){
  const a=chosen();$("props").hidden=!a;$("empty").hidden=!!a;$("textprops").hidden=a?.kind!=="text";
  if(a){
    $("name").textContent=a.name;$("kind").textContent={picture:"图片对象",text:"原生文字 / 形状",unsupported:"复杂对象（仅布局操作）"}[a.kind];
    ["x","y","w","h"].forEach((k,i)=>$(k).value=(a.box[i]*100).toFixed(2));
    $("rotation").value=a.rotation;
    if(a.kind==="text"){for(const k of ["font","size","color","align"])$(k).value=a[k];for(const k of ["bold","italic"])$(k).classList.toggle("active",!!a[k]);}
    $("recover").disabled=busy||!refs[pg]||a.kind!=="picture"||a.rotation%360!==0;$("pick-replace").disabled=$("recover").disabled;$("match").disabled=$("recover").disabled||!a.asset;
  }
  $("layers").replaceChildren();
  for(const o of objects().reverse()){
    const b=document.createElement("button");b.textContent=o.name+(o.text?" · "+o.text.slice(0,30):"");b.classList.toggle("active",o.id===selected);b.onclick=()=>{selected=o.id;chooseMode("select");live();refresh();};$("layers").append(b);
  }
  $("history").replaceChildren();
  txs.forEach((t,i)=>{const row=document.createElement("div");row.className="history-row";const b=document.createElement("button");b.textContent=(i<cursor?"✓ ":"")+t.label;b.disabled=busy;b.onclick=()=>{cursor=i+1;selected=null;live();refresh();};const span=document.createElement("span");span.textContent=(t.ms/1000).toFixed(2)+"s";row.append(b,span);$("history").prepend(row);});
  $("total").textContent=cursor+" 项已应用 · "+(activeTx().reduce((a,t)=>a+t.ms,0)/1000).toFixed(2)+" 秒";
  $("undo").disabled=busy||cursor===0;$("redo").disabled=busy||cursor===txs.length;$("verify").disabled=busy||!meta;$("export").disabled=busy||!meta;$("live").disabled=busy||!meta;
}
function refresh(){draw();panel();}
function commit(label,ops,start=performance.now()){
  if(!ops.length)return;
  txs=txs.slice(0,cursor);txs.push({label,ops,ms:performance.now()-start,time:Date.now()});cursor=txs.length;draft=null;live();refresh();setStatus(label+" · 已应用，可撤销");
}
function chooseMode(m){if(m!=="region")repairTarget=null;mode=m;$("select").classList.toggle("active",m==="select");$("region").classList.toggle("active",m==="region");if(m==="region"){selected=null;$("opacity").value=100;$("overlay").style.opacity=1;setStatus("在原图上框选需要恢复的区域。");}else{$("opacity").value=0;$("overlay").style.opacity=0;}live();refresh();}
$("select").onclick=()=>chooseMode("select");
$("region").onclick=()=>{if(!refs[pg])return setStatus("先上传当前页的原图。");repairTarget=null;chooseMode("region");};
$("opacity").oninput=()=>{$("overlay").style.opacity=$("opacity").value/100;};
function point(e){const r=board.getBoundingClientRect();return [(e.clientX-r.left)/r.width,(e.clientY-r.top)/r.height];}
const clamp=(x,l=0,h=1)=>Math.max(l,Math.min(h,x));
board.addEventListener("pointerdown",e=>{
  if(!meta||busy||e.button!==0||e.target.closest("textarea")||!$("exact").hidden)return;
  const p=point(e), started=performance.now();
  if(mode==="region"){drag={kind:"region",p,box:[p[0],p[1],0,0],started};}
  else{
    const handle=e.target.dataset.handle, id=e.target.closest(".object")?.dataset.id;
    if(!handle){selected=id||null;refresh();}
    const a=chosen();if(!a)return;
    drag={kind:handle?"resize":"move",handle,p,id:a.id,box:a.box.slice(),started};
  }
  board.setPointerCapture(e.pointerId);e.preventDefault();
});
board.addEventListener("pointermove",e=>{
  if(!drag)return;
  const p=point(e),dx=p[0]-drag.p[0],dy=p[1]-drag.p[1];
  if(drag.kind==="region"){const x=clamp(drag.p[0]),y=clamp(drag.p[1]),xx=clamp(p[0]),yy=clamp(p[1]);drag.box=[Math.min(x,xx),Math.min(y,yy),Math.abs(xx-x),Math.abs(yy-y)];}
  else{
    let [x,y,w,h]=drag.box;
    if(drag.kind==="move"){x+=dx;y+=dy;}
    else{const d=drag.handle,min=.004;if(d.includes("w")){const change=Math.min(dx,w-min);x+=change;w-=change;}if(d.includes("e"))w=Math.max(min,w+dx);if(d.includes("n")){const change=Math.min(dy,h-min);y+=change;h-=change;}if(d.includes("s"))h=Math.max(min,h+dy);}
    draft={id:drag.id,box:[x,y,w,h]};
  }
  draw();
});
board.addEventListener("pointerup",()=>{
  if(!drag)return;const d=drag;drag=null;
  if(d.kind==="region"){draw();if(d.box[2]>.003&&d.box[3]>.003)propose(d.box,repairTarget,d.started);return;}
  const b=draft?.box;draft=null;
  if(b&&b.some((v,i)=>Math.abs(v-d.box[i])>1e-5))commit(d.kind==="move"?"移动对象":"缩放对象",[op("layout",d.id,{box:b})],d.started);else refresh();
});
board.addEventListener("pointercancel",()=>{drag=null;draft=null;refresh();});
function editText(){
  const a=chosen();if(!a||a.kind!=="text"||busy)return;
  if(board.querySelector(".editor"))return;
  const t=document.createElement("textarea");t.className="editor";geometry(t,a.box);t.value=a.text;t.style.fontSize=(a.size*board.clientWidth/meta.width_pt)+"px";board.append(t);t.focus();t.select();
  let cancelled=false;const started=performance.now();
  t.onkeydown=e=>{if(e.key==="Escape"){cancelled=true;t.blur();}else if(e.key==="Enter"&&(e.ctrlKey||e.metaKey))t.blur();};
  t.onblur=()=>{const text=t.value;t.remove();if(!cancelled&&text!==a.text)commit("编辑文字",[op("text",a.id,{text})],started);};
}
board.addEventListener("dblclick",e=>{if(mode==="select"&&chosen()){const [x,y]=point(e),b=chosen().box;if(x>=b[0]&&x<=b[0]+b[2]&&y>=b[1]&&y<=b[1]+b[3])editText();}});
$("edittext").onclick=editText;
for(const k of ["x","y","w","h","rotation"])$(k).onchange=()=>{
  const a=chosen();if(!a)return;
  const b=["x","y","w","h"].map(k=>Number($(k).value)/100),r=Number($("rotation").value);
  if(b.some(v=>!Number.isFinite(v)||Math.abs(v)>10)||b[2]<=0||b[3]<=0||!Number.isFinite(r)){panel();return setStatus("无效位置或尺寸");}
  commit("调整对象属性",[op("layout",a.id,{box:b,rotation:((r%360)+360)%360})]);
};
for(const k of ["font","size","color","align"])$(k).onchange=()=>{const a=chosen();if(!a)return;const value=k==="size"?Number($(k).value):$(k).value;if(k==="size"&&!(value>0&&value<=400)){panel();return;}commit("修改文字样式",[op("text",a.id,{[k]:value})]);};
for(const k of ["bold","italic"])$(k).onclick=()=>{const a=chosen();if(a)commit("修改文字样式",[op("text",a.id,{[k]:!a[k]})]);};
for(const [k,label] of [["front","置顶"],["back","置底"],["delete","删除对象"]])$(k).onclick=()=>{const a=chosen();if(a){commit(label,[op(k,a.id)]);if(k==="delete"){selected=null;refresh();}}};
$("undo").onclick=()=>{if(cursor){cursor--;selected=null;live();refresh();}};
$("redo").onclick=()=>{if(cursor<txs.length){cursor++;selected=null;live();refresh();}};
function crop(ref,b){
  if(b[0]<0||b[1]<0||b[0]+b[2]>1.00001||b[1]+b[3]>1.00001)throw Error("选区超出原始设计边界");
  const c=document.createElement("canvas");c.width=Math.max(1,Math.round(b[2]*ref.naturalWidth));c.height=Math.max(1,Math.round(b[3]*ref.naturalHeight));c.getContext("2d").drawImage(ref,b[0]*ref.naturalWidth,b[1]*ref.naturalHeight,b[2]*ref.naturalWidth,b[3]*ref.naturalHeight,0,0,c.width,c.height);return c.toDataURL("image/png");
}
function propose(b,a,started){
  try{
    const asset=crop(refs[pg],b),id=a?a.id:"patch-"+crypto.randomUUID();
    candidate={operation:op(a?"replace":"insert",id,{box:b,asset,rotation:0}),started,label:a?"原图替换图片":"原图取件"};
    $("candidate-img").src=asset;
    $("candidate-note").textContent=a?"将以原图所选位置像素替换选中图片，并移至该位置，保留层级；不会新增重复图层。裁剪可能包含原图中重叠的文字或背景，请确认。":"将新增独立可移动图片，不会自动删除其他图层。请确认是否会遮挡现有对象。";
    $("candidate").showModal();
  }catch(e){setStatus(e.message);}
}
$("recover").onclick=()=>{const a=chosen();if(a?.kind==="picture"&&refs[pg])propose(a.box,a,performance.now());};

$("pick-replace").onclick=()=>{const a=chosen();if(a?.kind!=="picture"||!refs[pg])return;repairTarget=a;chooseMode("region");setStatus("在原始设计图上框选正确组件的位置，然后确认替换。");};
// Coarse-to-fine fixed-scale template matching. Alpha is used only to
// select visible samples. Ambiguous or weak matches are rejected.
function matchPosition(ref,asset,b){
  const W=300,H=Math.round(W*ref.naturalHeight/ref.naturalWidth);
  const tw=Math.round(b[2]*W),th=Math.round(b[3]*H);
  if(tw<8||th<8||tw>W*.75||th>H*.75)return null;
  function pixels(im,w,h){const c=document.createElement("canvas");c.width=w;c.height=h;const x=c.getContext("2d",{willReadFrequently:true});x.drawImage(im,0,0,w,h);return x.getImageData(0,0,w,h).data;}
  const rp=pixels(ref,W,H),tp=pixels(asset,tw,th),samples=[];
  let lo=255,hi=0;
  for(let y=1;y<th-1;y+=Math.max(1,Math.floor(th/8)))for(let x=1;x<tw-1;x+=Math.max(1,Math.floor(tw/8))){
    const i=(y*tw+x)*4;
    if(tp[i+3]<230)continue;
    const lum=(tp[i]+tp[i+1]+tp[i+2])/3;lo=Math.min(lo,lum);hi=Math.max(hi,lum);samples.push([x,y,tp[i],tp[i+1],tp[i+2]]);
  }
  if(samples.length<16||hi-lo<25)return null;
  function cost(x,y){let sum=0;for(const [dx,dy,r,g,b] of samples){const k=((y+dy)*W+x+dx)*4;sum+=Math.abs(r-rp[k])+Math.abs(g-rp[k+1])+Math.abs(b-rp[k+2]);}return sum/(samples.length*3);}
  const coarse=[];
  for(let y=0;y<=H-th;y+=3)for(let x=0;x<=W-tw;x+=3)coarse.push({x,y,c:cost(x,y)});
  coarse.sort((a,b)=>a.c-b.c);
  if(!coarse.length)return null;
  let best=coarse[0];
  for(let y=Math.max(0,best.y-3);y<=Math.min(H-th,coarse[0].y+3);y++)for(let x=Math.max(0,coarse[0].x-3);x<=Math.min(W-tw,coarse[0].x+3);x++){const c=cost(x,y);if(c<best.c)best={x,y,c};}
  const second=coarse.find(p=>Math.abs(p.x-best.x)>Math.max(4,tw*.2)||Math.abs(p.y-best.y)>Math.max(4,th*.2));
  if(best.c>24||!second||second.c-best.c<5)return null;
  return {box:[best.x/W,best.y/H,b[2],b[3]],error:best.c};
}
$("match").onclick=()=>task(async()=>{
  const a=chosen(),started=performance.now();if(!a?.asset||!refs[pg])return;
  const hit=matchPosition(refs[pg],await loadImg(a.asset),a.box);
  if(!hit)return setStatus("未找到足够明确的匹配。请使用框选原图替换或手动移动。");
  candidate={operation:op("layout",a.id,{box:hit.box,rotation:a.rotation}),started,label:"原图匹配归位"};
  $("candidate-img").src=crop(refs[pg],hit.box);
  $("candidate-note").textContent="已找到外观近似的候选位置（平均色差 "+hit.error.toFixed(1)+"）。确认后仅移动原图片，不改变其内容。请核实候选是否对应正确组件。";
  $("candidate").showModal();
});

$("cancel").onclick=()=>{$("candidate").close();candidate=null;};
$("confirm").onclick=()=>{if(!candidate)return;const c=candidate;candidate=null;$("candidate").close();chooseMode("select");selected=c.operation.id;commit(c.label,[c.operation],c.started);};
$("candidate").addEventListener("cancel",()=>{candidate=null;});
const readFile=f=>new Promise((res,rej)=>{const r=new FileReader();r.onload=()=>res(r.result);r.onerror=()=>rej(r.error);r.readAsDataURL(f);});
const loadImg=src=>new Promise((res,rej)=>{const im=new Image();im.onload=()=>res(im);im.onerror=()=>rej(Error("图片读取失败"));im.src=src;});
async function post(path,data){const r=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});if(!r.ok)throw Error((await r.text()).slice(0,300));return r;}
async function task(fn){if(busy)return;busy=true;panel();try{await fn();}catch(e){setStatus(e.message);}finally{busy=false;refresh();}}
function renderPages(){
  $("pages").replaceChildren();
  meta.pages.forEach((src,i)=>{const b=document.createElement("button");b.classList.toggle("active",i===pg);const im=document.createElement("img");im.src=src;const n=document.createElement("small");n.textContent="第 "+(i+1)+" 页";b.append(im,n);b.onclick=()=>{if(busy)return;pg=i;selected=null;chooseMode("select");renderPages();};$("pages").append(b);});
}
async function setRef(src){const im=await loadImg(src);if(Math.abs((im.naturalWidth/im.naturalHeight)/(meta.width/meta.height)-1)>.01)throw Error("原图与 PPT 页面宽高比差异超过 1%，请使用对应页面的设计图");refs[pg]=im;draw();}
async function loadDeck(src,ref){
  setStatus("正在读取 PPTX 对象与真实渲染…");
  const d=await(await post("/v2/inspect",{pptx:src})).json();
  source=src;meta=d;pg=0;refs={};txs=[];cursor=0;selected=null;exactPages=null;
  board.style.aspectRatio=d.width+"/"+d.height;chooseMode("select");renderPages();if(ref)await setRef(ref);setStatus("已加载 "+d.scene.length+" 页。编辑预览为近似效果，可点击真实渲染核验。");
}
$("pptx").onchange=e=>{const f=e.target.files[0];if(f)task(async()=>{if(cursor&&!confirm("打开新文件将清除当前会话修改，继续？"))return;await loadDeck(await readFile(f));});e.target.value="";};
$("reference").onchange=e=>{const f=e.target.files[0];if(f&&meta)task(async()=>{await setRef(await readFile(f));setStatus("原始设计已载入");});e.target.value="";};
$("sample").onclick=()=>task(async()=>{if(cursor&&!confirm("重新载入会清除当前会话修改，继续？"))return;const d=await(await fetch("/sample")).json();if(!d.available)throw Error("本地未安装城市样例");await loadDeck(d.pptx,d.reference);});
$("verify").onclick=()=>task(async()=>{setStatus("正在生成真实 PPTX 渲染…");const d=await(await post("/v2/preview",{pptx:source,transactions:activeTx()})).json();exactPages=d.pages;$("exact").src=exactPages[pg];$("exact").hidden=false;$("mode").textContent="LibreOffice 真实渲染";setStatus("真实渲染已完成，点击回到编辑继续。");});
$("live").onclick=()=>{live();refresh();};
$("export").onclick=()=>task(async()=>{const r=await post("/v2/export",{pptx:source,transactions:activeTx()}),url=URL.createObjectURL(await r.blob()),a=document.createElement("a");a.href=url;a.download="repaired-v2.pptx";a.click();setTimeout(()=>URL.revokeObjectURL(url),5000);setStatus("已导出 PPTX，源文件未修改。");});
document.addEventListener("keydown",e=>{
  if(e.target.closest("input,textarea,select,dialog")||$("candidate").open||busy)return;
  if(e.key.toLowerCase()==="q"&&refs[pg])$("overlay").style.opacity=1;
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="z"){e.preventDefault();$(e.shiftKey?"redo":"undo").click();}
  const a=chosen();if(!a)return;
  if(e.key==="Delete"||e.key==="Backspace"){e.preventDefault();$("delete").click();}
  const dirs={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]};
  if(dirs[e.key]){e.preventDefault();const [dx,dy]=dirs[e.key],b=a.box.slice(),step=e.shiftKey ? .01 : .001;b[0]+=dx*step;b[1]+=dy*step;commit("微调位置",[op("layout",a.id,{box:b})]);}
});
document.addEventListener("keyup",e=>{if(e.key.toLowerCase()==="q")$("overlay").style.opacity=$("opacity").value/100;});
new ResizeObserver(()=>{if(!drag)draw();}).observe(board);
refresh();
