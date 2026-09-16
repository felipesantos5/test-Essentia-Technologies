#!/usr/bin/env bash
# End-to-end smoke test against the running stack (`make up`).
# Always checks the API, the n8n webhook routing and the nginx proxy. When OPENAI_API_KEY is set
# in .env it also runs a text and an audio conversation turn and saves the audio reply.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
API_URL="${API_URL:-http://localhost:8000/api/v1}"
WEBHOOK_URL="${WEBHOOK_URL:-http://localhost:8080/webhook/clinic-chat}"
OUTPUT_DIR="${OUTPUT_DIR:-$ROOT_DIR/tmp/smoke}"
AUDIO_SAMPLE="$ROOT_DIR/docs/samples/pergunta-pagamento.wav"

env_value() { grep -E "^$1=" "$ROOT_DIR/.env" 2>/dev/null | tail -1 | cut -d= -f2- || true; }
API_KEY="$(env_value CLINIC_API_KEY)"
OPENAI_KEY="$(env_value OPENAI_API_KEY)"
SESSION_ID="smoke-$(date +%s)"
mkdir -p "$OUTPUT_DIR"

passed=0
failed=0
ok() { echo "  ✔ $1"; passed=$((passed + 1)); }
fail() { echo "  ✘ $1"; failed=$((failed + 1)); }

# expect_status <description> <expected status> <curl args...>
expect_status() {
  local description="$1" expected="$2"
  shift 2
  local status
  status="$(curl -s -o "$OUTPUT_DIR/last.json" -w '%{http_code}' "$@")"
  if [ "$status" = "$expected" ]; then ok "$description ($status)"; else fail "$description (got $status, expected $expected)"; fi
}

# json_field <file> <dotted.path>
json_field() {
  python3 -c 'import json, sys
value = json.load(open(sys.argv[1]))
for key in sys.argv[2].split("."):
    value = value[key]
print(value)' "$1" "$2"
}

echo "API ($API_URL)"
expect_status "health" 200 "$API_URL/health"
expect_status "rejects missing API key" 401 "$API_URL/specialties"
expect_status "payment info" 200 -H "X-API-Key: $API_KEY" "$API_URL/payment-info"
expect_status "availability" 200 -H "X-API-Key: $API_KEY" "$API_URL/availability"

echo "n8n webhook ($WEBHOOK_URL)"
expect_status "invalid request goes to the fallback branch" 400 -X POST -F "session_id=$SESSION_ID" "$WEBHOOK_URL"

if [ -z "$OPENAI_KEY" ]; then
  echo "  ⚠ OPENAI_API_KEY is empty in .env: skipping conversation checks"
else
  expect_status "text message" 200 -X POST -F "session_id=$SESSION_ID" \
    -F "message=Quais são as formas de pagamento?" "$WEBHOOK_URL"
  if [ "$(json_field "$OUTPUT_DIR/last.json" type)" = "text" ]; then
    reply="$(json_field "$OUTPUT_DIR/last.json" reply_text)"
    ok "text in, text out: ${reply:0:90}…"
  else
    fail "text message should get a text reply"
  fi

  expect_status "audio message" 200 -X POST -F "session_id=$SESSION_ID-audio" \
    -F "audio=@$AUDIO_SAMPLE;type=audio/wav" "$WEBHOOK_URL"
  if [ "$(json_field "$OUTPUT_DIR/last.json" type)" = "audio" ]; then
    json_field "$OUTPUT_DIR/last.json" audio.base64 | base64 --decode > "$OUTPUT_DIR/reply.mp3"
    ok "audio in, audio out: transcript \"$(json_field "$OUTPUT_DIR/last.json" transcript)\""
    ok "audio reply saved to ${OUTPUT_DIR#"$ROOT_DIR"/}/reply.mp3 ($(wc -c < "$OUTPUT_DIR/reply.mp3" | tr -d ' ') bytes)"
  else
    fail "audio message should get an audio reply"
  fi
fi

echo
echo "passed: $passed, failed: $failed"
[ "$failed" -eq 0 ]
