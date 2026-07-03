// Captures mono float32 audio, batches into 512-sample int16 frames (silero frame size).
class MicProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Int16Array(512);
    this.offset = 0;
  }

  process(inputs) {
    const channel = inputs[0]?.[0];
    if (!channel) return true;
    for (let i = 0; i < channel.length; i++) {
      const s = Math.max(-1, Math.min(1, channel[i]));
      this.buffer[this.offset++] = s < 0 ? s * 0x8000 : s * 0x7fff;
      if (this.offset === this.buffer.length) {
        this.port.postMessage(this.buffer.slice().buffer, []);
        this.offset = 0;
      }
    }
    return true;
  }
}

registerProcessor("mic-processor", MicProcessor);
