const button = document.getElementById("realtime-button");
const buttonLabel = document.getElementById("realtime-button-label");
const realtimeState = document.getElementById("realtime-state");
let peer = null;
let stream = null;
let dataChannel = null;
let connecting = false;

function avatarEvent(payload) {
  window.dispatchEvent(new CustomEvent("jenefar-avatar-event", { detail: payload }));
}

function setState(text, active = Boolean(peer)) {
  if (realtimeState) {
    realtimeState.textContent = text;
    realtimeState.title = text;
    realtimeState.dataset.active = active ? "true" : "false";
  }
}

function setButton(active, busy = false) {
  if (!button) return;
  button.setAttribute("aria-pressed", String(active));
  button.setAttribute("aria-busy", String(busy));
  button.disabled = busy;
  if (buttonLabel) buttonLabel.textContent = busy ? "CONNECTING…" : active ? "STOP LIVE" : "LIVE VOICE";
  button.title = active
    ? "Stop the live speech-to-speech session"
    : "Start the low-latency natural voice session";
}

async function responseJson(response) {
  let payload = {};
  try { payload = await response.json(); } catch (_) {}
  if (!response.ok) throw new Error(payload.error || ("HTTP " + response.status));
  return payload;
}

// /realtime/tool wraps the broker's JSON string in another JSON response.
// Unwrap both levels so approval_required is handled consistently.
function parseToolResult(payload) {
  let value = payload?.result ?? payload;
  for (let depth = 0; depth < 2 && typeof value === "string"; depth += 1) {
    try { value = JSON.parse(value); }
    catch (_) { return { status: "ok", result: value }; }
  }
  return value && typeof value === "object" ? value : { status: "ok", result: value };
}

function sendToolOutput(callId, payload) {
  if (!dataChannel || dataChannel.readyState !== "open") return;
  dataChannel.send(JSON.stringify({
    type: "conversation.item.create",
    item: {
      type: "function_call_output",
      call_id: callId,
      output: JSON.stringify(payload),
    },
  }));
  dataChannel.send(JSON.stringify({ type: "response.create" }));
}

function approvalDialog(tool, args, pendingId, callId) {
  // Build the dialog with textContent; tool arguments are untrusted model output.
  const overlay = document.createElement("div");
  overlay.className = "approval-overlay";
  const card = document.createElement("div");
  card.className = "approval-card";
  const title = document.createElement("div");
  title.className = "approval-title";
  title.textContent = "JENEFAR ACTION APPROVAL";
  const name = document.createElement("div");
  name.className = "approval-tool";
  name.textContent = tool;
  const details = document.createElement("pre");
  details.textContent = JSON.stringify(args, null, 2);
  const actions = document.createElement("div");
  actions.className = "approval-actions";
  const deny = document.createElement("button");
  deny.type = "button";
  deny.dataset.action = "deny";
  deny.textContent = "DENY";
  const approve = document.createElement("button");
  approve.type = "button";
  approve.dataset.action = "approve";
  approve.textContent = "APPROVE";
  actions.append(deny, approve);
  card.append(title, name, details, actions);
  overlay.appendChild(card);
  document.body.appendChild(overlay);

  const close = () => overlay.remove();
  deny.onclick = () => {
    close();
    setState("ACTION DENIED", true);
    sendToolOutput(callId, {
      status: "denied",
      message: "The user denied the requested action.",
    });
  };

  approve.onclick = async () => {
    actions.querySelectorAll("button").forEach(item => item.disabled = true);
    setState("EXECUTING APPROVED ACTION…", true);
    try {
      const payload = await fetch("/realtime/tool", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approve_id: pendingId }),
      }).then(responseJson);
      close();
      sendToolOutput(callId, parseToolResult(payload));
      setState("LIVE • READY", true);
    } catch (error) {
      close();
      sendToolOutput(callId, { status: "error", error: String(error?.message || error) });
      setState("TOOL ERROR — " + String(error?.message || error).slice(0, 65), true);
    }
  };
}

