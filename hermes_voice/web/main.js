import {
  ConnectionGuard,
  guardConnectionCallback,
} from "./connection_guard.mjs";

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

const connectionGuard = new ConnectionGuard();
let activeConnection = null;
let muted = false;
let currentEpoch = 0;
let playerNode = null;
let playerCtx = null;
let playerReady = Promise.resolve();
let micSession = null;
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

  const scroller = document.scrollingElement;
  if (scroller) {
    scroller.scrollTop = scroller.scrollHeight;
  } else {
    els.transcript.scrollTop = els.transcript.scrollHeight;
  }
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

const isCurrentConnection = (connection) => (
  connectionGuard.isCurrent(connection)
  && activeConnection === connection
);

const sendControl = (body) => {
  const connection = activeConnection;
  if (!isCurrentConnection(connection)) return false;
  if (connection.socket.readyState !== WebSocket.OPEN) return false;
  connection.socket.send(JSON.stringify(body));
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

async function closeAudioContext(context) {
  if (!context || context.state === "closed") return;
  try {
    await context.close();
  } catch (error) {
    console.warn("Audio context cleanup failed", error);
  }
}

async function ensurePlayer(sampleRate, connection) {
  if (!isCurrentConnection(connection)) return false;
  if (playerCtx && playerCtx.sampleRate === sampleRate && playerNode) return true;

  const nextContext = new AudioContext({ sampleRate });
  let nextNode = null;
  try {
    await nextContext.audioWorklet.addModule("/static/worklets/player.js");
    if (!isCurrentConnection(connection)) {
      await closeAudioContext(nextContext);
      return false;
    }

    nextNode = new AudioWorkletNode(nextContext, "player-processor");
    nextNode.connect(nextContext.destination);
    await nextContext.resume();
    if (!isCurrentConnection(connection)) {
      nextNode.disconnect();
      await closeAudioContext(nextContext);
      return false;
    }

    const previousContext = playerCtx;
    playerCtx = nextContext;
    playerNode = nextNode;
    if (previousContext && previousContext !== nextContext) {
      await closeAudioContext(previousContext);
    }
    return true;
  } catch (error) {
    nextNode?.disconnect();
    await closeAudioContext(nextContext);
    throw error;
  }
}

async function stopMic(connection = null) {
  const session = micSession;
  if (!session) return;
  if (connection && session.connection !== connection) return;

  micSession = null;
  session.node.port.onmessage = null;
  session.node.disconnect();
  for (const track of session.stream.getTracks()) track.stop();
  await closeAudioContext(session.context);
}

async function startMic(connection) {
  await stopMic();

  let stream = null;
  let context = null;
  let node = null;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        sampleRate: 16000,
        channelCount: 1,
      },
    });
    if (!isCurrentConnection(connection)) {
      for (const track of stream.getTracks()) track.stop();
      return false;
    }

    context = new AudioContext({ sampleRate: 16000 });
    await context.audioWorklet.addModule("/static/worklets/mic.js");
    if (!isCurrentConnection(connection)) {
      for (const track of stream.getTracks()) track.stop();
      await closeAudioContext(context);
      return false;
    }

    const source = context.createMediaStreamSource(stream);
    node = new AudioWorkletNode(context, "mic-processor");
    source.connect(node);
    const session = { connection, context, node, stream };
    micSession = session;
    node.port.onmessage = guardConnectionCallback(
      connectionGuard,
      connection,
      (event) => {
        if (micSession !== session) return;
        if (
          (!topicMode || topicReady)
          && !muted
          && connection.socket.readyState === WebSocket.OPEN
          && event.data.byteLength > 0
        ) {
          connection.socket.send(event.data);
        }
      },
    );
    await context.resume();
    if (!isCurrentConnection(connection)) {
      await stopMic(connection);
      return false;
    }
    return true;
  } catch (error) {
    if (micSession?.connection === connection) {
      await stopMic(connection);
    } else {
      node?.disconnect();
      for (const track of stream?.getTracks() ?? []) track.stop();
      await closeAudioContext(context);
    }
    throw error;
  }
}

