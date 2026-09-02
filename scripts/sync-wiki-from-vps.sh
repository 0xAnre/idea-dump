#!/usr/bin/env bash
# One-way wiki sync: VPS knowledge-base → local folder (optional Obsidian vault).
# Never copies local files back to the VPS.
set -euo pipefail

die() {
  echo "error: $*" >&2
  exit 1
}

expand_path() {
  local p="$1"
  if [[ "$p" == "~" ]]; then
    p="$HOME"
  elif [[ "$p" == ~/* ]]; then
    p="${HOME}/${p#~/}"
  fi
  printf '%s' "$p"
}

if [[ -n "${IDEA_DUMP_SYNC_ENV:-}" ]]; then
  [[ -f "$IDEA_DUMP_SYNC_ENV" ]] || die "IDEA_DUMP_SYNC_ENV is not a file: $IDEA_DUMP_SYNC_ENV"
  # shellcheck disable=SC1090
  source "$IDEA_DUMP_SYNC_ENV"
fi

: "${IDEA_DUMP_REMOTE_KB:=/opt/idea-dump/knowledge-base}"

[[ -n "${IDEA_DUMP_SSH_HOST:-}" ]] || die "IDEA_DUMP_SSH_HOST is not set (example: user@your-vps)"
[[ -n "${IDEA_DUMP_LOCAL_KB:-}" ]] || die "IDEA_DUMP_LOCAL_KB is not set (local destination folder)"

REMOTE_KB="$(expand_path "$IDEA_DUMP_REMOTE_KB")"
LOCAL_KB="$(expand_path "$IDEA_DUMP_LOCAL_KB")"
SSH_HOST="$IDEA_DUMP_SSH_HOST"

case "$LOCAL_KB" in
  / | /home | /Users | "$HOME" | "$HOME/")
    die "IDEA_DUMP_LOCAL_KB is too broad: $LOCAL_KB"
    ;;
esac
[[ -n "$REMOTE_KB" && "$REMOTE_KB" != / ]] || die "IDEA_DUMP_REMOTE_KB is invalid: $REMOTE_KB"

PRINT=0
if [[ "${1:-}" == "--print" ]]; then
  PRINT=1
fi

RSYNC=(rsync -a --exclude '.obsidian/' --exclude '.trash/')
if [[ "${IDEA_DUMP_RSYNC_DELETE:-0}" == 1 ]]; then
  MAX_DELETE="${IDEA_DUMP_RSYNC_MAX_DELETE:-50}"
  RSYNC+=(--delete --delete-after --delay-updates --max-delete="$MAX_DELETE")
fi

RSH=(ssh -o BatchMode=yes)
if [[ -n "${IDEA_DUMP_SSH_KEY:-}" ]]; then
  SSH_KEY="$(expand_path "$IDEA_DUMP_SSH_KEY")"
  if [[ "$PRINT" -eq 0 && ! -f "$SSH_KEY" ]]; then
    die "SSH key not found: $SSH_KEY"
  fi
  RSH+=(-o IdentitiesOnly=yes -i "$SSH_KEY")
fi

RSH_STRING="$(printf '%q ' "${RSH[@]}")"
RSH_STRING="${RSH_STRING% }"
SOURCE="${SSH_HOST}:${REMOTE_KB}/"
DEST="${LOCAL_KB}/"
RSYNC+=(-e "$RSH_STRING" "$SOURCE" "$DEST")

if [[ "$PRINT" -eq 1 ]]; then
  printf '%q ' "${RSYNC[@]}"
  printf '\n'
  exit 0
fi

mkdir -p "$LOCAL_KB"

LOCK_DIR="${TMPDIR:-/tmp}/idea-dump-wiki-sync.lock"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "skip: another sync is already running"
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

"${RSYNC[@]}"
echo "ok: ${SOURCE} -> ${DEST}"
