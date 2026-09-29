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

function sendToolOutput(callId, payload) {
  if (!dataChannel) return;
  dataChannel.send(JSON.stringify({
    type: "conversation.item.create",
    item: {
      type: "function_call_output",
      call_id: callId,
      output: JSON.stringify(payload),
    },
  }));
  dataChannel.send(JSON.stringify({type: "response.create"}));
}

function approvalDialog(tool, args, pendingId, callId) {
  const overlay = document.createElement("div");
  overlay.className = "approval-overlay";
  overlay.innerHTML = `
    <div class="approval-card">
      <div class="approval-title">JENEFAR ACTION APPROVAL</div>
      <div class="approval-tool">${tool}</div>
      <pre>${JSON.stringify(args, null, 2)}</pre>
      <div class="approval-actions">
        <button data-action="deny">DENY</button>
        <button data-action="approve">APPROVE</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  const close = () => overlay.remove();
  overlay.querySelector('[data-action="deny"]').onclick = () => {
    close();
    setState("LIVE • ACTION DENIED");
    sendToolOutput(callId, {
      status: "denied",
      message: "User denied the requested local action.",
    });
  };

  overlay.querySelector('[data-action="approve"]').onclick = async () => {
    overlay.querySelectorAll("button").forEach(item => item.disabled = true);
    setState("EXECUTING APPROVED ACTION…");
    try {
      const response = await fetch("/realtime/tool", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({approve_id: pendingId}),
      }).then(result => result.json());

      close();
      sendToolOutput(callId, response.result || response);
      setState("LIVE • REALTIME SPEECH");
    } catch (error) {
      close();
      sendToolOutput(callId, {
        status: "error",
        error: String(error),
      });
      setState("LIVE • REALTIME SPEECH");
    }
  };
}

async function handleRealtimeEvent(raw) {
  try {
    const event = JSON.parse(raw);

    if (event.type && event.type.includes("audio_transcript.delta")) {
      avatarEvent({
        state: "speaking",
        text: event.delta || "",
        level: 0.58,
        emotion: "neutral",
      });
    } else if (event.type && event.type.includes("audio") && !event.type.includes("transcript")) {
      avatarEvent({
        state: "speaking",
        level: event.type.includes("done") ? 0.08 : 0.65,
        emotion: "neutral",
      });
    }

    if (event.type && event.type.includes("input_audio")) {
      avatarEvent({ state: "listening", level: 0.12, emotion: "curious" });
    }

    if (event.type === "response.function_call_arguments.done") {
      const args = JSON.parse(event.arguments || "{}");
      const response = await fetch("/realtime/tool", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          name: event.name,
          arguments: args,
        }),
      }).then(result => result.json());

      const result = response.result || response;
      if (result.status === "approval_required" && result.pending_id) {
        avatarEvent({
          state: "waiting_approval",
          text: `Approval required for ${event.name}`,
          level: 0.15,
          emotion: "alert",
        });
        approvalDialog(
          event.name,
          args,
          result.pending_id,
          event.call_id,
        );
      } else {
        sendToolOutput(event.call_id, result);
      }
    }

    if (event.type === "response.done") {
      avatarEvent({ state: "idle", level: 0, emotion: "neutral" });
      setState(peer ? "LIVE • REALTIME SPEECH" : "OFFLINE");
    }
  } catch (error) {
    console.error("Realtime event error", error);
  }
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
