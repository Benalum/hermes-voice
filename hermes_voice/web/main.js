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
  if (playerCtx && playerCtx.sampleRate === sampleRate) return;
  if (playerCtx) await playerCtx.close();
  playerCtx = new AudioContext({ sampleRate });
  await playerCtx.audioWorklet.addModule("/static/worklets/player.js");
  playerNode = new AudioWorkletNode(playerCtx, "player-processor");
  playerNode.connect(playerCtx.destination);
}

async function startMic() {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      sampleRate: 16000,
      channelCount: 1,
    },
  });
  const micCtx = new AudioContext({ sampleRate: 16000 });
  await micCtx.audioWorklet.addModule("/static/worklets/mic.js");
  const source = micCtx.createMediaStreamSource(stream);
  const micNode = new AudioWorkletNode(micCtx, "mic-processor");
  source.connect(micNode);
  micNode.port.onmessage = (e) => {
    if (!muted && ws?.readyState === WebSocket.OPEN) ws.send(e.data);
  };
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
      ensurePlayer(msg.sample_rate);
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

function handleAudioFrame(buffer) {
  const view = new DataView(buffer);
  const epoch = view.getUint32(0, true);
  if (epoch !== currentEpoch || !playerNode) return;
  playerNode.port.postMessage(buffer.slice(4));
}

async function connect() {
  els.start.disabled = true;
  // Echo mode (M1): server replays mic audio at 16 kHz with epoch 0.
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
  ws.onmessage = (e) => {
    if (typeof e.data === "string") handleControl(JSON.parse(e.data));
    else handleAudioFrame(e.data);
  };
  ws.onclose = () => {
    setState("idle");
    els.start.disabled = false;
    els.mute.disabled = true;
    els.stopSpeaking.disabled = true;
  };
}

els.start.onclick = () => connect().catch((err) => addLine("agent", `⚠ ${err.message}`));
els.mute.onclick = () => {
  muted = !muted;
  els.mute.textContent = muted ? "Unmute" : "Mute";
  ws?.send(JSON.stringify({ type: "mute", on: muted }));
};
els.stopSpeaking.onclick = () => ws?.send(JSON.stringify({ type: "cancel" }));
els.chat.onchange = () => ws?.send(JSON.stringify({ type: "select_chat", chat_key: els.chat.value }));
