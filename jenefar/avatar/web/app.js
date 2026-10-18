const hudFrame=document.getElementById("hud-avatar-frame");
function updateEmbeddedHud(state,text){
  try{
    const win=hudFrame?.contentWindow;
    if(win && typeof win.updateAgentState==="function"){
      const normalized=state==="queued"?"thinking":state;
      win.updateAgentState(normalized,text||"");
    }
  }catch(_){}
}
if(hudFrame){
  hudFrame.addEventListener("load",()=>updateEmbeddedHud("idle","Jenefar ready"));
}
const desktopMirror=document.getElementById("desktop-mirror");
const desktopMirrorImage=document.getElementById("desktop-mirror-image");
const desktopMirrorTitle=document.getElementById("desktop-mirror-title");
const desktopMirrorStatus=document.getElementById("desktop-mirror-status");
let desktopMirrorTimer=null;

async function refreshDesktopMirror(){
  try{
    const response=await fetch("/desktop/mirror/status?ts="+Date.now(),{cache:"no-store"});
    if(!response.ok) return;
    const status=await response.json();
    if(!status.active){
      if(desktopMirror) desktopMirror.hidden=true;
      if(desktopMirrorTimer) clearTimeout(desktopMirrorTimer);
      desktopMirrorTimer=setTimeout(refreshDesktopMirror,1500);
      return;
    }
    if(desktopMirror) desktopMirror.hidden=false;
    if(desktopMirrorTitle) desktopMirrorTitle.textContent=(status.title||"LIVE WINDOW").toUpperCase();
    if(desktopMirrorStatus){
      const mode=String(status.capture_mode||"screen_crop").replaceAll("_"," ").toUpperCase();
      desktopMirrorStatus.textContent=status.native_hidden ? "LIVE • NATIVE HIDDEN" : "LIVE • "+mode;
    }
    if(desktopMirrorImage) desktopMirrorImage.src="/desktop/mirror.jpg?ts="+Date.now();
  }catch(_){
  }finally{
    desktopMirrorTimer=setTimeout(refreshDesktopMirror,700);
  }
}
refreshDesktopMirror();

const stage=document.getElementById("stage");
const canvas=document.getElementById("particles");
const ctx=canvas?.getContext("2d")||null;
const stateEl=document.getElementById("state");
const captionEl=document.getElementById("caption");
const dot=document.querySelector(".pulse-dot");
const activityList=document.getElementById("activity-list") || document.getElementById("workspace-log");
const runningCount=document.getElementById("activity-running") || document.getElementById("stat-running");
const queuedCount=document.getElementById("activity-queued") || document.getElementById("stat-queue");
const doneCount=document.getElementById("activity-done") || document.getElementById("stat-done");
const errorCount=document.getElementById("activity-errors") || document.getElementById("stat-error");

const labels={
  idle:["READY","Ready"],
  queued:["QUEUED","Kaam queue me hai"],
  listening:["LISTENING","Main sun rahi hoon"],
  thinking:["WORKING","Kaam kar rahi hoon"],
  result:["DONE","Result ready"],
  speaking:["SPEAKING","Jawaab de rahi hoon"],
  speaking_fallback:["SPEAKING","Browser voice use ho rahi hai"],
  completed:["DONE","Kaam complete"],
  waiting_approval:["APPROVAL","Confirmation chahiye"],
  error:["ERROR","Ek issue aaya hai"]
};

let width=0,height=0,dpr=1;
let particles=[];
let currentState="idle";
let speechLevel=0;
let emotion="neutral";
let emotionIntensity=0;
let lastActivityKey="";
let activityFilter="all";
const taskState=new Map();

function resize(){
  if(!canvas||!ctx) return;
  dpr=Math.min(window.devicePixelRatio||1,2);
  width=window.innerWidth;height=window.innerHeight;
  canvas.width=width*dpr;canvas.height=height*dpr;
  ctx.setTransform(dpr,0,0,dpr,0,0);
  particles=Array.from({length:Math.min(220,Math.floor(width/6))},()=>seedParticle());
}
function seedParticle(){
  const angle=Math.random()*Math.PI*2;
  const radius=Math.random()*Math.min(width,height)*.42+40;
  return{
    a:angle,r:radius,speed:.0015+Math.random()*.0035,
    drift:(Math.random()-.5)*.08,size:.6+Math.random()*2.1,
    phase:Math.random()*Math.PI*2
  };
}
function palette(state){
  if(state==="speaking"||state==="speaking_fallback") return [103,232,255];
  if(state==="thinking"||state==="result") return [167,139,250];
  if(state==="listening") return [109,255,214];
  if(state==="waiting_approval") return [255,187,92];
  if(state==="error") return [255,102,118];
  return [133,147,255];
}

function draw(t){
  if(!ctx){requestAnimationFrame(draw);return;}
  ctx.clearRect(0,0,width,height);
  const workWidth=width*.66;
  const centerX=workWidth/2,centerY=height*.46;
  const [r,g,b]=palette(currentState);
  const activity=currentState==="speaking"||currentState==="speaking_fallback"
    ? speechLevel
    : currentState==="thinking" ? .22
    : currentState==="listening" ? .10 : 0;
  particles.forEach((p,i)=>{
    p.a+=p.speed;p.phase+=.01;
    const stateBoost=(currentState==="speaking"||currentState==="speaking_fallback")
      ? 1.25+activity*1.7 : currentState==="thinking" ? 1.15 : 1;
    const rr=p.r+Math.sin(p.phase+t*.001)*18*stateBoost;
    const x=centerX+Math.cos(p.a)*rr;
    const y=centerY+Math.sin(p.a)*rr*.78;
    const alpha=.13+.16*(Math.sin(p.phase)+1)/2;
    const size=p.size*((currentState==="speaking"||currentState==="speaking_fallback")
      ? 1.05+activity*1.8 : 1);
    ctx.beginPath();
    ctx.arc(x,y,size,0,Math.PI*2);
    ctx.fillStyle=`rgba(${r},${g},${b},${alpha})`;
    ctx.fill();
    if(i%17===0 && currentState!=="idle"){
      ctx.beginPath();
      ctx.moveTo(centerX+Math.cos(p.a)*rr*.8,centerY+Math.sin(p.a)*rr*.62);
      ctx.lineTo(x,y);
      ctx.strokeStyle=`rgba(${r},${g},${b},.035)`;
      ctx.lineWidth=1;
      ctx.stroke();
    }
  });
  requestAnimationFrame(draw);
}

function updateTaskCounts(){
  let running=0,queued=0,done=0,errors=0;
  for(const state of taskState.values()){
    if(state==="queued") queued++;
    else if(state==="thinking"||state==="result"||state==="speaking"||state==="speaking_fallback") running++;
    else if(state==="completed") done++;
    else if(state==="error") errors++;
  }
  if(runningCount) runningCount.textContent=String(running);
  if(queuedCount) queuedCount.textContent=String(queued);
  if(doneCount) doneCount.textContent=String(done);
  if(errorCount) errorCount.textContent=String(errors);
}

const taskScreenLog=document.getElementById("task-screen-log");
const taskScreenTitle=document.getElementById("task-screen-title");
const taskScreenState=document.getElementById("task-screen-state");
const taskScreenProgress=document.getElementById("task-screen-progress-bar");
const taskScreenTaskId=document.getElementById("task-screen-task-id");
const taskScreenSummary=document.getElementById("task-screen-summary");
let taskScreenEntries=0;

