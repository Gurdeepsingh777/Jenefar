const button = document.getElementById("realtime-button");
const realtimeState = document.getElementById("realtime-state");
let peer = null;
let stream = null;
let dataChannel = null;

function avatarEvent(payload) {
  window.dispatchEvent(new CustomEvent("jenefar-avatar-event", { detail: payload }));
}

function setState(text) {
  if (realtimeState) realtimeState.textContent = text;
}

function handleRealtimeEvent(raw) {
  try {
    const event = JSON.parse(raw);
    if (event.type && event.type.includes("audio")) {
      avatarEvent({ state: "speaking", level: event.type.includes("done") ? 0.08 : 0.65, emotion: "neutral" });
    }
    if (event.type === "response.done") {
      avatarEvent({ state: "idle", level: 0, emotion: "neutral" });
    }
    if (event.type && event.type.includes("input_audio")) {
      avatarEvent({ state: "listening", level: 0.12, emotion: "curious" });
    }
  } catch (_) {}
}

async function startRealtime() {
  setState("CONNECTING…");
  const session = await fetch("/realtime/session", { method: "POST" }).then(r => r.json());
  if (!session.value) throw new Error(session.error || "No realtime client secret");

  peer = new RTCPeerConnection();
  peer.ontrack = event => {
    const audio = document.getElementById("realtime-audio") || document.createElement("audio");
    audio.id = "realtime-audio";
    audio.autoplay = true;
    audio.srcObject = event.streams[0];
    if (!audio.parentElement) document.body.appendChild(audio);
  };
  dataChannel = peer.createDataChannel("oai-events");
  dataChannel.addEventListener("message", event => handleRealtimeEvent(event.data));

  stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  stream.getTracks().forEach(track => peer.addTrack(track, stream));

  const offer = await peer.createOffer();
  await peer.setLocalDescription(offer);

  const response = await fetch(
    "https://api.openai.com/v1/realtime/calls?model=" + encodeURIComponent(session.model),
    {
      method: "POST",
      headers: {
        Authorization: "Bearer " + session.value,
        "Content-Type": "application/sdp",
      },
      body: offer.sdp,
    },
  );

  if (!response.ok) throw new Error("Realtime SDP exchange failed: " + await response.text());
  await peer.setRemoteDescription({ type: "answer", sdp: await response.text() });

  setState("LIVE • REALTIME SPEECH");
  avatarEvent({ state: "listening", level: 0.12, emotion: "curious" });
}

async function stopRealtime() {
  stream?.getTracks().forEach(track => track.stop());
  stream = null;
  dataChannel?.close();
  peer?.close();
  dataChannel = null;
  peer = null;
  setState("OFFLINE");
  avatarEvent({ state: "idle", level: 0, emotion: "neutral" });
}

button?.addEventListener("click", async () => {
  try {
    if (peer) await stopRealtime();
    else {
      await startRealtime();
      button.textContent = "STOP REALTIME";
    }
  } catch (error) {
    setState("ERROR");
    console.error(error);
  }
});
