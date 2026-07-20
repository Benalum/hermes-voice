const NativeWebSocket = window.WebSocket;

const DEFAULT_SPEED = 1.0;
const DEFAULT_END_SILENCE_MS = 768;
const SPEED_KEY = "hv_speech_speed";
const END_SILENCE_KEY = "hv_end_silence_ms";

const els = {
  speed: document.getElementById("speech-speed"),
  speedValue: document.getElementById("speech-speed-value"),
  endSilence: document.getElementById("end-silence"),
  endSilenceValue: document.getElementById("end-silence-value"),
};

let activeSocket = null;
let sendTimer = null;

const clamp = (value, minimum, maximum) => Math.min(maximum, Math.max(minimum, value));

const storedNumber = (key, fallback) => {
  const value = Number.parseFloat(localStorage.getItem(key) ?? "");
  return Number.isFinite(value) ? value : fallback;
};

const currentSettings = () => ({
  speech_speed: clamp(Number.parseFloat(els.speed.value), 0.5, 2.0),
  end_silence_ms: Math.round(
    clamp(Number.parseInt(els.endSilence.value, 10), 320, 4992) / 32,
  ) * 32,
});

const render = () => {
  const settings = currentSettings();
  els.speed.value = settings.speech_speed.toFixed(2);
  els.endSilence.value = String(settings.end_silence_ms);
  els.speedValue.value = `${settings.speech_speed.toFixed(2)}×`;
  els.speedValue.textContent = els.speedValue.value;
  els.endSilenceValue.value = `${(settings.end_silence_ms / 1000).toFixed(1)} s`;
  els.endSilenceValue.textContent = els.endSilenceValue.value;
  return settings;
};

const persist = () => {
  const settings = render();
  localStorage.setItem(SPEED_KEY, String(settings.speech_speed));
  localStorage.setItem(END_SILENCE_KEY, String(settings.end_silence_ms));
  return settings;
};

const sendSettings = (socket = activeSocket) => {
  if (!socket || socket.readyState !== NativeWebSocket.OPEN) return false;
  const settings = persist();
  socket.send(JSON.stringify({ type: "voice_settings", ...settings }));
  return true;
};

const scheduleSend = () => {
  persist();
  clearTimeout(sendTimer);
  sendTimer = setTimeout(() => sendSettings(), 80);
};

els.speed.value = String(clamp(storedNumber(SPEED_KEY, DEFAULT_SPEED), 0.5, 2.0));
els.endSilence.value = String(
  Math.round(clamp(storedNumber(END_SILENCE_KEY, DEFAULT_END_SILENCE_MS), 320, 4992) / 32) * 32,
);
render();

els.speed.addEventListener("input", scheduleSend);
els.endSilence.addEventListener("input", scheduleSend);

window.WebSocket = new Proxy(NativeWebSocket, {
  construct(Target, args) {
    const socket = Reflect.construct(Target, args);
    let isVoiceSocket = false;
    try {
      const url = new URL(String(args[0]), window.location.href);
      isVoiceSocket = url.pathname === "/ws";
    } catch {
      isVoiceSocket = false;
    }

    if (!isVoiceSocket) return socket;
    activeSocket = socket;

    socket.addEventListener("message", (event) => {
      if (typeof event.data !== "string") return;
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }
      if (message.type === "ready") {
        sendSettings(socket);
        return;
      }
      if (message.type !== "voice_settings_state") return;
      if (Number.isFinite(message.speech_speed)) {
        els.speed.value = String(clamp(message.speech_speed, 0.5, 2.0));
      }
      if (Number.isInteger(message.end_silence_ms)) {
        els.endSilence.value = String(clamp(message.end_silence_ms, 320, 4992));
      }
      persist();
    });

    socket.addEventListener("close", () => {
      if (activeSocket === socket) activeSocket = null;
    });
    return socket;
  },
});