function updateTaskScreen(event){
  if(!taskScreenLog) return;
  const state=String(event?.state||"idle");
  const text=String(event?.text||"").trim().replace(/\s*\[[a-f0-9]{12,}\]\s*$/i,"");
  const taskId=String(event?.task_id||"");
  const labelsMap={
    listening:"LISTENING",
    queued:"QUEUED",
    thinking:"ANALYZING",
    result:"RESULT",
    speaking:"RESPONDING",
    speaking_fallback:"VOICE FALLBACK",
    waiting_approval:"WAITING FOR APPROVAL",
    completed:"COMPLETED",
    error:"ERROR",
    idle:"READY"
  };
  const label=labelsMap[state]||state.toUpperCase();
  if(taskScreenState) taskScreenState.textContent=label;
  if(taskScreenTaskId) taskScreenTaskId.textContent=taskId ? "TASK #"+taskId : "TASK —";

  const summary=text.replace(/\s+/g," ").trim();
  if(taskScreenTitle && summary){
    taskScreenTitle.textContent=summary.length>92 ? summary.slice(0,92)+"…" : summary;
  }
  if(taskScreenSummary){
    taskScreenSummary.textContent=summary
      ? (summary.length>170 ? summary.slice(0,170)+"…" : summary)
      : (state==="idle" ? "No active task" : label);
  }

  const progressMap={
    queued:.14,listening:.20,thinking:.48,result:.72,
    speaking:.88,speaking_fallback:.88,waiting_approval:.62,
    completed:1,error:1,idle:0
  };
  if(taskScreenProgress) taskScreenProgress.style.width=((progressMap[state]??.28)*100)+"%";

  if(state==="idle" && !text) return;

  const row=document.createElement("div");
  row.className="task-log-line task-log-"+state;
  const dot=document.createElement("span");
  dot.className="task-log-dot";
  const body=document.createElement("div");
  body.className="task-log-body";
  const meta=document.createElement("div");
  meta.className="task-log-meta";
  meta.textContent=(new Date()).toLocaleTimeString()+"  "+label+(taskId?"  #"+taskId:"");
  const content=document.createElement("div");
  content.className="task-log-content";
  if(summary.length>520){
    content.textContent=summary.slice(0,520)+"…";
    const details=document.createElement("details");
    details.className="task-log-details";
    const summaryNode=document.createElement("summary");
    summaryNode.textContent="Pura output dekho";
    const pre=document.createElement("pre");
    pre.textContent=summary;
    details.appendChild(summaryNode);
    details.appendChild(pre);
    body.appendChild(meta);
    body.appendChild(content);
    body.appendChild(details);
  }else{
    content.textContent=summary || label;
    body.appendChild(meta);
    body.appendChild(content);
  }
  row.appendChild(dot);
  row.appendChild(body);
  taskScreenLog.prepend(row);
  taskScreenEntries++;
  while(taskScreenLog.children.length>28) taskScreenLog.removeChild(taskScreenLog.lastChild);
  if(taskScreenEntries>28) taskScreenEntries=28;
}

function activityBucket(state){
  if(state==="error") return "errors";
  if(state==="completed"||state==="result") return "results";
  if(state==="queued"||state==="thinking"||state==="speaking"||state==="speaking_fallback") return "running";
  return "all";
}

function addActivity(event){
  if(!activityList) return;
  const text=String(event.text||"").trim().replace(/\s*\[[a-f0-9]{12,}\]\s*$/i,"");
  const state=String(event.state||"idle");
  const taskId=String(event.task_id||"");
  if(taskId) taskState.set(taskId,state);
  updateTaskCounts();

  const key=state+"|"+taskId+"|"+text.slice(0,160);
  if(key===lastActivityKey && state!=="error") return;
  lastActivityKey=key;

  const bucket=activityBucket(state);
  activityList.querySelector(".workspace-idle")?.remove();
  const row=document.createElement("article");
  row.className="activity-item activity-"+state;
  row.dataset.bucket=bucket;
  row.dataset.state=state;
  row.dataset.taskId=taskId;
  const when=new Date().toLocaleTimeString();

  const main=document.createElement("div");
  main.className="activity-main";

  const meta=document.createElement("div");
  meta.className="activity-meta";
  meta.innerHTML=`<span class="activity-time"></span><span class="activity-state"></span><span class="activity-task"></span>`;
  meta.querySelector(".activity-time").textContent=when;
  meta.querySelector(".activity-state").textContent=state.toUpperCase();
  meta.querySelector(".activity-task").textContent=taskId ? "#"+taskId : "";

  const preview=document.createElement("div");
  preview.className="activity-text";
  preview.textContent=text||"Ready";
  main.appendChild(meta);
  main.appendChild(preview);

  if(text.length>260){
    const details=document.createElement("details");
    const summary=document.createElement("summary");
    summary.textContent="Pura result dekho";
    const pre=document.createElement("pre");
    pre.textContent=text;
    details.appendChild(summary);
    details.appendChild(pre);
    main.appendChild(details);
  }

  row.appendChild(main);
  activityList.prepend(row);
  while(activityList.children.length>120) activityList.removeChild(activityList.lastChild);
  applyActivityFilter();
}

function applyActivityFilter(){
  if(!activityList) return;
  [...activityList.children].forEach(row=>{
    const bucket=row.dataset.bucket||"all";
    row.hidden=!(activityFilter==="all"||bucket===activityFilter);
  });
}

const clearActivityButton=document.getElementById("clear-activity");
const clearWorkspaceButton=document.getElementById("clear-workspace");
function clearActivity(){
  if(activityList) activityList.replaceChildren();
  taskState.clear();
  updateTaskCounts();
  lastActivityKey="";
}
if(clearActivityButton) clearActivityButton.onclick=()=>document.getElementById("chat-log")?.replaceChildren();
if(clearWorkspaceButton) clearWorkspaceButton.onclick=clearActivity;

function setupActivityFilters(){
  const filters=document.querySelectorAll("[data-activity-filter], [data-tab]");
  filters.forEach(button=>{
    button.addEventListener("click",()=>{
      activityFilter=button.dataset.activityFilter||button.dataset.tab||"all";
      filters.forEach(item=>{
        item.dataset.active=String(item===button);
        item.classList.toggle("active",item===button);
      });
      applyActivityFilter();
    });
  });
}

const approvalDialogs=new Map();
function showApproval(event){
  const match=String(event.text||"").match(/\[([a-f0-9]{12,})\]/i);
  if(!match || approvalDialogs.has(match[1])) return;
  const pendingId=match[1];
  const overlay=document.createElement("div");
  overlay.className="approval-overlay";
  overlay.innerHTML="<div class='approval-card'><div class='approval-title'>JENEFAR ACTION APPROVAL</div><div class='approval-tool'></div><pre></pre><div class='approval-actions'><button data-action='deny'>DENY</button><button data-action='approve'>APPROVE</button></div></div>";
  const rawMessage=String(event.text||"Approval required");
  const cleanMessage=rawMessage.replace(/\s*\[[a-f0-9]{12,}\]\s*$/i,"").trim();
  overlay.querySelector(".approval-title").textContent="JENEFAR • CONFIRMATION NEEDED";
  overlay.querySelector(".approval-tool").textContent=cleanMessage || "Kya main ye critical action kar doon?";
  overlay.querySelector("pre").style.display="none";
  document.body.appendChild(overlay);
  approvalDialogs.set(pendingId,overlay);

  const close=()=>{ approvalDialogs.delete(pendingId); overlay.remove(); };

  const denyButton=overlay.querySelector("[data-action='deny']");
  const approveButton=overlay.querySelector("[data-action='approve']");

  denyButton.onclick=async()=>{
    try{
      await fetch("/approval/reject",{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({approve_id:pendingId})
      });
    }finally{
      close();
    }
  };

  approveButton.onclick=async()=>{
    overlay.querySelectorAll("button").forEach(button=>button.disabled=true);
    try{
      await fetch("/realtime/tool",{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({approve_id:pendingId})
      });
    }finally{
      close();
    }
  };
}

function pauseBrowserVoice(){
  voiceLocked=true;
  if(restartTimer) clearTimeout(restartTimer);
  try{recognition?.stop();}catch(_){}
  if(fallbackMode) stopFallbackMonitor(false);
  setVoiceInputStatus("MIC PAUSED WHILE JENEFAR SPEAKS",false);
}

function resumeBrowserVoice(){
  if(!micEnabled||voiceLocked) return;
  if(browserSpeechActive||("speechSynthesis" in window && window.speechSynthesis.speaking)) return;
  if(fallbackMode){
    startFallbackMonitor();
    return;
  }
  if(!voiceSupported||!recognition) return;
  if(restartTimer) clearTimeout(restartTimer);
  restartTimer=setTimeout(()=>{
    if(!micEnabled||voiceLocked||!recognition) return;
    try{recognition.start();}
    catch(error){
      if(error?.name==="InvalidStateError") return;
      addActivity({state:"error",text:"Mic could not start: "+(error?.name||error?.message||"unknown error")});
      setVoiceInputStatus("MIC START ERROR — turn mic OFF then ON",false);
      setMicButton(false,false);
      micEnabled=false;
      voiceLocked=true;
    }
  },restartDelay);
}

