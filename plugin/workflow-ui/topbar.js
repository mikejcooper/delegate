/* The top bar, the same on every board page: the logo and name on the left (a soft tile, the same grey as the
   side panel), a thin divider and the Inbox · Builder switch, then a live dot and one split button on the right.
   The button's face follows the page: "Run" (run your triggers) on the Inbox, "Build" (add a workflow) on the Builder pages;
   ▾ opens both. While a trigger run is pulling items in, the face shows "Running 2/5" instead, and clicking it
   opens the Run triggers panel on the Inbox.
   Use: <header id="topbar" data-page="inbox|library"></header> then <script src="topbar.js"></script>.
   It reads window.BOARD, which the Inbox and Builder already load; on a page that doesn't (data-poll), it loads
   board-data.js itself. The Inbox sets TopBar.onRun to open its own panel instead of reloading the page.
   Along the bottom of the window, one strip (docked, so it never moves the page) says what Claude is doing right
   now ("Claude: …", from activity.json, kept by live.py on every tool call), then "Claude is done" for two minutes,
   or, first, a failing board build (build-status.json), so the page never shows old data without saying so. Under the bar, a yellow banner while
   an update is installed that this chat hasn't loaded yet (reload.json, reload_check.py): type /reload-plugins. TopBar.copy(text, button?, label?) copies for the chat: one toast and a pulse on the button, on every page. */
