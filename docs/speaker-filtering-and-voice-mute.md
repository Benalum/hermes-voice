# Speaker filtering and voice mute

Hermes Voice provides two related local controls:

- **Speaker filtering** compares each completed utterance with enrolled voice
  samples before speech-to-text (STT). Rejected audio is not transcribed or
  forwarded.
- **Command mute** continues local STT only so an unmute command can be found,
  while suppressing every ordinary transcript before Telegram or the agent.

These controls share the server as their authority. Clicking the browser button
or saying a command changes the same mute state, and the browser updates after
the server acknowledges that state.

## Privacy boundary

Command mute is not a hard microphone mute.

| State | Browser sends audio to Hermes server | Local STT runs | Ordinary transcript reaches Telegram or the agent | Speech can interrupt reply playback |
|---|---:|---:|---:|---:|
| Unmuted | Yes | Yes | Yes | Yes |
| Command-muted | Yes | Yes, to detect unmute | No | No |
| Browser/OS microphone disabled | No | No | No | No |

Use the browser or operating-system microphone control when audio must not leave
the client device. Command mute is intended for hands-free pause/resume control:
audio stops at the Hermes Voice server, but the server must still listen for
“unmute me.”

## Install speaker-filter support

Install the normal speech backend plus the optional speaker-filter dependencies:

```bash
uv sync --locked --extra speech --extra speaker-filter --group dev
```

The extra installs Resemblyzer for embeddings, Resampy and SoundFile for WAV
conversion, and SoundDevice for optional direct microphone enrollment.
Resemblyzer's VAD dependency may compile a small native extension. On Ubuntu,
install `build-essential`; direct recording also needs the PortAudio runtime.

## Configure the gate

Add this section to `~/.hermes-voice/config.toml`:

```toml
[speaker_gate]
enabled = true
threshold = 0.75
store = "~/.hermes-voice/speakers.json"
```

The default threshold is `0.75`. A higher value is stricter; a lower value
accepts more variation but increases the chance that another person is accepted.
Do not lower it based on one rejected phrase. First enroll samples from the same
microphone and browser audio path used in normal operation, then compare several
same-speaker and different-speaker scores.

If the gate is enabled with no profiles, or if the encoder cannot load, the gate
fails open so the existing voice pipeline remains usable. Check service logs and
verify enrollment before relying on it as an access boundary.

## Enroll a speaker

Record 10–15 seconds of clear, natural speech. A 16 kHz mono signed 16-bit PCM
WAV is preferred, although the enrollment script converts other WAV rates.

On a Linux desktop using PulseAudio or PipeWire compatibility:

```bash
ffmpeg -f pulse -i default \
  -t 15 -ac 1 -ar 16000 -c:a pcm_s16le \
  alex-enrollment.wav
```

Copy the recording to the Hermes Voice host if the microphone is on another
machine, then enroll it from the repository root:

```bash
uv run python scripts/enroll_speaker.py \
  --name alex \
  --wav /path/to/alex-enrollment.wav
```

Direct recording is also available when PortAudio exposes a default input:

```bash
uv run python scripts/enroll_speaker.py --name alex --record 10
```

If `python -m sounddevice` lists no input device or recording fails with device
`-1`, record on the browser machine and use `--wav` instead.

### Multiple microphones and headsets

Enroll each normal audio path under the same name. Enrollment appends a new
embedding, and verification accepts the best matching sample:

```bash
uv run python scripts/enroll_speaker.py \
  --name alex --wav alex-laptop-enrollment.wav

uv run python scripts/enroll_speaker.py \
  --name alex --wav alex-headset-enrollment.wav
```

Browser echo cancellation, noise suppression, automatic gain control, headset
DSP, and VAD segmentation can make live utterances differ substantially from a
clean desktop recording. If offline verification is strong but live scores are
low, enroll a sample captured through the same browser and selected microphone
used for Hermes Voice.

Restart the service after changing profiles or configuration so the active
process reloads the store:

```bash
sudo systemctl restart hermes-voice.service
```

The speech models can take several seconds to warm. Wait for “Application
startup complete” or a successful health check before reconnecting:

```bash
curl -fsS http://127.0.0.1:8990/healthz
journalctl -fu hermes-voice.service
```

## Voice commands and browser button

The command recognizer accepts a complete command rather than triggering on a
phrase embedded in an ordinary sentence. Examples include:

- `Hermes mute me`
- `Hey Hermes, please mute me`
- `Mute`
- `Stop listening`
- `Hermes unmute me`
- `Start listening`
- `Hermes, can you listen to me please`

While unmuted, a mute command switches to command mute and is not forwarded.
While muted, ordinary speech is discarded at the server; only an unmute command
changes the state. The browser button follows the same rules:

- Clicking **Mute** keeps the WebSocket and microphone capture active.
- The server acknowledges the state and the button changes to **Unmute**.
- Saying “Hermes unmute me” can unmute a session that was muted by the button.
- Clicking **Unmute** can unmute a session that was muted by voice.
- Saying “Hermes mute me” during a reply mutes the session without stopping that
  reply; command recognition is resolved before a pending barge-in is applied.
- Muted speech never triggers barge-in or stops reply playback. Once unmuted,
  speaking during playback can interrupt it normally.

Mute state belongs to the current voice session and is reset when a new session
connects.

## Validate and tune

Use a separate verification recording that was not used for enrollment. Watch
the live decision logs while trying short and long phrases from each supported
microphone:

```bash
journalctl -fu hermes-voice.service
```

A healthy log entry includes the accepted decision, best similarity score,
configured threshold, speaker label, and utterance duration. Test all of these:

1. Enrolled speaker through the laptop microphone.
2. Enrolled speaker through each headset or phone audio path.
3. Several short and long phrases.
4. Background noise and silence.
5. A different speaker, with permission, to measure separation.

Choose a threshold below the lowest legitimate score but above the highest
different-speaker score, leaving margin for real-world variation. If those score
ranges overlap, collect better device-matched enrollment samples instead of
weakening the threshold.

## Protect enrollment data

Voice recordings and embeddings are sensitive data:

```bash
chmod 700 ~/.hermes-voice
chmod 600 ~/.hermes-voice/speakers.json
```

Do not commit enrollment/verification WAVs, `speakers.json`, gateway tokens,
Telegram credentials, or Telethon session files. Delete temporary recordings
from transfer locations after confirming the profile works.

## Tests

The focused model-free checks are:

```bash
uv run pytest -q \
  tests/kit/test_speaker_gate.py \
  tests/kit/test_voice_mute.py \
  tests/kit/test_protocol.py \
  tests/server/test_orchestrator_loop.py \
  tests/web/test_sticky_voice_controls.py

uv run ruff check .
uv run ruff format --check .
```

The orchestrator tests cover button/voice synchronization, suppression of muted
transcripts, spoken unmute after button mute, and the rule that muted speech does
not interrupt active playback.