function selectPremiumVoice(){
  if(!browserSpeechReady) return null;
  const voices=window.speechSynthesis.getVoices()||[];
  const preferred=["Microsoft Neerja Online (Natural) - English (India)","Microsoft Neerja - English (India)","Google हिन्दी","Google Hindi","Google English (India)","Microsoft Sonia Online (Natural) - English (United Kingdom)"];
  for(const name of preferred){
    const hit=voices.find(v=>v.name===name);
    if(hit) return hit;
  }
  return voices.find(v=>/^en-IN/i.test(v.lang))
      || voices.find(v=>/^hi-IN/i.test(v.lang))
      || voices.find(v=>/^en/i.test(v.lang))
      || voices[0]
      || null;
}

function playBrowserAudio(base64,mime,text){
  if(!base64) return false;
  try{
    const bytes=Uint8Array.from(atob(base64),char=>char.charCodeAt(0));
    const blob=new Blob([bytes],{type:mime||"audio/wav"});
    const url=URL.createObjectURL(blob);
    if(browserAudio){
      try{browserAudio.pause();}catch(_){}
      try{URL.revokeObjectURL(browserAudio.dataset?.url||"");}catch(_){}
    }
    browserAudio=new Audio(url);
    browserAudio.dataset.url=url;
    browserAudio.preload="auto";
    browserAudio.onplay=()=>{browserSpeechActive=true;};
    browserAudio.onended=()=>{
      browserSpeechActive=false;
      voiceLocked=false;
      URL.revokeObjectURL(url);
      resumeBrowserVoice();
    };
    browserAudio.onerror=()=>{
      browserSpeechActive=false;
      URL.revokeObjectURL(url);
      voiceLocked=false;
      if(text) browserSpeakFallback(text);
      else resumeBrowserVoice();
    };
    browserAudio.play().catch(()=>{
      browserSpeechActive=false;
      URL.revokeObjectURL(url);
      if(text) browserSpeakFallback(text);
      else {voiceLocked=false;resumeBrowserVoice();}
    });
    return true;
  }catch(_){
    return false;
  }
}

function browserSpeakFallback(text){
  if(!text||!browserSpeechReady) return;
  const clean=String(text).replace(/\[[^\]]*\]/g," ").replace(/\s+/g," ").trim();
  if(!clean) return;
  try{
    browserSpeechActive=true;
    pauseBrowserVoice();
    window.speechSynthesis.cancel();
    const utterance=new SpeechSynthesisUtterance(clean);
    const voice=selectPremiumVoice();
    if(voice) utterance.voice=voice;
    utterance.lang="en-IN";
    utterance.rate=.94;
    utterance.pitch=1.04;
    utterance.volume=.96;
    utterance.onend=()=>{browserSpeechActive=false;voiceLocked=false;resumeBrowserVoice();};
    utterance.onerror=()=>{browserSpeechActive=false;voiceLocked=false;resumeBrowserVoice();};
    window.speechSynthesis.speak(utterance);
  }catch(_){}
}

function apply(event){
  currentState=event.state||"idle";
  updateEmbeddedHud(currentState,event.text||"");
  speechLevel=Number(event.level||0);
  stage.dataset.state=currentState;
  emotion=event.emotion||"neutral";
  emotionIntensity=Number(event.intensity||0);
  stage.style.setProperty("--speech-level",speechLevel.toFixed(3));
  stage.style.setProperty("--emotion-intensity",emotionIntensity.toFixed(3));
  stage.dataset.emotion=emotion;
  window.dispatchEvent(new CustomEvent("jenefar-avatar-event",{detail:event}));
  addActivity(event);
  updateTaskScreen(event);
  updateChatFromEvent(event);

  if(currentState==="waiting_approval") showApproval(event);
  if(currentState==="speaking"){
    pauseBrowserVoice();
    if(event.audio_b64){
      playBrowserAudio(event.audio_b64,event.audio_mime,event.text||"");
    }
  }else if(currentState==="speaking_fallback"){
    pauseBrowserVoice();
    if(event.text) browserSpeakFallback(event.text);
  }else if(currentState==="idle"||currentState==="completed"){
    voiceLocked=false;
    resumeBrowserVoice();
  }

  const [stateText,caption]=labels[currentState]||["ACTIVE",event.text||""];
  if(stateEl) stateEl.textContent=stateText;
  if(captionEl) captionEl.textContent=event.text||caption;

  if(currentState==="speaking"||currentState==="speaking_fallback"){
    document.body.dataset.voiceActive="true";
  }else if(currentState==="idle"||currentState==="listening"||currentState==="completed"){
    document.body.dataset.voiceActive="false";
  }

  const [r,g,b]=palette(currentState);
  if(dot){
    dot.style.background=`rgb(${r},${g},${b})`;
    dot.style.boxShadow=`0 0 18px rgb(${r},${g},${b})`;
  }
  const voiceService=document.getElementById("service-voice");
  if(voiceService) voiceService.textContent=(currentState==="speaking"||currentState==="speaking_fallback"||currentState==="listening")?"●":"○";
}

function connect(){
  const source=new EventSource("/events");
  source.onmessage=(message)=>{
    try{apply(JSON.parse(message.data));}
    catch(error){
      console.error("[JENEFAR] Dashboard event handler failed:",error);
      setVoiceInputStatus("DASHBOARD UPDATE ERROR — check browser console",false);
    }
  };
  source.onerror=()=>{
    source.close();
    setTimeout(connect,1200);
  };
}

function updateChatFromEvent(event){
  const log=document.getElementById("chat-log");
  if(!log || !event?.task_id) return;
  const taskId=String(event.task_id);
  let row=log.querySelector('[data-task-id="'+CSS.escape(taskId)+'"]');
  if((event.state==="speaking"||event.state==="result") && event.text){
    if(!row){
      row=document.createElement("div");
      row.className="chat-row bot";
      row.dataset.taskId=taskId;
      row.innerHTML='<div class="mini-avatar">J</div><div class="bubble"></div>';
      log.appendChild(row);
    }
    row.querySelector(".bubble").textContent=event.text;
    log.scrollTop=log.scrollHeight;
  }
}


/* Browser voice */
const micButton=document.getElementById("mic-button");
const browserSpeechReady = "speechSynthesis" in window;
let voicesReady=false;
if(browserSpeechReady){
  const primeVoices=()=>{ window.speechSynthesis.getVoices(); voicesReady=true; };
  primeVoices();
  window.speechSynthesis.onvoiceschanged=primeVoices;
}
const voiceInputStatus=document.getElementById("voice-input-status") || document.getElementById("mic-status");
let recognition=null;
let micEnabled=true;
let voiceLocked=false;
let voiceSupported=false;
let restartTimer=null;
let restartDelay=450;
let browserSpeechActive=false;
let browserAudio=null;
let fallbackMode=false;
let fallbackStream=null;
let fallbackContext=null;
let fallbackAnalyser=null;
let fallbackSource=null;
let fallbackData=null;
let fallbackAnimationFrame=0;
let fallbackRecorder=null;
let fallbackChunks=[];
let fallbackRecordStartedAt=0;
let fallbackLastSpeechAt=0;
let fallbackStopping=false;
let fallbackSubmitting=false;

function setVoiceInputStatus(text,active=false){
  if(voiceInputStatus){
    voiceInputStatus.textContent=text;
    voiceInputStatus.dataset.active=active?"true":"false";
  }
}

function setMicButton(active, busy=false){
  if(!micButton) return;
  micButton.classList.toggle("is-active", active);
  micButton.classList.toggle("is-busy", busy);
  micButton.setAttribute("aria-pressed", String(active));
  micButton.setAttribute("aria-label",busy ? "Microphone processing" : active ? "Turn microphone off" : "Turn microphone on");
  const label=micButton.querySelector(".mic-label");
  if(label) label.textContent=busy ? "PROCESSING" : active ? "MIC ON" : "MIC OFF";
}


