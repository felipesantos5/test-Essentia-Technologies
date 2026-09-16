#!/bin/sh
# One-shot n8n provisioning, run before the n8n server starts:
#   1. imports credentials rendered from the environment;
#   2. imports the versioned workflows and publishes them (production webhooks need it).
# Each step only runs when its input changed since the last successful run, so a restart
# never wipes the Gmail OAuth token or edits made in the UI. FORCE_SYNC=1 re-applies all.
set -eu

STATE_DIR="/home/node/.n8n/bootstrap-state"
WORKFLOWS_DIR="/workflows"
# Sub-workflows first: the main workflow's tools call them.
WORKFLOW_IDS="clinicBookAppt01 clinicCancelAp01 clinicChatMain01"

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT
mkdir -p "$STATE_DIR"

log() { echo "[n8n-bootstrap] $*"; }
digest() { cat "$@" | sha256sum | cut -d' ' -f1; }
needs_sync() {
  name="$1"
  shift
  [ "${FORCE_SYNC:-0}" = "1" ] || [ "$(cat "$STATE_DIR/$name" 2>/dev/null)" != "$(digest "$@")" ]
}
mark_synced() {
  name="$1"
  shift
  digest "$@" > "$STATE_DIR/$name"
}

node /bootstrap/render-credentials.mjs "$WORK_DIR"
for credential in clinic-api openai gmail; do
  file="$WORK_DIR/$credential.json"
  if needs_sync "credential-$credential" "$file"; then
    log "importing credential '$credential'"
    n8n import:credentials --input="$file"
    mark_synced "credential-$credential" "$file"
  else
    log "credential '$credential' unchanged"
  fi
done

if needs_sync workflows "$WORKFLOWS_DIR"/*.json; then
  log "importing workflows"
  n8n import:workflow --separate --input="$WORKFLOWS_DIR"
  for id in $WORKFLOW_IDS; do
    log "publishing workflow $id"
    n8n publish:workflow --id="$id"
  done

  published="$(n8n list:workflow --active=true --onlyId)"
  for id in $WORKFLOW_IDS; do
    if ! echo "$published" | grep -qx "$id"; then
      log "ERROR: workflow $id is not published"
      exit 1
    fi
  done
  mark_synced workflows "$WORKFLOWS_DIR"/*.json
else
  log "workflows unchanged"
fi

log "done"
