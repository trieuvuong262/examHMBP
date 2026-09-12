# Tự động publish: local → Git → VPS

## Cách nhanh (Windows)

1. Một lần: copy `deploy.local.env.example` → `deploy.local.env`, sửa IP/user SSH.
2. Đảm bảo SSH vào VPS không hỏi mật khẩu (`ssh root@103.90.224.203`).
3. Chạy (**dùng `.bat` hoặc `.cmd`**, không gọi trực tiếp `publish.ps1` nếu PowerShell báo Execution Policy):

Trong **PowerShell** (terminal Cursor), phải có `.\` trước tên file:

```powershell
cd d:\Project\PortalJustPlay
.\publish.bat
.\publish.bat "update moi"
```

Hoặc:

```powershell
.\update.cmd "update moi"
```

Trong **CMD** (Command Prompt) thì không cần `.\`:

```cmd
cd /d d:\Project\PortalJustPlay
publish.bat "update moi"
```

Nếu vẫn muốn `.ps1`:

```powershell
powershell -ExecutionPolicy Bypass -File .\publish.ps1 "update moi"
```

Hoặc bật một lần cho user hiện tại (tuỳ chọn):

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Script sẽ lần lượt:

- `git add .`
- `git commit -m "update"` (hoặc message bạn truyền: `.\publish.ps1 "sua NAS"`)
- `git push`
- SSH lên VPS: `cd /opt/portaljustplay && ./deploy.sh`

## File liên quan

| File | Mô tả |
|------|--------|
| `publish.ps1` | Script chính trên Windows (PowerShell) |
| `publish.bat` | Gọi `publish.ps1` |
| `publish.sh` | Git Bash / Linux / macOS |
| `deploy.local.env` | Cấu hình VPS (không commit — đã gitignore) |
| `deploy.sh` | Chạy trên VPS: pull code, migrate, collectstatic, restart |
| `.github/workflows/deploy.yml` | Deploy dự phòng qua GitHub Actions — **chỉ chạy khi bấm tay** |

## Hai cách deploy sau khi push — chỉ bật MỘT cách

> Nếu bật cả hai, mỗi lần publish sẽ có **hai** tiến trình `deploy.sh` chạy song
> song trên cùng `/opt/portaljustplay`: tranh lock docker, build 2 lượt, và lượt
> này có thể `git reset --hard` trong lúc lượt kia đang build. Hiện đang dùng
> cách A, nên `on: push` trong workflow đã được comment lại.

### A) SSH từ máy bạn (`deploy.local.env`) — đang dùng

Tạo `deploy.local.env`:

```env
VPS_HOST=103.90.224.203
VPS_USER=root
VPS_PORT=22
PROJECT_DIR=/opt/portaljustplay
BRANCH=main
DEPLOY_AFTER_PUSH=1
```

Chạy `publish.ps1` → push xong → SSH chạy `deploy.sh` ngay.

### B) GitHub Actions (không cần `deploy.local.env`)

Workflow `.github/workflows/deploy.yml` hiện chỉ chạy khi bấm tay:
**GitHub → Actions → Deploy PortalJustPlay → Run workflow**.

Muốn Actions thành đường chính (tự deploy mỗi lần push `main`): bỏ comment khối
`on: push` trong workflow **và** đặt `DEPLOY_AFTER_PUSH=0` trong `deploy.local.env`.

Cấu hình **GitHub → Settings → Secrets → Actions**:

- `VPS_HOST` — IP VPS
- `VPS_USER` — user SSH (vd. `root`)
- `VPS_SSH_KEY` — private key PEM (public key đã có trong `~/.ssh/authorized_keys` trên VPS)
- `VPS_PORT` — (tuỳ chọn) mặc định 22

Khi đó chỉ cần `git push`; không chạy SSH từ `publish.ps1` nữa.

## Cờ tùy chọn của `deploy.sh`

| Biến | Mặc định | Tác dụng |
|------|----------|----------|
| `COLLECTSTATIC_CLEAR=1` | tắt | Xóa sạch `staticfiles` rồi copy lại (chỉ cần khi có asset rác). Mặc định `collectstatic` chỉ copy file mới. |
| `SKIP_NAS_VERIFY=0` | bỏ qua | Kiểm tra rclone/DSM NAS trong lúc deploy (tốn tới ~75s). Bình thường xem ở trang giám sát NAS. |
| `PULL_BASE_IMAGES=1` | tắt | Pull lại base image từ Docker Hub (có thể kéo theo build lại LibreOffice ~10–15 phút). |

## Lần đầu trên VPS

```bash
cd /opt/portaljustplay
git clone <url-repo> .   # nếu chưa có
chmod +x deploy.sh
./deploy.sh
```

Repo trên VPS phải `git pull`/`fetch` được từ remote bạn push (SSH deploy key hoặc HTTPS).

## Lưu ý

- `deploy.local.env` chứa IP — **không** commit lên Git.
- Commit message mặc định là `update`; nên dùng message rõ hơn khi cần: `.\publish.ps1 "fix org chart"`.
- Nếu không có thay đổi file, script bỏ qua `commit` nhưng vẫn `push` và deploy (nếu bật SSH).