function stopFallbackMonitor(releaseStream=false){
  if(fallbackAnimationFrame){
    cancelAnimationFrame(fallbackAnimationFrame);
    fallbackAnimationFrame=0;
  }
  if(fallbackRecorder&&fallbackRecorder.state==="recording"){
    fallbackRecorder.onstop=null;
    try{fallbackRecorder.stop();}catch(_){}
  }
  fallbackRecorder=null;
  fallbackChunks=[];
  fallbackStopping=false;
  if(fallbackSource){try{fallbackSource.disconnect();}catch(_){}}
  fallbackSource=null;
  fallbackAnalyser=null;
  fallbackData=null;
  if(fallbackContext){try{fallbackContext.close();}catch(_){};fallbackContext=null;}
  if(releaseStream){
    fallbackStream?.getTracks().forEach(track=>{try{track.stop();}catch(_){}});
    fallbackStream=null;
    fallbackMode=false;
  }
}

function resumeVoiceIfAssistantIdle(){
  const taskInProgress=["listening","queued","thinking","result","waiting_approval","speaking","speaking_fallback","error"].includes(currentState);
  const audioPlaying=browserSpeechActive
    || Boolean(browserAudio&&!browserAudio.ended)
    || ("speechSynthesis" in window&&window.speechSynthesis.speaking);
  if(taskInProgress||audioPlaying) return;
  voiceLocked=false;
  setMicButton(micEnabled,false);
  resumeBrowserVoice();
}

async function transcribeCapturedAudio(blob,durationMs){
  if(!micEnabled||voiceLocked||!blob||blob.size<1200||durationMs<550) return;
  fallbackSubmitting=true;
  voiceLocked=true;
  stopFallbackMonitor(false);
  setVoiceInputStatus("TRANSCRIBING VOICE…",true);
  setMicButton(true,true);
  try{
    const response=await fetch("/voice/audio",{
      method:"POST",
      headers:{"Content-Type":blob.type||"audio/webm"},
      body:blob
    });
    const result=await response.json();
    if(!response.ok||result?.error) throw new Error(result?.error||("HTTP "+response.status));
    if(result?.ignored){
      fallbackSubmitting=false;
      voiceLocked=false;
      if(result?.reason==="empty_transcript"){
        setVoiceInputStatus("NO WORDS RECOGNIZED — SPEAK CLOSER OR CHECK MIC LEVEL",false);
        addActivity({state:"error",text:"Audio was captured but speech-to-text returned an empty transcript."});
      }else{
        setVoiceInputStatus("MIC ON — LISTENING FOR SPEECH",true);
      }
      setMicButton(true,false);
      resumeBrowserVoice();
      return;
    }
    if(result?.busy){
      fallbackSubmitting=false;
      // Do not unlock during a still-running task. If its completion event
      // already arrived while STT was pending, the helper safely resumes now.
      setVoiceInputStatus("Jenefar is busy — mic will resume after reply",true);
      setMicButton(true,true);
      resumeVoiceIfAssistantIdle();
      return;
    }
    if(result?.accepted){
      const heard=String(result.transcript||result.text||"").trim();
      if(heard) addActivity({state:"listening",text:"You: "+heard});
      setVoiceInputStatus(heard ? "HEARD: "+heard.slice(0,90) : "COMMAND RECEIVED — WORKING",true);
      setMicButton(true,true);
      // Stay muted until the assistant finishes speaking to avoid feedback.
      fallbackSubmitting=false;
      return;
    }
    fallbackSubmitting=false;
    voiceLocked=false;
    setVoiceInputStatus("VOICE WAS NOT TRANSCRIBED — TRY AGAIN",false);
    setMicButton(true,false);
    resumeBrowserVoice();
  }catch(error){
    fallbackSubmitting=false;
    const errorText=String(error?.message||error);
    const providerUnavailable=/Speech-to-text unavailable|No speech-to-text provider is configured|No currently available STT provider|All configured STT providers failed|Browser microphone audio transcription is unavailable|HTTP 503/i.test(errorText);
    if(providerUnavailable&&fallbackMode&&voiceSupported&&recognition){
      stopFallbackMonitor(true);
      fallbackMode=false;
      voiceLocked=false;
      addActivity({state:"error",text:"Server STT is unavailable; switching to browser speech recognition: "+errorText});
      setVoiceInputStatus("SERVER STT UNAVAILABLE — TRYING BROWSER SPEECH",true);
      setMicButton(true,true);
      resumeBrowserVoice();
      return;
    }
    voiceLocked=false;
    addActivity({state:"error",text:"Audio STT failed: "+errorText});
    setVoiceInputStatus("VOICE STT ERROR — "+errorText.slice(0,90),false);
    setMicButton(true,false);
    resumeBrowserVoice();
  }
}

function startFallbackMonitor(){
  if(!micEnabled||voiceLocked||!fallbackMode||!fallbackStream||fallbackAnimationFrame||fallbackSubmitting) return;
  try{
    const AudioContextClass=window.AudioContext||window.webkitAudioContext;
    if(!AudioContextClass||!window.MediaRecorder) throw new Error("MediaRecorder/Web Audio unavailable");
    fallbackContext=new AudioContextClass();
    fallbackAnalyser=fallbackContext.createAnalyser();
    fallbackAnalyser.fftSize=1024;
    fallbackData=new Uint8Array(fallbackAnalyser.fftSize);
    fallbackSource=fallbackContext.createMediaStreamSource(fallbackStream);
    fallbackSource.connect(fallbackAnalyser);
    fallbackContext.resume().catch(()=>{});
  }catch(error){
    setVoiceInputStatus("AUDIO CAPTURE ERROR — "+String(error?.message||error).slice(0,80),false);
    addActivity({state:"error",text:"Audio capture setup failed: "+(error?.message||error)});
    return;
  }

  const beginSegment=(now)=>{
    try{
      const candidates=["audio/webm;codecs=opus","audio/ogg;codecs=opus","audio/webm","audio/ogg"];
      const mimeType=candidates.find(type=>MediaRecorder.isTypeSupported?.(type));
      const recorder=new MediaRecorder(fallbackStream,mimeType?{mimeType}:{});
      const chunks=[];
      fallbackRecorder=recorder;
      fallbackChunks=chunks;
      fallbackRecordStartedAt=now;
      fallbackLastSpeechAt=now;
      fallbackStopping=false;
      setVoiceInputStatus("SPEECH DETECTED — RECORDING UTTERANCE",true);
      recorder.ondataavailable=(event)=>{if(event.data&&event.data.size) chunks.push(event.data);};
      recorder.onerror=(event)=>{
        addActivity({state:"error",text:"Audio recorder: "+(event.error?.name||"recording error")});
      };
      recorder.onstop=()=>{
        if(fallbackRecorder===recorder) fallbackRecorder=null;
        fallbackStopping=false;
        fallbackChunks=[];
        if(!micEnabled||voiceLocked) return;
        const duration=Math.max(0,performance.now()-fallbackRecordStartedAt);
        const blob=new Blob(chunks,{type:recorder.mimeType||"audio/webm"});
        if(duration<550||blob.size<1200) return;
        transcribeCapturedAudio(blob,duration);
      };
      recorder.start();
    }catch(error){
      fallbackRecorder=null;
      setVoiceInputStatus("AUDIO RECORDER ERROR — "+String(error?.message||error).slice(0,80),false);
      addActivity({state:"error",text:"Could not start MediaRecorder: "+(error?.message||error)});
    }
  };

  const monitor=()=>{
    fallbackAnimationFrame=0;
    if(!micEnabled||voiceLocked||!fallbackMode||!fallbackStream||fallbackSubmitting) return;
    if(!fallbackAnalyser||!fallbackData) return;
    fallbackAnalyser.getByteTimeDomainData(fallbackData);
    let energy=0;
    for(let i=0;i<fallbackData.length;i++){
      const centered=fallbackData[i]-128;
      energy+=centered*centered;
    }
    const rms=Math.sqrt(energy/fallbackData.length)/128;
    const now=performance.now();
    // 0.020 misses quiet speech on some Linux microphone/USB levels.
    const speechThreshold=0.010;
    if(rms>speechThreshold){
      fallbackLastSpeechAt=now;
      if(!fallbackRecorder&&!fallbackStopping) beginSegment(now);
    }
    if(fallbackRecorder&&fallbackRecorder.state==="recording"){
      const elapsed=now-fallbackRecordStartedAt;
      const quietFor=now-fallbackLastSpeechAt;
      if((elapsed>=700&&quietFor>=850)||elapsed>=12000){
        fallbackStopping=true;
        try{fallbackRecorder.stop();}catch(_){fallbackStopping=false;}
      }
    }
    fallbackAnimationFrame=requestAnimationFrame(monitor);
  };
  fallbackAnimationFrame=requestAnimationFrame(monitor);
}


