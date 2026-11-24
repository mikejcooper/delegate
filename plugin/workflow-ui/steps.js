/* steps.js: the one way a workflow's steps (and a run's Workflow outcome, Steps.outcome) are drawn, shared by the Workflow Viewer and the Inbox (styles in steps.css).
   A page turns its steps into items and calls Steps.card(...) with Steps.layout(...) as the body; clicks on
   data-stage / data-allstages / data-detail go to Steps.click(...). Neither page draws step rows itself, so the
   two always look the same: same rows, same stages (rule 23), same Expand all and Details switch.

   item = {kind:"row", stage, sk:{code,short}, lane, tag, tagKind, title, sub (the grey line; else res.text, else what), insp (html under the row: Steps.inspector), extra, what, res:{text,cls}, status, more, n (a fixed label, e.g. "↳"; not counted),
           key + open (the page opens this step's details on a click on the row: data-stepkey, aria-expanded)}
        | {kind:"band", stage, code, label, hint}      (a hand-off between skills; pages add it only with Details on)
   tagKind: read check act guard dec route next need fail · status: done skipped uncertain failed needs_user live
   count: {t, bad} a pill on the right: how many of a run's items reached this step (Workflow Viewer, a run of several items)
   res.cls: "" (what happened) · "inf" (what should happen) · "one" (one line, cut) */