async function handleRealtimeEvent(raw) {
  let event;
  try { event = JSON.parse(raw); }
  catch (error) {
    console.error("[JENEFAR] Invalid Realtime event", error);
    return;
  }

  try {
    if (event.type?.includes("audio_transcript.delta")) {
      avatarEvent({ state: "speaking", text: event.delta || "", level: 0.58, emotion: "neutral" });
    } else if (event.type?.includes("audio") && !event.type.includes("transcript")) {
      avatarEvent({ state: "speaking", level: event.type.includes("done") ? 0.08 : 0.65, emotion: "neutral" });
    }

    if (event.type?.includes("input_audio")) {
      avatarEvent({ state: "listening", level: 0.12, emotion: "curious" });
    }

    if (event.type === "response.function_call_arguments.done") {
      const args = JSON.parse(event.arguments || "{}");
      const outer = await fetch("/realtime/tool", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: event.name, arguments: args }),
      }).then(responseJson);
      const result = parseToolResult(outer);

      if (result.status === "approval_required" && result.pending_id) {
        avatarEvent({
          state: "waiting_approval",
          text: "Approval required for " + event.name,
          level: 0.15,
          emotion: "alert",
        });
        setState("WAITING FOR APPROVAL", true);
        approvalDialog(event.name, args, result.pending_id, event.call_id);
      } else {
        sendToolOutput(event.call_id, result);
      }
    }

    if (event.type === "response.done") {
      avatarEvent({ state: "idle", level: 0, emotion: "neutral" });
      if (peer) setState("LIVE • READY", true);
    }

    if (event.type === "error") {
      const message = event.error?.message || event.message || "Unknown Realtime error";
      setState("VOICE ERROR — " + String(message).slice(0, 75), Boolean(peer));
      console.error("[JENEFAR] Realtime API error", event);
    }
  } catch (error) {
    console.error("[JENEFAR] Realtime event handling failed", error);
    setState("VOICE EVENT ERROR — " + String(error?.message || error).slice(0, 55), Boolean(peer));
  }
}

async function stopRealtime({ quiet = false } = {}) {
  stream?.getTracks().forEach(track => { try { track.stop(); } catch (_) {} });
  stream = null;
  if (dataChannel) { try { dataChannel.close(); } catch (_) {} }
  if (peer) { try { peer.close(); } catch (_) {} }
  dataChannel = null;
  peer = null;
  connecting = false;
  setButton(false, false);
  setState(quiet ? "STANDARD VOICE" : "LIVE VOICE OFF", false);
  avatarEvent({ state: "idle", level: 0, emotion: "neutral" });
}

async function startRealtime() {
  connecting = true;
  setButton(false, true);
  setState("CONNECTING TO LIVE VOICE…", false);
  try {
    const session = await fetch("/realtime/session", { method: "POST" }).then(responseJson);
    if (!session.value) throw new Error(session.error || "No Realtime client secret");

    peer = new RTCPeerConnection();
    peer.onconnectionstatechange = () => {
      if (!peer) return;
      if (peer.connectionState === "failed" || peer.connectionState === "disconnected") {
        setState("CONNECTION " + peer.connectionState.toUpperCase(), true);
      }
    };
    peer.ontrack = event => {
      const audio = document.getElementById("realtime-audio") || document.createElement("audio");
      audio.id = "realtime-audio";
      audio.autoplay = true;
      audio.playsInline = true;
      audio.srcObject = event.streams[0];
      if (!audio.parentElement) document.body.appendChild(audio);
      audio.play().catch(error => {
        setState("AUDIO PLAYBACK BLOCKED — CLICK PAGE", true);
        console.warn("[JENEFAR] Realtime autoplay may require a page interaction", error);
      });
    };
    dataChannel = peer.createDataChannel("oai-events");
    dataChannel.addEventListener("message", event => handleRealtimeEvent(event.data));
    dataChannel.addEventListener("open", () => setState("LIVE • READY", true));
    dataChannel.addEventListener("close", () => {
      if (peer) setState("LIVE CHANNEL CLOSED", true);
    });

    stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      video: false,
    });
    // Avoid two simultaneous speech-recognition streams and acoustic feedback.
    window.dispatchEvent(new CustomEvent("jenefar-realtime-start"));
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
    if (!response.ok) {
      const detail = await response.text();
      throw new Error("Realtime connection failed (" + response.status + "): " + detail.slice(0, 300));
    }
    await peer.setRemoteDescription({ type: "answer", sdp: await response.text() });
    connecting = false;
    setButton(true, false);
    setState("LIVE • READY", true);
    avatarEvent({ state: "listening", level: 0.12, emotion: "curious" });
  } catch (error) {
    const message = String(error?.message || error || "Unknown error");
    await stopRealtime({ quiet: true });
    setState("LIVE VOICE FAILED — " + message.slice(0, 70), false);
    console.error("[JENEFAR] Could not start live voice", error);
    throw error;
  }
}

button?.addEventListener("click", async () => {
  if (connecting) return;
  if (peer) {
    await stopRealtime();
    return;
  }
  try {
    await startRealtime();
  } catch (_) {
    // The exact failure remains visible in the status strip.
  }
});
