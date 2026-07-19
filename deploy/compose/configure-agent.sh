#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ! $1 =~ ^hermes[12]$ ]]; then
  echo "Usage: $0 hermes1|hermes2" >&2
  exit 2
fi

service="$1-agent"

set_config() {
  docker compose run --rm "${service}" config set "$1" "$2"
}

set_config stt.enabled true
set_config stt.provider hermes_speech
set_config stt.providers.hermes_speech.type command
set_config stt.providers.hermes_speech.command \
  "/usr/local/bin/hermes-speech-bridge stt --input {input_path} --output {output_path}"
set_config stt.providers.hermes_speech.output_format txt
set_config stt.providers.hermes_speech.timeout 180

set_config tts.provider hermes_speech
set_config tts.providers.hermes_speech.type command
set_config tts.providers.hermes_speech.command \
  "/usr/local/bin/hermes-speech-bridge tts --input {input_path} --output {output_path} --voice {voice} --speed {speed}"
set_config tts.providers.hermes_speech.output_format wav
set_config tts.providers.hermes_speech.timeout 180

echo "Configured ${service} to use the shared Hermes Speech service."