(function(){
var CSS=
'.tb{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:14px;height:56px;padding:0 20px;background:var(--tb-bg);border-bottom:1px solid var(--tb-line);font:14px/1.45 Inter,system-ui,-apple-system,sans-serif;color:var(--tb-ink)}'+
'.tb,.tb-act{--tb-bg:#fff;--tb-ink:#1a1a18;--tb-mut:#5c5c56;--tb-line:#e3e3de;--tb-soft:#f3f3ef;--tb-seg:#eae8e3;--tb-on:#fff;--tb-blue:#1D4ED8;--tb-bluebg:#eef3fd;--tb-blueline:#b9cbf3;--tb-green:#1F9D55;--tb-off:#b4b2a9}'+
'@media (prefers-color-scheme:dark){:root:not([data-theme=light]) .tb,:root:not([data-theme=light]) .tb-act{--tb-bg:#262624;--tb-ink:#f1efe8;--tb-mut:#b4b2a9;--tb-line:#3d3d3a;--tb-soft:#2c2c29;--tb-seg:#1c1c1a;--tb-on:#3a3a37;--tb-blue:#7d9ef0;--tb-bluebg:#22304f;--tb-blueline:#3b5590;--tb-green:#3ccf7a;--tb-off:#6b6b66}}'+
':root[data-theme=dark] .tb,:root[data-theme=dark] .tb-act{--tb-bg:#262624;--tb-ink:#f1efe8;--tb-mut:#b4b2a9;--tb-line:#3d3d3a;--tb-soft:#2c2c29;--tb-seg:#1c1c1a;--tb-on:#3a3a37;--tb-blue:#7d9ef0;--tb-bluebg:#22304f;--tb-blueline:#3b5590;--tb-green:#3ccf7a;--tb-off:#6b6b66}'+
'.tb a{text-decoration:none;color:inherit}'+
'.tb-brand{display:inline-flex;align-items:center;gap:9px;font-size:14px;font-weight:600;letter-spacing:-.01em;white-space:nowrap;flex:none}'+
'.tb-ver{font-size:11px;font-weight:500;color:var(--tb-mut);letter-spacing:0;font-variant-numeric:tabular-nums}'+
'.tb-div{width:1px;height:20px;background:var(--tb-line);flex:none}'+
'.tb-logo{display:inline-flex;align-items:center;justify-content:center;width:26px;height:26px;border-radius:8px;background:var(--tb-seg);color:var(--tb-ink)}'+
'.tb-seg{display:inline-flex;gap:2px;padding:3px;border-radius:9px;background:var(--tb-seg)}'+
'.tb-seg a{display:inline-flex;align-items:center;gap:6px;height:28px;padding:0 12px;border-radius:7px;font-size:13px;font-weight:600;color:var(--tb-mut)}'+
'.tb-seg a:hover{color:var(--tb-ink)}'+
'.tb-seg a[aria-current=page]{background:var(--tb-on);color:var(--tb-ink);box-shadow:0 1px 2px rgba(0,0,0,.14)}'+
'.tb-r{display:flex;align-items:center;justify-content:flex-end;gap:14px;margin-left:auto;position:relative}'+
'.tb-dot{width:8px;height:8px;border-radius:50%;background:var(--tb-off)}.tb-dot.on{background:var(--tb-green)}'+
'.tb-split{display:inline-flex;align-items:stretch;border-radius:9px;background:var(--tb-blue);color:#fff}'+
'.tb-split button{display:inline-flex;align-items:center;gap:6px;height:34px;border:0;background:transparent;color:inherit;font:600 13px/1 Inter,system-ui,sans-serif;cursor:pointer;white-space:nowrap}'+
'.tb-main{padding:0 12px 0 14px;border-radius:9px 0 0 9px}.tb-more{padding:0 9px;border-left:1px solid rgba(255,255,255,.3)!important;border-radius:0 9px 9px 0}'+
'.tb-split button:hover{background:rgba(0,0,0,.1)}'+
'.tb-split button:focus-visible{outline:2px solid var(--tb-ink);outline-offset:2px}'+
'.tb-split.run{background:var(--tb-bluebg);color:var(--tb-blue);box-shadow:inset 0 0 0 1px var(--tb-blueline)}'+
'.tb-split.run .tb-more{border-left-color:var(--tb-blueline)!important}.tb-split.run button:hover{background:rgba(29,78,216,.08)}'+
'.tb-pulse{width:8px;height:8px;border-radius:50%;background:var(--tb-blue);animation:tbpl 1.4s infinite}'+
'@keyframes tbpl{0%{box-shadow:0 0 0 0 rgba(29,78,216,.45)}70%{box-shadow:0 0 0 6px rgba(29,78,216,0)}100%{box-shadow:0 0 0 0 rgba(29,78,216,0)}}'+
'@media (prefers-reduced-motion:reduce){.tb-pulse{animation:none}}'+
'.tb-menu{position:absolute;right:0;top:44px;width:270px;padding:6px;border-radius:11px;background:var(--tb-bg);border:1px solid var(--tb-line);box-shadow:0 8px 24px rgba(0,0,0,.14)}'+
'.tb-menu button{display:flex;align-items:center;gap:10px;width:100%;padding:8px 10px;border:0;border-radius:7px;background:transparent;color:var(--tb-ink);text-align:left;cursor:pointer;font:inherit}'+
'.tb-menu button:hover,.tb-menu button:focus-visible{background:var(--tb-soft);outline:none}'+
'.tb-menu svg{color:var(--tb-mut);flex:none}.tb-menu b{display:block;font-size:13px}.tb-menu small{display:block;font-size:12px;color:var(--tb-mut)}'+
'.tb-menu .lu{margin-left:auto;font-size:11px;color:var(--tb-mut);white-space:nowrap}'+
'.tb-dot.bad{background:#d9363e}'+
/* the live strip: docked along the bottom of the window, so it never moves the page; pages get room for it */
'.tb-act{position:fixed;left:0;right:0;bottom:0;z-index:40;display:flex;align-items:center;gap:10px;min-height:40px;padding:8px max(20px,env(safe-area-inset-right,0px)) calc(8px + env(safe-area-inset-bottom,0px)) max(20px,env(safe-area-inset-left,0px));font:13px/1.4 Inter,system-ui,sans-serif;border-top:1px solid var(--tb-line);background:linear-gradient(var(--tb-bluebg),var(--tb-bluebg)),var(--tb-bg);color:var(--tb-ink);box-shadow:0 -4px 16px rgba(0,0,0,.06)}'+
'.tb-act[hidden]{display:none}.tb-act b{font-weight:600;flex:none}.tb-act .m{color:var(--tb-mut);margin-left:auto;flex:none;white-space:nowrap}.tb-act .tx{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}'+
'.tb-act.idle{background:linear-gradient(var(--tb-soft),var(--tb-soft)),var(--tb-bg)}.tb-act.idle .m{margin-left:0}.tb-act.bad{background:#fdecec;color:#8a1c22;border-top-color:#f3c2c4}'+
'@media (prefers-color-scheme:dark){:root:not([data-theme=light]) .tb-act.bad{background:#3a1d1f;color:#ffb4b8;border-top-color:#6b2a2e}}:root[data-theme=dark] .tb-act.bad{background:#3a1d1f;color:#ffb4b8;border-top-color:#6b2a2e}'+
'body.tb-has-act{padding-bottom:48px}body.tb-has-act .tb-toast{bottom:calc(60px + env(safe-area-inset-bottom,0px))}'+
'@media (max-width:600px){.tb-act{flex-wrap:wrap;gap:2px 8px}.tb-act .m{margin-left:0;flex-basis:100%}}'+
'.tb-toast{position:fixed;left:50%;bottom:calc(20px + env(safe-area-inset-bottom,0px));transform:translate(-50%,8px);opacity:0;pointer-events:none;transition:opacity .2s ease,transform .2s ease;z-index:50;display:flex;align-items:center;gap:10px;width:max-content;max-width:min(560px,calc(100vw - 32px));box-sizing:border-box;padding:9px 10px 9px 14px;border-radius:10px;background:#1a1a18;color:#fff;font:13px/1.4 Inter,system-ui,sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.25)}'+
'.tb-toast.on{opacity:1;transform:translate(-50%,0);pointer-events:auto}'+
'.tb-toast .tk{flex:none;display:inline-grid;place-items:center;width:18px;height:18px;border-radius:50%;background:#1f8a4c;color:#fff;font-size:11px;font-weight:700}.tb-toast.bad .tk{background:#9b2c22}'+
'.tb-toast b{flex:none;font-weight:600;white-space:nowrap}'+
'.tb-toast code{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font:12px ui-monospace,Menlo,monospace;background:rgba(255,255,255,.12);padding:2px 6px;border-radius:5px}'+
'.tb-toast .hint{flex:none;color:#b9b6ad;white-space:nowrap}'+
'.tb-toast input{flex:1;min-width:0;font:12px ui-monospace,Menlo,monospace;padding:5px 7px;border-radius:6px;border:0}'+
'.tb-toast button{flex:none;border:0;background:transparent;color:#bbb;cursor:pointer;font-size:16px;width:24px;height:24px;border-radius:6px}.tb-toast button:hover{background:rgba(255,255,255,.1);color:#fff}'+
'@media (max-width:600px){.tb-toast .hint{display:none}}'+
'@media (prefers-reduced-motion:reduce){.tb-toast{transition:none}.tb-copied{animation:none!important;outline:2px solid #1f8a4c}}'+
/* the button just clicked to copy: a short green pulse, the same on every page and every copy button */
'.tb-copied{animation:tbcp 1.2s ease-out}@keyframes tbcp{0%{box-shadow:0 0 0 3px rgba(31,138,76,.6);background-color:rgba(31,138,76,.16)}100%{box-shadow:0 0 0 3px rgba(31,138,76,0)}}'+
/* the reload banner, just under the bar: an update is installed but this chat still runs the old copy (reload.json) */
'.tb-rl{position:sticky;top:56px;z-index:19;display:flex;flex-wrap:wrap;align-items:center;gap:6px 12px;padding:9px 20px;background:#fff6e0;color:#5c3d00;border-bottom:1px solid #f0d58a;font:13px/1.4 Inter,system-ui,sans-serif}'+
'.tb-rl[hidden]{display:none}.tb-rl b{font-weight:600}.tb-rl .tx{flex:1 1 300px;min-width:0}'+
'.tb-rl code{font:12.5px ui-monospace,Menlo,monospace;background:rgba(92,61,0,.09);padding:1px 6px;border-radius:5px}'+
'.tb-rl button{flex:none;height:28px;padding:0 11px;border-radius:999px;border:1px solid #d9b65a;background:#fff;color:#5c3d00;font:600 13px/1 Inter,system-ui,sans-serif;cursor:pointer}.tb-rl button:hover{background:#fdf0cc}'+
'@media (prefers-color-scheme:dark){:root:not([data-theme=light]) .tb-rl{background:#3a2f14;color:#f5d98e;border-bottom-color:#6b5420}:root:not([data-theme=light]) .tb-rl button{background:#262624;color:#f5d98e;border-color:#8a6d2a}:root:not([data-theme=light]) .tb-rl code{background:rgba(245,217,142,.12)}}'+
':root[data-theme=dark] .tb-rl{background:#3a2f14;color:#f5d98e;border-bottom-color:#6b5420}:root[data-theme=dark] .tb-rl button{background:#262624;color:#f5d98e;border-color:#8a6d2a}:root[data-theme=dark] .tb-rl code{background:rgba(245,217,142,.12)}'+
'@media (max-width:640px){.tb-rl{padding:8px 12px}}'+
'@media (max-width:640px){.tb{padding:0 12px;gap:10px}.tb-name,.tb-ver,.tb-div{display:none}.tb-seg a{padding:0 10px}}'+
'@media (max-width:480px){.tb-lbl{display:none}.tb-main{padding:0 10px}.tb-seg a{padding:0 8px;gap:4px}}';

function svg(p,s){return'<svg width="'+(s||14)+'" height="'+(s||14)+'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+p+"</svg>"}
var IC={
  logo:'<circle cx="5" cy="6" r="2"/><circle cx="5" cy="18" r="2"/><circle cx="19" cy="12" r="2"/><path d="M7 6h3a3 3 0 0 1 3 3v0a3 3 0 0 0 3 3h1M7 18h3a3 3 0 0 0 3-3v0a3 3 0 0 1 3-3"/>', /* two things in, one result */
  inbox:'<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5.1L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1z"/>',
  lib:'<rect x="3" y="13" width="8" height="8" rx="1.5"/><rect x="13" y="13" width="8" height="8" rx="1.5"/><rect x="8" y="3" width="8" height="8" rx="1.5"/>', /* Builder: building blocks */
  run:'<path d="M6 4l14 8-14 8z"/>',add:'<path d="M12 5v14M5 12h14"/>',chev:'<path d="M6 9l6 6 6-6"/>'};
var ACTS={run:{t:"Run",d:"Run your workflows: pull in new items now",i:"run"},add:{t:"Build",d:"Add a new workflow",i:"add"}};
var KEY="board.newact";
function getLast(){try{var v=localStorage.getItem(KEY);return ACTS[v]?v:"run"}catch(e){return"run"}}
function setLast(v){try{localStorage.setItem(KEY,v)}catch(e){}}
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})}

