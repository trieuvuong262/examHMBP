# Zalo OA + ZBS Template Message (OTP quên mật khẩu Portal)

> Mục tiêu **P1**: cấu hình OA/App/ZBS + template OTP + client Portal sẵn sàng gửi thử.  
> **P2** (đã có): quên mật khẩu trên login → OTP Zalo → đặt MK mới (`/accounts/forgot-password/`).

## Luồng P2 (user)

1. Login → **Quên mật khẩu?**
2. Nhập username hoặc mã NS → OTP gửi Zalo (`Profile.phone`)
3. Nhập OTP → đặt mật khẩu mới → đồng bộ Odoo/NAS → về login

Yêu cầu: P0 (có SĐT) + P1 (`zalo_is_ready()`).

| URL | Việc |
|-----|------|
| `/accounts/forgot-password/` | Yêu cầu OTP |
| `/accounts/forgot-password/otp/` | Nhập OTP |
| `/accounts/forgot-password/new/` | Đặt MK mới |

Code: `zalo.password_reset`, `zalo.views_password_reset`.

## Liên kết chính thức

| | |
|--|--|
| Tạo / quản lý OA | https://oa.zalo.me |
| Developers (App) | https://developers.zalo.me |
| ZBS Template Message | https://oa.zalo.me/home/documents/vie/guides/zbs-template-message |
| OAuth OA access token | `POST https://oauth.zaloapp.com/v4/oa/access_token` |
| Gửi template qua SĐT | `POST https://business.openapi.zalo.me/message/template` |

## Checklist ops (JustPlay)

1. **OA doanh nghiệp** JustPlay — xác thực (tích vàng nếu Zalo yêu cầu cho ZBS).
2. **ZBS Account** — liên kết OA + App, nạp tiền (template OTP ~ vài trăm đồng/tin khi gửi thành công).
3. **App** trên developers.zalo.me — lấy `App ID` + `Secret Key`; gắn quyền OA / ZBS theo hướng dẫn Zalo.
4. **Callback URL** của App trỏ về URL nội bộ IT (có thể tạm `https://portal.justplay.vn/` hoặc trang trống) chỉ để nhận `code`.
5. **Template loại Xác thực (OTP)** — nội dung gợi ý:

   > Ma OTP JustPlay Portal cua ban la: `{{otp}}`. Het han sau 5 phut. Khong chia se ma nay.

   Ghi đúng tên hệ thống **JustPlay Portal**. Sau khi Zalo duyệt → copy `template_id`.
6. Điền `.env` (xem bên dưới) → `docker compose restart web` (hoặc tương đương).
7. Đổi auth code → token:

   ```bash
   docker compose exec web python manage.py zalo_oauth_exchange --code 'PASTE_CODE'
   docker compose exec web python manage.py zalo_status
   ```

8. Gửi thử (mode development — chỉ admin OA/App nhận được):

   ```bash
   docker compose exec web python manage.py zalo_send_test_otp --phone 09xxxxxxxx
   ```

9. Khi ổn → tắt development:

   ```env
   ZALO_DEVELOPMENT_MODE=0
   ```

## Biến môi trường

```env
ZALO_ENABLED=1
ZALO_APP_ID=
ZALO_APP_SECRET=
ZALO_OA_ID=                 # tuỳ chọn — ghi chú
ZALO_OTP_TEMPLATE_ID=       # ID template OTP đã duyệt
ZALO_OTP_TEMPLATE_PARAM=otp # tên tham số trong template_data
ZALO_DEVELOPMENT_MODE=1     # 1 = chỉ gửi admin OA khi test
ZALO_REFRESH_TOKEN=         # tuỳ chọn seed lần đầu; sau đó token nằm trong DB
# ZALO_CODE_VERIFIER=       # nếu App dùng PKCE
```

Token **access** (~25h) và **refresh** (~3 tháng, dùng 1 lần) được lưu bảng `zalo_zalooauthtoken` (pk=1). Mỗi lần refresh, Portal ghi đè refresh mới — **không** chỉ dựa vào `.env` lâu dài.

## Lệnh quản trị

| Lệnh | Việc |
|------|------|
| `python manage.py zalo_status` | Checklist cấu hình + token DB |
| `python manage.py zalo_oauth_exchange --code …` | Lần đầu / khi mất refresh |
| `python manage.py zalo_refresh_token` | Ép làm mới access |
| `python manage.py zalo_send_test_otp --phone …` | Gửi OTP thử |

## Code Portal

| Module | Vai trò |
|--------|---------|
| `zalo.client.ZaloClient` | OAuth + gửi ZBS template |
| `zalo.services.send_password_reset_otp` | API cho P2 quên MK |
| `hrm.phone` | Chuẩn hóa SĐT `84…` (P0) |

## Lưu ý

- OTP ZBS gửi theo **SĐT**, không cần user Follow OA.
- Template OTP gửi 24/7; các loại tin khác có khung giờ.
- SĐT nhân sự phải có trên hồ sơ (`Profile.phone`) — P0.
- Không commit `APP_SECRET` / token vào git.
