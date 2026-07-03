// Ring-buffer playback of int16 PCM chunks posted from the main thread.
// A {flush: true} message drops everything queued (barge-in).
class PlayerProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.queue = [];
    this.current = null;
    this.pos = 0;
    this.port.onmessage = (e) => {
      if (e.data?.flush) {
        this.queue = [];
        this.current = null;
        this.pos = 0;
        return;
      }
      this.queue.push(new Int16Array(e.data));
    };
  }

  process(_inputs, outputs) {
    const out = outputs[0][0];
    for (let i = 0; i < out.length; i++) {
      if (!this.current || this.pos >= this.current.length) {
        this.current = this.queue.shift() ?? null;
        this.pos = 0;
        if (!this.current) {
          out.fill(0, i);
          return true;
        }
      }
      out[i] = this.current[this.pos++] / 0x8000;
    }
    return true;
  }
}

registerProcessor("player-processor", PlayerProcessor);