function handleControl(msg, connection) {
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
      playerReady = ensurePlayer(msg.sample_rate, connection).catch((error) => {
        if (isCurrentConnection(connection)) {
          addLine("agent", `⚠ Audio output failed: ${error.message}`);
        }
        return false;
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

async function handleAudioFrame(buffer, connection) {
  if (!isCurrentConnection(connection) || buffer.byteLength < 4) return;
  const view = new DataView(buffer);
  const epoch = view.getUint32(0, true);
  if (epoch !== currentEpoch) return;
  await playerReady;
  if (!isCurrentConnection(connection) || !playerNode) return;
  playerNode.port.postMessage(buffer.slice(4));
}

function resetConnectionUi() {
  muted = false;
  els.mute.textContent = "Mute";
  topicMode = false;
  resetTopicUi();
  setState("idle");
  els.start.disabled = false;
  els.mute.disabled = true;
  els.stopSpeaking.disabled = true;
}

async function disconnectConnection(connection, { closeSocket = true } = {}) {
  if (!connection) return false;
  const wasCurrent = connectionGuard.invalidate(connection);
  if (wasCurrent && activeConnection === connection) activeConnection = null;

  if (wasCurrent) playerNode?.port.postMessage({ flush: true });
  await stopMic(connection);

  if (closeSocket && connection.socket.readyState < WebSocket.CLOSING) {
    connection.socket.close(1000, "user stopped session");
  }

  if (!wasCurrent || activeConnection !== null) return false;
  resetConnectionUi();
  return true;
}

async function disconnect() {
  const connection = activeConnection;
  if (!connection) {
    resetConnectionUi();
    return;
  }
  await disconnectConnection(connection);
}

async function connect() {
  const existing = activeConnection;
  if (existing && existing.socket.readyState < WebSocket.CLOSING) return;

  els.start.disabled = true;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${proto}://${location.host}/ws`);
  const connection = connectionGuard.activate(socket);
  activeConnection = connection;
  currentEpoch = 0;
  playerNode?.port.postMessage({ flush: true });

  socket.binaryType = "arraybuffer";
  socket.onopen = guardConnectionCallback(
    connectionGuard,
    connection,
    () => {
      socket.send(JSON.stringify({
        type: "hello",
        token: localStorage.getItem("hv_token") ?? "",
      }));
      els.mute.disabled = false;
      els.stopSpeaking.disabled = false;
    },
  );
  socket.onmessage = guardConnectionCallback(
    connectionGuard,
    connection,
    (event) => {
      if (typeof event.data === "string") {
        try {
          handleControl(JSON.parse(event.data), connection);
        } catch (error) {
          if (isCurrentConnection(connection)) {
            addLine("agent", `⚠ Invalid server message: ${error.message}`);
          }
        }
      } else {
        void handleAudioFrame(event.data, connection).catch((error) => {
          if (isCurrentConnection(connection)) {
            addLine("agent", `⚠ Audio playback failed: ${error.message}`);
          }
        });
      }
    },
  );
  socket.onerror = guardConnectionCallback(
    connectionGuard,
    connection,
    () => addLine("agent", "⚠ WebSocket connection failed"),
  );
  socket.onclose = () => {
    void disconnectConnection(connection, { closeSocket: false });
  };

  try {
    playerReady = ensurePlayer(16000, connection);
    await playerReady;
    if (!isCurrentConnection(connection)) return;
    await startMic(connection);
  } catch (error) {
    const disconnectedCurrent = await disconnectConnection(connection);
    if (disconnectedCurrent) throw error;
  }
}

els.start.onclick = () => connect().catch((error) => addLine("agent", `⚠ ${error.message}`));
els.mute.onclick = () => {
  muted = !muted;
  els.mute.textContent = muted ? "Unmute" : "Mute";
  sendControl({ type: "mute", on: muted });
};
els.stopSpeaking.onclick = () => {
  sendControl({ type: "cancel" });
};
els.chat.onchange = () => {
  if (!sendControl({ type: "select_chat", chat_key: els.chat.value })) return;
  clearTranscript();
  resetTopicUi("switching chat…");
  topicMode = true;
  els.topicSearch.value = "";
  els.topicSearch.disabled = false;
  els.refreshTopics.disabled = false;
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
  activeConnection?.socket.close();
  for (const track of micSession?.stream.getTracks() ?? []) track.stop();
});