async function sendBrowserTranscript(text){
  const clean=String(text||"").trim();
  if(!clean||voiceLocked||!micEnabled) return;
  pauseBrowserVoice();
  setVoiceInputStatus("QUEUING: "+clean,true);
  addActivity({state:"listening",text:"You: "+clean});

  try{
    const response=await fetch("/voice/text",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({text:clean})
    });
    const result=await response.json();
    if(result?.ignored){
      voiceLocked=false;
      setMicButton(micEnabled, false);
      resumeBrowserVoice();
      return;
    }
    if(result?.error){
      addActivity({state:"error",text:"Voice error: "+result.error});
      setVoiceInputStatus("VOICE ERROR",false);
      setMicButton(false, false);
      micEnabled=false;
      voiceLocked=true;
      try{recognition?.stop();}catch(_){}
      return;
    }
    if(result?.busy){
      setVoiceInputStatus("Jawaab abhi chal raha hai — thoda wait karo",true);
      setMicButton(false, true);
      return;
    }
    if(result?.exit){
      micEnabled=false;
      voiceLocked=true;
      try{recognition?.stop();}catch(_){}
      setVoiceInputStatus("VOICE OFF",false);
      setMicButton(false, false);
      return;
    }
    if(result?.accepted){
      setVoiceInputStatus("Jawaab aa raha hai",true);
      setMicButton(true, true);
      // Keep the microphone locked while the server thinks and synthesizes TTS.
      // apply() releases it only after assistant audio/speech has actually ended.
      return;
    }
    voiceLocked=false;
    resumeBrowserVoice();
  }catch(error){
    addActivity({state:"error",text:"Voice request failed: "+error});
    setVoiceInputStatus("VOICE CONNECTION ERROR",false);
    setMicButton(false, false);
    voiceLocked=false;
    resumeBrowserVoice();
  }
}

function setupBrowserVoice(){
  const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;
  const canRecord=Boolean(navigator.mediaDevices?.getUserMedia&&window.MediaRecorder&&(window.AudioContext||window.webkitAudioContext));
  voiceSupported=Boolean(Recognition);

  if(micButton){
    micButton.addEventListener("pointerdown",()=>micButton.classList.add("pressed"),{passive:true});
    micButton.addEventListener("pointerup",()=>micButton.classList.remove("pressed"),{passive:true});
    micButton.addEventListener("pointercancel",()=>micButton.classList.remove("pressed"),{passive:true});
  }

  async function requestMicrophonePermission(){
    if(!navigator.mediaDevices?.getUserMedia){
      setVoiceInputStatus("MIC API UNSUPPORTED",false);
      return null;
    }
    try{
      setVoiceInputStatus("MIC PERMISSION: CLICK ALLOW",true);
      return await navigator.mediaDevices.getUserMedia({
        audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true},
        video:false
      });
    }catch(error){
      const code=error?.name||"unknown";
      addActivity({state:"error",text:"Microphone permission: "+code});
      if(code==="NotAllowedError"||code==="SecurityError"){
        micEnabled=false;
        voiceLocked=true;
        setVoiceInputStatus("MIC BLOCKED — USE SITE SETTINGS TO ALLOW",false);
      }else if(code==="NotFoundError"||code==="DevicesNotFoundError"){
        micEnabled=false;
        voiceLocked=true;
        setVoiceInputStatus("NO MICROPHONE DEVICE FOUND",false);
      }else{
        setVoiceInputStatus("MIC ERROR: "+code,false);
      }
      setMicButton(false,false);
      return null;
    }
  }

  if(micButton){
    micButton.onclick=async()=>{
      if(micEnabled){
        micEnabled=false;
        voiceLocked=true;
        try{recognition?.stop();}catch(_){}
        stopFallbackMonitor(true);
        setVoiceInputStatus("MIC OFF",false);
        setMicButton(false,false);
        return;
      }
      if(!voiceSupported&&!canRecord){
        setVoiceInputStatus("MIC UNSUPPORTED — USE CHAT OR A SUPPORTED BROWSER",false);
        setMicButton(false,false);
        return;
      }

      const stream=await requestMicrophonePermission();
      if(!stream) return;
      micEnabled=true;
      voiceLocked=false;
      if(canRecord){
        // Prefer server-side STT to Chromium's built-in recognizer for Hinglish.
        fallbackMode=true;
        fallbackStream=stream;
        setVoiceInputStatus("MIC ON — SERVER STT READY; SPEAK NATURALLY",true);
        setMicButton(true,false);
        startFallbackMonitor();
      }else if(voiceSupported&&recognition){
        stream.getTracks().forEach(track=>{try{track.stop();}catch(_){}});
        fallbackMode=false;
        setVoiceInputStatus("BROWSER MIC: STARTING",true);
        setMicButton(true,false);
        resumeBrowserVoice();
      }else{
        stream.getTracks().forEach(track=>{try{track.stop();}catch(_){}});
        micEnabled=false;
        voiceLocked=true;
        setVoiceInputStatus("MIC CAPTURE UNSUPPORTED — USE CHAT",false);
        setMicButton(false,false);
      }
    };
  }

  if(Recognition){
    recognition=new Recognition();
    recognition.lang="hi-IN";
    recognition.continuous=true;
    recognition.interimResults=false;
    recognition.maxAlternatives=1;

    recognition.onstart=()=>{
      if(voiceLocked||!micEnabled){try{recognition.stop();}catch(_){};return;}
      restartDelay=450;
      setVoiceInputStatus("BROWSER MIC: LISTENING",true);
      setMicButton(true,false);
    };

    recognition.onresult=(event)=>{
      for(let i=event.resultIndex;i<event.results.length;i++){
        const result=event.results[i];
        if(result.isFinal&&!voiceLocked&&micEnabled){
          const text=(result[0]?.transcript||"").trim();
          if(text) sendBrowserTranscript(text);
        }
      }
    };

    recognition.onerror=(event)=>{
      const code=event.error||"unknown";
      if(code==="aborted") return;
      addActivity({state:"error",text:"Browser mic: "+code});
      if(code==="not-allowed"||code==="service-not-allowed"){
        micEnabled=false;
        voiceLocked=true;
        setVoiceInputStatus("MIC PERMISSION DENIED",false);
        setMicButton(false,false);
      }else{
        restartDelay=Math.min(5000,Math.max(900,restartDelay*1.8));
        setVoiceInputStatus("MIC RETRYING IN "+(restartDelay/1000).toFixed(1)+"s — "+code,false);
        setMicButton(true,true);
      }
    };

    recognition.onend=()=>{
      if(!micEnabled||voiceLocked||browserSpeechActive) return;
      resumeBrowserVoice();
    };
  }

  // Request the microphone only after a direct user click. Browsers without
  // SpeechRecognition use MediaRecorder + server-side OpenAI/Groq STT.
  micEnabled=false;
  voiceLocked=true;
  if(canRecord){
    setVoiceInputStatus("CLICK MIC ON — SERVER STT READY",false);
    if(micButton){
      const label=micButton.querySelector(".mic-label");
      if(label) label.textContent="MIC OFF";
      micButton.title="Click to enable microphone recording and server-side OpenAI/Groq/Gemini transcription.";
    }
  }else if(voiceSupported){
    setVoiceInputStatus("CLICK MIC ON TO START",false);
    if(micButton) micButton.title="Click to enable browser speech recognition.";
  }else{
    setVoiceInputStatus("MIC UNSUPPORTED — TYPE IN CHAT",false);
    if(micButton){
      const label=micButton.querySelector(".mic-label");
      if(label) label.textContent="MIC UNSUPPORTED";
      micButton.title="This browser does not expose microphone recording. Chat input remains available.";
    }
  }
}


/* Premium dashboard interactions */
function updateUiClock(){
  const el=document.getElementById("ui-clock");
  if(el) el.textContent=new Date().toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"});
}
setInterval(updateUiClock,1000); updateUiClock();

