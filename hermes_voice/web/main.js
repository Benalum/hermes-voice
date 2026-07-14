const els = {
  chat: document.getElementById("chat"),
  topicSearch: document.getElementById("topic-search"),
  topic: document.getElementById("topic"),
  refreshTopics: document.getElementById("refresh-topics"),
  topicStatus: document.getElementById("topic-status"),
  immersion: document.getElementById("immersion"),
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
let selectedTopicId = null;
let requestedTopicId = null;
let topicReady = false;
let topicSearchTimer = null;
let topicMode = false;
let availableTopics = [];
let transcriptEntries = [];
let transcriptSequence = 0;
let immersionMode = false;

const setState = (name) => {
  els.state.textContent = name;
  els.state.dataset.state = name.startsWith("waiting") ? "waiting" : name;
};

const setTopicStatus = (text) => {
  els.topicStatus.textContent = text;
};

const transcriptSpeakerRuns = () => {
  const runs = [];
  for (const entry of transcriptEntries) {
    if (entry.role !== "user" && entry.role !== "agent") continue;
    const currentRun = runs.at(-1);
    if (currentRun?.role === entry.role) {
      currentRun.entries.push(entry);
    } else {
      runs.push({ role: entry.role, entries: [entry] });
    }
  }
  return runs;
};

const visibleTranscriptEntries = () => {
  if (!immersionMode) return transcriptEntries;
  return transcriptSpeakerRuns()
    .slice(-2)
    .flatMap((run) => run.entries);
};

const renderTranscript = () => {
  const lines = visibleTranscriptEntries().map((entry) => {
    const div = document.createElement("div");
    div.className = `line ${entry.role}`;
    div.textContent = entry.text;
    return div;
  });
  els.transcript.replaceChildren(...lines);
  els.transcript.scrollTop = els.transcript.scrollHeight;
};

const addLine = (role, text) => {
  const normalized = String(text ?? "").trim();
  if (!normalized) return;
  transcriptEntries.push({ role, text: normalized, sequence: transcriptSequence++ });
  renderTranscript();
};

const replaceTranscript = (entries) => {
  transcriptEntries = entries.map((entry) => ({
    role: entry.role,
    text: entry.text,
    sequence: transcriptSequence++,
  }));
  renderTranscript();
};

const clearTranscript = () => {
  transcriptEntries = [];
  els.transcript.replaceChildren();
};

const sendControl = (body) => {
  if (ws?.readyState !== WebSocket.OPEN) return false;
  ws.send(JSON.stringify(body));
  return true;
};

const resetTopicUi = (status = "not connected") => {
  clearTimeout(topicSearchTimer);
  topicSearchTimer = null;
  selectedTopicId = null;
  requestedTopicId = null;
  topicReady = false;
  availableTopics = [];
  els.topicSearch.disabled = true;
  els.topic.disabled = true;
  els.refreshTopics.disabled = true;
  els.topic.replaceChildren(new Option("No topic selected", ""));
  setTopicStatus(status);
};

const requestTopics = () => {
  topicReady = false;
  els.topic.disabled = true;
  setTopicStatus("loading topics…");
  sendControl({ type: "list_topics", query: "", limit: 100 });
};

const matchingTopics = () => {
  const words = els.topicSearch.value
    .trim()
    .toLocaleLowerCase()
    .split(/\s+/)
    .filter(Boolean);
  if (words.length === 0) return availableTopics;
  return availableTopics.filter((topic) => {
    const title = String(topic.title ?? "").toLocaleLowerCase();
    return words.every((word) => title.includes(word));
  });
};

const applyTopicSearch = () => {
  populateTopics(matchingTopics());
};

const selectTopic = (topicId) => {
  if (!Number.isInteger(topicId) || topicId <= 0) return;
  requestedTopicId = topicId;
  selectedTopicId = null;
  topicReady = false;
  clearTranscript();
  els.topic.disabled = true;
  setTopicStatus("loading topic history…");
  sendControl({ type: "select_topic", topic_id: topicId, history_limit: 100 });
};

const renderHistory = (messages) => {
  const entries = messages.flatMap((message) => {
    const role = message.role === "user" ? "user" : "agent";
    const attachment = message.has_attachment ? "📎 Attachment" : "";
    const text = [message.text?.trim(), attachment].filter(Boolean).join("\n");
    return text ? [{ role, text }] : [];
  });
  replaceTranscript(entries);
};

const populateTopics = (topics) => {
  const previousTopicId = selectedTopicId ?? requestedTopicId;
  const options = topics.map((topic) => {
    const option = document.createElement("option");
    option.value = String(topic.topic_id);
    option.textContent = topic.pinned ? `📌 ${topic.title}` : topic.title;
    option.disabled = Boolean(topic.closed);
    return option;
  });

  if (options.length === 0) {
    els.topic.replaceChildren(new Option("No matching topics", ""));
    els.topic.disabled = true;
    if (!els.topicSearch.value.trim()) {
      selectedTopicId = null;
      requestedTopicId = null;
      topicReady = false;
    }
    setTopicStatus("no matching topics");
    return;
  }

  const previousOption = options.find(
    (option) => Number(option.value) === previousTopicId && !option.disabled,
  );
  if (previousOption) {
    els.topic.replaceChildren(...options);
    els.topic.disabled = false;
    previousOption.selected = true;
    if (selectedTopicId === previousTopicId) {
      topicReady = true;
      setTopicStatus("topic ready");
    } else {
      setTopicStatus("loading topic history…");
    }
    return;
  }

  if (previousTopicId !== null) {
    const placeholder = new Option("Choose a topic…", "", true, true);
    placeholder.disabled = true;
    els.topic.replaceChildren(placeholder, ...options);
    els.topic.disabled = false;
    topicReady = false;
    setTopicStatus(`${options.length} matching topics`);
    return;
  }

  els.topic.replaceChildren(...options);
  els.topic.disabled = false;
  const firstAvailable = options.find((option) => !option.disabled);
  if (!firstAvailable) {
    selectedTopicId = null;
    requestedTopicId = null;
    topicReady = false;
    setTopicStatus("all matching topics are closed");
    return;
  }

  firstAvailable.selected = true;
  selectTopic(Number(firstAvailable.value));
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
    if (
      (!topicMode || topicReady)
      && !muted
      && ws?.readyState === WebSocket.OPEN
      && event.data.byteLength > 0
    ) {
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
      topicMode = options.length > 0;
      setState("listening");

      if (topicMode) {
        els.topicSearch.value = "";
        els.topicSearch.disabled = false;
        els.refreshTopics.disabled = false;
        clearTranscript();
        requestTopics();
      } else {
        resetTopicUi("topics unavailable in this mode");
      }
      break;
    }
    case "topics":
      availableTopics = Array.isArray(msg.topics) ? msg.topics : [];
      applyTopicSearch();
      break;
    case "topic_selected":
      if (msg.topic_id === requestedTopicId) {
        setTopicStatus("loading topic history…");
      }
      break;
    case "topic_history": {
      if (msg.topic_id !== requestedTopicId) break;
      const messages = Array.isArray(msg.messages) ? msg.messages : [];
      renderHistory(messages);
      selectedTopicId = msg.topic_id;
      topicReady = true;
      els.topic.disabled = false;
      setTopicStatus(`${messages.length} messages loaded`);
      break;
    }
    case "state":
      setState(msg.name);
      break;
    case "transcript":
      if (msg.final && (!topicMode || topicReady)) addLine("user", msg.text);
      break;
    case "agent_text":
      if (!topicMode || topicReady) addLine("agent", msg.text);
      break;
    case "speak_start":
      currentEpoch = msg.epoch;
      playerReady = ensurePlayer(msg.sample_rate).catch((error) => {
        addLine("agent", `⚠ Audio output failed: ${error.message}`);
      });
      break;
    case "speak_stop":
      if (msg.epoch !== currentEpoch) break;
      if (msg.flush) playerNode?.port.postMessage({ flush: true });
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
      setTopicStatus("request failed");
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

  topicMode = false;
  resetTopicUi();
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
      topicMode = false;
      resetTopicUi();
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
  sendControl({ type: "mute", on: muted });
};
/*
els.stopSpeaking.onclick = () => {
  if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "cancel" }));
};
*/
els.stopSpeaking.onclick = () => {
  sendControl({ type: "cancel" });
};
els.chat.onchange = () => {
  if (ws?.readyState !== WebSocket.OPEN) return;
  clearTranscript();
  resetTopicUi("switching chat…");
  topicMode = true;
  els.topicSearch.value = "";
  els.topicSearch.disabled = false;
  els.refreshTopics.disabled = false;
  sendControl({ type: "select_chat", chat_key: els.chat.value });
  requestTopics();
};
els.topic.onchange = () => {
  selectTopic(Number(els.topic.value));
};
els.refreshTopics.onclick = () => {
  requestTopics();
};
els.topicSearch.oninput = () => {
  clearTimeout(topicSearchTimer);
  topicSearchTimer = setTimeout(() => applyTopicSearch(), 100);
};
els.immersion.onchange = () => {
  immersionMode = els.immersion.checked;
  renderTranscript();
};
window.addEventListener("beforeunload", () => {
  ws?.close();
  for (const track of micStream?.getTracks() ?? []) track.stop();
});
