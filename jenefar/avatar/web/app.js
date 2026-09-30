const stage=document.getElementById("stage");
const canvas=document.getElementById("particles");
const ctx=canvas.getContext("2d");
const stateEl=document.getElementById("state");
const captionEl=document.getElementById("caption");
const dot=document.querySelector(".pulse-dot");
const activityList=document.getElementById("activity-list");
const runningCount=document.getElementById("activity-running");
const queuedCount=document.getElementById("activity-queued");
const doneCount=document.getElementById("activity-done");
const errorCount=document.getElementById("activity-errors");

const labels={
  idle:["IDLE","Jenefar is ready"],
  queued:["QUEUED","Task added to queue"],
  listening:["LISTENING","I'm listening…"],
  thinking:["THINKING","Processing your request…"],
  result:["RESULT","Result ready"],
  speaking:["SPEAKING","Jenefar is responding"],
  speaking_fallback:["SPEAKING","Using browser voice fallback"],
  completed:["DONE","Task completed"],
  waiting_approval:["WAITING APPROVAL","A tool needs confirmation"],
  error:["ERROR","Task needs attention"]
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

function activityBucket(state){
  if(state==="error") return "errors";
  if(state==="completed"||state==="result") return "results";
  if(state==="queued"||state==="thinking"||state==="speaking"||state==="speaking_fallback") return "running";
  return "all";
}

function addActivity(event){
  if(!activityList) return;
  const text=String(event.text||"").trim();
  const state=String(event.state||"idle");
  const taskId=String(event.task_id||"");
  if(taskId) taskState.set(taskId,state);
  updateTaskCounts();

  const key=state+"|"+taskId+"|"+text.slice(0,160);
  if(key===lastActivityKey && state!=="error") return;
  lastActivityKey=key;

  const bucket=activityBucket(state);
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
  preview.textContent=text||"Jenefar is active";
  main.appendChild(meta);
  main.appendChild(preview);

  if(text.length>260){
    const details=document.createElement("details");
    const summary=document.createElement("summary");
    summary.textContent="View full output";
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
if(clearActivityButton){
  clearActivityButton.onclick=()=>{
    activityList.innerHTML="";
    taskState.clear();
    updateTaskCounts();
    lastActivityKey="";
  };
}

function setupActivityFilters(){
  document.querySelectorAll("[data-activity-filter]").forEach(button=>{
    button.addEventListener("click",()=>{
      activityFilter=button.dataset.activityFilter||"all";
      document.querySelectorAll("[data-activity-filter]").forEach(item=>{
        item.dataset.active=String(item===button);
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
  overlay.querySelector(".approval-tool").textContent=String(event.text||"Approval required");
  overlay.querySelector("pre").textContent="Pending ID: "+pendingId;
  document.body.appendChild(overlay);
  approvalDialogs.set(pendingId,overlay);
  const close=()=>{approvalDialogs.delete(pendingId);overlay.remove();};
  overlay.querySelector("[data-action='deny']").onclick=async()=>{
    try{
      await fetch("/approval/reject",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({approve_id:pendingId})});
    }finally{close();}
  };
  overlay.querySelector("[data-action='approve']").onclick=async()=>{
    overlay.querySelectorAll("button").forEach(button=>button.disabled=true);
    try{
      await fetch("/realtime/tool",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({approve_id:pendingId}));
    }finally{close();}
  };
}

function pauseBrowserVoice(){
  voiceLocked=true;
  if(restartTimer) clearTimeout(restartTimer);
  try{recognition?.stop();}catch(_){}
  setVoiceInputStatus("BROWSER MIC: PAUSED WHILE JENEFAR SPEAKS",false);
}

function resumeBrowserVoice(){
  if(!micEnabled||voiceLocked) return;
  if("speechSynthesis" in window && window.speechSynthesis.speaking) return;
  if(restartTimer) clearTimeout(restartTimer);
  restartTimer=setTimeout(()=>{
    if(!micEnabled||voiceLocked) return;
    try{recognition?.start();}catch(_){}
  },450);
}

function browserSpeakFallback(text){
  if(!text||!("speechSynthesis" in window)) return;
  try{
    browserSpeechActive=true;
    pauseBrowserVoice();
    window.speechSynthesis.cancel();
    const utterance=new SpeechSynthesisUtterance(text);
    utterance.lang="hi-IN";
    utterance.rate=.98;
    utterance.pitch=1.02;
    utterance.onend=()=>{browserSpeechActive=false;resumeBrowserVoice();};
    utterance.onerror=()=>{browserSpeechActive=false;resumeBrowserVoice();};
    window.speechSynthesis.speak(utterance);
  }catch(_){}
}

function apply(event){
  currentState=event.state||"idle";
  speechLevel=Number(event.level||0);
  stage.dataset.state=currentState;
  emotion=event.emotion||"neutral";
  emotionIntensity=Number(event.intensity||0);
  stage.style.setProperty("--speech-level",speechLevel.toFixed(3));
  stage.style.setProperty("--emotion-intensity",emotionIntensity.toFixed(3));
  stage.dataset.emotion=emotion;
  window.dispatchEvent(new CustomEvent("jenefar-avatar-event",{detail:event}));
  addActivity(event);

  if(currentState==="waiting_approval") showApproval(event);
  if(currentState==="speaking"||currentState==="speaking_fallback"){
    pauseBrowserVoice();
    if(currentState==="speaking_fallback") browserSpeakFallback(event.text||"");
  }else if(currentState==="idle"||currentState==="completed"){
    voiceLocked=false;
    resumeBrowserVoice();
  }

  const [stateText,caption]=labels[currentState]||["ACTIVE",event.text||""];
  stateEl.textContent=stateText;
  captionEl.textContent=event.text||caption;

  if(currentState==="speaking"||currentState==="speaking_fallback"){
    document.body.dataset.voiceActive="true";
  }else if(currentState==="idle"||currentState==="listening"||currentState==="completed"){
    document.body.dataset.voiceActive="false";
  }

  const [r,g,b]=palette(currentState);
  dot.style.background=`rgb(${r},${g},${b})`;
  dot.style.boxShadow=`0 0 18px rgb(${r},${g},${b})`;
}

function connect(){
  const source=new EventSource("/events");
  source.onmessage=(message)=>{
    try{apply(JSON.parse(message.data));}catch(_){}
  };
  source.onerror=()=>{
    source.close();
    setTimeout(connect,1200);
  };
}

/* Browser voice */
const micButton=document.getElementById("mic-button");
const voiceInputStatus=document.getElementById("voice-input-status");
let recognition=null;
let micEnabled=true;
let voiceLocked=false;
let voiceSupported=false;
let restartTimer=null;
let browserSpeechActive=false;

function setVoiceInputStatus(text,active=false){
  if(voiceInputStatus){
    voiceInputStatus.textContent=text;
    voiceInputStatus.dataset.active=active?"true":"false";
  }
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
      resumeBrowserVoice();
      return;
    }
    if(result?.error){
      addActivity({state:"error",text:"Voice error: "+result.error});
      setVoiceInputStatus("VOICE ERROR",false);
      resumeBrowserVoice();
      return;
    }
    if(result?.accepted){
      setVoiceInputStatus("TASK "+String(result.task_id||"")+" QUEUED",true);
    }
    if(result?.exit){
      micEnabled=false;
      voiceLocked=true;
      try{recognition?.stop();}catch(_){}
      setVoiceInputStatus("VOICE OFF",false);
    }else{
      voiceLocked=false;
      resumeBrowserVoice();
    }
  }catch(error){
    addActivity({state:"error",text:"Voice request failed: "+error});
    setVoiceInputStatus("VOICE CONNECTION ERROR",false);
    voiceLocked=false;
    resumeBrowserVoice();
  }
}

function setupBrowserVoice(){
  const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;

  async function requestMicrophonePermission(){
    if(!navigator.mediaDevices?.getUserMedia){
      setVoiceInputStatus("MIC API UNSUPPORTED",false);
      return false;
    }
    try{
      setVoiceInputStatus("MIC PERMISSION: CLICK ALLOW",true);
      const stream=await navigator.mediaDevices.getUserMedia({audio:true,video:false});
      stream.getTracks().forEach(track=>track.stop());
      setVoiceInputStatus("MIC PERMISSION GRANTED",true);
      return true;
    }catch(error){
      const code=error?.name||"unknown";
      addActivity({state:"error",text:"Microphone permission: "+code});
      if(code==="NotAllowedError"||code==="SecurityError"){
        micEnabled=false;
        voiceLocked=true;
        setVoiceInputStatus("MIC BLOCKED — USE SITE SETTINGS TO ALLOW",false);
        if(micButton) micButton.textContent="MIC ON";
      }else{
        setVoiceInputStatus("MIC ERROR: "+code,false);
      }
      return false;
    }
  }

  if(micButton){
    micButton.onclick=async()=>{
      if(!voiceSupported) return;
      if(micEnabled){
        micEnabled=false;
        voiceLocked=true;
        try{recognition?.stop();}catch(_){}
        setVoiceInputStatus("BROWSER MIC: OFF",false);
        micButton.textContent="MIC ON";
      }else{
        micEnabled=true;
        voiceLocked=false;
        const granted=await requestMicrophonePermission();
        if(!granted) return;
        setVoiceInputStatus("BROWSER MIC: STARTING",false);
        resumeBrowserVoice();
      }
    };
  }

  if(!Recognition){
    voiceSupported=false;
    micEnabled=false;
    setVoiceInputStatus("BROWSER SPEECH UNSUPPORTED",false);
    if(micButton) micButton.textContent="MIC UNSUPPORTED";
    return;
  }

  voiceSupported=true;
  recognition=new Recognition();
  recognition.lang="hi-IN";
  recognition.continuous=true;
  recognition.interimResults=false;
  recognition.maxAlternatives=1;

  recognition.onstart=()=>{
    if(voiceLocked||!micEnabled){try{recognition.stop();}catch(_){};return;}
    setVoiceInputStatus("BROWSER MIC: LISTENING",true);
    if(micButton) micButton.textContent="MIC OFF";
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
      if(micButton) micButton.textContent="MIC ON";
    }else{
      setVoiceInputStatus("MIC RETRYING…",false);
    }
  };

  recognition.onend=()=>{
    if(!micEnabled||voiceLocked||browserSpeechActive) return;
    resumeBrowserVoice();
  };

  // Do not auto-start SpeechRecognition on page load. Browser permission prompts
  // are more reliable when microphone access follows a user gesture.
  micEnabled=false;
  voiceLocked=true;
  setVoiceInputStatus("CLICK MIC ON TO START",false);
  if(micButton) micButton.textContent="MIC ON";
}

setupActivityFilters();
window.addEventListener("resize",resize);
resize();
connect();
requestAnimationFrame(draw);
setupBrowserVoice();
