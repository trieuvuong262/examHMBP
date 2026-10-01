#!/usr/bin/env bash
# Watchdog VPN site-to-site VPS <-> NAS (chạy mỗi phút bằng cron).
#
# Sự cố đã gặp: tunnel IPsec vẫn ESTABLISHED nhưng có nhiều CHILD_SA trùng cho
# NAS; VPS gửi qua SA Fortigate đã bỏ → NAS timeout, mount rclone kẹt I/O error.
#
# Mỗi lượt:
#   1. NAS không vào được (3 lần thử) → gỡ CHILD_SA trùng không nhận dữ liệu;
#      vẫn hỏng thì down/up cả kết nối IPsec.
#   2. NAS vào được nhưng mount /mnt/nas-portal kẹt (host hoặc container web)
#      → restart rclone-nas + recreate web/worker để nhận mount mới.
#
# Usage: bash scripts/vps-nas-tunnel-watchdog.sh
set -uo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/portaljustplay}"
NAS_HOST="${NAS_LAN_HOST:-192.168.40.252}"
IPSEC_CONN="${IPSEC_CONN:-vps-to-fortigate}"
MOUNT_POINT="${NAS_MOUNT_ROOT:-/mnt/nas-portal}"
MOUNT_UNIT="${NAS_MOUNT_UNIT:-rclone-nas.service}"
COOLDOWN_SECONDS="${WATCHDOG_COOLDOWN_SECONDS:-300}"
STATE_DIR="/var/lib/portaljustplay"
LAST_ACTION_FILE="${STATE_DIR}/nas-watchdog.last"
LOCK_FILE="/run/portaljustplay-nas-watchdog.lock"

exec 9>"$LOCK_FILE"
flock -n 9 || exit 0

log() { echo "$(date '+%F %T') $*"; }

nas_reachable() {
  local attempt
  for attempt in 1 2 3; do
    if timeout 5 bash -c "echo >/dev/tcp/${NAS_HOST}/445" 2>/dev/null \
      || timeout 5 bash -c "echo >/dev/tcp/${NAS_HOST}/5556" 2>/dev/null; then
      return 0
    fi
    [[ $attempt -lt 3 ]] && sleep 5
  done
  return 1
}

in_cooldown() {
  [[ -f "$LAST_ACTION_FILE" ]] || return 1
  local last now
  last="$(cat "$LAST_ACTION_FILE" 2>/dev/null || echo 0)"
  now="$(date +%s)"
  (( now - last < COOLDOWN_SECONDS ))
}

mark_action() {
  mkdir -p "$STATE_DIR"
  date +%s > "$LAST_ACTION_FILE"
}

# CHILD_SA chỉ phủ NAS/32 và chưa nhận byte nào (SA mà Fortigate đã bỏ).
stale_nas_children() {
  ipsec statusall 2>/dev/null | awk -v conn="$IPSEC_CONN" -v nas="${NAS_HOST}/32" '
    match($0, conn "\\{[0-9]+\\}:") {
      id = substr($0, RSTART + length(conn) + 1, RLENGTH - length(conn) - 3)
      if ($0 ~ / bytes_i/) {
        zero[id] = ($0 ~ /, 0 bytes_i/) ? 1 : 0
      } else if ($0 ~ "=== " nas "[[:space:]]*$") {
        nas_child[id] = 1
      }
    }
    END {
      total = 0; for (id in nas_child) total++
      for (id in nas_child) if (zero[id] && total > 1) { print id; total-- }
    }'
}

mount_ok_host() {
  timeout 10 ls "$MOUNT_POINT" >/dev/null 2>&1
}

mount_ok_web() {
  timeout 20 docker compose -f "${PROJECT_DIR}/docker-compose.yml" --project-directory "${PROJECT_DIR}" \
    exec -T web timeout 10 ls "$MOUNT_POINT" >/dev/null 2>&1
}

recreate_app() {
  log "recreate web + worker để nhận mount mới"
  docker compose -f "${PROJECT_DIR}/docker-compose.yml" --project-directory "${PROJECT_DIR}" \
    up -d --force-recreate --no-deps web worker >/dev/null 2>&1
  local i status=""
  for i in $(seq 1 40); do
    status="$(docker inspect -f '{{.State.Health.Status}}' portaljustplay-web-1 2>/dev/null || true)"
    [[ "$status" == "healthy" ]] && break
    sleep 3
  done
  docker compose -f "${PROJECT_DIR}/docker-compose.yml" --project-directory "${PROJECT_DIR}" \
    exec -T nginx nginx -s reload >/dev/null 2>&1 || true
  log "web ${status:-unknown}, nginx reloaded"
}

repair_mount() {
  log "mount ${MOUNT_POINT} kẹt — restart ${MOUNT_UNIT}"
  systemctl restart "$MOUNT_UNIT"
  sleep 5
  if ! mount_ok_host; then
    log "mount host vẫn lỗi sau restart"
    return 1
  fi
  recreate_app
}

repair_tunnel() {
  local ids id
  ids="$(stale_nas_children)"
  if [[ -n "$ids" ]]; then
    for id in $ids; do
      log "gỡ CHILD_SA trùng ${IPSEC_CONN}{${id}}"
      ipsec down "${IPSEC_CONN}{${id}}" >/dev/null 2>&1 || true
    done
    sleep 3
    if nas_reachable; then
      log "NAS thông lại sau khi gỡ CHILD_SA trùng"
      return 0
    fi
  fi
  log "kết nối lại IPsec ${IPSEC_CONN}"
  ipsec down "$IPSEC_CONN" >/dev/null 2>&1 || true
  sleep 2
  ipsec up "$IPSEC_CONN" >/dev/null 2>&1 || true
  sleep 5
  if nas_reachable; then
    log "NAS thông lại sau khi kết nối lại IPsec"
    return 0
  fi
  log "NAS vẫn không thông — cần kiểm tra Fortigate / NAS"
  return 1
}

if nas_reachable; then
  if mount_ok_host && mount_ok_web; then
    exit 0
  fi
  in_cooldown && exit 0
  mark_action
  if ! mount_ok_host; then
    repair_mount
  else
    log "container web không đọc được ${MOUNT_POINT}"
    recreate_app
  fi
  exit 0
fi

in_cooldown && exit 0
mark_action
log "NAS ${NAS_HOST} không vào được (445/5556)"
if repair_tunnel; then
  mount_ok_host || repair_mount
  mount_ok_web || recreate_app
fi
