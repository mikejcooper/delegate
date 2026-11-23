/* Which workflow a run belongs to, which decisions it took, and which path that is.
   One copy, loaded by workflow-viewer.html and workflows.html, so both pages always name the same path.
   W = workflows-data.js (window.WFDEF), runs = board-data.js runs (window.BOARD.runs). */
(function(g){
function stepsOf(r){return r.steps||[]}
function forks(r){return stepsOf(r).filter(function(s){return/^forked\s*→/.test(s.step||"")})}
/* a trigger request that ended without running any item (nothing kept, or every item already handled): still a run of
   its workflow, shown as its own row on the Inbox and in the Builder's Past runs. Not a change made by hand. */
function checkOnly(r){return!!r&&r.kind==="trigger"&&(r.state==="done"||r.state==="stalled")&&!forks(r).length&&!stepsOf(r).some(function(s){return s.type==="Pulled In"})&&(r.matches||[]).some(function(m){return m.entry})&&!stepsOf(r).some(function(s){return s.hand})&&!/^\s*(skip|mark|delete|turn|answer)\b/i.test(String(r.request||""))}
/* What a request step that names an item (link_wf) says about it, decided here once for every page:
   "pulled" (pulled in, not run), "seen" (a trigger found it again: Already Done), or null for a change made by
   hand (skip, mark, delete, the switch): those set the item's status through the done list and must never count
   as the item being found again. Hand steps say "hand": true; older traces are known by their type or words. */
var HAND=/^(skipped|marked\b|deleted|delete\b|setting|switch|unskipped|restored)/i;
function isHand(s){return!!(s&&(s.hand||HAND.test(s.type||"")||HAND.test(s.step||"")))}
function linkOf(s){if(!s||!s.link_wf||isHand(s))return null;return s.type==="Pulled In"?"pulled":"seen"}
function seenSteps(r){return stepsOf(r).filter(function(s){return linkOf(s)==="seen"})}
function pulledSteps(r){return stepsOf(r).filter(function(s){return s.type==="Pulled In"})}
/* which option a decision step took, from its own words: the option whose words all appear in the step (most words wins);
   with no option named, a two-way decision reads its status (done = the first option), and so does a check whose
   other options all stop the run. */
function words(x){return String(x||"").toLowerCase().replace(/[’]/g,"'").split(/[^a-z0-9&'≥%]+/).filter(Boolean).map(function(w){return w.length>3&&/s$/.test(w)&&!/ss$/.test(w)?w.slice(0,-1):w})} /* "alerts" counts as "alert" */
function altOf(alts,s){var have=words([s.title,s.step,s.result].join(" ")),best=-1,bn=0;
  /* a result that opens with an option's own words ("Neither: …", "Breaking change - …") is that option, whatever the
     step's title says: "Flag breaking and security changes" put "breaking" in every line and matched the wrong one */
  var r0=String(s.result||"").toLowerCase().trim(),lead=-1,ll=0;
  alts.forEach(function(a,i){var ph=String(a.when||"").toLowerCase().trim();if(ph&&r0.indexOf(ph)===0&&!/[a-z0-9]/.test(r0.charAt(ph.length))&&ph.length>ll){lead=i;ll=ph.length}});
  if(lead>=0)return[lead];
  /* every word of the option must appear; more words win; on a tie, the option whose whole phrase is written in the result (then anywhere) wins */
  var res=String(s.result||"").toLowerCase(),all=[s.title,s.step,s.result].join(" ").toLowerCase();
  alts.forEach(function(a,i){var w=words(a.when);if(!w.length||!w.every(function(x){return have.indexOf(x)>=0}))return;
    var ph=String(a.when).toLowerCase(),sc=w.length*10+(res.indexOf(ph)>=0?5:all.indexOf(ph)>=0?2:0);if(sc>bn){best=i;bn=sc}});
  if(best>=0)return[best];if(alts.length===2)return[s.status==="done"?0:1];
  if(s.status==="done"&&alts.slice(1).every(function(a){return a.ends||a.k==="stop"}))return[0]; /* a check whose other options all stop the run: done = it passed */
  return null}
/* does a trace step match a definition step's "from"? One test for both pages: the Inbox maps its rows with it too */
function matches(f,s){var t=f.type_any||[],w=f.step_any||[];
  return(!t.length||t.indexOf(s.type)>=0||(s.as&&t.indexOf(s.as)>=0))&&(!w.length||w.some(function(x){x=String(x).toLowerCase();return(s.step||"").toLowerCase().indexOf(x)>=0||(s.result||"").toLowerCase().indexOf(x)>=0}))}
/* which workflow step each of a run's trace steps is: {trace index: definition step}. Each trace step is used once,
   in the definition's order; a code step matches by its "key". Both pages use it (the Inbox's rows, the Viewer's ticks). */
function mapSteps(def,r){var m={},used={},ss=stepsOf(r);if(!def)return m;
  /* 1. the line stamped with the step's key ("wstep": run_item.py writes it when the line's name is the step's title) */
  def.steps.forEach(function(st){for(var i=0;i<ss.length;i++){if(!used[i]&&ss[i].wstep&&ss[i].wstep===st.key){used[i]=1;m[i]=st;break}}});
  /* 2. older, unstamped lines: a code step by its "key", else the step's "from" finder, else the same title */
  def.steps.forEach(function(st){if(Object.keys(m).some(function(j){return m[j]===st}))return;var f=st.from;
    for(var i=0;i<ss.length;i++){if(used[i]||ss[i].wstep)continue;
      var hit=f&&typeof f==="object"&&(f.key?ss[i].key===f.key:matches(f,ss[i]))||sameTitle(st,ss[i]);
      if(hit){used[i]=1;m[i]=st;break}}});
  return m}
/* the line's name is the step's title, word for word (case and spacing aside), as run_item.py stamps it */
function normT(x){return String(x||"").replace(/If:/g,"").toLowerCase().split(/\s+/).filter(Boolean).join(" ").replace(/[.?:! ]+$/,"")}
function sameTitle(st,s){var t=normT(st.title);return!!t&&(t===normT(s.title)||t===normT(s.step))}
/* the trace line for one definition step: its stamp first, else its finder, else its title */
function lineOf(r,st){var ss=stepsOf(r);return ss.filter(function(s){return s.wstep&&s.wstep===st.key})[0]
  ||(st.from&&typeof st.from==="object"&&!st.from.key?ss.filter(function(s){return!s.wstep&&matches(st.from,s)})[0]:null)
  ||ss.filter(function(s){return!s.wstep&&sameTitle(st,s)})[0]||null}
function findStep(r,f){return stepsOf(r).filter(function(s){return matches(f,s)})[0]}
function resolve(step,r,runs){ /* -> {res, taken} for one definition step on one real run; from:"branch" + taken_by: see README.md */
  var f=step.from,e=r.end||{};if(!f){var ls=lineOf(r,step);if(!ls)return{};var lo={res:ls.result||ls.step};if(step.alts){var la=altOf(step.alts,ls);if(la)lo.taken=la}return lo}
  if(typeof f==="object"&&f.key){ /* a code step: its trace line carries the function's name as "key" */
    var ks=stepsOf(r).filter(function(x){return x.key===f.key})[0]||lineOf(r,step);if(!ks)return{};var ko={res:ks.result||ks.step};
    if(step.alts){var ki=step.alts.map(function(a){return a.when}).indexOf(String(ks.result));if(ki>=0)ko.taken=[ki];else{var ka=altOf(step.alts,ks);if(ka)ko.taken=ka}}return ko}
  if(step.taken_by&&typeof step.taken_by==="object"){var hb=findStep(r,step.taken_by);if(!hb&&!e.end)return{};return{res:hb?step.taken_by.yes:step.taken_by.no,taken:[hb?0:1]}} /* branch 0 when that step exists, else branch 1 */
  if(typeof f==="object"){var s=lineOf(r,step);if(!s)return{};var o={res:s.result||s.step};
    if(step.key==="d2"||step.key==="n2")o.taken=[0];
    if(step.key==="d3")o.taken=[].concat(forks(r).length||seenSteps(r).length||pulledSteps(r).length?[0]:[],stepsOf(r).some(function(x){return x.status==="skipped"&&!x.link_wf&&!isHand(x)})?[1]:[]);
    if((!o.taken||!o.taken.length)&&step.alts){var at=altOf(step.alts,s);if(at)o.taken=at}
    return o}
  if(f==="seen"){ /* each option lists the steps that show it ran ("seen": [finder, ...]); the option with the most, all found, wins; [] is the default once the run has ended */
    var al=step.alts||[],best=-1,bn=-1;al.forEach(function(a,i){var need=a.seen||[];if(need.every(function(x){return findStep(r,x)})&&need.length>bn&&(need.length||e.end)){best=i;bn=need.length}});
    return best<0?{}:{res:al[best].then||al[best].when,taken:[best]}}
  if(f==="verdict"){var o2={res:e.verdict||""};if(step.taken_by==="attention"&&e.end)o2.taken=[e.attention==="action"?0:e.attention==="review"?2:1];return o2}
  if(f==="entry")return{res:r.entry?"Matched the "+r.entry+" trigger":"No trigger matched",taken:[(function(){var al=step.alts||[],i=al.map(function(a){return a.entry}).indexOf(r.entry);return i<0?al.length-1:i})()]};
  var n=forks(r).length+pulledSteps(r).length,a=seenSteps(r).length;
  if(f==="ids"){if(!n&&!a)return{};return{res:n&&a?n+" new, "+a+" done before":n?"All "+n+" new":"All "+a+" already done: linked to the earlier run",taken:[].concat(n?[0]:[],a?[1]:[])}}
  if(f==="dispatched"){var ks2=(runs||[]).filter(function(x){return x.group===r.group&&x.kind==="run"}).map(function(k){return k.label});var pu=pulledSteps(r).length,fk=forks(r).length;if(pu&&!fk)return{res:"Pulled in "+pu+", not run yet",taken:[0]};return{res:fk?"Sent "+fk+(ks2.length?": "+ks2.join(", "):""):"Nothing sent",taken:fk?[1]:undefined}}
  return{};
}
/* every skill a run used, old names resolved to today's (workflows.json "alias_of"), so runs from before a rename still match */
function runSkills(run,S){S=S||{};var out=[];[{skill:run.via}].concat(run.steps||[]).forEach(function(x){var k=x.skill;if(!k)return;k=(S[k]&&S[k].alias_of)||k;if(out.indexOf(k)<0)out.push(k)});return out}
function classify(r,W){ /* -> the workflow definition a run belongs to, or null */
  if(!W||!r)return null;
  if(r.flow){var fl=W.workflows.filter(function(w){return w.id===r.flow})[0];if(fl)return fl} /* a trace that names its workflow wins */
  var wfs=W.workflows,lab=(r.label||"").toLowerCase(),sks=runSkills(r,W.skills);
  var by=function(test){return wfs.filter(function(w){return w.match&&test(w.match)})[0]};
  return by(function(m){return m.label_all&&m.label_all.every(function(k){return lab.indexOf(k.toLowerCase())>=0})})
    ||by(function(m){return m.label_any&&m.label_any.some(function(k){return lab.indexOf(k.toLowerCase())>=0})&&(!m.skill||sks.indexOf(m.skill)>=0)})
    ||by(function(m){return m.default&&sks.indexOf(m.skill)>=0})||null;
}
function decisions(r,steps,runs){ /* -> {res:{key:text}, taken:{key:[branch]}} */
  var res={},taken={};(steps||[]).forEach(function(s){var o=resolve(s,r,runs);if(o.res)res[s.key]=o.res;if(o.taken&&o.taken.length)taken[s.key]=o.taken});
  return{res:res,taken:taken}}
/* which path a run took: the first path whose decisions all equal the run's; failing that, the first whose every decision
   shares a branch with the run's (a run that sorted both alerts and other emails took the "new security alerts" path) */
function pathOf(taken,paths){taken=taken||{};paths=paths||[];
  var keys=function(p){return Object.keys(p.taken||{})};
  var exact=function(p){var k=keys(p);return k.length&&k.every(function(d){return taken[d]&&String(taken[d])===String(p.taken[d])})};
  var within=function(p){var k=keys(p);return k.length&&k.every(function(d){return taken[d]&&p.taken[d].some(function(b){return taken[d].indexOf(b)>=0})})};
  var hit=paths.filter(exact)[0]||paths.filter(within)[0];return hit?hit.label.replace(/^If: /,""):""}
/* one item run -> {wf, path, hasPaths}; path is "" for a run not finished yet or not one of the paths */
function ofRun(r,W,runs){var def=classify(r,W);if(!def)return{wf:null,path:"",hasPaths:false};
  var paths=def.simulated||[],done=r.state==="done";
  return{wf:def,path:done?pathOf(decisions(r,def.steps,runs).taken,paths):"",hasPaths:paths.length>0,done:done}}
/* one trigger request -> its path, read on that trigger's own view (the Workflow Viewer's "Started by …" view):
   the routing step plus the steps and paths marked with its entry. "" while it runs or with no trigger. */
function ofRequest(r,W,runs){if(!W||!W.dispatcher||!r||!r.entry||r.state!=="done")return"";var D=W.dispatcher,ek=r.entry;
  var steps=D.steps.filter(function(x,i){return i===0||x.entry===ek}),paths=(D.simulated||[]).filter(function(x){return x.entry===ek});
  if(!paths.length)return"";return pathOf(decisions(r,steps,runs).taken,paths)||"Not one of the paths"}
/* a test that missed its path: which decisions of the expected path the run didn't match.
   -> [{title, want, got}] (got "" when no step for that decision was found in the trace); [] when the path isn't known */
function missing(r,W,runs,expect){var def=classify(r,W);if(!def)return[];var nrm=function(x){return String(x||"").replace(/^If:\s*/,"").trim().toLowerCase()};
  var p=(def.simulated||[]).filter(function(x){return nrm(x.label)===nrm(expect)})[0];if(!p)return[];
  var d=decisions(r,def.steps,runs).taken,out=[];
  Object.keys(p.taken||{}).forEach(function(k){var want=p.taken[k],got=d[k]||[];if(got.length&&want.some(function(b){return got.indexOf(b)>=0}))return;
    var st=def.steps.filter(function(s){return s.key===k})[0]||{},al=st.alts||[],nm=function(ix){return ix.map(function(i){return(al[i]||{}).when||("option "+(i+1))}).join(" or ")};
    out.push({title:st.title||k,want:nm(want),got:got.length?nm(got):""})});
  return out}
/* schedules: a workflow's trigger may run on its own (its entry's `schedule`, from its Definition). nextRun gives the
   next time it is due (a Date, local time) or null when paused or unset; schedText says it in a few words. */
function nextRun(sc,from){if(!sc||sc.paused)return null;var now=from||new Date();
  if(sc.on){var o=String(sc.on).split("-"),h=String((sc.times||[])[0]||"").split(":");if(h.length<2)return null;var at=new Date(+o[0],+o[1]-1,+o[2],+h[0],+h[1]);return at>now?at:null} /* a one-off ("once 2026-11-19 18:07"): due once, then gone */
  var days=sc.days&&sc.days.length?sc.days:[0,1,2,3,4,5,6],slots=[];
  if(sc.every_h){var a=(sc.from||"00:00").split(":"),b=(sc.to||"23:59").split(":"),m=+a[0]*60+ +a[1],e=+b[0]*60+ +b[1];for(;m<=e;m+=sc.every_h*60)slots.push(m)}
  else (sc.times||[]).forEach(function(t){var p=t.split(":");slots.push(+p[0]*60+ +p[1])});
  if(!slots.length)return null;slots.sort(function(x,y){return x-y});
  for(var d=0;d<8;d++){var day=new Date(now.getFullYear(),now.getMonth(),now.getDate()+d),wd=(day.getDay()+6)%7;if(days.indexOf(wd)<0)continue;
    for(var i=0;i<slots.length;i++){var t=new Date(day.getTime()+slots[i]*60000);if(t>now)return t}}
  return null}
function whenNext(t,from){if(!t)return"";var now=from||new Date(),d0=new Date(now.getFullYear(),now.getMonth(),now.getDate()),d=Math.round((new Date(t.getFullYear(),t.getMonth(),t.getDate())-d0)/864e5),
  hm=("0"+t.getHours()).slice(-2)+":"+("0"+t.getMinutes()).slice(-2);
  return(d===0?"today ":d===1?"tomorrow ":["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][(t.getDay()+6)%7]+" ")+hm}
function schedText(sc){if(!sc)return"";if(sc.on){var d=new Date(sc.on+"T00:00");return"once, "+["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][(d.getDay()+6)%7]+" "+d.getDate()+" "+["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][d.getMonth()]+" "+((sc.times||[])[0]||"")}var t=String(sc.text||"").split(/\s*[·|]\s*/).filter(function(x){return!/^(paused|pull in only|pull in|run them|run)$/i.test(x)}).join(" ");
  return t}
/* run names (RUN-TRACE.md, Run names): a run is named after its item, in the source's own words; the kind of run is a
   tag and the time is shown apart. Older labels carry both inside the name ("Test: …", "… 19 Nov 18:08",
   "…: answered yes"); runName takes them out, so every view shows the same clean name. -> {name, tags:[…]} */
var RN_MON="Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec";
function runName(label){var t=String(label||"").trim(),tags=[],m;
  m=t.match(/^(test|sample|live|try|rerun)\s*:\s*/i);if(m){var k=m[1].toLowerCase();if(k!=="live")tags.push(k.charAt(0).toUpperCase()+k.slice(1));t=t.slice(m[0].length);t=t.charAt(0).toUpperCase()+t.slice(1)}
  m=t.match(/\s*[:·,-]\s*answered\s+(yes|no)\s*$/i);if(m){tags.push("Answered "+m[1].toLowerCase());t=t.slice(0,m.index)}
  t=t.replace(new RegExp("\\s*(?:·\\s*)?(?:\\d{1,2}\\s+(?:"+RN_MON+")[a-z]*\\.?)?\\s*(?:\\d{1,2}:\\d{2})?\\s*(?:UTC|GMT)?\\s*$","i"),"").replace(/\s*[·:,-]\s*$/,"").trim();
  return{name:t||String(label||"").trim(),tags:tags}}
/* a run's name and tags from the run itself: its label, plus Answered / Rerun from its header (a rerun keeps its name) */
function runNameOf(r){var rn=runName(r&&r.label);if(r&&r.rerun_of&&!rn.tags.some(function(t){return/^Answered|^Rerun/.test(t)})){
    var a=(r.steps||[])[0];rn.tags.push(a&&a.type==="Asked You"?"Answered":"Rerun")}
  return rn}
/* a verdict or summary as HTML: escaped, its one **…** drawn bold (RUN-TRACE.md) */
function richText(s){return String(s||"").replace(/[&<>"']/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]}).replace(/\*\*(.+?)\*\*/g,"<b>$1</b>")}
/* a list's "when": relative, the exact time only on a run's own page */
function relTime(t){if(!t)return"";var s=Math.max(0,Date.now()/1000-t);if(s<60)return"just now";if(s<3600)return Math.floor(s/60)+"m ago";if(s<86400)return Math.floor(s/3600)+"h ago";if(s<172800)return"yesterday";if(s<604800)return Math.floor(s/86400)+" days ago";
  var d=new Date(t*1000);return d.toLocaleDateString([],{day:"numeric",month:"short"})}
/* the chat command that takes requests that ran nothing ("Nothing new" rows) off the board, the same on the Inbox
   and the Builder's Past runs (core-dispatcher, Change items by hand: "delete request dispatch-…") */
function reqDeleteLine(rs){if(!rs.length)return"";if(rs.length===1)return"delete request "+rs[0].id+"  ("+rs[0].name+") from the board";
  return"delete these requests from the board (nothing ran in them):\n"+rs.map(function(r){return"- "+r.id+"  ("+r.name+")"}).join("\n")}
/* a loop workflow's run (core-architect rule 33): the items that stopped or failed in its loops, as outcome lines
   ({k:"stop"|"error", t, d}), so the run's outcome says so without listing every item. Both pages use it. */
function loopNodes(b,W,runs){if(!b||b.kind!=="batch"||!W)return[];var def=classify(b,W);if(!def||!(def.loops||[]).length)return[];
  var nrm=function(x){return String(x||"").replace(/^If:\s*/,"").trim().toLowerCase()},out=[];
  (def.loops||[]).forEach(function(L,li){var nm=function(t){return String(t||"").toLowerCase().replace(/for each/g," ").trim().replace(/\s+/g," ")};
    var its=(runs||[]).filter(function(r){var g=nm(r.loop||def.loops[0].key);return r.kind==="run"&&r.batch===b.id&&(g===nm(L.key)||g===nm(L.title)||g===nm(L.each))});
    var each=L.each||"item",pl=function(n){return n===1?each:/s$/.test(each)?each:/[^aeiou]y$/.test(each)?each.slice(0,-1)+"ies":each+"s"};
    var failed=its.filter(function(r){return stepsOf(r).some(function(z){return z.status==="failed"})});
    var stopped=its.filter(function(r){if(failed.indexOf(r)>=0)return false;var p=nrm((r.end||{}).path),sm=(def.simulated||[]).filter(function(x){return nrm(x.label)===p})[0];return sm&&(sm.out||[])[0]==="stop"});
    var why=function(rs){var w=[];rs.forEach(function(r){var p=String((r.end||{}).path||"").replace(/^If:\s*/,"");if(p&&w.indexOf(p)<0)w.push(p)});return w.join(" · ")};
    if(failed.length)out.push({k:"error",t:failed.length+" "+pl(failed.length)+" failed",d:"in "+(L.title||"the loop")});
    if(stopped.length)out.push({k:"stop",t:stopped.length+" "+pl(stopped.length)+" stopped",d:[why(stopped),"in "+(L.title||"the loop")].filter(Boolean).join(" · ")})});
  return out}
g.RunPath={loopNodes:loopNodes,reqDeleteLine:reqDeleteLine,runName:runName,runNameOf:runNameOf,richText:richText,relTime:relTime,nextRun:nextRun,whenNext:whenNext,schedText:schedText,linkOf:linkOf,isHand:isHand,mapSteps:mapSteps,matches:matches,lineOf:lineOf,sameTitle:sameTitle,missing:missing,stepsOf:stepsOf,forks:forks,checkOnly:checkOnly,seenSteps:seenSteps,pulledSteps:pulledSteps,altOf:altOf,findStep:findStep,resolve:resolve,runSkills:runSkills,classify:classify,decisions:decisions,pathOf:pathOf,ofRun:ofRun,ofRequest:ofRequest};
})(window);
