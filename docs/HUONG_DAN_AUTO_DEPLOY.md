# Hướng dẫn Auto Deploy — Push Git là VPS tự cập nhật

> Dành cho người **chưa từng làm CI/CD**. Làm lần lượt từ trên xuống, **đừng bỏ bước**.

---

## Mục lục

1. [Auto deploy là gì?](#1-auto-deploy-là-gì)
2. [Cần có sẵn những gì?](#2-cần-có-sẵn-những-gì)
3. [Sơ đồ hoạt động](#3-sơ-đồ-hoạt-động)
4. [PHẦN A — Chuẩn bị trên VPS](#phần-a--chuẩn-bị-trên-vps)
5. [PHẦN B — Tạo khóa SSH trên máy Windows](#phần-b--tạo-khóa-ssh-trên-máy-windows)
6. [PHẦN C — Gắn khóa lên VPS](#phần-c--gắn-khóa-lên-vps)
7. [PHẦN D — Cho VPS tải code từ GitHub](#phần-d--cho-vps-tải-code-từ-github)
8. [PHẦN E — Cấu hình GitHub Secrets](#phần-e--cấu-hình-github-secrets)
9. [PHẦN F — Đẩy file workflow lên GitHub](#phần-f--đẩy-file-workflow-lên-github)
10. [PHẦN G — Kiểm tra lần đầu](#phần-g--kiểm-tra-lần-đầu)
11. [Lỗi thường gặp](#11-lỗi-thường-gặp)
12. [Deploy tay khi cần](#12-deploy-tay-khi-cần)

---

## 1. Auto deploy là gì?

**Trước đây (thủ công):**

1. Sửa code trên máy
2. `git push`
3. SSH vào VPS
4. Chạy `./deploy.sh`

**Sau khi cấu hình auto deploy:**

1. Sửa code trên máy
2. `git push`
3. **Xong** — GitHub tự SSH vào VPS và chạy `./deploy.sh` giúp bạn

File cấu hình nằm tại: `.github/workflows/deploy.yml` (đã có sẵn trong repo).

---

## 2. Cần có sẵn những gì?

| Thứ | Ví dụ của JustPlay |
|-----|---------------------|
| Máy chủ VPS (Linux) | IP `103.90.224.203` |
| Đăng nhập SSH được | `ssh root@103.90.224.203` |
| Code đã clone trên VPS | Thư mục `/opt/portaljustplay` |
| Docker + docker compose đã chạy được | `./deploy.sh` chạy OK thủ công |
| Repo GitHub | Ví dụ: `github.com/trieuvuong262/examHMBP` |
| Quyền Admin repo GitHub | Vào Settings → Secrets |

**Hai loại khóa SSH (đừng nhầm):**

| Khóa | Ai dùng | Mục đích |
|------|---------|----------|
| **Khóa A — GitHub Actions → VPS** | GitHub gọi VPS | Chạy lệnh deploy |
| **Khóa B — VPS → GitHub** | VPS khi `git pull` | Tải code mới về |

---

## 3. Sơ đồ hoạt động

```
Bạn push code lên GitHub (branch main)
        │
        ▼
GitHub Actions (máy ảo của GitHub)
        │  dùng Khóa A (SSH)
        ▼
VPS: cd /opt/portaljustplay && ./deploy.sh
        │
        ├── git pull          ← cần Khóa B
        ├── docker migrate
        ├── build web/nginx
        └── collectstatic
        │
        ▼
Website cập nhật ✓
```

---

## PHẦN A — Chuẩn bị trên VPS

### A1. Đăng nhập VPS

Trên Windows, mở **PowerShell** hoặc **PuTTY**:

```bash
ssh root@103.90.224.203
```

(Nhập mật khẩu VPS khi được hỏi.)

### A2. Kiểm tra thư mục project

```bash
ls -la /opt/portaljustplay
```

Phải thấy các file: `deploy.sh`, `docker-compose.yml`, `.env`, `manage.py`...

Nếu **chưa có**, clone repo (thay URL đúng repo của bạn):

```bash
mkdir -p /opt
cd /opt
git clone https://github.com/trieuvuong262/examHMBP.git portaljustplay
cd portaljustplay
```

### A3. Cho phép chạy deploy.sh

```bash
chmod +x /opt/portaljustplay/deploy.sh
```

### A4. Thử deploy thủ công một lần (bắt buộc)

```bash
cd /opt/portaljustplay
./deploy.sh
```

Nếu bước này **lỗi**, sửa xong rồi mới làm auto deploy. Auto deploy chỉ gọi lại script này.

---

## PHẦN B — Tạo khóa SSH trên máy Windows

> **Khóa A** — GitHub Actions dùng để vào VPS. Tạo trên **máy tính của bạn** (Windows).

### B1. Mở PowerShell

Nhấn `Win + X` → **Terminal** hoặc **PowerShell**.

### B2. Tạo cặp khóa

Copy nguyên dòng lệnh, Enter:

```powershell
ssh-keygen -t ed25519 -C "github-actions-deploy" -f "$env:USERPROFILE\.ssh\portaljustplay_deploy"
```

- Hỏi passphrase: **Enter 2 lần để bỏ trống** (đơn giản hơn cho người mới).
- Tạo ra 2 file:
  - `C:\Users\TÊN-BẠN\.ssh\portaljustplay_deploy` → **PRIVATE** (bí mật)
  - `C:\Users\TÊN-BẠN\.ssh\portaljustplay_deploy.pub` → **PUBLIC** (gắn lên VPS)

### B3. Xem nội dung public key

```powershell
Get-Content "$env:USERPROFILE\.ssh\portaljustplay_deploy.pub"
```

Copy **toàn bộ** một dòng (bắt đầu bằng `ssh-ed25519 ...`). Lưu tạm Notepad — dùng ở Phần C.

### B4. Xem nội dung private key (cho GitHub Secret)

```powershell
Get-Content "$env:USERPROFILE\.ssh\portaljustplay_deploy"
```

Copy **toàn bộ**, gồm:

```
-----BEGIN OPENSSH PRIVATE KEY-----
...
-----END OPENSSH PRIVATE KEY-----
```

Lưu tạm Notepad — dùng ở Phần E. **Không gửi cho ai, không commit lên Git.**

---

## PHẦN C — Gắn khóa lên VPS

Quay lại cửa sổ SSH đang đăng nhập VPS (Phần A).

### C1. Tạo thư mục SSH (nếu chưa có)

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
```

### C2. Thêm public key (Khóa A)

```bash
nano ~/.ssh/authorized_keys
```

- Dán **dòng public key** từ B3 vào cuối file (một dòng duy nhất).
- Lưu: `Ctrl+O` → Enter → `Ctrl+X`.

```bash
chmod 600 ~/.ssh/authorized_keys
```

### C3. Thử SSH bằng khóa từ máy Windows

**Mở PowerShell mới** trên Windows:

```powershell
ssh -i "$env:USERPROFILE\.ssh\portaljustplay_deploy" root@103.90.224.203
```

- Nếu vào được **không hỏi mật khẩu** → Khóa A OK.
- Nếu vẫn hỏi mật khẩu → kiểm tra lại C2 (copy đủ dòng, không xuống dòng).

---

## PHẦN D — Cho VPS tải code từ GitHub

> **Khóa B** — VPS dùng khi `git pull` trong `deploy.sh`.

### D1. Tạo khóa trên VPS

Trên VPS:

```bash
ssh-keygen -t ed25519 -C "vps-git-pull" -f ~/.ssh/github_portaljustplay -N ""
```

### D2. Xem public key

```bash
cat ~/.ssh/github_portaljustplay.pub
```

Copy toàn bộ dòng.

### D3. Thêm Deploy Key trên GitHub

1. Mở trình duyệt → repo GitHub (vd: `github.com/trieuvuong262/examHMBP`)
2. **Settings** (tab repo, không phải Settings tài khoản)
3. Menu trái: **Deploy keys** → **Add deploy key**
4. Title: `VPS portaljustplay`
5. Key: dán public key từ D2
6. **Không** tick "Allow write access" (chỉ cần đọc)
7. **Add key**

### D4. Cấu hình Git trên VPS dùng khóa B

Trên VPS:

```bash
cat >> ~/.ssh/config << 'EOF'
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/github_portaljustplay
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config
```

### D5. Đổi remote sang SSH (nếu đang dùng HTTPS)

```bash
cd /opt/portaljustplay
git remote -v
```

Nếu thấy `https://github.com/...`, đổi sang SSH:

```bash
git remote set-url origin git@github.com:trieuvuong262/examHMBP.git
```

(Thay `trieuvuong262/examHMBP` đúng user/repo của bạn.)

### D6. Thử pull

```bash
ssh -T git@github.com
```

Lần đầu hỏi `Are you sure...` → gõ `yes`.

Thấy dạng: `Hi trieuvuong262/examHMBP! You've successfully authenticated...` → OK.

```bash
cd /opt/portaljustplay
git pull origin main
```

Không lỗi → VPS đã tải code được.

---

## PHẦN E — Cấu hình GitHub Secrets

Secrets = chỗ GitHub lưu mật khẩu/khóa **an toàn**, workflow đọc khi chạy.

### E1. Vào trang Secrets

1. Repo GitHub → **Settings**
2. Trái: **Secrets and variables** → **Actions**
3. **New repository secret** (tạo 3 secret)

### E2. Tạo từng secret

| Tên secret | Dán gì vào | Ví dụ |
|------------|------------|-------|
| `VPS_HOST` | IP hoặc domain VPS | `103.90.224.203` |
| `VPS_USER` | User SSH | `root` |
| `VPS_SSH_KEY` | **Private key Khóa A** (cả block BEGIN/END) | Nội dung file `portaljustplay_deploy` |

**Lưu ý `VPS_SSH_KEY`:**

- Copy từ `-----BEGIN OPENSSH PRIVATE KEY-----` đến `-----END OPENSSH PRIVATE KEY-----`
- Không thêm dấu cách thừa đầu/cuối
- Không bọc trong dấu ngoặc kép

Sau khi xong phải có **đúng 3 secrets** trong danh sách.

---

## PHẦN F — Đẩy file workflow lên GitHub

Trên máy dev (Windows), trong thư mục project:

```powershell
cd D:\Project\PortalJustPlay
git status
```

Phải thấy file `.github/workflows/deploy.yml`.

```powershell
git add .github/workflows/deploy.yml docs/HUONG_DAN_AUTO_DEPLOY.md
git commit -m "Thêm auto deploy khi push main"
git push origin main
```

---

## PHẦN G — Kiểm tra lần đầu

### G1. Xem GitHub Actions

1. Repo GitHub → tab **Actions**
2. Chọn workflow **Deploy PortalJustPlay**
3. Run mới nhất:
   - **Chấm xanh** = deploy thành công
   - **Chấm đỏ** = bấm vào xem log dòng lỗi

### G2. Xem website

Mở trình duyệt → vào IP/domain portal → thử tính năng vừa sửa.

### G3. Chạy tay từ GitHub (không cần push)

Actions → Deploy PortalJustPlay → **Run workflow** → Run workflow.

Dùng khi muốn deploy lại mà không có code mới.

---

## 11. Lỗi thường gặp

### `dial tcp ... i/o timeout` / `connection refused`

- VPS tắt hoặc firewall chặn port 22
- Sai `VPS_HOST`
- Kiểm tra: `ping 103.90.224.203`, mở port SSH trên cloud panel

### `ssh: unable to authenticate` / `handshake failed`

- Sai `VPS_SSH_KEY` (copy thiếu dòng, nhầm public/private)
- Public key chưa add vào `authorized_keys` trên VPS
- Làm lại Phần B + C + E

### `git pull` failed / `Permission denied (publickey)` trong log Actions

- Chưa làm Phần D (Deploy key VPS → GitHub)
- Remote vẫn là HTTPS mà không có token
- Trên VPS chạy thử: `git pull origin main`

### `ERROR: Project directory not found`

- Sai đường dẫn — workflow mặc định `/opt/portaljustplay`
- Sửa dòng `cd` trong `.github/workflows/deploy.yml` nếu project nằm chỗ khác

### `deploy.sh: Permission denied`

Trên VPS:

```bash
chmod +x /opt/portaljustplay/deploy.sh
```

### Deploy xong nhưng web không đổi

- Trình duyệt cache — thử Ctrl+F5
- Vào VPS: `docker compose ps` xem container `web` có **Up**
- `docker compose logs web --tail 50`

---

## 12. Deploy tay khi cần

Auto deploy hỏng hoặc đang sửa server — vẫn deploy được bằng tay:

```bash
ssh root@103.90.224.203
cd /opt/portaljustplay
./deploy.sh
```

---

## Checklist nhanh (in ra dán tường)

```
□ VPS có /opt/portaljustplay và ./deploy.sh chạy OK
□ Khóa A: tạo trên Windows, public → VPS authorized_keys
□ Khóa A: private → GitHub Secret VPS_SSH_KEY
□ Khóa B: tạo trên VPS, public → GitHub Deploy keys
□ VPS: git remote SSH + git pull OK
□ GitHub Secrets: VPS_HOST, VPS_USER, VPS_SSH_KEY
□ Push file .github/workflows/deploy.yml
□ Tab Actions thấy chấm xanh
```

---

## Bảo mật cơ bản

- **Không** commit file `.env`, private key, mật khẩu lên GitHub
- Private key Khóa A **chỉ** nằm trong GitHub Secrets
- Nên tạo user `deploy` riêng thay vì `root` khi đã quen (nâng cao)
- Repo **private** + Deploy key read-only là đủ cho hầu hết trường hợp

---

*Cập nhật: 2026 — JustPlay Portal / PortalJustPlay*