var Steps=(function(){
  function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]})}
  var DETAIL_KEY="board.detail"; /* one Details setting for both pages */
  function loadDetail(){try{return localStorage.getItem(DETAIL_KEY)==="1"}catch(e){return false}}
  function loadOutDetail(){try{return localStorage.getItem(DETAIL_KEY+":out")==="1"}catch(e){return false}}
  function saveDetail(on){try{localStorage.setItem(DETAIL_KEY,on?"1":"0")}catch(e){}}

  /* a stage is open when the user opened it; until then, only when it holds a failed or waiting step */
  function isOpen(state,prefix,key,flag){var v=state.stage[prefix+key];return v===undefined?flag==="failed"||flag==="needs_user":!!v}
  /* a stage's status from its steps: failed, waiting on you, or done (every step finished or left alone); else none */
  function flagOf(items){var f="";items.forEach(function(x){if(x.status==="failed")f="failed";else if(x.status==="needs_user"&&!f)f="needs_user"});
    if(!f&&items.length&&items.every(function(x){return x.status==="done"||x.status==="skipped"})&&items.some(function(x){return x.status==="done"}))f="done";return f}

  function switchHtml(on){return'<button class="fl-sw" type="button" data-detail="1" role="switch" aria-checked="'+!!on+'" title="Show every step in full: what it does, why, and the detail behind it"><span>Details</span><span class="fl-kn" aria-hidden="true"></span></button>'}
  /* o: {line (html), stages (bool), allOpen, detail, body (html), foot (html)} */
  function card(o){
    return'<div class="fl-card"><div class="fl-ch"><span>'+(o.line||"")+'</span><span class="fl-tools">'+
      (o.stages?'<button class="fl-xall" type="button" data-allstages="1" aria-pressed="'+!!o.allOpen+'">'+(o.allOpen?"Collapse all":"Expand all")+"</button>":"")+
      switchHtml(o.detail)+'</span></div><div class="fl-flow">'+(o.body||"")+"</div>"+(o.foot||"")+"</div>"}
  function foot(labelHtml,text){return'<div class="fl-foot">'+labelHtml+"<span>"+esc(text)+"</span></div>"}

  /* a draft's change marks, against the last published version (core-architect: a draft is edited on the board) */
  var MARK={"new":"NEW",chg:"CHANGED",del:"REMOVED",guess:"GUESS",moved:"MOVED",ask:"OPEN","just-new":"JUST ADDED","just-chg":"JUST CHANGED","just-del":"JUST REMOVED",since:"CHANGED SINCE LAST RUN"};
  function row(x,n,prev,detail,inst){
    var sk=x.sk||{code:"d",short:""},same=prev&&prev.sk&&prev.sk.code===sk.code&&prev.sk.short===sk.short&&(!detail||prev.lane===x.lane),nsk=prev&&!same&&prev.sk&&(prev.sk.code!==sk.code||prev.sk.short!==sk.short);
    /* a trigger's four slots (rule 30): source, window, item, kind; a trigger holds nothing else */
    if(x.kind==="slots")return'<div class="fl-slots" aria-label="What the trigger holds">'+x.slots.map(function(z){return'<div><span>'+esc(z[0])+"</span><b>"+esc(z[1]||"—")+"</b></div>"}).join("")+"</div>";
    if(x.kind==="fan")return'<div class="fl-fan"><span><b>'+esc(x.title)+"</b>"+(x.sub?" · "+esc(x.sub):"")+"</span></div>";
    var h='<div class="fl-row'+(x.trig?" fl-trg":"")+(x.wfs?" fl-wfs":"")+(x.nest?" fl-nest":"")+(inst?" inst":"")+(x.status?" st-"+esc(x.status):"")+(MARK[x.mark]?" fl-m-"+esc(x.mark):"")+(x.open!=null?" fl-tap":"")+'"'+(x.key&&x.open!=null?' data-stepkey="'+esc(x.key)+'" aria-expanded="'+!!x.open+'"':"")+'><div class="fl-rail'+(same?" same":"")+(nsk?" nsk":"")+'"><span class="fl-bar fl-bar-'+esc(sk.code)+'"></span><span class="fl-k fl-k-'+esc(sk.code)+'">'+esc(sk.short)+"</span>"+(detail&&x.lane?'<span class="fl-ln">'+esc(x.lane)+"</span>":"")+"</div>";
    /* two lines for every step: [kind] title, then one grey line that only adds what the title doesn't say */
    h+='<div class="fl-ln2"><span class="fl-nn">'+esc(x.n||n)+'</span></div><div class="fl-body"><span class="fl-w1"><span class="fl-kd'+(x.tagKind==="fail"?" fail":"")+'">'+esc(x.tag||"")+"</span>"+esc(x.title)+(MARK[x.mark]?'<span class="fl-mk fl-mk-'+esc(x.mark)+'"'+(x.markTip?' title="'+esc(x.markTip)+'"':"")+">"+MARK[x.mark]+"</span>":"")+(x.markTip?'<span class="fl-mvy">'+esc(x.markTip)+"</span>":"")+(x.count?'<span class="fl-cnt2'+(x.count.bad?" bad":"")+'" title="Items from this run that reached this step">'+esc(x.count.t)+"</span>":"")+"</span>";
    var sub=x.sub!=null?x.sub:(x.res&&x.res.text)||x.what||"";
    if(sub)h+='<span class="fl-sub'+(x.subCls?" "+esc(x.subCls):"")+'">'+esc(sub)+"</span>";
    if(x.was)h+='<span class="fl-was">'+esc(x.was)+"</span>"; /* in a run: what this step gave on the last run of the same item */
    h+=(x.extra||"")+(x.more||"")+"</div>";
    if(x.insp)h+='<div class="fl-insp-w">'+x.insp+"</div>";
    return h+"</div>"}
  function band(x){return'<div class="fl-band"><span></span><div class="fl-ln2" style="align-self:stretch"></div><span class="fl-bd fl-bd-'+esc(x.code)+'"><span>'+esc(x.label)+"</span>"+(x.hint?'<span class="fl-h">'+esc(x.hint)+"</span>":"")+"</span></div>"}
  function stageRow(key,n,S,info,open,flag){
    return'<button class="fl-row fl-stg'+(S&&S.trig?" fl-trg":"")+(S&&S.wf?" fl-wfs":"")+(flag?" st-"+flag:"")+'" type="button" data-stage="'+esc(key)+'" aria-expanded="'+open+'"><div class="fl-rail"></div><div class="fl-ln2"><span class="fl-nn">'+n+'</span></div><div class="fl-body"><span class="fl-stt"><span class="fl-chev" aria-hidden="true">'+(open?"▾":"▸")+"</span>"+(S&&S.trig?'<span class="fl-trgtag">Trigger</span>':"")+(S&&S.wfTag?'<span class="fl-wftag">Workflow</span>':"")+esc(S.title||key)+'<span class="fl-stc">'+(S&&S.note?esc(S.note)+" · ":"")+info.count+" step"+(info.count===1?"":"s")+"</span>"+
      (flag==="failed"||flag==="needs_user"?'<span class="fl-flag '+flag+'">'+(flag==="failed"?"Failed":"Needs you")+"</span>":"")+
      "</span></div></button>"}
  /* a step opened under its row: Summary · Data · Logic in a run, Logic alone outside one.
     o = {key, tabs:["summary","data","logic"], cur, meta, view:"table"|"json",
          summary:{inn, tags:[], out, warn, how} | {derived, goKey, goLabel},
          data:{inn:[[k,v]], out:[[k,v,flag]], note} | {derived, goKey, goLabel},
          logic:{what, rule, ruleText, ruleOpen, opts:[{w,t,on}], mark, missing}} */
  var TABW={summary:"Summary",data:"Data",logic:"Logic"};
  function val(v){return v==null?"":Array.isArray(v)?(v.length?v.map(val).join(", "):"(none)"):typeof v==="object"?JSON.stringify(v):String(v)}
  function kv(rows){return'<div class="fl-kv">'+rows.map(function(r){return'<div class="fl-kvr'+(r[2]?" warn":"")+'"><span class="fl-kk">'+esc(r[0])+'</span><span class="fl-kvv">'+esc(val(r[1]))+(r[2]?'<span class="fl-flagt">'+esc(r[2])+"</span>":"")+"</span></div>"}).join("")+"</div>"}
  function json(rows){var o={};rows.forEach(function(r){o[r[0]]=r[1]});return'<pre class="fl-json">'+esc(JSON.stringify(o,null,2))+"</pre>"}
  function derived(d,key){return'<div class="fl-iempty"><span>'+esc(d.derived)+"</span>"+(d.goKey?'<button class="fl-lbtn" type="button" data-gostep="'+esc(d.goKey)+'">'+esc(d.goLabel||"Open that step")+"</button>":"")+"</div>"}
  /* the step panel (the step details design): tabs only when there is more than one (a run: Summary · Data · Logic;
     a workflow page: Logic alone, no tab bar). Summary: any warning as one line on top, then one sentence and a few
     fact chips. Data: what went in and what came out as a plain list, JSON a link away. Logic: one sentence (the rule
     only when it adds something), a decision's options with the one taken highlighted, and the rule text on request. */
  var NOTEW={uncertain:"Not sure:",failed:"Failed:",needs_user:"Waiting on you:"};
  /* the step panel, frame A (the step details design): a soft card under its step with no lines inside, the tabs a small
     switch (a run: Summary · Data · Logic; a workflow page: none, Logic alone), the status in small grey type.
     Summary: any warning on top, one sentence, a few fact chips. Data: what came out as clean rows, what went in below,
     everything else ("All fields") and JSON on request. Logic, read top to bottom: the question (the step's tip), this
     run's answer in a blue box, the other answers in one grey line, then "How it decides" for the rule. */
  function inspector(o){
    var tabs=o.tabs||["logic"],cur=tabs.indexOf(o.cur)>=0?o.cur:tabs[0],k=esc(o.key),bare=tabs.length<2&&!o.meta,h='<div class="fl-insp fi2'+(bare?" fi-bare":"")+'" role="region" aria-label="Step details">';
    /* no tabs and no status (a workflow page): no header row, only the × in the corner */
    h+='<div class="fi-h">'+(tabs.length>1?'<span class="fi-tabs" role="tablist">'+tabs.map(function(t){return'<button class="'+(t===cur?"on":"")+'" type="button" role="tab" aria-selected="'+(t===cur)+'" data-itab="'+k+'|'+t+'">'+TABW[t]+"</button>"}).join("")+"</span>":"")+
      '<span class="fi-meta">'+esc(o.meta||"")+'</span><button class="fi-x" type="button" data-iclose="'+k+'" aria-label="Close this step">×</button></div><div class="fi-b">';
    var lab=function(t){return'<span class="fi-lab">'+esc(t)+"</span>"},rows=function(list){return'<div class="fi-rows">'+list.map(function(r){return'<div class="'+(r[2]?"warn":"")+'"><span>'+esc(r[0])+"</span><span>"+(isList(r[1])?listHtml(r[1]):esc(val(r[1])))+(r[2]?"<em>"+esc(r[2])+"</em>":"")+"</span></div>"}).join("")+"</div>"};
    /* a list of items (e.g. io.out.seen: "subject · sender · time · id · kept"): one line each, its first part the name,
       the middle parts quiet, a last part that says kept or stopped as a small mark */
    function isList(v){return Array.isArray(v)&&v.length>0&&v.every(function(x){return typeof x==="string"||typeof x==="number"})}
    function listHtml(v){var kept=v.filter(function(x){return/ · (kept|carried on)\b[^·]*$/i.test(String(x))}).length,stop=v.filter(function(x){return/ · (stopped|skipped)\b[^·]*$/i.test(String(x))}).length;
      /* a long list (a trigger can see 100 emails): a count on top and a box that scrolls on its own */
      return(v.length>8?'<div class="fi-lc">'+v.length+" items"+(kept||stop?" · "+kept+" kept · "+stop+" stopped":"")+"</div>":"")+'<ol class="fi-list'+(v.length>8?" long":"")+'">'+v.map(function(x){var p=String(x).split(" · "),last=p.length>1?p[p.length-1]:"",mk=/^(kept|stopped|skipped|carried on)\b/i.test(last)?last:"";if(mk)p.pop();
      return"<li><b>"+esc(p[0])+"</b>"+(p.length>1?'<span class="fi-lm">'+esc(p.slice(1).join(" · "))+"</span>":"")+(mk?'<span class="fi-lt'+(/^kept|^carried/i.test(mk)?" on":"")+'">'+esc(mk)+"</span>":"")+"</li>"}).join("")+"</ol>"}
    var go=function(d){return'<p class="fi-p mut">'+esc(d.derived)+"</p>"+(d.goKey?'<button class="fi-lk" type="button" data-gostep="'+esc(d.goKey)+'">'+esc(d.goLabel||"Open that step")+" ›</button>":"")};
    if(cur==="summary"){var s=o.summary||{},st=o.status;
      if(s.derived)h+=go(s);
      else h+=(NOTEW[st]||s.warn?'<p class="fi-note '+esc(st||"warn")+'"><b>'+esc(NOTEW[st]||"Note:")+"</b> "+esc(s.warn||s.out||"")+"</p>":"")+(s.out&&!(NOTEW[st]&&!s.warn)?'<p class="fi-p">'+esc(s.out)+"</p>":"")+
        ((s.tags||[]).length?'<div class="fi-chips">'+s.tags.map(function(t){return"<span>"+esc(t)+"</span>"}).join("")+"</div>":"")}
    if(cur==="data"){var d=o.data||{},js=o.view==="json",all=!!o.allFields;
      if(d.derived)h+=go(d);
      else if(js)h+=json((d.inn||[]).map(function(r){return["in: "+r[0],r[1]]}).concat((d.out||[]).map(function(r){return["out: "+r[0],r[1]]})))+'<div class="fi-lks"><button class="fi-lk" type="button" data-dview="table">Back to the fields</button></div>';
      else{var out=d.out||[],inn=d.inn||[],main=d.note?out.filter(function(r){return r[0]==="result"}):out,rest=d.note?out.filter(function(r){return r[0]!=="result"}):[];
        if(d.note)main=main.map(function(r){return["result",r[1]]});
        h+=lab(d.outLab||"Came out")+(main.length?rows(main):'<p class="fi-p mut sm">Nothing logged</p>');
        if(!d.noIn)h+=lab("Went in")+(inn.length?rows(inn):'<p class="fi-p mut sm">'+(d.note?"Not logged on this run (an older trace)":"Nothing logged")+"</p>");
        if(all&&rest.length)h+=lab("All fields")+rows(rest);
        h+='<div class="fi-lks">'+(rest.length?'<button class="fi-lk" type="button" data-allf="'+k+'">'+(all?"Fewer fields ▴":"All fields ("+(rest.length+main.length)+") ▾")+"</button>":"")+'<button class="fi-lk" type="button" data-dview="json">JSON</button></div>'}}
    if(cur==="logic"){var L=o.logic||{},opts=L.opts||[],on=opts.filter(function(p){return p.on}),off=opts.filter(function(p){return!p.on}),plan=L.mark!=="THIS RUN";
      var q=L.q||L.what||L.rule;
      h+=q?'<p class="fi-p fi-q">'+esc(q)+"</p>":'<p class="fi-p mut">No rule is written down for this step.</p>';
      if(opts.length&&on.length&&!plan)h+='<div class="fi-this"><span>This run</span><b>'+esc(on[0].w)+"</b> <i>→ "+esc(on[0].t)+"</i></div>"+
        (off.length?'<p class="fi-p mut sm"><span class="fi-oth">Otherwise:</span> '+(function(){var lc=function(t){return t.charAt(0).toLowerCase()+t.slice(1)},by=[],ix={};off.forEach(function(p){if(ix[p.t]==null){ix[p.t]=by.length;by.push({t:p.t,w:[]})}by[ix[p.t]].w.push(lc(p.w))});
          return by.map(function(g){return esc(g.w.join(" or "))+" → "+esc(lc(g.t))}).join("; ")})()+"</p>":"");
      else if(opts.length)h+='<div class="fi-optl">'+opts.map(function(p){return"<span><b>"+esc(p.w)+"</b> <i>→ "+esc(p.t)+"</i></span>"}).join("")+"</div>";
      else if(q!==(L.what||L.rule)&&(L.what||L.rule))h+='<p class="fi-p mut sm">'+esc(L.what||L.rule)+"</p>";
      if(L.missing)h+='<p class="fi-note warn">'+esc(L.missing)+"</p>";
      if(L.ruleText||(L.rule&&L.rule!==q))h+='<button class="fi-lk" type="button" data-rule="'+k+'" aria-expanded="'+!!L.ruleOpen+'">'+(L.ruleOpen?"How it decides ▴":"How it decides ▾")+"</button>"+
        (L.ruleOpen?(L.rule&&L.rule!==q?'<p class="fi-p sm">'+esc(L.rule)+"</p>":"")+(L.ruleText?'<blockquote class="fi-rule">'+esc(L.ruleText)+"</blockquote>":""):"")}
    return h+"</div></div>"}

  /* o: {stages:[{key,title,n,notes}] or null, state:{stage:{}}, prefix, detail, info(key, rows) -> {count, notes, answers, last}}
     Items with no stage before the first stage show flat; later ones stay in the stage before them. */
  function layout(items,o){
    var stg=o.stages&&o.stages.length?o.stages:null,h="",prev=null,n=0;
    var k=0;   /* a step drawn inside another (a part written as code): its parent's number, then .1, .2 */
    if(!stg){items.forEach(function(x){if(x.kind==="band"){h+=band(x);return}if(x.nest){h+=row(x,n+"."+(++k),prev,o.detail,false);prev=x;return}k=0;if(!x.n)n++;h+=row(x,n,prev,o.detail,false);prev=x});return h}
    var byKey={};stg.forEach(function(s){byKey[s.key]=s});
    var cur=null,groups=[],lead=[];
    items.forEach(function(x){var k=x.stage&&byKey[x.stage]?x.stage:cur;if(!k){lead.push(x);return}if(k!==cur){cur=k;groups.push({key:k,items:[]})}groups[groups.length-1].items.push(x)});
    lead.forEach(function(x){if(x.kind==="band"){h+=band(x);return}if(!x.n)n++;h+=row(x,n,prev,o.detail,false);prev=x});
    var sn=0;
    groups.forEach(function(g){
      var S=byKey[g.key],tr=!!(S&&S.trig),num=tr?"T":String(++sn);
      var rows=g.items.filter(function(x){return x.kind==="row"}),flag=flagOf(rows),open=isOpen(o.state,o.prefix,g.key,flag);
      var info=o.info?o.info(g.key,rows):{count:rows.length};if(info.count==null)info.count=rows.length;
      /* each stage in one block, so its tint runs behind every row in it; the hand-over line sits outside, untinted */
      var fans=g.items.filter(function(x){return x.kind==="fan"}).map(function(x){return row(x)}).join("");
      h+='<div class="fl-grp'+(tr?" fl-g-trg":S&&S.wf?" fl-g-wf":"")+'">'+stageRow(g.key,num,S,info,open,flag);prev=null;
      if(!open){h+="</div>"+fans;return} /* the divider shows even when the trigger is closed */
      var i=0;
      g.items.forEach(function(x){if(x.kind==="band"){h+=band(x);return}if(x.kind==="fan")return;if(x.kind==="slots"){h+=row(x);prev=null;return}if(x.nest){h+=row(x,(tr?"T"+i:num+"."+i)+"."+(++k),prev,o.detail,true);prev=x;return}k=0;if(!x.n)i++;h+=row(Object.assign({trig:tr,wfs:!!(S&&S.wf)},x),tr?"T"+i:num+"."+i,prev,o.detail,true);prev=x});h+="</div>"+fans});
    return h}
  function allOpen(items,o){
    if(!o.stages||!o.stages.length)return false;var keys={},any=false;
    items.forEach(function(x){if(x.stage)keys[x.stage]=keys[x.stage]||[];if(x.stage&&x.kind==="row")keys[x.stage].push(x)});
    return Object.keys(keys).every(function(k){any=true;return isOpen(o.state,o.prefix,k,flagOf(keys[k]))})&&any}

  /* ---------- the calm layout (the Workflow Viewer): one quiet line per stage, step and decision ----------
     The same items as layout(), drawn calmer (rule 23's four layers): a stage is one line with its outcome on the right;
     plain steps in a row fold into one "N steps" line; decisions, code steps and anything failed, waiting or new keep
     their own line; steps that run on one answer sit indented under a grey "if …"; a code step's own steps hide behind
     it. Detail adds a small block under every line: its rule, its answers and where each leads, what went in and came
     out. Extra item fields: type, answer, right, branch, tip, det:{rule,opts:[{w,t,on}],inn,out}.
     o: as layout(), plus mode ("run" | "plan") and info(key, rows) -> {out, tip, skipped}. */
  var CI={combine:"⇉",read:"↓",check:"✓",guard:"✓",act:"✎",dec:"◆",route:"↗",next:"→",need:"!",fail:"✕",code:"{ }",draft:"✉",send:"✉",fold:"≡",live:"…"};
  function tipHtml(t){return t?'<span class="c-ii" data-tip="'+esc(t)+'" tabindex="0" aria-label="'+esc(t)+'">i</span>':""}
  var CMARK={"new":"new",chg:"changed","just-new":"just added","just-chg":"just changed",del:"removed","just-del":"just removed",guess:"guess",moved:"moved",ask:"open",since:"changed since last run"};
  function calmLine(x,o,kids){
    var st=x.status||"",kind=st==="failed"?"fail":st==="live"?"live":kids.length?"code":x.combines?"combine":x.tagKind==="dec"||x.type==="dec"?"dec":/draft|send/i.test(x.tag||"")?"draft":x.tagKind||x.type||"check";
    var r="";
    if(st==="failed")r='<span class="c-a fail">failed</span>';
    else if(st==="live")r='<span class="c-r">working on it</span>';
    else if(x.answer)r='<span class="c-a'+(st==="needs_user"?" need":"")+'">'+esc(x.answer)+"</span>";
    else if(x.right)r='<span class="c-r'+(st==="needs_user"?" need":"")+'">'+esc(x.right)+"</span>";
    else if(x.type==="dec"&&x.nAnswers)r='<span class="c-none">'+x.nAnswers+" answers</span>";
    var mk=CMARK[x.mark]?'<span class="c-mk c-mk-'+esc(x.mark)+'"'+(x.markTip?' title="'+esc(x.markTip)+'"':"")+">"+CMARK[x.mark]+"</span>":"";
    var tap=x.key&&x.open!=null,ko=kids.length&&(o.detail||o.state.kids[o.prefix+x.key]);
    if(ko&&o.mode==="run"&&st!=="failed"&&st!=="live"&&!x.answer)r="";
    if(x.open&&x.insp&&o.mode==="run"&&st!=="live")r=""; /* its open panel says what it found: the line doesn't repeat it */
    var h='<div class="c-st'+(x.open?" open":"")+(x.mark==="del"||x.mark==="just-del"?" c-del":"")+'"><div class="c-ln'+(tap?" c-tap":"")+(st?" st-"+esc(st):"")+'"'+(tap?' data-stepkey="'+esc(x.key)+'" aria-expanded="'+!!x.open+'" role="button" tabindex="0"':"")+">"+
      '<span class="c-ic c-ic-'+esc(kind)+'">'+(CI[kind]||"·")+'</span><span class="c-tx">'+esc(x.title)+tipHtml(x.tip)+mk+
      (kids.length?'<button class="c-kb" type="button" data-ckids="'+esc(x.key)+'" aria-expanded="'+!!ko+'">'+(ko?"hide its steps":"its "+kids.length+" steps")+"</button>":"")+
      (x.count?'<span class="fl-cnt2'+(x.count.bad?" bad":"")+'" title="Items from this run that reached this step">'+esc(x.count.t)+"</span>":"")+
      "</span><span class=\"c-rt\">"+r+(o.mode==="run"&&x.took?'<span class="c-tk">'+esc(x.took)+"</span>":"")+"</span></div>";
    h+=enrich(x,o);
    if(x.extra&&(o.detail||x.open))h+='<div class="c-ex">'+x.extra+"</div>";
    if(x.was)h+='<div class="c-was">Last run: '+esc(x.was)+"</div>";
    if(x.insp)h+='<div class="c-insp">'+x.insp+"</div>";
    if(ko)h+='<div class="c-kids">'+kids.map(function(k){return'<div class="c-ln c-kl"><span class="c-ic">'+(CI[k.tagKind]||"·")+'</span><span class="c-tx">'+esc(k.title)+'</span><span class="c-rt">'+(k.right?'<span class="c-r">'+esc(k.right)+"</span>":k.status==="skipped"?'<span class="c-none">skipped</span>':"")+"</span></div>"}).join("")+"</div>";
    return h+"</div>"}
  function detHtml(d){var r=[];
    if(d.rule)r.push('<span class="c-dk">Rule</span><span class="c-dv">'+esc(d.rule)+"</span>");
    if(d.opts&&d.opts.length)r.push('<span class="c-dk">Answers</span><span class="c-dv">'+d.opts.map(function(p){return'<span class="c-an'+(p.on?" on":d.picked?" off":"")+'"><b>'+esc(p.w)+"</b> → "+esc(p.t)+"</span>"}).join("")+"</span>");
    if(d.inn)r.push('<span class="c-dk">In</span><span class="c-dv c-mono">'+esc(d.inn)+"</span>");
    if(d.out)r.push('<span class="c-dk">Out</span><span class="c-dv c-mono">'+esc(d.out)+"</span>");
    return r.length?'<div class="c-det">'+r.join("")+"</div>":""}
  /* a plain step folds; anything worth seeing on its own line doesn't */
  function plain(x,kids){return x.kind==="row"&&!x.n&&!x.nest&&!kids.length&&x.type!=="dec"&&x.tagKind!=="dec"&&!x.mark&&!x.open&&!x.was&&!x.extra&&!x.count&&!(x.status&&x.status!=="done"&&x.status!=="skipped")}
  function calmBody(items,o){
    /* a stage mostly on one answer, with a smaller branch inside it (its decision is in this stage): one outer "if …",
       the inner branch indented within it, instead of the outer label repeating around the inner one */
    var rs=items.filter(function(x){return x.kind==="row"&&!x.nest&&!x.n}),b0=rs.length&&rs[0].branch,decs={};
    rs.forEach(function(x){if(x.type==="dec"&&x.key)decs[x.key]=1});
    if(b0&&rs.every(function(x){return x.branch===b0||(x.branch&&decs[x.branchDec])})&&rs.some(function(x){return x.branch!==b0})){
      var inner=items.map(function(x){return x.branch===b0?Object.assign({},x,{branch:""}):x});
      return'<div class="c-br">'+(o.mode==="run"?"":'<div class="c-bw">'+esc(b0)+"</div>")+calmBody(inner,o)+"</div>"}
    /* a code step's own steps go behind it */
    var units=[];items.forEach(function(x){if(x.kind==="band")return;if(x.nest&&units.length){units[units.length-1].kids.push(x);return}units.push({x:x,kids:[]})});
    var h="",i=0;
    function unit(u){var x=u.x;
      if(x.kind==="fan")return'<div class="c-fan">'+esc(x.title)+(x.sub?" · "+esc(x.sub):"")+"</div>";
      if(x.kind==="slots")return'<div class="c-slots">'+x.slots.map(function(z){return'<span><i>'+esc(z[0])+"</i> "+esc(z[1]||"—")+"</span>"}).join("")+"</div>";
      return calmLine(x,o,u.kids)}
    /* a run of plain steps folds only when it saves room: 4 or more in a row, or 2 or more in a stage that would show
       over 7 lines; never a whole stage (opening a stage shows its steps). A fold is named by its first and last step. */
    function run(list){var out="",j=0;
      while(j<list.length){var u=list[j];
        if(plain(u.x,u.kids)&&!o.detail){var g=[];while(j<list.length&&plain(list[j].x,list[j].kids))g.push(list[j++]);
          if(g.length===1||g.length===list.length||(g.length<4&&list.length<=7)){out+=g.map(unit).join("");continue}
          var fk=o.prefix+"f:"+(g[0].x.key||j),fo=!!o.state.cfold[fk],last=g.map(function(z){return z.x.right}).filter(Boolean).pop()||"";
          out+='<div class="c-fo'+(fo?" open":"")+'"><button class="c-ln c-fl" type="button" data-cfold="'+esc(fk)+'" aria-expanded="'+fo+'"><span class="c-ic">'+CI.fold+'</span><span class="c-tx">'+esc(g[0].x.title)+" … "+esc(g[g.length-1].x.title)+' <span class="c-fn">· '+g.length+' steps</span></span><span class="c-rt">'+(last?'<span class="c-r">'+esc(last)+"</span>":"")+"</span></button>"+(fo?'<div class="c-fb">'+g.map(unit).join("")+"</div>":"")+"</div>";continue}
        out+=unit(u);j++}
      return out}
    /* a whole stage on one answer: its stage line already says when it runs, so no indent */
    var rows=units.filter(function(u){return u.x.kind==="row"}),whole=rows.length&&rows[0].x.branch&&rows.every(function(u){return u.x.branch===rows[0].x.branch});
    while(i<units.length){var b=whole?"":units[i].x.branch;
      if(b){var grp=[];while(i<units.length&&units[i].x.branch===b)grp.push(units[i++]);
        h+='<div class="c-br">'+(o.mode==="run"?"":'<div class="c-bw">'+esc(b)+"</div>")+run(grp)+"</div>";continue}
      var seg=[];while(i<units.length&&(whole||!units[i].x.branch))seg.push(units[i++]);h+=run(seg)}
    return h}
  /* a short workflow (no stages, rule 23) drawn like stage lines, so short and long read the same: each step a bold
     numbered line (a decision a ◆), what it makes on the right (a run: what it found), a step that runs on one answer
     tucked under its decision with "only if …" on the right, and what the draft changed as a small dot */
  /* a decision where one answer goes on and every other ends the run reads as a condition on the steps after it, so
     the numbered list draws it as an inset gate, not a numbered-column row: just its question (Detail lists its answers).
     A failed or waiting decision, or one whose answers lead to steps of their own, keeps its full row. */
  function gateOf(x){var al=x.alts||[];if(x.type!=="dec"||al.length<2)return false;var st=x.status||"";if(st==="failed"||st==="needs_user")return false;
    var stop=function(a){return!!(a.ends||a.k==="stop")},go=al.filter(function(a){return!stop(a)});if(go.length!==1)return false;
    return true}
  /* loops (core-architect rule 33): steps that go round once per item, inside one run. Each item says which loops it is
     in (lchain: loop keys, outermost first); o.loops = {key: {title, each, count, pick, menu}}. Simple marks a repeating
     line with a small grey ↻ (a line in a loop inside a loop sits indented); Detail draws the loop as a thin grey line
     down the left of what repeats, headed "↻ For each <item>", with its count and, on a run, the item picker. */
  /* a step inside a loop carries no mark of its own: the "↻ For each <item>" line above says it repeats, and the
     loop's steps sit indented under it (a loop inside a loop one step further), so where the loop ends shows too */
  function lpg(x,o){return""}
  function lnest(x,o){var d=o.loops?(x&&x.lchain||[]).length:0;return d>1?" c-in2":d===1?" c-in1":""}
  /* a loop opens with one light line, in Simple and Detail alike: "↻ For each email [All 8 emails ▾] ‹ ›  8 left off".
     On a run its picker shows one item's own results in the lines below; the lines that repeat carry the grey ↻. */
  function loopWrap(o){var st=[];
    function head(k,d){var L=(o.loops||{})[k]||{title:k};
      return'<div class="c-lbar'+(d?" inner":"")+'" role="group" aria-label="'+esc(L.title||"Loop")+'"><span class="c-li" aria-hidden="true">↻</span><span class="c-lt">'+esc(L.title||"")+(L.max?" · up to "+esc(L.max):"")+"</span>"+
        (L.pick||"")+(L.count?'<span class="c-lc">'+esc(L.count)+"</span>":"")+(L.menu||"")+"</div>"}
    return{at:function(chain){if(!o.loops)return"";chain=chain||[];var out="",i=0;
        while(i<st.length&&i<chain.length&&st[i]===chain[i])i++;
        st=st.slice(0,i);
        for(var j=i;j<chain.length;j++){out+=head(chain[j],j);st.push(chain[j])}return out},
      end:function(){st=[];return""}}}
  /* Detail: under a line, one grey sentence (what it does) and a row of small fact chips (x.facts: [[cls, label, value]]) */
  function enrich(x,o){if(!o.detail||x.open)return"";var f=(x.facts||[]).filter(function(c){return c&&c[2]!=null&&c[2]!==""}),d=x.desc||"";
    if(!d&&!f.length)return"";
    return'<div class="c-enr">'+(d?"<p>"+esc(d)+"</p>":"")+(f.length?'<div class="c-fx">'+f.map(function(c){return'<span class="'+esc(c[0]||"")+'">'+(c[1]?"<i>"+esc(c[1])+"</i>":"")+esc(c[2])+"</span>"}).join("")+"</div>":"")+"</div>"}
  /* the numbered steps (a workflow of 7 or fewer, rule 23), the same lines in Simple and Detail: every step its number
     (decisions and steps on one answer too, so the board counts as the skill does), what it found on the right (on the
     workflow page, what it makes), the grey ↻ on steps that repeat, a step on one answer indented under its decision.
     On a run, a step that didn't run stays as a faded line saying why (x.off). Detail adds a grey sentence and fact
     chips under each line; a click opens the step's Summary · Data · Logic panel, inset under it. */
  function flatNum(items,o){var h="",n=0,lastDec="",LW=loopWrap(o);
    var dot=function(x){return CMARK[x.mark]?'<span class="c-mdot c-mk-'+esc(x.mark)+'" title="'+esc(CMARK[x.mark]+(x.markTip?": "+x.markTip:""))+'" aria-label="'+esc(CMARK[x.mark])+'"></span>':""};
    var rt=function(x){var st=x.status||"";if(x.open&&x.insp&&o.mode==="run"&&st!=="live")return"";if(st==="failed")return'<span class="c-a fail">failed</span>';
      if(x.off)return'<span class="c-none">'+esc(x.right||"didn’t run")+"</span>";
      if(o.mode==="run")return x.answer?'<span class="c-a'+(st==="needs_user"?" need":"")+'">'+esc(x.answer)+"</span>":x.right?'<span class="c-r">'+esc(x.right)+"</span>":"";
      if(x.branch&&x.branchDec)return'<span class="c-none">only '+esc(x.branch)+"</span>";
      return x.type==="dec"&&x.answer?'<span class="c-a">'+esc(x.answer)+"</span>":x.type==="dec"&&x.nAnswers?'<span class="c-none">'+x.nAnswers+" answers</span>":x.makes?'<span class="c-r">'+esc(x.makes)+"</span>":""};
    var circ=function(x){var st=x.status||"";if(st==="live"&&x.n==="…")return'<span class="c-n live">…</span>'; /* the "working on it" line is no step of its own: no number */
      n++;if(st==="failed")return'<span class="c-n fail">✕</span>';if(st==="needs_user")return'<span class="c-n need">!</span>';
      return'<span class="c-n'+(o.mode==="run"&&st==="done"&&!x.off?" ok":"")+'">'+n+"</span>"};
    var extra=function(x){var e=enrich(x,o);if(x.extra&&(o.detail||x.open))e+='<div class="c-ex">'+x.extra+"</div>";if(x.was)e+='<div class="c-was">Last run: '+esc(x.was)+"</div>";if(x.insp)e+='<div class="c-insp">'+x.insp+"</div>";return e};
    items.forEach(function(x){
      if(x.kind!=="row"||x.nest){if(x.kind==="fan"||x.kind==="slots")h+=LW.at([])+calmBody([x],o);return}
      h+=LW.at(x.lchain);
      if(x.n==="↳"){h+=calmLine(x,o,[]);return}
      var tap=x.key&&x.open!=null,at=tap?' data-stepkey="'+esc(x.key)+'" aria-expanded="'+!!x.open+'" role="button" tabindex="0"':"";
      var sub=x.branch&&x.branchDec&&x.branchDec===lastDec?" c-nbsub":""; /* runs on one answer of the decision just above */
      if(x.type==="dec")lastDec=x.key;
      h+='<div class="c-sg c-nlg'+lnest(x,o)+sub+(x.off?" c-off2":"")+(x.open?" open":"")+'"><div class="c-sh c-nl'+(tap?" c-tap":"")+(x.status&&!x.off?" st-"+esc(x.status):"")+'"'+at+">"+circ(x)+'<span class="c-stt"><span class="c-stl">'+dot(x)+lpg(x,o)+esc(x.title)+tipHtml(x.tip)+"</span></span>"+
        '<span class="c-so">'+rt(x)+(x.took&&!x.off?'<span class="c-tk">'+esc(x.took)+"</span>":"")+'</span><span class="c-cv" aria-hidden="true">'+(tap?"›":"")+"</span></div>"+extra(x)+"</div>"});
    return'<div class="c-flatn">'+h+"</div>"}
  /* one stage line and, when open, its steps: every stage is drawn by this, and so is the trigger (its tile where a
     stage has its number). b: {key, mk, title, tip, out, outCls, cls, took, note, items, open, view} */
  function stageBlock(b,o){var tap=b.tap!=null?b.tap:!!(b.items&&b.items.length);
    var inner=b.mk+'<span class="c-stt"><span class="c-stl">'+(b.lp||"")+esc(b.title)+tipHtml(b.tip)+"</span>"+((b.open||o.detail)&&b.tip?'<small class="c-sub">'+esc(b.tip)+"</small>":"")+"</span>"+
      '<span class="c-so'+(b.outCls?" "+b.outCls:"")+'">'+esc(b.out||"")+(b.took&&!b.open?'<span class="c-tk">'+esc(b.took)+"</span>":"")+'</span><span class="c-cv" aria-hidden="true">'+(tap||b.view?"›":"")+"</span>";
    var head=tap?'<button class="c-sh" type="button" data-stage="'+esc(b.key)+'" aria-expanded="'+!!b.open+'">'+inner+"</button>":
      b.view?'<button class="c-sh" type="button" data-view="'+esc(b.view)+'">'+inner+"</button>":'<div class="c-sh">'+inner+"</div>";
    return'<div class="c-sg'+(b.open?" open":"")+(b.cls?" "+b.cls:"")+(b.nest||"")+'">'+head+(b.open&&tap?'<div class="c-sb">'+(b.note?'<div class="c-tnote">'+esc(b.note)+"</div>":"")+calmBody(b.items,o)+"</div>":"")+"</div>"}
  /* the trigger, before the steps on every page (o.trig): a stage like the others, with its tile */
  function trigBlock(o){var t=o.trig;if(!t)return"";var rows=(t.items||[]).filter(function(x){return x.kind==="row"}),flag=flagOf(rows),open=!!(t.items&&t.items.length)&&isOpen(o.state,o.prefix,"_trig",flag);
    return stageBlock({key:"_trig",mk:'<span class="c-n c-ntile">'+(t.icon||"")+"</span>",title:t.title,tip:t.tip,out:open&&o.mode==="run"?"":t.out,took:t.took,note:t.note,items:t.items,view:t.view,
      open:open,cls:"c-trg"},o)}
  function calm(items,o){
    var stg=o.stages&&o.stages.length?o.stages:null;
    o.state.cfold=o.state.cfold||{};o.state.kids=o.state.kids||{};
    var tb=trigBlock(o);
    if(!stg)return tb+(o.numbered?flatNum(items,o):'<div class="c-flat">'+calmBody(items,o)+"</div>");
    var byKey={};stg.forEach(function(s){byKey[s.key]=s});
    var cur=null,groups=[],lead=[];
    items.forEach(function(x){var k=x.stage&&byKey[x.stage]?x.stage:cur;if(!k){lead.push(x);return}if(k!==cur){cur=k;groups.push({key:k,items:[]})}groups[groups.length-1].items.push(x)});
    var LW=loopWrap(o),chainOf=function(g){var r=(g.items||[]).filter(function(x){return x.kind==="row"&&x.lchain})[0];return r?r.lchain:[]};
    var h=tb+(lead.length?'<div class="c-flat">'+calmBody(lead,o)+"</div>":""),sn=0,have={};groups.forEach(function(g){have[g.key]=g});
    /* every stage in order: one this route doesn't reach stays as a faded line saying when it would run */
    stg.map(function(S){return have[S.key]||{key:S.key,items:[],off:true}}).forEach(function(g){
      var gch=g.off?(o.stageChain&&o.stageChain[g.key])||[]:chainOf(g),gx={lchain:gch};h+=LW.at(gch);
      if(g.off){var oi=o.info?o.info(g.key,[]):{};if(!o.showOff&&!oi.out)return;
        var offTip=oi.tip||byKey[g.key].tip;
        h+='<div class="c-sg skip'+lnest(gx,o)+'"><div class="c-sh c-off"><span class="c-n">'+(++sn)+'</span><span class="c-stt"><span class="c-stl">'+lpg(gx,o)+esc(byKey[g.key].title||g.key)+tipHtml(offTip)+"</span>"+(o.detail&&offTip?'<small class="c-sub">'+esc(offTip)+"</small>":"")+'</span><span class="c-so">'+esc(oi.out||"")+'</span><span></span></div></div>';return}
      var S=byKey[g.key],tr=!!(S&&S.trig),num=tr?"T":String(++sn),rows=g.items.filter(function(x){return x.kind==="row"}),flag=flagOf(rows),open=isOpen(o.state,o.prefix,g.key,flag);
      var info=o.info?o.info(g.key,rows):{};
      var mk=flag==="failed"?'<span class="c-n fail">✕</span>':flag==="needs_user"?'<span class="c-n need">!</span>':o.mode==="run"&&flag==="done"?'<span class="c-n ok">✓</span>':'<span class="c-n">'+num+"</span>";
      var outc=open&&o.mode==="run"&&rows.length?"":info.out||""; /* on a run, an open stage's steps already say what it found */
      if(tr)mk='<span class="c-n c-ntile">'+(S.icon||"")+"</span>";
      h+=stageBlock({key:g.key,mk:mk,title:S.title||g.key,tip:info.tip||S.tip,out:outc,outCls:flag==="needs_user"?"need":flag==="failed"?"fail":"",
        cls:(info.skipped?"skip":"")+(tr?" c-trg":""),items:g.items,tap:true,open:open,lp:lpg(gx,o),nest:lnest(gx,o)},o)});
    return h+LW.end()}
  /* one tooltip for every ⓘ (data-tip), on both pages: shown on hover or keyboard focus, above it (below if no room) */
  if(typeof document!=="undefined"){
    var TIP=null;
    var showTip=function(el){if(!TIP){TIP=document.createElement("div");TIP.className="c-tip";document.body.appendChild(TIP)}
      TIP.textContent=el.getAttribute("data-tip");TIP.classList.add("on");var r=el.getBoundingClientRect(),t=TIP.getBoundingClientRect();
      var x=Math.min(Math.max(8,r.left+r.width/2-t.width/2),window.innerWidth-t.width-8),y=r.top-t.height-8;if(y<8)y=r.bottom+8;TIP.style.left=x+"px";TIP.style.top=y+"px"};
    var hideTip=function(){if(TIP)TIP.classList.remove("on")};
    document.addEventListener("mouseover",function(e){var t=e.target&&e.target.closest&&e.target.closest("[data-tip]");if(t)showTip(t)});
    document.addEventListener("mouseout",function(e){if(e.target&&e.target.closest&&e.target.closest("[data-tip]"))hideTip()});
    document.addEventListener("focusin",function(e){var t=e.target&&e.target.closest&&e.target.closest("[data-tip]");if(t)showTip(t)});
    document.addEventListener("focusout",hideTip);document.addEventListener("scroll",hideTip,true);
    /* a click on an ⓘ only shows it: it never opens the line it sits on */
    document.addEventListener("click",function(e){var t=e.target&&e.target.closest&&e.target.closest("[data-tip]");if(t){e.preventDefault();e.stopPropagation();showTip(t)}else hideTip()},true)}

  /* a click on a stage, Expand all or Details: returns true when handled (the page then redraws) */
  function click(t,state,prefix,stageKeys){
    if(!t||!t.dataset)return false;
    if(t.dataset.cfold){state.cfold=state.cfold||{};state.cfold[t.dataset.cfold]=!state.cfold[t.dataset.cfold];return true}
    if(t.dataset.ckids){state.kids=state.kids||{};var kk=prefix+t.dataset.ckids;state.kids[kk]=!state.kids[kk];return true}
    if(t.dataset.stage){state.stage[prefix+t.dataset.stage]=t.getAttribute("aria-expanded")!=="true";return true}
    if(t.dataset.allstages){var all=t.getAttribute("aria-pressed")!=="true";(stageKeys||[]).forEach(function(k){state.stage[prefix+k]=all});return true}
    if(t.dataset.detail){state.detail=!state.detail;saveDetail(state.detail);return true}
    if(t.dataset.odet!=null){state.odet=t.dataset.odet==="1";try{localStorage.setItem(DETAIL_KEY+":out",state.odet?"1":"0")}catch(e){}return true}
    return false}
  /* how long a run took (board-data's took / waited, in seconds), worded the same on both pages */
  function dur(sec){sec=Math.max(0,Math.round(sec||0));if(sec<60)return sec+"s";var m=Math.floor(sec/60),h=Math.floor(m/60);
    return h?h+"h "+(m%60)+"m":m+"m"+(sec%60?" "+(sec%60)+"s":"")}
  function took(r){if(!r||r.took==null)return"";return"Took "+dur(r.took)+(r.waited?" · "+dur(r.waited)+" waiting on you":"")}
  /* a run's status, in the Inbox's words, so both pages say the same thing: [word, class, kind] */
  function runStatus(r){r=r||{};var e=r.end||{};
    if(r.state==="running"||r.state==="scanning")return["Running","e-run","run"];
    if(r.state==="stalled")return["Stopped","e-stop","stop"];
    if((r.steps||[]).some(function(x){return x.status==="failed"}))return["Failed","e-fail","fail"];
    if(e.attention==="action")return["Needs you","e-ask","ask"];
    if(e.attention==="review")return["Check this","e-check","check"];
    return["Done","e-done","done"]}
  /* the Workflow outcome box for one run, the same on both pages (styles in steps.css): its status, then a few lines of
     plain text: worked → what it found; waiting → on whom and for what, first; didn't work → what happened and a possible
     fix. Then anything it created, one row each with a button to open it. From the trace's end line (verdict, next,
     waiting, problems, notes, done; RUN-TRACE.md), else worked out from its steps.
     o = {kind: "Workflow" | "Trigger" | "Request", chat: the page's name for its chat button, took: a line for the header,
          test: a test run (no rerun), details: a link to the full run,
          bare: just what's inside, with no box or header (the Inbox, under the row that already shows the status)} */
  var RSTAT={done:"",ask:"ask",check:"check",stop:"stop",fail:"stop",run:"next"};
  function outcome(r,o){o=o||{};var quote=(function(){var w=((r&&r.steps)||[]).filter(function(z){return z.status==="needs_user"}).pop();return w&&w.sub&&w.sub!==w.result?w.sub:""})();var st=runStatus(r),e=(r&&r.end)||{},K=o.kind||"Workflow",running=st[2]==="run",steps=(r&&r.steps)||[];
    var nm=function(z){return String(z.title||z.step||"A step").replace(/[?:]+$/,"")},chat=o.chat||"Chat about this";
    var waits=steps.filter(function(z){return z.status==="needs_user"}),fails=steps.filter(function(z){return z.status==="failed"});
    var probs=(e.problems||[]).map(function(x){return typeof x==="string"?{what:x}:x});
    fails.forEach(function(z){probs.push({what:nm(z)+" didn’t work"+(z.result?": "+z.result:""),why:z.why})});
    if(r&&r.state==="stalled")probs.push({what:"It stopped before finishing"+(steps.length?", after “"+nm(steps[steps.length-1])+"”":""),fix:"Run it again, or "+chat+" to find out why"});
    /* a headline (the verdict), then a list: waiting on you, what went wrong, the facts it worked out, notes.
       **bold** in the end line's text is kept as bold (md); everything else is plain text */
    var md=function(s){return esc(s).replace(/\*\*([^*]+)\*\*/g,"<b>$1</b>")},end=function(s){s=String(s||"").trim();return/[.?!”"]$/.test(s)?s:s+"."};
    var L=[],hl="";
    if(running){var ls=steps[steps.length-1];hl="<b>Still running:</b> "+esc(ls?nm(ls)+(ls.result?": "+ls.result:""):"just started")}
    else{
      hl=e.verdict?md(end(e.verdict)):probs.length?"<b>"+esc(end(probs[0].what))+"</b>":"";
      if(e.waiting||waits.length){var w=e.waiting||waits[waits.length-1].result||nm(waits[waits.length-1]);w=typeof w==="string"?w:(w&&w.t)||"";
        L.push({c:"o-ask",h:"<b>Waiting on you:</b> "+md(end(w))+(quote?'<span class="ofs">'+esc(quote)+"</span>":"")})}
      probs.forEach(function(x,k){if(k===0&&!e.verdict)return;L.push({c:"o-bad",h:"<b>"+md(end(x.what))+"</b>"+(x.why?'<span class="ofs">'+esc(x.why)+"</span>":"")})});
      if(!e.verdict&&probs[0]&&probs[0].why)L.push({c:"o-bad",h:'<span class="ofs" style="margin:0">'+esc(probs[0].why)+"</span>"});
      var fx=probs.map(function(x){return x.fix}).filter(Boolean)[0],box=K==="Workflow"&&r&&r.wf; /* the buttons below already offer a rerun */
      if(probs.length&&(fx&&!/^Run it again, or /.test(fx)||!box))L.push({c:"",h:"<b>Possible fix:</b> "+md(fx||"Run it again later. If it fails again, "+chat+" and Claude can look.")});
      (e.facts||[]).forEach(function(f){if(!f||!f.k)return;L.push({c:"",h:"<b>"+esc(f.k)+":</b> "+md(f.v==null?"":String(f.v))+(f.why?' <span class="ofw">· '+esc(f.why)+"</span>":"")})});
      if(e.next&&(e.attention==="review"||e.attention==="action")&&!e.waiting&&!waits.length)L.push({c:"o-ask",h:"<b>Next:</b> "+md(end(e.next))});
      steps.forEach(function(z){if(z.status==="uncertain")L.push({c:"o-warn",h:"<b>Not sure:</b> "+esc(nm(z))+(z.result?" · "+esc(z.result):"")})});
      (e.notes||[]).forEach(function(x){L.push({c:"o-note",h:md(String(x))})});
      if(!hl&&L.length&&!L[0].c)hl=L.shift().h;
    }
    /* what it created: drafts, a hand-off, a file. Each with a button to open it */
    var CK={"Email Draft Created":"mail","Email Sent":"mail","Handed Off":"next","File Changed":"file","Design Drafted":"file","Pulled In":"inbox"};
    var OPEN={mail:["Open drafts ↗","https://mail.google.com/mail/u/0/#drafts"],next:["Open in Inbox ↗","workflows.html"],inbox:["Open in Inbox ↗","workflows.html"],file:["",""]};
    if(o.inInbox)OPEN.next=OPEN.inbox=["",""]; /* already on the Inbox */
    var made=[],seen={};
    if(e.done&&e.done.length)e.done.forEach(function(x){if(typeof x==="string")x={k:"shown",t:x};if(x.k==="untouched"||x.k==="shown")return;made.push({k:x.k,t:x.t,d:x.detail||"",href:safeHref(x.href)?x.href:"",step:x.step||"",pv:x.preview||""})});
    else steps.forEach(function(z){var k=CK[z.type]||CK[z.as];if(!k||z.status!=="done")return;var t=z.result||nm(z);if(seen[t])return;seen[t]=1;made.push({k:k,t:nm(z),d:t,step:z.wstep||""})});
    /* the timeline: the summary (the end line's summary, else its verdict and first facts), then the steps that mattered;
       what it created gets its Open button on its own step, and the Copy buttons sit on the step that waits or failed */
    var OPN=function(x){var op=OPEN[x.k]||["",""],href=x.href||op[1],lab=x.href?hrefLabel(x.href):op[0];return href&&lab?[href,lab]:["",""]};
    var ns=running?[]:runNodes(r,e,waits,probs,o);
    made.forEach(function(x){var op=OPN(x),hit=ns.filter(function(n){return(n.k==="made"||n.k==="changed"||n.k==="next")&&(x.step&&n.key===x.step||n.t===x.t||n.d===x.d||n.d===x.t||op[0]&&n.href===op[0])})[0];
      if(hit){if(op[0]&&!hit.href){hit.href=op[0];hit.lab=op[1]}if(x.pv&&!hit.pv)hit.pv=x.pv}else ns.push({k:x.k==="next"?"next":"made",t:x.t,d:x.d,href:op[0],lab:op[1],pv:x.pv})});
    if(!running&&o.loopNodes&&o.loopNodes.length){var q0=ns.length&&ns[0].k==="quiet"?1:0;Array.prototype.splice.apply(ns,[q0,0].concat(o.loopNodes.map(function(x){var y={};for(var k in x)y[k]=x[k];y.lp=1;return y})))} /* a loop's stopped or failed items (RunPath.loopNodes) */
    var nx=o.test||(r&&r.try)?null:nextOf(r,waits,fails,probs),acts=actsHtml(r,o,K,running,nx),holder=nx?ns.filter(function(n){return nx.kind==="ask"?n.k==="ask":n.k==="error"})[0]:null;
    if(holder){holder.acts=acts;acts=""}
    var fs=(e.facts||[]).filter(function(f){return f&&f.k}).slice(0,2).map(function(f){return esc(f.k)+": "+md(f.v==null?"":String(f.v))});
    var sum=running?hl:e.summary?md(end(e.summary)):hl+(hl&&fs.length?" "+fs.join("; ")+".":"");
    var stc={done:"ok",ask:"need",check:"need",stop:"fail",fail:"fail",run:"run"}[st[2]]||"ok";
    return flowBox({summary:sum,facts:L.map(function(x){return x.h}),nodes:ns,st:stc,stl:st[0],pill:'<span class="opill '+(RSTAT[st[2]]||"")+'">'+esc(st[0])+"</span>"},
      {kind:K,detail:!!o.detail,toggle:!!o.toggle&&!o.bare,took:o.took,bare:o.bare,boxed:o.boxed,acts:acts,details:o.details,warnings:o.warnings,wtab:o.wtab,wlink:o.wlink,wkey:o.wkey})}
  /* what to do next, inside the box: the lines to paste into the Claude chat, each with Copy. Waiting on you: the yes
     and the no (a waiting run is picked up by "rerun workflow wf-…", core-dispatcher); failed or stopped: the rerun line,
     and a note for Claude to find out why. Only for a real workflow run with a workflow ID (never a test or a try: o.test). */
  /* the lines to paste for a run that waits on you or failed: {kind:"ask"|"stop", title, note, lines:[[text, button, main]]} or null */
  function nextOf(r,waits,fails,probs){
    if(!r||!r.wf)return null;var e=r.end||{},wf=r.wf;
    var nm=function(z){return String(z.title||z.step||"a step").replace(/[?:]+$/,"")};
    var q=e.waiting||(waits.length?waits[waits.length-1].result||nm(waits[waits.length-1]):"");q=typeof q==="string"?q:(q&&q.t)||"";
    if(q){var qs=q.replace(/\s+/g," ").trim();if(qs.length>90)qs=qs.slice(0,87)+"…";
      /* the waiting step's own question (core-dispatcher, Approvals wait on the Inbox): what it would do, and
         "answer wf-…: yes|no", which picks the run up at that step */
      var w=waits.length?waits[waits.length-1]:{},ask=w.ask||{},show=ask.show||(w.io&&w.io.out)||{};
      return{kind:"ask",q:ask.q||q,show:show,yes:ask.yes,no:ask.no,title:"Next step: answer in the chat",note:"Paste one into the Claude chat: the run carries on from the step that waits.",
        lines:[["answer "+wf+": yes","Copy",1],["answer "+wf+": no","Copy",0]]}}
    if(probs.length||r.state==="stalled"){var f=fails[0],what=f?"“"+nm(f)+"” failed"+(f.result?": "+f.result:""):probs[0]?probs[0].what:"it stopped before finishing";
      return{kind:"stop",what:what,title:"To fix",note:"Paste the first to try again. If it fails again, paste the second.",
        lines:[["rerun workflow "+wf,"Copy",1],[(r.label?"The run "+r.id+" ("+r.label+")":"The run "+r.id)+": "+what+". Look at its trace, say why it happened, and suggest a fix.","Copy for Claude",0]]}}
    return null}
  /* the buttons under what happened, the same on both pages. Each copies a line for the Claude chat (core-dispatcher
     requests), so neither page wires them: waiting on you → Copy "yes" / Copy "no"; failed or stopped → Copy rerun /
     Copy for Claude; otherwise Run again / Ask Claude. o.details: a link to the full run (the Inbox's See details). */
  function actsHtml(r,o,K,running,n){
    if(K!=="Workflow"||!r)return"";var b=function(lab,line,pri){return'<button class="ocb'+(pri?" pri":"")+'" type="button" data-occopy="'+esc(line)+'" title="'+esc(line)+'">'+esc(lab)+"</button>"},h="",hint="";
    var who=(r.label?r.label+", ":"")+"run "+r.id;
    if(n&&n.kind==="ask"){var sk=Object.keys(n.show||{}).slice(0,5);
      if(sk.length)h='<div class="oask">'+sk.map(function(k){return'<span class="oask-r"><span class="oask-k">'+esc(k)+"</span> "+esc(String(n.show[k]).slice(0,160))+"</span>"}).join("")+"</div>";
      h+=b(n.yes?"Copy “yes”: "+n.yes:"Copy “yes”",n.lines[0][0],1)+b(n.no?"Copy “no”: "+n.no:"Copy “no”",n.lines[1][0]);hint="Paste it into the Claude chat and send it: the run carries on from the step that waits."}
    else if(n&&n.kind==="stop"){h=b("Copy rerun",n.lines[0][0],1)+b("Copy for Claude",n.lines[1][0]);hint="If a rerun fails too, paste the second one."}
    else if(!running){if(r.wf&&!o.test&&!r.try)h=b("Run again","rerun workflow "+r.wf);h+=b("Ask Claude","Let’s talk about "+who+": ")}
    /* o.details is drawn by flowBox as its own footer row, the same under every outcome */
    if(o.test||(r&&r.try))hint=(hint?hint+" ":"")+(r&&r.sample?"A test run on a sample: nothing was saved or sent.":r&&r.try&&r.try_real?"A try for real: every step ran on your real data, saves and sends included.":r&&r.try?"A test run on your real data: nothing was saved or sent.":"A test on recorded data: nothing real was read or sent.");
    if(!h&&!hint)return"";
    return'<div class="oacts">'+h+"</div>"+(hint?'<span class="ohint">'+esc(hint)+"</span>":"")}
  /* The outcome as a short timeline: what was done (one or two sentences), then only the steps that mattered, in order
     (failed, waited on you, raised a doubt, made something, changed something outside, handed on), the quiet steps
     between them as a count, and a one-line tally. Simple: one line each. Detail: the facts and each step's own line.
     The status shows three ways at once: a dot by the title, a dot before the summary, and the box's left edge.
     m = {summary, facts:[html], nodes:[{k:"quiet",n,from,to} | {k:"error|ask|issue|stop|made|changed|next",t,d,href,lab,acts}],
          st:"ok|need|fail|run", pill, plan: a path, not a run}
     o = {kind, detail, toggle: draw Simple / Detail, took, bare, sub, acts: buttons when no node holds them} */
  /* section icons: one thin black line icon before each section's title (outcome, decisions, steps, run details) */
  var SVG=function(p){return'<svg class="secic" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+p+"</svg>"};
  var SECI={out:SVG('<path d="M5 21V4"/><path d="M5 4h11l-2 4 2 4H5"/>'),dec:SVG('<circle cx="6" cy="6" r="2"/><circle cx="18" cy="6" r="2"/><circle cx="12" cy="19" r="2"/><path d="M6 8v2a3 3 0 0 0 3 3h6a3 3 0 0 0 3-3V8"/><path d="M12 13v4"/>'),
    steps:SVG('<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1"/><circle cx="4.5" cy="12" r="1"/><circle cx="4.5" cy="18" r="1"/>'),info:SVG('<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8v.5"/>')};
  /* an item's kind, for the small icon by each item and the source row: from a noun or a connection ("property email", "Outlook") */
  var KIC={email:'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',message:'<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    task:'<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 12l3 3 5-6"/>',page:'<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/>',file:'<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',item:'<circle cx="12" cy="12" r="8"/>'};
  function kindOf(t){t=String(t||"").toLowerCase();return/mail|outlook|gmail|inbox/.test(t)?"email":/message|slack|dm|\bx\b|tweet|chat/.test(t)?"message":/task|ticket|salesforce|issue|todo/.test(t)?"task":/article|story|page|news|post|listing|web/.test(t)?"page":/file|document|sheet/.test(t)?"file":"item"}
  var KW={email:"Email",message:"Message",task:"Task",page:"Page",file:"File",item:"Item"};
  function kindIcon(k,lab){return'<svg class="kic" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" role="img" aria-label="'+esc(lab||KW[k]||"Item")+'">'+(KIC[k]||KIC.item)+"</svg>"}
  var NK={error:["✕","Failed","Can fail"],ask:["!","Needs you","Will ask you"],issue:["?","Worth a look","May flag"],stop:["■","Stopped","Stops here"],
    made:["▤","Made","Will make"],changed:["✎","Changed","Will change"],next:["→","Handed on","Hands on"]};
  /* a made thing's preview (RUN-TRACE.md, "made"): a picture the board serves (shots/…), or a little card of text
     (an email's to, subject and first line; a page's title and first line). Nothing else is drawn */
  function pvHtml(p){if(!p)return"";
    if(typeof p==="string")return safeHref(p)&&/\.(png|jpe?g|gif|webp)$/i.test(p)?'<span class="opv"><img src="'+esc(p)+'" alt="" loading="lazy"></span>':"";
    var L=[p.to?"To: "+p.to:"",p.title||p.subject||"",p.line||""].filter(Boolean);
    return L.length?'<span class="opv opvt" aria-hidden="true">'+L.map(function(x,i){return"<span"+(i===(p.to?1:0)?' class="opvh"':"")+">"+esc(String(x).slice(0,80))+"</span>"}).join("")+"</span>":""}
  function flowBody(m,o){o=o||{};var d=!!o.detail,P=!!m.plan,h="",ns=m.nodes||[];
    if(m.summary)h+='<p class="osum">'+m.summary+"</p>";
    if(d&&m.facts&&m.facts.length)h+='<ul class="ofl ofacts">'+m.facts.map(function(x){return"<li>"+x+"</li>"}).join("")+"</ul>";
    var tl="";
    ns.forEach(function(n){
      if(n.k==="quiet"){tl+='<div class="efn quiet"><span class="efd">✓</span><div><small>'+n.n+" step"+(n.n>1?"s":"")+(d?(P?" with nothing to note":" ran with nothing to note")+(n.n>1&&n.from?" · "+esc(n.from)+" → "+esc(n.to):n.from?" · "+esc(n.from):""):P?"":" fine")+"</small></div></div>";return}
      var k=NK[n.k]||NK.made,dd=String(n.d||"").replace(/<[^>]+>/g,""),pv=pvHtml(n.pv);
      tl+='<div class="efn '+n.k+(pv?" haspv":"")+'"><span class="efd">'+k[0]+"</span>"+(pv?'<div class="efm">'+pv:"")+"<div>"+(d?'<span class="efk">'+(n.kw||(P?k[2]:k[1]))+"</span>":"")+"<b>"+esc(n.t)+"</b>"+(dd?"<small>"+esc(dd)+"</small>":"")+(n.acts?'<div class="efa">'+n.acts+"</div>":"")+"</div>"+(pv?"</div>":"")+
        (n.href?'<button class="olk" type="button" data-copy-path="'+esc(n.href)+'" data-copy-msg="Link copied" title="'+esc(n.href)+'">Copy link</button>':n.copy?'<button class="olk" type="button" data-copy-path="'+esc(n.copy)+'" title="'+esc(n.copy)+'">'+esc(n.lab||"Copy path")+"</button>":"")+"</div>"});
    var c=function(k){return ns.filter(function(n){return n.k===k&&!n.lp&&!n.held}).length},hb=ns.filter(function(n){return n.held}).length /* a loop item that stopped never stops the run: its own line says so, the end line doesn't count it */,parts=[],q=ns.filter(function(n){return n.k==="quiet"}).reduce(function(a,n){return a+n.n},0);
    if(c("error"))parts.push('<b class="t-fail">'+c("error")+(P?" can fail":" failed")+"</b>");if(c("stop"))parts.push('<b class="t-need">'+(P?"stops":"stopped")+"</b>");
    if(c("ask"))parts.push('<b class="t-need">'+c("ask")+(P?" to answer":" needs you")+"</b>");if(c("issue"))parts.push('<b class="t-need">'+c("issue")+" to check</b>");
    if(c("made"))parts.push(c("made")+" made");if(c("changed"))parts.push(c("changed")+" changed");if(c("next"))parts.push(c("next")+" handed on");if(hb)parts.push(hb+" not sent"); /* a try's sends: shown, never counted as made */
    if(d&&q&&parts.length)parts.push(q+(P?" quiet":" ran fine"));
    var NS=ns.notSent;if(NS)parts.push("Not sent: you didn’t say yes");
    if((ns.length||!P)&&m.st!=="run")tl+='<div class="efn end"><span class="efd">'+(parts.length?"■":"✓")+"</span><div>"+(d?'<span class="efk">'+(P?"At the end":"End")+"</span>":"")+'<span class="tally">'+(parts.length?parts.join(" · "):P?"Makes and changes nothing, and asks nothing":"Nothing made or sent")+"</span></div>"+
      (NS&&NS.msg?'<button class="olk" type="button" data-occopy="'+esc(NS.msg)+'" title="'+esc(NS.msg)+'">Copy message</button>':"")+"</div>";
    return h+(tl?'<div class="ef'+(d?"":" sm")+'">'+tl+"</div>":"")+(o.acts||"")}
  var BANDI={ok:'<path d="M20 6L9 17l-5-5"/>',need:'<path d="M12 7v6M12 17v.5"/>',fail:'<path d="M6 6l12 12M18 6L6 18"/>',run:'<circle cx="12" cy="12" r="3"/>'};
  /* Warnings: where the run reviewer (core-run-reviewer) found the run went off its path. A tab of the outcome box, next
     to Outcome, on the run's own page; the run's status is never changed by them. Each: a title, one line, a fix, and
     a Fix / Dismiss choice; one Copy for Claude copies every choice as lines for the chat (o.warnings: the run's open
     warnings; o.wtab: the tab shown) */
  var INFOI='<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9.5"/><path d="M12 11v6M12 7.5h.01"/></svg>';
  /* info (the reviewer's "Nothing to change.") gets a light-blue (i); warn the amber triangle */
  function owIsInfo(s){return s.severity==="info"}
  var WARNI='<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/></svg>';
  /* each warning: a Fix / Dismiss choice (warn starts on Fix, info on Dismiss; a second click clears it), then one
     Copy for every choice made: a "fix warning …" line per fix and one "dismiss warning …" line. WCH keeps the
     choices across redraws; a click changes them in place (owSync), never redrawing the page */
  var WCH={};
  function owPick(s){var c=WCH[s.id];return c===undefined?(s.severity==="info"?"dis":"fix"):c}
  function owText(ws){var f=[],d=[];ws.forEach(function(s){var c=owPick(s);if(c==="fix")f.push("fix warning "+s.id+": "+s.title);else if(c==="dis")d.push(s.id)});
    if(d.length)f.push("dismiss warning "+d.join(" "));return{text:f.join("\n"),fix:f.length-(d.length?1:0),dis:d.length}}
  function owLabel(t){var p=[];if(t.fix)p.push(t.fix+" to fix");if(t.dis)p.push(t.dis+" to dismiss");return p.length?p.join(" · "):"Nothing chosen"}
  function warnBody(ws){if(!ws.length)return'<p class="owempty">No warnings: this run followed its path.</p>';
    var t=owText(ws),ids=ws.map(function(s){return s.id}).join(" ");
    return ws.map(function(s){var c=owPick(s);return'<div class="owarn'+(owIsInfo(s)?" owinfo":"")+'"><span class="owi">'+(owIsInfo(s)?INFOI:WARNI)+'</span><div class="owtx"><b>'+esc(s.title)+"</b>"+
      '<p>'+esc(s.detail||s.what||s.why||"")+"</p>"+(s.fix?'<p class="owfix"><b>Fix:</b> '+esc(s.fix)+"</p>":"")+"</div>"+
      '<span class="c-seg owseg" role="group" aria-label="What to do with this warning"><button type="button" class="owc'+(c==="fix"?" on":"")+'" data-owch="fix" data-owid="'+esc(s.id)+'" aria-pressed="'+(c==="fix")+'">Fix</button><button type="button" class="owc'+(c==="dis"?" on":"")+'" data-owch="dis" data-owid="'+esc(s.id)+'" aria-pressed="'+(c==="dis")+'">Dismiss</button></span></div>'}).join("")+
      '<div class="owall" data-owids="'+esc(ids)+'"><span class="owsum">'+esc(owLabel(t))+'</span><div class="owacts"><button class="obtn" type="button" data-copy="'+esc(t.text)+'" data-ck="owcopy"'+(t.text?"":" disabled")+'>Copy for Claude</button></div></div>'}
  /* a Fix / Dismiss click: update the choice, its buttons and the Copy line in place */
  document.addEventListener("click",function(ev){var b=ev.target.closest&&ev.target.closest("[data-owch]");if(!b)return;
    ev.stopPropagation();ev.preventDefault();var id=b.dataset.owid,ch=b.dataset.owch,seg=b.parentNode,box=b.closest(".owbody");
    var was=seg.querySelector(".owc.on");WCH[id]=was&&was.dataset.owch===ch?null:ch;
    [].forEach.call(seg.querySelectorAll(".owc"),function(x){var on=x.dataset.owch===WCH[id];x.classList.toggle("on",on);x.setAttribute("aria-pressed",on)});
    if(!box)return;var all=box.querySelector(".owall");if(!all)return;
    var ws=[].map.call(box.querySelectorAll(".owarn"),function(w){var on=w.querySelector(".owc.on"),t=w.querySelector(".owtx b");return{id:w.querySelector(".owc").dataset.owid,title:t?t.textContent:"",severity:"",_c:on?on.dataset.owch:null}});
    ws.forEach(function(s){WCH[s.id]=s._c});var t=owText(ws),cp=all.querySelector("[data-copy]");
    all.querySelector(".owsum").textContent=owLabel(t);cp.setAttribute("data-copy",t.text);cp.disabled=!t.text},true);
  function flowBox(m,o){o=o||{};var K=o.kind||"Workflow";
    /* open warnings sit in the status band, next to its status: [✓ Done] [⚠ 1 warning]. The two switch the box between
       the outcome and the warnings (o.wtab; on the Inbox o.wkey names the row); with o.wlink the warnings are a link */
    var ws=o.warnings&&o.warnings.length?o.warnings:null,wt=!!ws&&!o.wlink&&o.wtab==="warnings";
    var seg=o.toggle&&!wt?'<span class="c-seg" role="group" aria-label="How much to show"><button type="button"'+(o.detail?' data-odet="0"':"")+' aria-pressed="'+!o.detail+'">Simple</button><button type="button"'+(o.detail?"":' data-odet="1"')+' aria-pressed="'+!!o.detail+'">Detail</button></span>':"";
    var head=o.bare?"":'<div class="pbh">'+SECI.out+"<b>"+esc(K)+" outcome</b>"+(o.sub?"<span>"+esc(o.sub)+"</span>":"")+(seg?'<span class="pbt">'+seg+"</span>":"")+"</div>";
    var stIn='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+(BANDI[m.st]||BANDI.ok)+"</svg>"+esc(m.stl||"")+(o.took?" · "+esc(String(o.took).replace(/^Took/,"took").replace(/^took/,o.plan?"takes":"Took")):"");
    var wk=o.wkey?' data-owkey="'+esc(o.wkey)+'"':""; /* the Inbox: which row's box the switch belongs to */
    var nI=ws?ws.filter(owIsInfo).length:0,nW=ws?ws.length-nI:0,oc=ws&&!nW?" owinfo":"";
    var wIn=ws?'<span class="owti">'+(nW?WARNI:INFOI)+"</span>"+[nW?nW+" warning"+(nW>1?"s":""):"",nI?nI+" info":""].filter(Boolean).join(" · "):"";
    var band=!ws?'<div class="oband '+m.st+'">'+stIn+"</div>"
      :'<div class="oband '+m.st+' owband">'+(o.wlink?'<span class="obst">'+stIn+'</span><a class="obw'+oc+'" href="'+esc(o.wlink)+'" title="Where this run went off its path">'+wIn+"</a>"
        :'<button type="button" class="obst" data-owtab="outcome"'+wk+' aria-pressed="'+!wt+'">'+stIn+'</button><button type="button" class="obw'+oc+'" data-owtab="warnings"'+wk+' aria-pressed="'+wt+'" title="Where this run went off its path">'+wIn+"</button>")+"</div>";
    /* the Inbox (o.boxed): just the outcome card the Builder shows inside its box (band, summary, steps), with no
       title or outer box, then the way to the full run as its own button, with the Builder's icon */
    var BLD='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="19" r="2"/><path d="M12 7v4M12 11l-6 6M12 11l6 6"/></svg>';
    var foot=o.details?'<div class="obld"><a class="obtn" href="'+esc(o.details)+'">'+BLD+"View in Builder ↗</a></div>":"";
    var cls=o.boxed?"ocard ":o.bare?"obare ":"pb outb runout ";
    if(wt)return'<section class="'+cls+'ptx oflow" aria-label="'+esc(K)+' warnings">'+head+'<div class="obody ores '+m.st+'">'+band+'<div class="owbody">'+warnBody(ws)+"</div></div></section>"+foot;
    return'<section class="'+cls+'ptx oflow" aria-label="'+esc(K)+' outcome">'+head+'<div class="obody ores '+m.st+'">'+band+flowBody(m,o)+"</div></section>"+foot}
  /* a run's steps as timeline nodes: what each one did, by its status and its trace type (RUN-TRACE.md) */
  var CHG=/(Sent|Posted|Reply|Replied|Updated|Deleted|Published|Paid)$/,MADE=/^(Email Draft Created|File Changed|Design Drafted|Reported|Report|Saved|Created)$|Created$|Drafted$/;
  function safeHref(h){h=String(h||"");return/^https:\/\//.test(h)||/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?\//.test(h)||/^(shots|pages)\/[A-Za-z0-9._\/-]+$/.test(h)&&h.indexOf("..")<0}
  /* a link's button says where it goes, never what kind of item it was once assumed to be (a Slack DM is no draft) */
  function hrefLabel(h){h=String(h||"");var m=[[/notion\.(so|com)/,"Open in Notion ↗"],[/slack\.com/,"Open in Slack ↗"],[/mail\.google\.com/,"Open in Gmail ↗"],
    [/outlook\.(office|live)\.com|outlook\.com/,"Open in Outlook ↗"],[/(^|\/\/)(www\.)?(x|twitter)\.com/,"Open on X ↗"],[/docs\.google\.com/,"Open in Google ↗"]];
    for(var i=0;i<m.length;i++)if(m[i][0].test(h))return m[i][1];return"Open ↗"}
  /* a step from before RUN-TRACE's "made": the link or path it logged in its data (io.out), under a usual name */
  function loggedLink(z){var o=(z&&z.io&&z.io.out)||{},ks=["link","url","href","page","file","path"];for(var i=0;i<ks.length;i++){var v=o[ks[i]];if(typeof v==="string"&&(safeHref(v)||localPath(v)))return v}return""}
  /* a file on this computer (RUN-TRACE "made": its path): the board can't open it, so its button copies the path */
  function localPath(h){h=String(h||"");return!/^[a-z]+:/i.test(h)&&/^(\/|~\/|\.{0,2}\/|[A-Za-z0-9._-]+\/)/.test(h)&&!safeHref(h)}
  function runNodes(r,e,waits,probs,o){o=o||{};var steps=(r&&r.steps)||[],ns=[],nm=function(z){return String(z.title||z.step||"A step").replace(/[?:]+$/,"")},cut=function(t){t=String(t||"");return t.length>140?t.slice(0,137)+"…":t};
    var held="",notSent=false;
    var quiet=function(z){var l=ns[ns.length-1];if(l&&l.k==="quiet"){l.n++;l.to=nm(z)}else ns.push({k:"quiet",n:1,from:nm(z),to:nm(z)})};
    steps.forEach(function(z){if(z.hand)return;var ty=z.type==="Mocked"||z.type==="Fake Read"?(z.as||""):(z.type||""),would=z.type==="Mocked"||!!(r&&(r.try||r.test))&&!(z.made&&z.made.href)&&/^would\b/i.test(String(z.result||"")); /* a try's held-back send: it says what it would have done and made nothing */
      if(z.status==="failed")ns.push({k:"error",t:nm(z),d:z.result||z.why||""});
      else if(z.status==="needs_user")ns.push({k:"ask",t:nm(z),d:e.waiting&&typeof e.waiting==="string"?e.waiting:z.result||""});
      else if(z.status==="uncertain")ns.push({k:"issue",t:nm(z),d:z.result||""});
      else if(z.status==="skipped"||z.status==="")return;
      else if(/^(message|reply) (drafted|written)$/i.test(ty)&&!(z.made&&z.made.name)){held=z.result||held;quiet(z)} /* only in the run until it is sent: not made */
      else if(ty==="Asked You"&&z.status==="done"&&/no yes|sent nothing|not sent|said no|didn.t say yes/i.test(String(z.result||""))){notSent=true;quiet(z)}
      else if(CHG.test(ty)||MADE.test(ty)||z.made&&z.made.name){var ch=CHG.test(ty)&&!MADE.test(ty),n={k:ch?"changed":"made",t:nm(z),d:z.result||"",kw:would?(ch?"Would change":"Would make"):"",held:would,key:z.wstep||""};
        if(z.made&&z.made.name){var mk=z.made;n.t=String(mk.name);n.d=[mk.kind,"from "+(o.stepNo&&z.wstep&&o.stepNo(z.wstep)?"Step "+o.stepNo(z.wstep)+": ":"")+nm(z)].filter(Boolean).join(" · ");
          n.pv=mk.preview||"";if(safeHref(mk.href)){n.href=mk.href;n.lab=hrefLabel(mk.href)}else if(localPath(mk.href)){n.copy=String(mk.href);n.lab="Copy path"}}
        else{var lk=loggedLink(z);if(safeHref(lk)){n.href=lk;n.lab=hrefLabel(lk)}else if(localPath(lk)){n.copy=lk;n.lab="Copy path"}}  /* runs from before "made": the link it logged in its data */
        ns.push(n)}
      else if(ty==="Handed Off"&&z.skill&&steps.indexOf(z)>0)ns.push({k:"next",t:nm(z),d:z.result||""});
      else quiet(z)});
    ns.forEach(function(n){n.d=cut(n.d)});
    if(!steps.some(function(z){return z.status==="failed"}))probs.forEach(function(p){ns.push({k:"error",t:p.what,d:p.why||p.fix||""})});
    if(notSent)ns.notSent={msg:held}; /* the last line says it wasn't sent, with the message to copy */
    return ns}
  /* a Copy in the outcome box: on both pages, without each page wiring it */
  if(typeof document!=="undefined")document.addEventListener("click",function(ev){var b=ev.target&&ev.target.closest&&ev.target.closest("[data-occopy]");if(!b)return;ev.preventDefault();ev.stopPropagation();
    window.TopBar.copy(b.getAttribute("data-occopy"),b)},true); /* the one toast and button pulse (topbar.js) */
  return{dur:dur,took:took,runStatus:runStatus,outcome:outcome,flowBox:flowBox,SECI:SECI,kindOf:kindOf,kindIcon:kindIcon,KW:KW,inspector:inspector,esc:esc,card:card,foot:foot,layout:layout,calm:calm,tipHtml:tipHtml,allOpen:allOpen,click:click,loadDetail:loadDetail,loadOutDetail:loadOutDetail,saveDetail:saveDetail,switchHtml:switchHtml}
})();
/* "Copy path" on something a run made on this computer (RUN-TRACE "made" with a file path) */
document.addEventListener("click",function(ev){var b=ev.target.closest&&ev.target.closest("[data-copy-path]");if(!b)return;ev.preventDefault();ev.stopPropagation();
  var t=b.getAttribute("data-copy-path");if(window.TopBar&&TopBar.copy)TopBar.copy(t,b,b.getAttribute("data-copy-msg")||"Path copied");else try{navigator.clipboard.writeText(t)}catch(e){}},true);
