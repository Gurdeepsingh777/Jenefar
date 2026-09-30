const stage=document.getElementById("stage");
const canvas=document.getElementById("particles");
const ctx=canvas.getContext("2d");
const stateEl=document.getElementById("state");
const captionEl=document.getElementById("caption");
const dot=document.querySelector(".pulse-dot");

const labels={
  idle:["IDLE","Jenefar is ready"],
  listening:["LISTENING","I'm listening…"],
  thinking:["THINKING","Processing your request…"],
  speaking:["SPEAKING","Jenefar is responding"],
  waiting_approval:["WAITING APPROVAL","A tool needs confirmation"]
};

let width=0,height=0,dpr=1;
let particles=[];

function resize(){
  dpr=Math.min(window.devicePixelRatio||1,2);
  width=window.innerWidth;height=window.innerHeight;
  canvas.width=width*dpr;canvas.height=height*dpr;
  ctx.setTransform(dpr,0,0,dpr,0,0);
  particles=Array.from({length:Math.min(260,Math.floor(width/5))},()=>seedParticle());
}
function seedParticle(){
  const angle=Math.random()*Math.PI*2;
  const radius=Math.random()*Math.min(width,height)*.42+40;
  return{
    a:angle,
    r:radius,
    speed:.0015+Math.random()*.0035,
    drift:(Math.random()-.5)*.08,
    size:.6+Math.random()*2.1,
    phase:Math.random()*Math.PI*2
  };
}
function palette(state){
  if(state==="speaking") return [103,232,255];
  if(state==="thinking") return [167,139,250];
  if(state==="listening") return [109,255,214];
  if(state==="waiting_approval") return [255,187,92];
  return [133,147,255];
}
let currentState="idle";
let speechLevel=0;
let emotion="neutral";
let emotionIntensity=0;

function draw(t){
  ctx.clearRect(0,0,width,height);
  const workWidth = width * 0.66;
  const centerX=workWidth/2,centerY=height*.46;
  const [r,g,b]=palette(currentState);
  const activity = currentState==="speaking" ? speechLevel : currentState==="thinking" ? .22 : currentState==="listening" ? .10 : 0;
  particles.forEach((p,i)=>{
    p.a+=p.speed;
    p.phase+=.01;
    const stateBoost=currentState==="speaking" ? 1.25 + activity * 1.7 : currentState==="thinking" ? 1.15 : 1;
    const rr=p.r + Math.sin(p.phase+t*.001)*18*stateBoost;
    const x=centerX+Math.cos(p.a)*rr;
    const y=centerY+Math.sin(p.a)*rr*.78;
    const alpha=.15+.18*(Math.sin(p.phase)+1)/2;
    const size=p.size*(currentState==="speaking" ? 1.05 + activity * 1.8 : 1);
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

function apply(event){
  currentState=event.state||"idle";
  speechLevel=Number(event.level||0);
  stage.dataset.state=currentState;
  emotion=event.emotion||"neutral";
  emotionIntensity=Number(event.intensity||0);
  stage.style.setProperty("--speech-level", speechLevel.toFixed(3));
  stage.style.setProperty("--emotion-intensity", emotionIntensity.toFixed(3));
  stage.dataset.emotion=emotion;
  window.dispatchEvent(new CustomEvent("jenefar-avatar-event", { detail: event }));
  addActivity(event);
  if(currentState==="waiting_approval") showApproval(event);
  const [stateText,caption]=labels[currentState]||["ACTIVE",event.text||""];
  stateEl.textContent=stateText;
  captionEl.textContent=event.text||caption;
  if (currentState === "speaking") {
    document.body.dataset.voiceActive = "true";
  } else if (currentState === "idle" || currentState === "listening") {
    document.body.dataset.voiceActive = "false";
  }
  const [r,g,b]=palette(currentState);
  dot.style.background=`rgb(${r},${g},${b})`;
  dot.style.boxShadow=`0 0 18px rgb(${r},${g},${b})`;
}

const activityList=document.getElementById("activity-list");
let lastActivityKey="";
const approvalDialogs=new Map();

function addActivity(event){
  if(!activityList) return;
  const text=String(event.text||"").trim();
  if(!text && !event.state) return;
  const key=String(event.state||"")+"|"+text;
  if(key===lastActivityKey && event.state!=="error") return;
  lastActivityKey=key;
  const row=document.createElement("div");
  row.className="activity-item activity-"+(event.state||"idle");
  const when=new Date().toLocaleTimeString();
  row.innerHTML="<span class='activity-time'>"+when+"</span><span class='activity-state'>"+String(event.state||"").toUpperCase()+"</span><span class='activity-text'></span>";
  row.querySelector(".activity-text").textContent=text || "Jenefar is active";
  activityList.prepend(row);
  while(activityList.children.length>80) activityList.removeChild(activityList.lastChild);
}

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
    }finally{ close(); }
  };
  overlay.querySelector("[data-action='approve']").onclick=async()=>{
    overlay.querySelectorAll("button").forEach(button=>button.disabled=true);
    try{
      await fetch("/realtime/tool",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({approve_id:pendingId})});
    }finally{ close(); }
  };
}

