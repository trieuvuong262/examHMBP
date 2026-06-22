#!/usr/bin/env bash
# Mở port RustDesk trên UFW — không đổi rule SSH/80/443 của Portal.
#
# Chạy trên VPS:
#   sudo bash scripts/rustdesk-ufw.sh
#   DRY_RUN=1 sudo bash scripts/rustdesk-ufw.sh
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
  log "UFW chưa cài — bỏ qua (mở port 21115-21117 TCP + 21116 UDP trên firewall cloud/VPS thủ công)."
  exit 0
fi

log "==> RustDesk UFW (không đụng Portal 80/443/22)"

# Tối thiểu theo https://rustdesk.com/docs/en/self-host/
allow_rule "21115/tcp" "RustDesk NAT test"
allow_rule "21116/tcp" "RustDesk ID TCP"
allow_rule "21116/udp" "RustDesk ID UDP"
allow_rule "21117/tcp" "RustDesk relay"

if [[ "$DRY_RUN" != "1" ]]; then
  ufw reload >/dev/null 2>&1 || true
fi

log "==> UFW (liên quan RustDesk):"
ufw status | grep -E '2111[567]|Status' || true