document.querySelectorAll(".nav-item").forEach(btn=>{
  btn.addEventListener("click",()=>{
    document.querySelectorAll(".nav-item").forEach(item=>item.classList.remove("active"));
    btn.classList.add("active");
    const target=btn.dataset.nav||"home";
    const targets={
      home:()=>window.scrollTo({top:0,behavior:"smooth"}),
      chat:()=>document.getElementById("chat-input")?.focus(),
      voice:()=>document.getElementById("mic-button")?.click(),
      vision:()=>setVoiceInputStatus("Vision command ready — bolo kya dekhna hai",true),
      apps:()=>document.querySelector(".quick-apps")?.classList.toggle("panel-focus"),
      web:()=>dispatchDashboardCommand("web search karo"),
      notes:()=>document.getElementById("chat-input")?.focus(),
      automation:()=>dispatchDashboardCommand("automation dikhao"),
      settings:()=>{toggleModelPanel(true);setVoiceInputStatus("Model settings open",true)}
    };
    targets[target]?.();
  });
});

async function dispatchDashboardCommand(command){
  const clean=String(command||"").trim();
  if(!clean) return;
  // Typed commands can arrive while the mic is enabled. Stop capture before
  // sending so Jenefar cannot transcribe its own answer as a fresh user task.
  pauseBrowserVoice();
  const log=document.getElementById("chat-log");
  try{
    const response=await fetch("/voice/text",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({text:clean})
    });
    const result=await response.json();
    if(result?.error) throw new Error(result.error);
    if(result?.exit){
      micEnabled=false;
      voiceLocked=true;
      try{recognition?.stop();}catch(_){}
      setVoiceInputStatus("VOICE OFF",false);
      setMicButton(false,false);
      return result;
    }
    if(log && result?.accepted){
      const bot=document.createElement("div");
      bot.className="chat-row bot";
      bot.innerHTML='<div class="mini-avatar">J</div><div class="bubble"></div>';
      bot.querySelector(".bubble").textContent="Jawaab aa raha hai...";
      bot.dataset.taskId=String(result.task_id||"");
      log.appendChild(bot);
      log.scrollTop=log.scrollHeight;
    }
    if(result?.accepted || result?.busy){
      // Keep capture locked until the corresponding speaking/completed event.
      return result;
    }
    voiceLocked=false;
    resumeBrowserVoice();
    return result;
  }catch(error){
    voiceLocked=false;
    resumeBrowserVoice();
    addActivity({state:"error",text:"Dashboard command failed: "+error});
    return null;
  }
}
document.querySelectorAll("[data-command]").forEach(btn=>{
  btn.addEventListener("click",()=>dispatchDashboardCommand(btn.dataset.command||""));
});

document.getElementById("chat-form")?.addEventListener("submit",async event=>{
  event.preventDefault();
  const input=document.getElementById("chat-input");
  const log=document.getElementById("chat-log");
  const text=String(input?.value||"").trim();
  if(!text||!log) return;
  const user=document.createElement("div");
  user.className="chat-row user";
  user.innerHTML='<div class="bubble user-bubble"></div>';
  const userBubble=user.querySelector(".bubble");
  userBubble.textContent=text;
  log.appendChild(user);
  if(input) input.value="";
  const result=await dispatchDashboardCommand(text);
  if(result?.display_text) userBubble.textContent=result.display_text;
});

document.getElementById("dock-talk")?.addEventListener("click",()=>document.getElementById("mic-button")?.click());
document.getElementById("dock-vision")?.addEventListener("click",()=>document.getElementById("stage")?.setAttribute("data-state","thinking"));
document.getElementById("dock-chat")?.addEventListener("click",()=>document.getElementById("chat-input")?.focus());

setupActivityFilters();
window.addEventListener("resize",resize);
resize();
connect();
requestAnimationFrame(draw);
setupBrowserVoice();

// Live Realtime voice owns the microphone; stop the standard STT listener first.
window.addEventListener("jenefar-realtime-start",()=>{
  if(micEnabled&&micButton) micButton.click();
});

/* Cinematic 3D holographic environment */
(function setupHolographicEnvironment(){
  const particleHost = document.getElementById("holo-particles");
  if(particleHost){
    const count = Math.min(75, Math.max(36, Math.floor(window.innerWidth / 22)));
    for(let i=0;i<count;i++){
      const el=document.createElement("span");
      el.className="holo-particle";
      el.style.left=(Math.random()*100)+"%";
      el.style.top=(38+Math.random()*55)+"%";
      el.style.animationDelay=(-Math.random()*8)+"s";
      el.style.animationDuration=(5+Math.random()*7)+"s";
      particleHost.appendChild(el);
    }
  }

  const canvas=document.getElementById("earth-canvas");
  if(!canvas) return;
  const ctx=canvas.getContext("2d");
  if(!ctx) return;
  let size=0, dpr=1, rotation=0;
  const points=Array.from({length:900},()=>({
    lat:(Math.random()-.5)*Math.PI,
    lon:(Math.random()*2-1)*Math.PI,
    jitter:Math.random()
  }));

  function resizeEarth(){
    const rect=canvas.getBoundingClientRect();
    size=Math.max(1,Math.min(rect.width,rect.height));
    dpr=Math.min(window.devicePixelRatio||1,2);
    canvas.width=size*dpr; canvas.height=size*dpr;
    ctx.setTransform(dpr,0,0,dpr,0,0);
  }

  function landMask(lat,lon){
    const x=Math.sin(lon*1.7)+.35*Math.sin(lon*4.7+lat*2);
    const y=Math.cos(lat*2.15)+.3*Math.sin(lat*5.2-lon);
    return (x+y+0.24*Math.sin(lat*9+lon*3))>.95;
  }

  function drawEarth(t){
    ctx.clearRect(0,0,size,size);
    const cx=size/2, cy=size/2, R=size*.31;
    const grad=ctx.createRadialGradient(cx-R*.28,cy-R*.32,R*.08,cx,cy,R*1.25);
    grad.addColorStop(0,"rgba(130,235,255,.42)");
    grad.addColorStop(.42,"rgba(31,131,255,.22)");
    grad.addColorStop(1,"rgba(0,18,48,0)");
    ctx.fillStyle=grad; ctx.beginPath(); ctx.arc(cx,cy,R*1.35,0,Math.PI*2); ctx.fill();

    ctx.save();
    ctx.beginPath(); ctx.arc(cx,cy,R,0,Math.PI*2); ctx.clip();
    const ocean=ctx.createLinearGradient(0,cy-R,0,cy+R);
    ocean.addColorStop(0,"rgba(10,71,121,.70)");
    ocean.addColorStop(.5,"rgba(7,35,82,.95)");
    ocean.addColorStop(1,"rgba(2,15,43,.92)");
    ctx.fillStyle=ocean; ctx.fillRect(cx-R,cy-R,R*2,R*2);

    const lonShift=rotation;
    for(const p of points){
      const z=Math.cos(p.lat)*Math.cos(p.lon+lonShift);
      if(z<=0) continue;
      const x=cx+R*Math.cos(p.lat)*Math.sin(p.lon+lonShift);
      const y=cy-R*Math.sin(p.lat);
      const isLand=landMask(p.lat,p.lon);
      ctx.fillStyle=isLand ? "rgba(84,220,255,.62)" : "rgba(97,195,255,.23)";
      const s=isLand ? 1.3 : .55;
      ctx.beginPath(); ctx.arc(x,y,s,0,Math.PI*2); ctx.fill();
    }

    ctx.strokeStyle="rgba(98,211,255,.14)";
    ctx.lineWidth=0.7;
    for(let i=-2;i<=2;i++){
      const yy=cy+i*R*.32;
      ctx.beginPath(); ctx.ellipse(cx,yy,R*.96,Math.max(5,R*.10),0,0,Math.PI*2); ctx.stroke();
    }
    for(let i=0;i<9;i++){
      const a=(-Math.PI/2)+(i*Math.PI/8);
      ctx.beginPath(); ctx.ellipse(cx,cy,R*Math.abs(Math.cos(a)),R,0,0,Math.PI*2); ctx.stroke();
    }
    ctx.restore();

    ctx.strokeStyle="rgba(76,226,255,.62)";
    ctx.lineWidth=1.2;
    ctx.beginPath(); ctx.arc(cx,cy,R+1,0,Math.PI*2); ctx.stroke();
    ctx.strokeStyle="rgba(139,115,255,.28)";
    ctx.lineWidth=.8;
    ctx.beginPath(); ctx.arc(cx,cy,R*1.10,0,Math.PI*2); ctx.stroke();

    rotation += .0026;
    requestAnimationFrame(drawEarth);
  }

  window.addEventListener("resize",resizeEarth);
  resizeEarth();
  requestAnimationFrame(drawEarth);
})();



