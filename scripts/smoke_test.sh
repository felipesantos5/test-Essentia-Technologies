#!/usr/bin/env bash
# Smoke test ponta a ponta contra a stack no ar (`make up`).
# Sempre confere a API, o roteamento do webhook no n8n e o proxy do nginx. Com OPENAI_API_KEY
# preenchida no .env, também roda um turno de texto e um de áudio e salva a resposta em áudio.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
API_URL="${API_URL:-http://localhost:8000/api/v1}"
WEB_URL="${WEB_URL:-http://localhost:8080}"
WEBHOOK_URL="${WEBHOOK_URL:-$WEB_URL/webhook/clinic-chat}"
OUTPUT_DIR="${OUTPUT_DIR:-$ROOT_DIR/tmp/smoke}"
AUDIO_SAMPLE="$ROOT_DIR/docs/samples/pergunta-pagamento.wav"
MAX_TIME=130 # um pouco acima do proxy_read_timeout do nginx

env_value() { grep -E "^$1=" "$ROOT_DIR/.env" 2>/dev/null | tail -1 | cut -d= -f2- || true; }
API_KEY="$(env_value CLINIC_API_KEY)"
OPENAI_KEY="$(env_value OPENAI_API_KEY)"
SESSION_ID="smoke-$(date +%s)"
mkdir -p "$OUTPUT_DIR"

passed=0
failed=0
ok() { echo "  ✔ $1"; passed=$((passed + 1)); }
fail() { echo "  ✘ $1"; failed=$((failed + 1)); }

# expect_status <descrição> <status esperado> <argumentos do curl...>
# Com a stack fora do ar o curl devolve 000 em vez de abortar o script.
expect_status() {
  local description="$1" expected="$2"
  shift 2
  local status
  status="$(curl -s --max-time "$MAX_TIME" -o "$OUTPUT_DIR/last.json" -w '%{http_code}' "$@" || true)"
  if [ "$status" = "$expected" ]; then ok "$description ($status)"; else fail "$description (recebeu $status, esperava $expected)"; fi
}

# json_field <arquivo> <caminho.com.pontos>; vazio quando a resposta não é JSON (ex.: página 502 do nginx)
json_field() {
  python3 -c 'import json, sys
try:
    value = json.load(open(sys.argv[1]))
    for key in sys.argv[2].split("."):
        value = value[key]
    print(value)
except (ValueError, KeyError, TypeError):
    pass' "$1" "$2"
}

echo "API ($API_URL)"
expect_status "health" 200 "$API_URL/health"
expect_status "recusa requisição sem API key" 401 "$API_URL/specialties"
expect_status "valores e formas de pagamento" 200 -H "X-API-Key: $API_KEY" "$API_URL/payment-info"
expect_status "horários disponíveis" 200 -H "X-API-Key: $API_KEY" "$API_URL/availability"

echo "Painel de consultas ($WEB_URL/painel.html)"
expect_status "página do painel" 200 "$WEB_URL/painel.html"
expect_status "listagem pelo proxy do nginx, com a API key injetada" 200 "$WEB_URL/api/v1/appointments"
expect_status "proxy recusa escrita (só GET)" 403 -X POST "$WEB_URL/api/v1/appointments"
expect_status "proxy não expõe as outras rotas" 404 "$WEB_URL/api/v1/patients"

echo "Webhook do n8n ($WEBHOOK_URL)"
expect_status "requisição inválida cai no fallback do Switch" 400 -X POST -F "session_id=$SESSION_ID" "$WEBHOOK_URL"

if [ -z "$OPENAI_KEY" ]; then
  echo "  ⚠ OPENAI_API_KEY vazia no .env: pulando os turnos de conversa"
else
  expect_status "mensagem de texto" 200 -X POST -F "session_id=$SESSION_ID" \
    -F "message=Quais são as formas de pagamento?" "$WEBHOOK_URL"
  if [ "$(json_field "$OUTPUT_DIR/last.json" type)" = "text" ]; then
    reply="$(json_field "$OUTPUT_DIR/last.json" reply_text)"
    ok "texto entra, texto sai: ${reply:0:90}…"
  else
    fail "mensagem de texto deveria receber resposta em texto"
  fi

  expect_status "mensagem de áudio" 200 -X POST -F "session_id=$SESSION_ID-audio" \
    -F "audio=@$AUDIO_SAMPLE;type=audio/wav" "$WEBHOOK_URL"
  if [ "$(json_field "$OUTPUT_DIR/last.json" type)" = "audio" ]; then
    json_field "$OUTPUT_DIR/last.json" audio.base64 | base64 --decode > "$OUTPUT_DIR/reply.mp3"
    ok "áudio entra, áudio sai: transcrição \"$(json_field "$OUTPUT_DIR/last.json" transcript)\""
    ok "resposta em áudio salva em ${OUTPUT_DIR#"$ROOT_DIR"/}/reply.mp3 ($(wc -c < "$OUTPUT_DIR/reply.mp3" | tr -d ' ') bytes)"
  else
    fail "mensagem de áudio deveria receber resposta em áudio"
  fi
fi

echo
echo "aprovados: $passed, reprovados: $failed"
[ "$failed" -eq 0 ]