function connect(){
  const source=new EventSource("/events");
  source.onmessage=(message)=>{
    try{apply(JSON.parse(message.data));}catch(_){ }
  };
  source.onerror=()=>{source.close();setTimeout(connect,1200);};
}

window.addEventListener("resize",resize);
resize();
connect();
requestAnimationFrame(draw);

 


const micButton=document.getElementById("mic-button");
const voiceInputStatus=document.getElementById("voice-input-status");
let recognition=null;
let voiceShouldRun=true;
let voiceSupported=false;
let restartTimer=null;

function setVoiceInputStatus(text, active=false){
  if(voiceInputStatus){
    voiceInputStatus.textContent=text;
    voiceInputStatus.dataset.active=active ? "true" : "false";
  }
}

function browserSpeakFallback(text){
  if(!text || !("speechSynthesis" in window)) return;
  try{
    window.speechSynthesis.cancel();
    const utterance=new SpeechSynthesisUtterance(text);
    utterance.lang="hi-IN";
    utterance.rate=0.98;
    utterance.pitch=1.02;
    window.speechSynthesis.speak(utterance);
  }catch(_){}
}

async function sendBrowserTranscript(text){
  const clean=String(text||"").trim();
  if(!clean) return;
  setVoiceInputStatus("HEARD: "+clean, true);
  addActivity({state:"listening",text:"You: "+clean});
  try{
    const response=await fetch("/voice/text",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({text:clean})
    });
    const result=await response.json();
    if(result?.ignored) return;
    if(result?.error){
      addActivity({state:"error",text:"Voice error: "+result.error});
      setVoiceInputStatus("VOICE ERROR",false);
      return;
    }
    if(result?.reply){
      addActivity({state:"speaking",text:result.reply});
    }
    if(!result?.spoken && result?.reply){
      browserSpeakFallback(result.reply);
    }
    if(result?.exit){
      voiceShouldRun=false;
      recognition?.stop();
    }
  }catch(error){
    addActivity({state:"error",text:"Voice request failed: "+error});
    setVoiceInputStatus("VOICE CONNECTION ERROR",false);
  }
}

function setupBrowserVoice(){
  const Recognition=window.SpeechRecognition || window.webkitSpeechRecognition;
  if(!Recognition){
    voiceSupported=false;
    voiceShouldRun=false;
    setVoiceInputStatus("BROWSER SPEECH UNSUPPORTED",false);
    if(micButton) micButton.textContent="PYTHON MIC";
    return;
  }

  voiceSupported=true;
  recognition=new Recognition();
  recognition.lang="hi-IN";
  recognition.continuous=true;
  recognition.interimResults=false;
  recognition.maxAlternatives=1;

  recognition.onstart=()=>{
    setVoiceInputStatus("BROWSER MIC: LISTENING",true);
    if(micButton) micButton.textContent="MIC OFF";
  };

  recognition.onresult=(event)=>{
    for(let i=event.resultIndex;i<event.results.length;i++){
      const result=event.results[i];
      if(result.isFinal){
        const text=(result[0]?.transcript||"").trim();
        if(text) sendBrowserTranscript(text);
      }
    }
  };

  recognition.onerror=(event)=>{
    const code=event.error||"unknown";
    addActivity({state:"error",text:"Browser mic: "+code});
    if(code==="not-allowed" || code==="service-not-allowed"){
      voiceShouldRun=false;
      setVoiceInputStatus("MIC PERMISSION DENIED",false);
      if(micButton) micButton.textContent="MIC ON";
    }else{
      setVoiceInputStatus("MIC RETRYING…",false);
    }
  };

  recognition.onend=()=>{
    if(!voiceShouldRun) return;
    if(restartTimer) clearTimeout(restartTimer);
    restartTimer=setTimeout(()=>{
      try{ recognition.start(); }catch(_){}
    },500);
  };

  if(micButton){
    micButton.onclick=()=>{
      if(!voiceSupported) return;
      if(voiceShouldRun){
        voiceShouldRun=false;
        try{ recognition.stop(); }catch(_){}
        setVoiceInputStatus("BROWSER MIC: OFF",false);
        micButton.textContent="MIC ON";
      }else{
        voiceShouldRun=true;
        try{ recognition.start(); }catch(_){}
      }
    };
  }

  setTimeout(()=>{
    if(!voiceShouldRun) return;
    try{ recognition.start(); }catch(_){}
  },700);
}

setupBrowserVoice();
