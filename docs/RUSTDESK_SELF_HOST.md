# RustDesk self-host — JustPlay

Hướng dẫn triển khai remote desktop nội bộ trên VPS, **không ảnh hưởng Portal** đang chạy.

## Kiến trúc

```
[Máy nhân viên] ──RustDesk client──► VPS 103.90.224.203
                                      ├── Portal (80/443) — không đổi
                                      └── RustDesk hbbs+hbbr (21115-21117)
```

- **hbbs**: đăng ký ID, bắt tay kết nối  
- **hbbr**: relay khi không P2P được  
- Traffic mã hóa E2E; server chỉ relay/signaling  

Tài liệu chính thức: [RustDesk self-host](https://rustdesk.com/docs/en/self-host/)

---

## Bước 1 — DNS (Mat Bao)

Domain `justplay.vn` dùng nameserver **Mat Bao** (`ns1.matbao.com`, `ns2.matbao.com`).

### Thêm bản ghi A (bắt buộc trước khi client dùng domain)

1. Đăng nhập [Mat Bao](https://www.matbao.net/) → **Quản lý tên miền** → `justplay.vn`
2. **Quản lý DNS** / **Bản ghi DNS**
3. Thêm bản ghi:

| Loại | Host / Tên | Giá trị | TTL |
|------|------------|---------|-----|
| **A** | `rd` | `103.90.224.203` | 300–3600 |

(Không cần `www` — chỉ subdomain `rd`.)

4. Lưu và đợi **5–30 phút** (đôi khi đến 2 giờ).

### Kiểm tra

```bash
nslookup rd.justplay.vn
# Phải trả về: 103.90.224.203
```

Trên Windows PowerShell: `Resolve-DnsName rd.justplay.vn`

**Lưu ý:** VPS đã cấu hình `RUSTDESK_PUBLIC_HOST=rd.justplay.vn`. Client chỉ kết nối qua domain sau khi DNS trỏ đúng IP.

---

## Bước 2 — Copy stack lên VPS

Trên máy dev (hoặc sau `git pull` trên VPS):

```bash
ssh root@103.90.224.203

sudo mkdir -p /opt/rustdesk
# Nếu repo Portal ở /opt/portaljustplay:
sudo rsync -a /opt/portaljustplay/rustdesk/ /opt/rustdesk/
# Hoặc scp từ máy local:
# scp -r rustdesk/ root@103.90.224.203:/opt/rustdesk/
```

```bash
cd /opt/rustdesk
cp .env.example .env
nano .env
```

Chỉnh `.env`:

```env
RUSTDESK_PUBLIC_HOST=rd.justplay.vn
RUSTDESK_IMAGE=rustdesk/rustdesk-server:1.1.14
ALWAYS_USE_RELAY=Y
```

```bash
chmod +x deploy.sh scripts/rustdesk-ufw.sh
./deploy.sh
```

Script sẽ:

1. Pull image RustDesk (không build Portal)  
2. Chạy `rustdesk-hbbr` + `rustdesk-hbbs` (`network_mode: host`)  
3. Mở UFW port 21115–21117 (không đụng 22/80/443)  
4. In **public key** từ `data/id_ed25519.pub`  

### Kiểm tra

```bash
docker ps --filter name=rustdesk
docker logs rustdesk-hbbs --tail 30
docker logs rustdesk-hbbr --tail 30
cat /opt/rustdesk/data/id_ed25519.pub
```

Log hbbs nên có `ALWAYS_USE_RELAY=Y`.

### Firewall cloud (nếu có panel VPS)

Mở thêm (ngoài UFW): **TCP 21115, 21116, 21117** và **UDP 21116**.

---

## Bước 3 — Cấu hình client

### Windows (script IT)

Tải RustDesk: https://rustdesk.com/download

```powershell
cd D:\Project\PortalJustPlay\scripts
Set-ExecutionPolicy -Scope Process Bypass
.\rustdesk-configure-client-windows.ps1 `
  -ServerHost rd.justplay.vn `
  -PublicKey "DÁN_NỘI_DUNG_id_ed25519.pub"
```

Khởi động lại RustDesk (thoát icon tray → mở lại).

### Thủ công (mọi OS)

1. Mở RustDesk → menu **⋮** → **Network** → **Unlock network settings**  
2. **ID server**: `rd.justplay.vn`  
3. **Relay server**: `rd.justplay.vn`  
4. **Key**: dán nội dung `id_ed25519.pub`  
5. **Apply**  

### Ghim key (bắt buộc)

Nếu không ghim key, client có thể bị lừa kết nối server giả. Chỉ dùng key từ `/opt/rustdesk/data/id_ed25519.pub` trên VPS.

---

## Bảo mật vận hành

| Việc | Ghi chú |
|------|---------|
| Tách thư mục | `/opt/rustdesk` — `deploy.sh` Portal **không** chạy stack này |
| Giới hạn RAM | `HBBS_MEM_LIMIT` / `HBBR_MEM_LIMIT` trong `.env` |
| Relay bắt buộc | `ALWAYS_USE_RELAY=Y` — hạn chế P2P trực tiếp |
| Mật khẩu | Unattended password dài, đổi định kỳ; chỉ IT remote không hỏi user |
| Backup key | Sao lưu `data/id_ed25519` + `.pub` (mất = cấu hình lại mọi máy) |
| Quyền file | `chmod 700 data` và `chmod 600 data/id_ed25519*` |
| Không dùng chung | Không gộp RustDesk vào `docker-compose.yml` Portal |

### Không làm

- Không commit `rustdesk/data/` hoặc private key lên Git  
- Không mở port RustDesk ra internet rồi bỏ qua ghim key  
- Không dùng mật khẩu unattended yếu / chung một mật khẩu cho cả công ty trên client user  

### Nâng cấp sau (tuỳ chọn)

- **RustDesk Pro**: LDAP, 2FA, quản lý thiết bị tập trung  
- **Giới hạn IP relay** (UFW): chỉ mở 21117 từ IP văn phòng — chặt nhưng khó cho nhân viên WFH  

---

## Cập nhật / gỡ

```bash
cd /opt/rustdesk
# Sửa RUSTDESK_IMAGE trong .env nếu cần
./deploy.sh
```

Dừng (không ảnh hưởng Portal):

```bash
cd /opt/rustdesk
docker compose down
```

---

## Xử lý sự cố

| Triệu chứng | Kiểm tra |
|-------------|----------|
| Client không đăng ký ID | UDP **21116** trên firewall cloud + UFW |
| Kết nối treo | Relay `21117/tcp`; log `rustdesk-hbbr` |
| Key không khớp | Client key ≠ `id_ed25519.pub` trên VPS |
| Portal chậm sau khi cài | Giảm `HBBR_MEM_LIMIT`; theo dõi `docker stats` |

---

## Liên hệ

IT nội bộ — cấp key và script cấu hình cho từng máy hoặc triển khai GPO hàng loạt.
