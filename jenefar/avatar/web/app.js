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

function draw(t){
  ctx.clearRect(0,0,width,height);
  const centerX=width/2,centerY=height*.46;
  const [r,g,b]=palette(currentState);
  particles.forEach((p,i)=>{
    p.a+=p.speed;
    p.phase+=.01;
    const stateBoost=currentState==="speaking"?1.8:currentState==="thinking"?1.15:1;
    const rr=p.r + Math.sin(p.phase+t*.001)*18*stateBoost;
    const x=centerX+Math.cos(p.a)*rr;
    const y=centerY+Math.sin(p.a)*rr*.78;
    const alpha=.15+.18*(Math.sin(p.phase)+1)/2;
    const size=p.size*(currentState==="speaking"?1.35:1);
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
  stage.dataset.state=currentState;
  const [stateText,caption]=labels[currentState]||["ACTIVE",event.text||""];
  stateEl.textContent=stateText;
  captionEl.textContent=event.text||caption;
  const [r,g,b]=palette(currentState);
  dot.style.background=`rgb(${r},${g},${b})`;
  dot.style.boxShadow=`0 0 18px rgb(${r},${g},${b})`;
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
