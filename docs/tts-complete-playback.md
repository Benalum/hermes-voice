# Complete TTS Playback

## Problem

Hermes Voice could stop speaking before reaching the end of an otherwise
complete model response.

The cutoff had multiple contributing causes:

1. Speech normalization enforced a hard 1,500-character limit.
2. Text beyond that limit was replaced with
   `message truncated, see Telegram`.
3. Normal `speak_stop` messages caused the browser AudioWorklet queue to be
   flushed even though playback had not finished.
4. Persistent cancellation state could affect later replies.
5. PCM transmission completion was treated too similarly to audible playback
   completion.

The epoch comparison was investigated and retained. Epoch validation correctly
prevents genuinely canceled or obsolete speech from leaking into a newer turn.

## Kokoro verification

Kokoro was tested independently with:

- more than 2,400 characters in one synthesis call;
- approximately 94 seconds of generated audio;
- the same input split into Hermes-style sentence blocks;
- approximately 98 seconds of sentence-block audio;
- non-empty PCM output for every sentence.

Kokoro successfully synthesized all text it received. The observed cutoff was
caused by the surrounding application pipeline rather than a general Kokoro
duration limitation.

## Fix

The TTS pipeline now:

- distinguishes normal completion from cancellation;
- preserves queued browser audio during normal completion;
- flushes browser audio only during cancellation or barge-in;
- streams PCM in bounded frames near playback speed;
- pre-synthesizes the next sentence to reduce pauses;
- retains epoch protection against stale audio;
- removes persistent cancellation state;
- makes the spoken-text limit configurable.

## Configuration

`HV_MAX_SPOKEN_CHARS` controls the normalized spoken-text limit:

- a positive integer limits speech to that many characters;
- `0` disables character-based truncation;
- an unset or invalid value uses the repository default.

Example systemd configuration for unlimited speech:

```ini
[Service]
Environment=HV_MAX_SPOKEN_CHARS=0
```

The repository default is 12,000 characters. Individual deployments can choose
a different safety limit or disable the limit explicitly.

## Live verification

The corrected deployment successfully read a 20-sentence response without
prematurely stopping and without producing the old truncation notice.

Stop Speech, chat changes, and genuine barge-in events continue to advance the
epoch and discard obsolete audio.