document.getElementById("media-pause")?.addEventListener("click",()=>{
  if(browserAudio){
    try{browserAudio.pause();}catch(_){}
    try{URL.revokeObjectURL(browserAudio.dataset?.url||"");}catch(_){}
    browserAudio=null;
  }
  if("speechSynthesis" in window){
    window.speechSynthesis.cancel();
    browserSpeechActive=false;
    voiceLocked=false;
    resumeBrowserVoice();
  }
});


/* Actual host telemetry: values are sampled by the local backend, never simulated. */
function formatMetricBytes(value){
  const bytes=Number(value);
  if(!Number.isFinite(bytes)||bytes<0) return "N/A";
  const units=["B","KB","MB","GB","TB"];
  let size=bytes, unit=0;
  while(size>=1024&&unit<units.length-1){size/=1024;unit++;}
  return size.toFixed(unit===0?0:1)+" "+units[unit];
}
function setMetricRing(name,value,detail){
  const ring=document.getElementById("metric-"+name);
  const valueEl=document.getElementById("metric-"+name+"-value");
  const detailEl=document.getElementById("metric-"+name+"-detail");
  const n=Number(value);
  const valid=value!==null&&value!==undefined&&value!==""&&Number.isFinite(n)&&n>=0;
  if(ring){
    ring.classList.toggle("meter-unavailable",!valid);
    ring.style.setProperty("--meter-value",valid?String(Math.min(100,n)):"0");
    ring.title=valid?name.toUpperCase()+" usage: "+n+"%":String(detail||"Sensor unavailable");
    if(valid){
      ring.setAttribute("aria-valuenow",String(Math.round(n)));
      ring.setAttribute("role","progressbar");
      ring.setAttribute("aria-label",name.toUpperCase()+" usage "+n+" percent");
    }else{
      ring.removeAttribute("aria-valuenow");
      ring.setAttribute("role","img");
      ring.setAttribute("aria-label",name.toUpperCase()+" telemetry unavailable");
    }
  }
  if(valueEl) valueEl.textContent=valid?Math.round(n)+"%":"N/A";
  if(detailEl) detailEl.textContent=detail|| (valid?"Live sample":"Sensor unavailable");
}
function showMetricsUnavailable(message){
  setMetricRing("cpu",null,message);
  setMetricRing("ram",null,message);
  setMetricRing("gpu",null,message);
  const updated=document.getElementById("metrics-updated");
  if(updated) updated.textContent="LIVE TELEMETRY UNAVAILABLE";
}
async function refreshSystemMetrics(){
  try{
    const response=await fetch("/system/metrics?ts="+Date.now(),{cache:"no-store"});
    const data=await response.json();
    if(!response.ok||!data?.available) throw new Error(data?.error||"System metrics endpoint unavailable");
    const cpu=data.cpu||{};
    const ram=data.ram||{};
    const process=data.process||{};
    const gpu=data.gpu||{};
    setMetricRing("cpu",cpu.usage_percent,
      cpu.logical_cores?String(cpu.logical_cores)+" logical cores":"System CPU");
    setMetricRing("ram",ram.usage_percent,
      formatMetricBytes(ram.used_bytes)+" / "+formatMetricBytes(ram.total_bytes));
    if(gpu.available&&Number.isFinite(Number(gpu.usage_percent))){
      const vram=Number.isFinite(Number(gpu.memory_used_mb))&&Number.isFinite(Number(gpu.memory_total_mb))
        ?Math.round(Number(gpu.memory_used_mb))+" / "+Math.round(Number(gpu.memory_total_mb))+" MB VRAM"
        :"GPU detected";
      setMetricRing("gpu",gpu.usage_percent,vram);
    }else{
      setMetricRing("gpu",null,gpu.reason||"No supported GPU telemetry");
    }
    const updated=document.getElementById("metrics-updated");
    if(updated){
      const stamp=data.sampled_at?new Date(data.sampled_at):new Date();
      updated.textContent="LIVE · "+stamp.toLocaleTimeString([], {hour:"2-digit",minute:"2-digit",second:"2-digit"})
        +(Number.isFinite(Number(process.memory_percent))?" · JENEFAR RAM "+Number(process.memory_percent).toFixed(1)+"%":"");
      updated.title="System values sampled by the local backend at "+stamp.toISOString();
    }
  }catch(error){
    showMetricsUnavailable(String(error?.message||error));
  }
}
refreshSystemMetrics();
setInterval(refreshSystemMetrics,1500);

/* Browser model controls apply to the live runtime for subsequent responses. */
const modelPanel=document.getElementById("model-panel");
const modelButton=document.getElementById("model-settings-button");
const modelChoice=document.getElementById("model-choice");
const modelIdInput=document.getElementById("model-id-input");
const modelFeedback=document.getElementById("model-feedback");
const applyModelButton=document.getElementById("apply-model-button");
function setModelFeedback(message,state=""){
  if(!modelFeedback) return;
  modelFeedback.textContent=message;
  modelFeedback.dataset.state=state;
}
function toggleModelPanel(force){
  if(!modelPanel) return;
  const shouldOpen=typeof force==="boolean"?force:modelPanel.hidden;
  modelPanel.hidden=!shouldOpen;
  modelButton?.setAttribute("aria-expanded",String(shouldOpen));
  if(shouldOpen) refreshModelStatus();
}
async function refreshModelStatus(){
  if(!modelChoice||!modelIdInput) return;
  try{
    const response=await fetch("/model/status?ts="+Date.now(),{cache:"no-store"});
    const status=await response.json();
    if(!response.ok) throw new Error(status?.error||"Model status request failed");
    const active=status.active||{};
    const providers=Array.isArray(status.providers)?status.providers:[];
    modelChoice.replaceChildren();
    if(!providers.length){
      const option=document.createElement("option");
      option.value="";
      option.textContent="No configured cloud providers";
      modelChoice.appendChild(option);
      modelChoice.disabled=true;
      applyModelButton && (applyModelButton.disabled=true);
      if(modelIdInput) modelIdInput.value=active.model||"";
      const label=document.getElementById("active-model-label");
      if(label) label.textContent=active.model||"NOT CONFIGURED";
      setModelFeedback("No cloud provider is configured. Add a provider API key in .env, then restart Jenefar.","error");
      return;
    }
    modelChoice.disabled=false;
    if(applyModelButton) applyModelButton.disabled=false;
    const currentModel=String(active.model||"").trim();
    const currentProvider=String(active.provider||"").trim();
    let activeOptionValue="";
    for(const provider of providers){
      const discovered=Array.isArray(provider.models)?provider.models.filter(Boolean):[];
      const catalogModels=discovered.length?discovered:[provider.model].filter(Boolean);
      const isCatalogFallback=provider.catalog_source!=="provider-api";
      for(const modelName of [...new Set(catalogModels)]){
        const option=document.createElement("option");
        option.value=provider.id+"::"+modelName;
        option.dataset.provider=provider.id;
        option.dataset.model=modelName;
        option.textContent=(provider.label||provider.id)+" · "+modelName
          +(provider.available?"":" (cooldown)")
          +(isCatalogFallback?" · fallback catalog":"");
        modelChoice.appendChild(option);
        if(provider.id===currentProvider&&modelName===currentModel) activeOptionValue=option.value;
      }
    }
    // Retain visibility of the current .env/runtime model if the provider's live
    // catalog does not advertise it, but do not silently treat it as verified.
    if(currentModel&&currentProvider&&!activeOptionValue){
      const option=document.createElement("option");
      option.value=currentProvider+"::"+currentModel;
      option.dataset.provider=currentProvider;
      option.dataset.model=currentModel;
      option.textContent=currentProvider+" · "+currentModel+" (current setting; not verified)";
      modelChoice.appendChild(option);
      activeOptionValue=option.value;
    }
    if(!modelChoice.options.length){
      const option=document.createElement("option");
      option.value="";
      option.textContent="No models returned by configured providers";
      modelChoice.appendChild(option);
    }
    const chosen=providers.find(item=>item.id===currentProvider)||providers[0];
    modelChoice.value=activeOptionValue||modelChoice.options[0].value;
    const selectedOption=modelChoice.selectedOptions?.[0];
    modelIdInput.value=selectedOption?.dataset?.model||currentModel||chosen.model||"";
    const label=document.getElementById("active-model-label");
    if(label) label.textContent=currentModel||chosen.model||"SELECT MODEL";
    const catalogWarnings=providers.filter(item=>item.catalog_source==="fallback")
      .map(item=>item.label+" catalog unavailable"+(item.catalog_diagnostic?": "+item.catalog_diagnostic:""));
    setModelFeedback("Active: "+(active.provider||chosen.id)+" / "+(currentModel||chosen.model||"unknown")
      +(status.runtime_override?" · browser override active":"")
      +(catalogWarnings.length?" · "+catalogWarnings.join("; "):""),"success");
  }catch(error){
    const message=String(error?.message||error);
    const label=document.getElementById("active-model-label");
    if(label) label.textContent="STATUS ERROR";
    setModelFeedback("Could not load model configuration: "+message,"error");
  }
}
modelChoice?.addEventListener("change",()=>{
  const option=modelChoice.selectedOptions?.[0];
  if(option?.dataset?.model&&modelIdInput) modelIdInput.value=option.dataset.model;
});
modelButton?.addEventListener("click",()=>toggleModelPanel());
document.getElementById("model-panel-close")?.addEventListener("click",()=>toggleModelPanel(false));
document.addEventListener("keydown",event=>{
  if(event.key==="Escape"&&modelPanel&&!modelPanel.hidden) toggleModelPanel(false);
});
applyModelButton?.addEventListener("click",async()=>{
  const selectedOption=modelChoice?.selectedOptions?.[0];
  const provider=String(selectedOption?.dataset?.provider||"").trim();
  const model=String(modelIdInput?.value||"").trim();
  if(!provider||!model){
    setModelFeedback("Select a configured provider and enter a model ID first.","error");
    return;
  }
  applyModelButton.disabled=true;
  applyModelButton.textContent="APPLYING…";
  setModelFeedback("Applying "+provider+" / "+model+" to new requests…");
  try{
    const response=await fetch("/model/select",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({provider,model})
    });
    const result=await response.json();
    if(!response.ok||result?.error) throw new Error(result?.error||"Model selection failed");
    const label=document.getElementById("active-model-label");
    if(label) label.textContent=result.active?.model||model;
    let option=modelChoice.selectedOptions?.[0];
    if(!option||option.dataset.provider!==provider){
      option=document.createElement("option");
      option.value=provider+"::"+model;
      option.dataset.provider=provider;
      modelChoice.appendChild(option);
    }
    option.dataset.model=model;
    option.value=provider+"::"+model;
    option.textContent=(provider.charAt(0).toUpperCase()+provider.slice(1))+" · "+model+" (runtime)";
    modelChoice.value=option.value;
    setModelFeedback("Applied: "+provider+" / "+model+". New requests will use this selection; an unavailable provider may still fall back.","success");
  }catch(error){
    setModelFeedback(String(error?.message||error),"error");
  }finally{
    applyModelButton.disabled=false;
    applyModelButton.textContent="APPLY MODEL";
  }
});


