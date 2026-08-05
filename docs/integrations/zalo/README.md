# Zalo OA + ZBS Template Message (OTP quên mật khẩu Portal)

> **P2:** quên mật khẩu trên login — chọn **Email** (đang dùng) hoặc **Zalo** (bảo trì).  
> Email: có sẵn → gửi link; chưa có → nhập email → lưu hồ sơ → gửi link.  
> URL: `/accounts/forgot-password/`.

## Luồng quên mật khẩu (user)

1. Login → **Quên mật khẩu?**
2. Nhập username / mã NS → chọn **Email** (Zalo hiện “Bảo trì”)
3. **Đã có email:** thông báo kiểm tra hộp thư  
   **Chưa có email:** nhập email → lưu `User.email` → gửi mail
4. Mở link trong email → đặt mật khẩu mới → đăng nhập

| URL | Việc |
|-----|------|
| `/accounts/forgot-password/` | Chọn kênh + nhập tài khoản |
| `/accounts/forgot-password/email/` | Nhập email khi hồ sơ trống |
| `/accounts/forgot-password/email-sent/` | Đã gửi mail |
| `/accounts/forgot-password/confirm/<uid>/<token>/` | Đặt MK từ link |
| `/accounts/forgot-password/otp/` | OTP Zalo (khi hết bảo trì) |

Code: `zalo.email_password_reset`, `zalo.views_password_reset`.

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
   - Nếu Zalo yêu cầu **xác minh domain**: file
     `static/zalo_verifier….html` được phục vụ tại
     `https://portal.justplay.vn/zalo_verifier….html` (route Django public).
     Deploy + restart web rồi bấm xác minh trên Developers.
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
