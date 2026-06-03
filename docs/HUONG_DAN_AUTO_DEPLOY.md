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
| `.github/workflows/deploy.yml` | Tự deploy khi push `main` (qua GitHub Actions) |

## Hai cách deploy sau khi push

### A) SSH từ máy bạn (`deploy.local.env`)

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

Đã có workflow `.github/workflows/deploy.yml`: mỗi lần **push lên `main`**, GitHub SSH vào VPS chạy `./deploy.sh`.

Cấu hình **GitHub → Settings → Secrets → Actions**:

- `VPS_HOST` — IP VPS
- `VPS_USER` — user SSH (vd. `root`)
- `VPS_SSH_KEY` — private key PEM (public key đã có trong `~/.ssh/authorized_keys` trên VPS)
- `VPS_PORT` — (tuỳ chọn) mặc định 22

Khi đó chỉ cần `git push`; không bắt buộc chạy SSH từ `publish.ps1`.

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