/* REA bridge status is based on the actual local MCP process, not a decorative badge. */
const reaDot=document.getElementById("rea-status-dot");
const reaStatusLabel=document.getElementById("rea-status-label");
const reaConnectButton=document.getElementById("rea-connect-button");
function paintReaStatus(status){
  if(!reaStatusLabel) return;
  const connected=Boolean(status?.connected);
  const ready=Boolean(status?.ready);
  const skill=Boolean(status?.skill_enabled);
  if(reaDot){
    reaDot.dataset.state=connected?"connected":ready?"ready":"offline";
  }
  if(connected){
    reaStatusLabel.textContent="REA CONNECTED · "+Number(status.advertised_tools||status.tool_count||0)+" TOOLS";
    if(reaConnectButton) reaConnectButton.textContent="CONNECTED";
    if(reaConnectButton) reaConnectButton.title="REA MCP is connected and its advertised tools can be called.";
  }else if(ready){
    reaStatusLabel.textContent=skill?"REA READY · SKILL ENABLED":"REA READY · SKILL DISABLED";
    if(reaConnectButton) reaConnectButton.textContent="CONNECT";
    if(reaConnectButton) reaConnectButton.title="Start the official REA MCP server and list its live tool catalog.";
  }else{
    reaStatusLabel.textContent="REA SETUP REQUIRED";
    if(reaConnectButton) reaConnectButton.textContent="RETRY";
    if(reaConnectButton) reaConnectButton.title=String(status?.last_error||"Check Node.js/npx and REA configuration.");
  }
  if(reaConnectButton) reaConnectButton.disabled=connected;
}
async function refreshReaStatus(){
  try{
    const response=await fetch("/rea/status?ts="+Date.now(),{cache:"no-store"});
    const status=await response.json();
    if(!response.ok) throw new Error(status?.last_error||status?.error||"REA status unavailable");
    paintReaStatus(status);
  }catch(error){
    paintReaStatus({ready:false,connected:false,last_error:String(error?.message||error)});
    if(reaStatusLabel) reaStatusLabel.title=String(error?.message||error);
  }
}
reaConnectButton?.addEventListener("click",async()=>{
  if(reaConnectButton.disabled) return;
  reaConnectButton.disabled=true;
  reaConnectButton.textContent="CONNECTING…";
  if(reaStatusLabel) reaStatusLabel.textContent="CONNECTING TO OFFICIAL REA MCP…";
  try{
    const response=await fetch("/rea/connect",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:"{}"
    });
    const result=await response.json();
    if(!response.ok||result?.error) throw new Error(result?.error||"REA MCP connection failed");
    paintReaStatus({
      connected:true,ready:true,skill_enabled:result.skill_enabled,
      advertised_tools:result.tool_count,tool_count:result.tool_count
    });
    if(reaStatusLabel) reaStatusLabel.title=(result.tool_examples||[]).join(", ");
  }catch(error){
    const message=String(error?.message||error);
    paintReaStatus({ready:false,connected:false,last_error:message});
    if(reaStatusLabel){
      reaStatusLabel.textContent="REA CONNECTION FAILED";
      reaStatusLabel.title=message;
    }
  }finally{
    if(reaConnectButton) reaConnectButton.disabled=false;
    refreshReaStatus();
  }
});
refreshReaStatus();
setInterval(refreshReaStatus,10000);
refreshModelStatus();


/* Dynamic right-rail layout: use measured panel heights instead of brittle fixed
   top coordinates. The CSS variables only affect desktop/tablet-width layouts. */
(function setupDynamicRightRail() {
  const stage = document.getElementById("stage");
  const systemCard = document.querySelector(".system-card");
  const commandStack = document.querySelector(".command-stack");
  const workspace = document.getElementById("activity-panel");
  if (!stage || !systemCard || !commandStack || !workspace) return;

  let framePending = false;
  const layout = () => {
    if (window.innerWidth <= 1000) {
      stage.style.removeProperty("--jenefar-right-commands-top");
      stage.style.removeProperty("--jenefar-right-workspace-top");
      return;
    }

    const stageTop = stage.getBoundingClientRect().top;
    const systemBottom = systemCard.getBoundingClientRect().bottom - stageTop;
    const commandTop = Math.ceil(systemBottom + 12);
    stage.style.setProperty("--jenefar-right-commands-top", commandTop + "px");

    // Element height is independent of its top coordinate, so this measurement
    // remains stable while the right rail is being repositioned.
    const commandHeight = commandStack.getBoundingClientRect().height;
    const workspaceTop = Math.ceil(commandTop + commandHeight + 12);
    stage.style.setProperty("--jenefar-right-workspace-top", workspaceTop + "px");
  };

  const scheduleLayout = () => {
    if (framePending) return;
    framePending = true;
    requestAnimationFrame(() => {
      framePending = false;
      layout();
    });
  };

  window.addEventListener("resize", scheduleLayout, { passive: true });
  if (typeof ResizeObserver !== "undefined") {
    const observer = new ResizeObserver(scheduleLayout);
    observer.observe(systemCard);
    observer.observe(commandStack);
  }
  scheduleLayout();
  // The initial font/layout pass can change card height after the first frame.
  window.addEventListener("load", scheduleLayout, { once: true });
})();
