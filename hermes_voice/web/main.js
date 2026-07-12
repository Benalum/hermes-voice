const els = {
  chat: document.getElementById("chat"),
  start: document.getElementById("start"),
  mute: document.getElementById("mute"),
  stopSpeaking: document.getElementById("stop-speaking"),
  state: document.getElementById("state"),
  transcript: document.getElementById("transcript"),
};

let ws = null;
let muted = false;
let currentEpoch = 0;
let playerNode = null;
let playerCtx = null;
let playerReady = Promise.resolve();
let micCtx = null;
let micNode = null;
let micStream = null;

const setState = (name) => {
  els.state.textContent = name;
  els.state.dataset.state = name.startsWith("waiting") ? "waiting" : name;
};

const addLine = (role, text) => {
  const div = document.createElement("div");
  div.className = `line ${role}`;
  div.textContent = text;
  els.transcript.appendChild(div);
  els.transcript.scrollTop = els.transcript.scrollHeight;
};

async function ensurePlayer(sampleRate) {
  if (playerCtx && playerCtx.sampleRate === sampleRate && playerNode) return;
  if (playerCtx) await playerCtx.close();
  playerCtx = new AudioContext({ sampleRate });
  await playerCtx.audioWorklet.addModule("/static/worklets/player.js");
  playerNode = new AudioWorkletNode(playerCtx, "player-processor");
  playerNode.connect(playerCtx.destination);
  await playerCtx.resume();
}

async function stopMic() {
  if (micNode) micNode.port.onmessage = null;
  micNode?.disconnect();
  micNode = null;
  for (const track of micStream?.getTracks() ?? []) track.stop();
  micStream = null;
  if (micCtx) await micCtx.close();
  micCtx = null;
}

async function startMic() {
  await stopMic();
  micStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      sampleRate: 16000,
      channelCount: 1,
    },
  });
  micCtx = new AudioContext({ sampleRate: 16000 });
  await micCtx.audioWorklet.addModule("/static/worklets/mic.js");
  const source = micCtx.createMediaStreamSource(micStream);
  micNode = new AudioWorkletNode(micCtx, "mic-processor");
  source.connect(micNode);
  micNode.port.onmessage = (event) => {
    if (!muted && ws?.readyState === WebSocket.OPEN && event.data.byteLength > 0) {
      ws.send(event.data);
    }
  };
  await micCtx.resume();
}

function handleControl(msg) {
  switch (msg.type) {
    case "ready": {
      const options = msg.chats.map((chat) => {
        const opt = document.createElement("option");
        opt.value = chat.key;
        opt.textContent = chat.label;
        if (chat.key === msg.active_chat) opt.selected = true;
        return opt;
      });
      els.chat.replaceChildren(...options);
      els.chat.disabled = options.length === 0;
      setState("listening");
      break;
    }
    case "state":
      setState(msg.name);
      break;
    case "transcript":
      if (msg.final) addLine("user", msg.text);
      break;
    case "agent_text":
      addLine("agent", msg.text);
      break;
    case "speak_start":
      currentEpoch = msg.epoch;
      playerReady = ensurePlayer(msg.sample_rate).catch((error) => {
        addLine("agent", `⚠ Audio output failed: ${error.message}`);
      });
      break;
    case "speak_stop":
      playerNode?.port.postMessage({ flush: true });
      break;
    case "error":
      if (msg.message.includes("invalid token")) {
        const token = prompt("Gateway token:");
        if (token) {
          localStorage.setItem("hv_token", token);
          location.reload();
        }
        break;
      }
      addLine("agent", `⚠ ${msg.message}`);
      break;
  }
}

async function handleAudioFrame(buffer) {
  if (buffer.byteLength < 4) return;
  const view = new DataView(buffer);
  const epoch = view.getUint32(0, true);
  if (epoch !== currentEpoch) return;
  await playerReady;
  if (!playerNode) return;
  playerNode.port.postMessage(buffer.slice(4));
}

/*
Old disconnect function

async function disconnect() {
  const socket = ws;
  ws = null;
  if (socket && socket.readyState < WebSocket.CLOSING) socket.close();
  await stopMic();
}
*/

async function disconnect() {
  const socket = ws;
  ws = null;

  // Immediately discard any audio already queued for playback.
  playerNode?.port.postMessage({ flush: true });

  // Stop microphone delivery before closing the socket so no more
  // audio frames can be sent while the connection is shutting down.
  await stopMic();

  if (socket && socket.readyState < WebSocket.CLOSING) {
    socket.close(1000, "user stopped session");
  }

  muted = false;
  els.mute.textContent = "Mute";

  setState("idle");
  els.start.disabled = false;
  els.mute.disabled = true;
  els.stopSpeaking.disabled = true;
}

async function connect() {
  if (ws && ws.readyState < WebSocket.CLOSING) return;
  els.start.disabled = true;
  try {
    await ensurePlayer(16000);
    await startMic();
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.binaryType = "arraybuffer";
    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "hello", token: localStorage.getItem("hv_token") ?? "" }));
      els.mute.disabled = false;
      els.stopSpeaking.disabled = false;
    };
    ws.onmessage = (event) => {
      if (typeof event.data === "string") {
        try {
          handleControl(JSON.parse(event.data));
        } catch (error) {
          addLine("agent", `⚠ Invalid server message: ${error.message}`);
        }
      } else {
        handleAudioFrame(event.data);
      }
    };
    ws.onerror = () => addLine("agent", "⚠ WebSocket connection failed");
    ws.onclose = async () => {
      ws = null;
      await stopMic();
      setState("idle");
      els.start.disabled = false;
      els.mute.disabled = true;
      els.stopSpeaking.disabled = true;
    };
  } catch (error) {
    await disconnect();
    els.start.disabled = false;
    throw error;
  }
}

els.start.onclick = () => connect().catch((error) => addLine("agent", `⚠ ${error.message}`));
els.mute.onclick = () => {
  muted = !muted;
  els.mute.textContent = muted ? "Unmute" : "Mute";
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "mute", on: muted }));
  }
};
/*
els.stopSpeaking.onclick = () => {
  if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "cancel" }));
};
*/
els.stopSpeaking.onclick = () => {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "cancel" }));
  }
};
els.chat.onchange = () => {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "select_chat", chat_key: els.chat.value }));
  }
};
window.addEventListener("beforeunload", () => {
  ws?.close();
  for (const track of micStream?.getTracks() ?? []) track.stop();
});
