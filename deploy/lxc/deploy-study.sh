#!/usr/bin/env bash
set -Eeuo pipefail

CT="${1:-}"
BRANCH="${HERMES_STUDY_BRANCH:-agent/portable-study-sessions}"

if [[ "$CT" != "102" && "$CT" != "103" ]]; then
  echo "Usage: $0 102|103" >&2
  exit 2
fi

pct status "$CT"

pct exec "$CT" -- env HERMES_STUDY_BRANCH="$BRANCH" bash -s <<'CT_SCRIPT'
set -Eeuo pipefail

REPO=/opt/hermes-voice
SERVICE=hermes-voice.service
BRANCH="${HERMES_STUDY_BRANCH:?}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="/var/backups/hermes-voice-study/$STAMP"
DROPIN_DIR=/etc/systemd/system/hermes-voice.service.d
DROPIN="$DROPIN_DIR/study.conf"
ROLLBACK_ARMED=false
OLD_HEAD=

rollback() {
  local rc=$?
  trap - ERR
  if [[ "$ROLLBACK_ARMED" == true ]]; then
    echo "Deployment failed; restoring the previous Hermes Voice state." >&2
    cd "$REPO"
    git switch --detach "$OLD_HEAD" || true
    if [[ -f "$BACKUP/study-before.tgz" ]]; then
      rm -rf /var/lib/hermes-voice/study
      tar -C /var/lib/hermes-voice -xzf "$BACKUP/study-before.tgz"
    fi
    rm -rf "$DROPIN_DIR"
    if [[ -d "$BACKUP/hermes-voice.service.d" ]]; then
      cp -a "$BACKUP/hermes-voice.service.d" "$DROPIN_DIR"
    fi
    systemctl daemon-reload || true
    systemctl restart "$SERVICE" || true
    systemctl --no-pager --full status "$SERVICE" || true
  fi
  exit "$rc"
}
trap rollback ERR

[[ -d "$REPO/.git" ]] || { echo "Missing repository: $REPO" >&2; exit 1; }
[[ -x "$REPO/.venv/bin/python" ]] || { echo "Missing virtual environment" >&2; exit 1; }

mkdir -p "$BACKUP"
git config --global --add safe.directory "$REPO" 2>/dev/null || true

cd "$REPO"
OLD_HEAD="$(git rev-parse HEAD)"
printf '%s\n' "$OLD_HEAD" > "$BACKUP/previous-head.txt"
systemctl cat "$SERVICE" > "$BACKUP/hermes-voice.service.txt"
cp -a "$DROPIN_DIR" "$BACKUP/" 2>/dev/null || true
ROLLBACK_ARMED=true

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Refusing to deploy over uncommitted changes:" >&2
  git status --short >&2
  exit 1
fi

if [[ -d /var/lib/hermes-voice/study ]]; then
  tar -C /var/lib/hermes-voice -czf "$BACKUP/study-before.tgz" study
fi

git fetch --no-tags origin "refs/heads/$BRANCH"
git switch -C deploy/study FETCH_HEAD
NEW_HEAD="$(git rev-parse HEAD)"
printf '%s\n' "$NEW_HEAD" > "$BACKUP/deployed-head.txt"

"$REPO/.venv/bin/python" -m compileall -q hermes_voice tests
if "$REPO/.venv/bin/python" -m pytest --version >/dev/null 2>&1; then
  runuser -u hermes -- env HOME=/home/hermes \
    "$REPO/.venv/bin/python" -m pytest -q tests/study
fi

install -d -o hermes -g hermes -m 0700 /var/lib/hermes-voice/study
install -d -m 0755 "$DROPIN_DIR"
cat > "$DROPIN" <<'UNIT'
[Service]
Environment=HV_STUDY_DIR=/var/lib/hermes-voice/study
ExecStart=
ExecStart=/opt/hermes-voice/.venv/bin/uvicorn hermes_voice.server.study_app:create_app --factory --host 127.0.0.1 --port 8990 --log-level info
UNIT

systemctl daemon-reload
systemctl restart "$SERVICE"

for attempt in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8990/healthz >/tmp/hermes-study-health.json; then
    break
  fi
  sleep 1
done

curl -fsS http://127.0.0.1:8990/healthz
printf '\n'

curl -fsS http://127.0.0.1:8990/study \
  --output /tmp/hermes-study-page.html
grep -q 'Hermes Study' /tmp/hermes-study-page.html

curl -fsS -X POST \
  http://127.0.0.1:8990/api/study/content-packs/mcat-phase-1-v1 \
  >/tmp/hermes-phase1-pack.json

"$REPO/.venv/bin/python" - <<'PY'
import json
from pathlib import Path
from urllib.request import urlopen

legacy = {
    'MCAT Biology: Cells, Genetics & Organ Systems',
    'MCAT Biochemistry: Amino Acids, Enzymes & Metabolism',
    'MCAT General & Organic Chemistry',
    'MCAT Physics: Mechanics, Fluids, Circuits & Optics',
    'MCAT Psychology & Sociology',
    'MCAT CARS: Passage Reasoning',
}
base = 'http://127.0.0.1:8990'
pack = json.loads(Path('/tmp/hermes-phase1-pack.json').read_text())
decks = json.load(urlopen(f'{base}/api/study/decks'))['decks']
progress = json.load(urlopen(
    f'{base}/api/study/curricula/mcat-medical-foundations-phase-1/progress'
))['progress']
result = pack['result']

assert len(decks) == 22, len(decks)
assert not ({deck['name'] for deck in decks} & legacy), decks
assert sum(int(deck['card_count']) for deck in decks) == 660, decks
assert min(int(deck['card_count']) for deck in decks) >= 30, decks
assert result['courses'] == 22, result
assert result['bindings'] == 22, result
assert result['total_cards'] == 660, result
assert result['media_attached'] + result['media_skipped'] == 44, result
assert len(progress['courses']) == 22, progress
assert sum(
    int(deck['bound'])
    for course in progress['courses']
    for deck in course['decks']
) == 22, progress
assert progress['next_deck'] is not None, progress

print(json.dumps({
    'pack_result': result,
    'phase1_decks': len(decks),
    'phase1_cards': sum(int(deck['card_count']) for deck in decks),
    'phase1_visuals': result['media_attached'] + result['media_skipped'],
    'curriculum_bindings': result['bindings'],
    'next_deck': progress['next_deck'],
}, indent=2))
PY

systemctl --no-pager --full status "$SERVICE"
ROLLBACK_ARMED=false
trap - ERR
echo "Backup and rollback metadata: $BACKUP"
echo "Previous commit: $OLD_HEAD"
echo "Deployed commit: $NEW_HEAD"
CT_SCRIPT