/* a trigger run that is pulling items in (not one workflow, a rerun, a test or a change by hand) */
var NOTPULL=/^\s*["“]?\s*(rerun\b|test\b|run\s+(the\s+)?workflow\s+(?!manager\b)|run\s+these\s+\d+\s+items|skip\b|mark\b|delete\b|turn\s+run\s+each)/i;
/* the "Pulling in" panel is for a run of several triggers ("run workflow manager", "run all triggers", "… with these
   triggers", a scheduled run): a run of one workflow has its own row on the Inbox, which already says what it is doing */
function isPull(r){var q=String(r.request||"");if(!q||q==="dispatcher request"||NOTPULL.test(q))return false;
  if(/workflow manager|^\s*delegate run\b|run all triggers|these triggers|\(scheduled:/i.test(q))return true;
  return(r.matches||[]).filter(function(m){return m.entry}).length>1}
function liveReq(B){if(!B||!B.runs)return null;return B.runs.filter(function(r){return r.kind!=="run"&&(r.state==="running"||r.state==="scanning"||r.state==="waiting")&&isPull(r)}).sort(function(a,b){return b.started-a.started})[0]||null}
/* "2/5": the trigger it's on, of the ones it chose to run; just "Running" until it has chosen */
function progress(L){var on=(L.matches||[]).filter(function(m){return m.entry}).length,of=(L.candidates||[]).length;return on&&of>=on?on+"/"+of:""}

var el,page,open=false,SIG="";
/* the version beside the name: the last one seen stays until a new one loads, so it never blinks out while
   board-data.js (re)loads */
var VER="";try{VER=localStorage.getItem("delegate.version")||""}catch(e){}
function verNow(B){var v=B&&B.version;if(v&&v!==VER){VER=v;try{localStorage.setItem("delegate.version",v)}catch(e){}}return VER}
function ago(t){var s=Math.max(0,Math.round(Date.now()/1000-t));return s<60?s+" s ago":s<3600?Math.round(s/60)+" min ago":Math.round(s/3600)+" h ago"}
function render(){
  if(!el)return;var B=window.BOARD,L=liveReq(B),last=page==="inbox"?"run":"add", /* the face follows the page: Run triggers on the Inbox, Add a workflow on the Builder */fresh=!!B&&Date.now()/1000-B.built<15,pg=progress(L||{});
  var ver=verNow(B),sig=[ver,!!L,pg,last,open,fresh,badBuild(),B?Math.floor((Date.now()/1000-B.built)/60):-1].join("|");if(sig===SIG)return;SIG=sig;
  var a=ACTS[last];
  var main=L?'<button class="tb-main" type="button" data-tb="panel" title="Pulling in'+(pg?" · "+esc(pg.replace("/"," of "))+" triggers":"")+'. Open the Run workflows panel"><span class="tb-pulse" aria-hidden="true"></span>Running'+(pg?" "+esc(pg):"…")+"</button>"
    :'<button class="tb-main" type="button" data-tb="'+last+'" aria-label="'+esc(a.t)+'">'+svg(IC[a.i])+'<span class="tb-lbl">'+esc(a.t)+"</span></button>";
  var menu=open?'<div class="tb-menu" role="menu">'+["run","add"].map(function(k){var x=ACTS[k];return'<button type="button" role="menuitem" data-tb="'+k+'">'+svg(IC[x.i],15)+"<span><b>"+esc(x.t)+"</b><small>"+esc(x.d)+"</small></span>"+""+"</button>"}).join("")+"</div>":"";
  el.innerHTML='<a class="tb-brand" href="workflows.html"><span class="tb-logo">'+svg(IC.logo,16)+'</span><span class="tb-name">Delegate</span>'+(ver?'<span class="tb-ver" title="Delegate version">v'+esc(ver)+"</span>":"")+'</a><span class="tb-div" aria-hidden="true"></span>'+
    '<div class="tb-seg" role="navigation" aria-label="Board pages"><a href="workflows.html"'+(page==="inbox"?' aria-current="page"':"")+">"+svg(IC.inbox)+'Inbox</a><a href="workflow-viewer.html"'+(page==="library"?' aria-current="page"':"")+">"+svg(IC.lib)+"Builder</a></div>"+
    '<div class="tb-r"><span class="tb-dot'+(badBuild()?" bad":fresh?" on":"")+'" role="img" aria-label="'+(badBuild()?"Board not updating":fresh?"Live":"Not live")+'" title="'+(badBuild()?"The board couldn't update: see the red line":B?(fresh?"Live":"Not live")+" · updated "+ago(B.built):"Loading…")+'"></span>'+
    '<span class="tb-split'+(L?" run":"")+'">'+main+'<button class="tb-more" type="button" data-tb="menu" aria-haspopup="menu" aria-expanded="'+open+'" aria-label="More actions">'+svg(IC.chev,13)+"</button></span>"+menu+"</div>"}
function act(k){open=false;
  if(k==="run"||k==="panel"){if(k==="run")setLast("run");SIG="";render();
    if(TopBar.onRun)TopBar.onRun();else location.href="workflows.html?panel=1";return}
  if(k==="add"){setLast("add");SIG="";render();location.href="workflow-viewer.html?w=new";return}} /* the new-workflow page in the Builder */
function load(){var s=document.createElement("script");s.src="board-data.js?ts="+Date.now();s.onload=s.onerror=function(){s.remove()};document.head.appendChild(s)}
/* the bottom strip: what Claude is doing right now (activity.json, live.py), "Claude is done" for two minutes after, or a failing build */
var ACT=null,BUILD=null,strip=null;
function badBuild(){if(!BUILD)return null;var k=Object.keys(BUILD).filter(function(x){return BUILD[x]&&BUILD[x].ok===false});return k.length?{which:k[0],e:BUILD[k[0]]}:null}
function dur(s){s=Math.max(0,Math.round(s));return s<60?s+" s":Math.floor(s/60)+" min "+(s%60?s%60+" s":"")}
function since(t){var s=Math.max(0,Math.round(Date.now()/1000-t));return s<60?s+" s":Math.round(s/60)+" min"}
function drawStrip(){if(!strip)return;var b=badBuild(),a=ACT,now=Date.now()/1000,h="",cls="";
  if(b){cls="bad";h='<b>The board couldn’t update</b><span class="tx">'+esc((b.which==="workflows"?"Builder: ":"Inbox: ")+((b.e.errors||[])[0]||"the build failed"))+'</span><span class="m">Showing the last version that built.</span>'}
  else if(a&&a.busy&&now-a.t<1800){var quiet=now-a.t>90;
    h='<span class="tb-pulse" aria-hidden="true"></span><b>Claude:</b><span class="tx">'+esc(a.text||"working")+'</span><span class="m">'+(quiet?"no update for "+since(a.t):since(a.t)+" ago")+(a.started?" · "+since(a.started)+" on this request":"")+"</span>"}
  else if(a&&!a.busy&&now-a.t<120){cls="idle";h='<b>Claude is done</b><span class="m">Waiting for you in the chat'+(a.started?" · took "+dur(a.t-a.started):"")+"</span>"}
  strip.hidden=!h;document.body.classList.toggle("tb-has-act",!!h);strip.className="tb-act"+(cls?" "+cls:"");if(h&&strip.innerHTML!==h)strip.innerHTML=h;strip.setAttribute("aria-live","polite")}
/* the reload banner: Claude Code installed a newer copy of the plugin, but this chat runs the old one until the user
   types /reload-plugins (Claude can't). reload.json is written on every message (reload_check.py), so it goes away
   by itself on the first message after the reload. */
var RL=null,UP=null,rlEl=null,RLSIG="";
function drawReload(){if(!el)return;var r=RL,on=!!(r&&r.needed&&r.installed),
  /* or: a git clone couldn't pull a newer release by itself (update.json, git_update.py), for a reason only the user can fix */
  u=!on&&UP&&UP.show&&UP.available?UP:null,sig=on?r.running+">"+r.installed:u?"u"+u.available+"|"+u.reason:"";
  if(sig===RLSIG)return;RLSIG=sig;
  if(!rlEl){rlEl=document.createElement("div");rlEl.className="tb-rl";rlEl.setAttribute("role","status");rlEl.hidden=true;el.insertAdjacentElement("afterend",rlEl);
    rlEl.addEventListener("click",function(ev){var b=ev.target.closest("button");if(!b)return;var t="/reload-plugins",ok=function(){flash(b);toast(t,true,"Copied")},no=function(){toast(t,false)};
      try{navigator.clipboard.writeText(t).then(ok,no)}catch(x){no()}})}
  rlEl.hidden=!sig;
  rlEl.innerHTML=on?'<span class="tx"><b>Delegate '+esc(r.installed)+' is installed.</b> This chat is still on '+esc(r.running)+'. Type <code>/reload-plugins</code> in the Claude chat to switch.</span><button type="button">Copy /reload-plugins</button>'
    :u?'<span class="tx"><b>Delegate '+esc(u.available)+' is out, but this folder is still on '+esc(u.current)+'.</b> It couldn’t update by itself: '+esc(u.message||"git couldn’t apply it")+'.</span>':""}
function pollLive(){var q="?ts="+Date.now();
  fetch("reload.json"+q,{cache:"no-store"}).then(function(r){return r.ok?r.json():null}).then(function(j){RL=j;drawReload()}).catch(function(){});
  fetch("update.json"+q,{cache:"no-store"}).then(function(r){return r.ok?r.json():null}).then(function(j){UP=j;drawReload()}).catch(function(){});
  fetch("activity.json"+q,{cache:"no-store"}).then(function(r){return r.ok?r.json():null}).then(function(j){ACT=j;drawStrip()}).catch(function(){});
  fetch("build-status.json"+q,{cache:"no-store"}).then(function(r){return r.ok?r.json():null}).then(function(j){var was=!!badBuild();BUILD=j;if(was!==!!badBuild()){SIG="";render()}drawStrip()}).catch(function(){})}
/* Copying for the chat: one way on every page. TopBar.copy(text, button?, label?) copies the text, pulses the button
   that was clicked (passed, or the last one pressed) and shows the one toast: a single line that fades away by itself
   (paused while the pointer is on it). When the browser blocks copying, the toast shows the text selected, to copy by hand. */
var toastEl=null,toastT=0,lastBtn=null,lastAt=0;
function noteBtn(e){var b=e.target&&e.target.closest&&e.target.closest("button,a,[role=button],[data-copy]");if(b){lastBtn=b;lastAt=Date.now()}}
document.addEventListener("pointerdown",noteBtn,true);
document.addEventListener("keydown",function(e){if(e.key==="Enter"||e.key===" ")noteBtn({target:document.activeElement})},true);
function flash(b){if(!b||!b.isConnected)return;b.classList.remove("tb-copied");void b.offsetWidth;b.classList.add("tb-copied");setTimeout(function(){b.classList.remove("tb-copied")},1300)}
function hideToast(){if(toastEl)toastEl.classList.remove("on")}
function armToast(ms){clearTimeout(toastT);toastT=setTimeout(hideToast,ms)}
function toast(cmd,ok,label){cmd=String(cmd==null?"":cmd);
  if(!toastEl){toastEl=document.createElement("div");toastEl.className="tb-toast";toastEl.setAttribute("role","status");toastEl.setAttribute("aria-live","polite");document.body.appendChild(toastEl);
    toastEl.addEventListener("mouseenter",function(){clearTimeout(toastT)});toastEl.addEventListener("mouseleave",function(){armToast(toastEl.classList.contains("bad")?8000:2500)})}
  var lines=cmd.split("\n"),first=lines[0]+(lines.length>1?"  (+"+(lines.length-1)+" more line"+(lines.length>2?"s":"")+")":"");
  toastEl.className="tb-toast"+(ok?"":" bad");
  toastEl.innerHTML=ok?'<span class="tk" aria-hidden="true">✓</span><b>'+esc(label||"Copied")+'</b><code title="'+esc(cmd)+'">'+esc(first)+'</code><span class="hint">Paste it into the Claude chat</span><button type="button" aria-label="Close">×</button>'
    :'<span class="tk" aria-hidden="true">!</span><b>Copy this by hand</b><input readonly value="'+esc(cmd)+'" aria-label="The text to copy"><button type="button" aria-label="Close">×</button>';
  toastEl.querySelector("button").onclick=function(){clearTimeout(toastT);hideToast()};
  void toastEl.offsetWidth;toastEl.classList.add("on");
  if(!ok){var i=toastEl.querySelector("input");i.focus();i.select()}
  armToast(ok?4000:15000)}
/* Delegate's commands (scripts/commands.py): every request is "delegate <verb> <thing> <name>", detail after a colon.
   The board's buttons are written in the older phrasing; cmd() turns a copied line into its delegate form, and
   fixCmds() shows that form on the page (each button's data-copy and title, and a command shown in a <code>).
   A line that isn't one of Delegate's commands (a workflow's own phrase, a reply to Claude) is left as it is. */
var KD="(workflow|trigger|connection)",CMDS=[
  [/^run workflow manager(?: with these| no question)|^run these \d+ items|^(?:skip|mark|delete) these (?:items|requests)/i,function(t){return"delegate "+t}],
  [/^run (?:the )?workflow manager\s*$/i,"delegate run"],[/^run all triggers\s*$/i,"delegate run all"],
  [/^run trigger (\S+)\s*$/i,"delegate run trigger $1"],
  [/^run workflow (\S+) on (.+)$/i,"delegate run workflow $1: $2"],[/^run workflow (\S+) (for real|as a test)\s*$/i,"delegate run workflow $1: $2"],
  [/^run workflow (\S+)\s*$/i,"delegate run workflow $1"],
  [/^rerun workflow (wf-\S+)(?:\s+(for real|as a test))?\s*$/i,function(t,id,m){return"delegate rerun "+id+(m?": "+m:"")}],
  [/^test workflow (\S+) (.+)$/i,"delegate test workflow $1: $2"],[/^test workflow (\S+)\s*$/i,"delegate test workflow $1"],[/^test trigger (\S+)\s*$/i,"delegate test trigger $1"],
  [new RegExp("^discard the draft of "+KD+" (\\S+)\\s*$","i"),"delegate discard $1 $2"],
  [new RegExp("^undo the last change to "+KD+" (\\S+)\\s*$","i"),"delegate undo $1 $2"],
  [new RegExp("^validate "+KD+" (\\S+)\\s*$","i"),"delegate validate $1 $2"],
  [new RegExp("^publish "+KD+" (\\S+) (.+)$","i"),"delegate publish $1 $2: $3"],[new RegExp("^publish "+KD+" (\\S+)\\s*$","i"),"delegate publish $1 $2"],
  [new RegExp("^restore "+KD+" (\\S+) to (v\\d+)\\s*$","i"),"delegate restore $1 $2: $3"],
  [new RegExp("^change "+KD+" (\\S+):\\s*(.*)$","i"),function(t,k,n,d){return"delegate change "+k+" "+n+": "+d}],
  [new RegExp("^delete "+KD+" (\\S+)\\s*$","i"),"delegate delete $1 $2"],
  [/^rename (workflow|connection|category) (\S+) to\s*(.*)$/i,function(t,k,n,d){return"delegate rename "+k+" "+n+": "+d}],
  [/^move workflow (\S+) to\s*(.*)$/i,function(t,n,d){return"delegate move workflow "+n+": "+d}],
  [/^tidy up the names\b.*$/i,"delegate tidy names"],
  [/^(?:change )?schedule workflow (\S+):\s*(.*)$/i,"delegate schedule workflow $1: $2"],
  [/^(pause|resume) schedule workflow (\S+)\s*$/i,"delegate $1 workflow $2"],[/^remove schedule workflow (\S+)\s*$/i,"delegate unschedule workflow $1"],
  [/^(set up|check|fix) connection (\S+)\s*$/i,"delegate $1 connection $2"],[/^carry on setting up connection (\S+)\s*$/i,"delegate set up connection $1"],
  [/^what needs setting up\??\s*$/i,"delegate check connections"],
  [/^create the new workflow (\S+)\s*$/i,"delegate create workflow $1"],
  [/^add examples to workflow (\S+)\s*$/i,"delegate add examples workflow $1"],[/^add tests for workflow (\S+)\s*$/i,"delegate add tests workflow $1"],
  [/^add a workflow:\s*(.*)$/i,"delegate add workflow: $1"],
  [/^answer (wf-\S+):\s*(.*)$/i,"delegate answer $1: $2"],[/^skip (wf-\S+)\b.*$/i,"delegate skip $1"],
  [/^mark (wf-\S+) done\b.*$/i,"delegate done $1"],[/^mark (wf-\S+) (needs you|not run)\b.*$/i,"delegate mark $1: $2"],
  [/^delete (wf-\S+)\b.*$/i,"delegate delete $1"],[/^delete requests? (dispatch-[\w-]+)\b.*$/i,"delegate delete request $1"],
  [/^turn (.+?) (on|off)\s*$/i,"delegate turn $2 $1"],[/^keep (wf-\S+) as a test\s*$/i,"delegate keep $1: test"],
  [/^review run (wf-\S+)\s*$/i,"delegate review $1"],[/^dismiss warning (sg-\S+)\s*$/i,"delegate dismiss $1"],[/^fix warning (sg-\S+)\s*$/i,"delegate fix $1"],
  [/^share the update of workflow (\S+)\s*$/i,"delegate share workflow $1: update"],
  [/^share an issue with workflow (\S+):\s*(.*)$/i,"delegate share workflow $1: issue $2"],[/^share workflow (\S+)\s*$/i,"delegate share workflow $1"],
  [/^keep my side of (c\d+) in workflow (\S+)\s*$/i,"delegate pick workflow $2: $1 mine"],[/^take the update's side of (c\d+) in workflow (\S+)\s*$/i,"delegate pick workflow $2: $1 theirs"],
  [/^merge both sides of (c\d+) in workflow (\S+)\s*$/i,"delegate pick workflow $2: $1 merge"],
  [/^replay a run of debug (\S+)\s*$/i,"delegate replay debug $1"],[/^share the fixed version of debug (\S+)\s*$/i,"delegate share debug $1: fix"],
  [/^remove debug (\S+)\s*$/i,"delegate delete debug $1"]];
function cmd(text){text=String(text==null?"":text);if(/^\s*delegate\b/i.test(text))return text;var t=text.replace(/^\s+/,"");
  for(var i=0;i<CMDS.length;i++){var r=CMDS[i];if(r[0].test(t))return typeof r[1]==="function"?(r[0].lastIndex=0,t.replace(r[0],r[1])):t.replace(r[0],r[1])}
  return text}
function fixCmds(){Array.prototype.forEach.call(document.querySelectorAll("[data-copy]"),function(el){var o=el.getAttribute("data-copy"),n=cmd(o);if(n===o)return;
  el.setAttribute("data-copy",n);if(el.title)el.title=el.title.split(o).join(n);
  var box=el.closest(".hcard,.xo,.stbar,.shpick,.cf")||el;Array.prototype.forEach.call(box.querySelectorAll("code"),function(c){if(c.textContent===o)c.textContent=n})})}
var fixQ=false;try{new MutationObserver(function(){if(fixQ)return;fixQ=true;Promise.resolve().then(function(){fixQ=false;fixCmds()})}).observe(document.documentElement,{childList:true,subtree:true})}catch(e){}
function copy(text,btn,label){text=cmd(String(text==null?"":text));launch(text);
  var b=btn||(Date.now()-lastAt<1500?lastBtn:null);
  var done=function(ok){if(ok)flash(b);toast(text,ok,label)};
  var byHand=function(){var a=document.createElement("textarea"),ok=false;a.value=text;a.setAttribute("readonly","");a.style.position="fixed";a.style.opacity="0";document.body.appendChild(a);a.select();try{ok=document.execCommand("copy")}catch(x){}a.remove();done(ok)};
  try{navigator.clipboard.writeText(text).then(function(){done(true)},byHand)}catch(x){byHand()}}
/* where a copied line came from (the Builder, the Inbox, the welcome): the run it starts opens on that page (live.py,
   serve_board.py /launch). window.LAUNCH_FROM, set just before a copy, overrides the page (the welcome sets it) */
function launch(text){try{var bld=/workflow-viewer/.test(location.pathname),w=bld?new URLSearchParams(location.search).get("w")||"":"";
  var from=window.LAUNCH_FROM||(bld?"builder":"inbox");window.LAUNCH_FROM="";
  if(bld&&window.UI&&UI.view)w=UI.view;
  fetch("/launch",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({cmd:text,page:from,w:w})}).catch(function(){})}catch(x){}}
function init(){
  el=document.getElementById("topbar");if(!el)return;page=el.dataset.page||"";el.classList.add("tb");
  var st=document.createElement("style");st.textContent=CSS;document.head.appendChild(st);
  el.addEventListener("click",function(ev){var b=ev.target.closest("[data-tb]");if(!b)return;var k=b.dataset.tb;
    if(k==="menu"){open=!open;SIG="";render();if(open){var f=el.querySelector(".tb-menu button");if(f)f.focus()}return}act(k)});
  document.addEventListener("click",function(ev){if(open&&ev.target.isConnected&&!el.contains(ev.target)) /* a click in the bar re-renders it, so its target is gone */{open=false;SIG="";render()}});
  document.addEventListener("keydown",function(ev){if(open&&ev.key==="Escape"){open=false;SIG="";render();var m=el.querySelector(".tb-more");if(m)m.focus()}});
  /* switching Inbox ⇄ Builder goes back to where you last were on that page (its address: view, workflow, run) */
  var FILE={inbox:"workflows.html",library:"workflow-viewer.html"},here=function(){return location.pathname.split("/").pop()+location.search+location.hash};
  var saveHere=function(){try{if(FILE[page]&&here().indexOf(FILE[page])===0)localStorage.setItem("board.last."+page,here())}catch(e){}};
  saveHere();setInterval(saveHere,1000);window.addEventListener("pagehide",saveHere);
  el.addEventListener("click",function(ev){var a=ev.target.closest(".tb-seg a");if(!a||a.getAttribute("aria-current")==="page")return;saveHere();
    var to=a.getAttribute("href")===FILE.inbox?"inbox":"library",last="";try{last=localStorage.getItem("board.last."+to)||""}catch(e){}
    if(last&&last.indexOf(FILE[to])===0)a.setAttribute("href",last)},true);
  if(el.hasAttribute("data-poll")){load();setInterval(load,2000)}
  strip=document.createElement("div");strip.className="tb-act";strip.hidden=true;document.body.appendChild(strip);
  pollLive();setInterval(pollLive,1500);setInterval(drawStrip,1000);
  render();setInterval(render,1000)}
window.TopBar={onRun:null,render:function(){SIG="";render()},liveReq:liveReq,isPull:isPull,toast:toast,copy:copy,cmd:cmd};
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);else init();
})();
