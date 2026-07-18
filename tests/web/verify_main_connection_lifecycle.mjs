import assert from "node:assert/strict";

class FakeElement {
  constructor() {
    this.children = [];
    this.dataset = {};
    this.disabled = false;
    this.value = "";
    this.textContent = "";
    this.checked = false;
    this.scrollHeight = 0;
    this.scrollTop = 0;
    this.onclick = null;
    this.onchange = null;
    this.oninput = null;
    this.attributes = new Map();
  }

  replaceChildren(...children) {
    this.children = children;
  }

  setAttribute(name, value) {
    this.attributes.set(name, value);
  }
}

const elements = new Map();
const element = (id) => {
  if (!elements.has(id)) elements.set(id, new FakeElement());
  return elements.get(id);
};

globalThis.document = {
  getElementById: element,
  createElement: () => new FakeElement(),
};
globalThis.Option = class Option extends FakeElement {
  constructor(text, value, defaultSelected = false, selected = false) {
    super();
    this.textContent = text;
    this.value = value;
    this.defaultSelected = defaultSelected;
    this.selected = selected;
  }
};
globalThis.window = { addEventListener() {} };
globalThis.location = {
  protocol: "http:",
  host: "example.test",
  reload() {},
};
globalThis.localStorage = {
  getItem() { return "token"; },
  setItem() {},
};
globalThis.prompt = () => null;

const sockets = [];
class FakeWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  constructor(url) {
    this.url = url;
    this.readyState = FakeWebSocket.CONNECTING;
    this.sent = [];
    this.closeCalls = [];
    sockets.push(this);
  }

  send(data) {
    this.sent.push(data);
  }

  close(code, reason) {
    this.closeCalls.push([code, reason]);
    this.readyState = FakeWebSocket.CLOSING;
  }
}
globalThis.WebSocket = FakeWebSocket;

const workletNodes = [];
class FakeAudioWorkletNode {
  constructor(_context, name) {
    this.name = name;
    this.port = {
      onmessage: null,
      messages: [],
      postMessage: (message) => this.port.messages.push(message),
    };
    workletNodes.push(this);
  }

  connect() {}
  disconnect() {}
}
globalThis.AudioWorkletNode = FakeAudioWorkletNode;

class FakeAudioContext {
  constructor({ sampleRate }) {
    this.sampleRate = sampleRate;
    this.state = "running";
    this.destination = {};
    this.audioWorklet = { addModule: async () => {} };
  }

  createMediaStreamSource() {
    return { connect() {} };
  }

  async resume() {}

  async close() {
    this.state = "closed";
  }
}
globalThis.AudioContext = FakeAudioContext;

const streams = [];
Object.defineProperty(globalThis, "navigator", {
  configurable: true,
  value: {
    mediaDevices: {
      async getUserMedia() {
        const track = { stopped: false, stop() { this.stopped = true; } };
        const stream = { track, getTracks: () => [track] };
        streams.push(stream);
        return stream;
      },
    },
  },
});

await import("../../hermes_voice/web/main.js?connection-lifecycle-test");

const start = element("start");
const mute = element("mute-indicator");
const state = element("state");

await start.onclick();
assert.equal(sockets.length, 1);
const first = sockets[0];
first.readyState = FakeWebSocket.OPEN;
first.onopen();
first.onmessage({
  data: JSON.stringify({
    type: "ready",
    chats: [
      {
        key: "hermes",
        label: "Hermes",
      },
    ],
    active_chat: "hermes",
  }),
});
assert.equal(state.textContent, "listening");
assert.equal(mute.disabled, false);

const firstMic = workletNodes.find((node) => node.name === "mic-processor");
assert.ok(firstMic);

const topicMicCallback = firstMic.port.onmessage;
const beforeTopicSelection = first.sent.length;

topicMicCallback({
  data: new Uint8Array([1]).buffer,
});
assert.equal(first.sent.length, beforeTopicSelection);

first.onmessage({
  data: JSON.stringify({
    type: "topics",
    topics: [
      {
        topic_id: 98,
        title: "System",
        pinned: false,
        closed: false,
      },
    ],
  }),
});
assert.equal(first.sent.length, beforeTopicSelection + 1);

topicMicCallback({
  data: new Uint8Array([2]).buffer,
});
assert.equal(first.sent.length, beforeTopicSelection + 1);

first.onmessage({
  data: JSON.stringify({
    type: "topic_history",
    topic_id: 98,
    messages: [],
  }),
});

topicMicCallback({
  data: new Uint8Array([3]).buffer,
});
assert.equal(first.sent.length, beforeTopicSelection + 2);

first.onmessage({
  data: JSON.stringify({ type: "mute_state", on: true, source: "button" }),
});
const beforeMutedAudio = first.sent.length;
topicMicCallback({
  data: new Uint8Array([4]).buffer,
});
assert.equal(first.sent.length, beforeMutedAudio + 1);
assert.equal(mute.textContent, "Muted");
assert.equal(mute.attributes.get("aria-pressed"), "true");

const chat = element("chat");
chat.value = "333";
chat.onchange();
const beforeTopiclessChatAudio = first.sent.length;
topicMicCallback({
  data: new Uint8Array([5]).buffer,
});
assert.equal(first.sent.length, beforeTopiclessChatAudio);

first.onmessage({
  data: JSON.stringify({ type: "topics", topics: [] }),
});
topicMicCallback({
  data: new Uint8Array([6]).buffer,
});
assert.equal(first.sent.length, beforeTopiclessChatAudio + 1);

const staleMicCallback = topicMicCallback;
const firstSendCount = first.sent.length;

first.readyState = FakeWebSocket.CLOSING;
await start.onclick();
assert.equal(sockets.length, 2);
const second = sockets[1];
second.readyState = FakeWebSocket.OPEN;
second.onopen();
second.onmessage({
  data: JSON.stringify({ type: "ready", chats: [], active_chat: null }),
});
const secondSendCount = second.sent.length;
assert.equal(state.textContent, "listening");
assert.equal(mute.disabled, false);
assert.equal(start.disabled, true);

first.onmessage({
  data: JSON.stringify({ type: "state", name: "stale" }),
});
first.onerror();
first.onclose();
await new Promise((resolve) => setTimeout(resolve, 0));

assert.equal(state.textContent, "listening");
assert.equal(mute.disabled, false);
assert.equal(start.disabled, true);

staleMicCallback({ data: new Uint8Array([1]).buffer });
assert.equal(first.sent.length, firstSendCount);
assert.equal(second.sent.length, secondSendCount);

second.readyState = FakeWebSocket.CLOSED;
second.onclose();
await new Promise((resolve) => setTimeout(resolve, 0));

assert.equal(state.textContent, "idle");
assert.equal(mute.disabled, true);
assert.equal(start.disabled, false);
assert.equal(streams[0].track.stopped, true);
assert.equal(streams[1].track.stopped, true);
