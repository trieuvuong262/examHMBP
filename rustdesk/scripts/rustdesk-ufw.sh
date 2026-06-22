#!/usr/bin/env bash
# Mở port RustDesk trên UFW — không đổi rule SSH/80/443 của Portal.
set -euo pipefail

DRY_RUN="${DRY_RUN:-0}"

log() { echo "$@"; }

allow_rule() {
  local spec="$1"
  local comment="$2"
  if ufw status 2>/dev/null | grep -Fq "$spec"; then
    log "    Đã có: $spec"
    return 0
  fi
  if [[ "$DRY_RUN" == "1" ]]; then
    log "    [dry-run] ufw allow $spec comment '$comment'"
    return 0
  fi
  ufw allow "$spec" comment "$comment" >/dev/null
  log "    + ufw allow $spec"
}

if ! command -v ufw >/dev/null 2>&1; then
  log "UFW chưa cài — mở port 21115-21117 TCP + 21116 UDP trên firewall VPS/cloud thủ công."
  exit 0
fi

log "==> RustDesk UFW (không đụng Portal 80/443/22)"

allow_rule "21115/tcp" "RustDesk NAT test"
allow_rule "21116/tcp" "RustDesk ID TCP"
allow_rule "21116/udp" "RustDesk ID UDP"
allow_rule "21117/tcp" "RustDesk relay"
allow_rule "21118/tcp" "RustDesk hbbs websocket"
allow_rule "21119/tcp" "RustDesk hbbr websocket"

if [[ "$DRY_RUN" != "1" ]]; then
  ufw reload >/dev/null 2>&1 || true
fi

log "==> UFW (liên quan RustDesk):"
ufw status | grep -E '2111[56789]|Status' || true
