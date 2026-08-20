# Từ vựng SKU chuẩn — chuẩn bị cho server sản phẩm trung tâm

Số liệu lấy từ DB production ngày 20/08/2026. Từ vựng đã được nghiệp vụ duyệt và
**đã áp lên production** — xem mục 7 để biết kết quả, mục 8 cho phần còn tồn.

Nguồn chân lý của từ vựng trong code: `kho_san_pham/sku_vocabulary.py`.
Danh sách cần nghiệp vụ điền: [color-review.csv](./color-review.csv).
Thiết kế tồn kho ở central: [inventory-schema.md](./inventory-schema.md).

## 1. Bối cảnh

Kế hoạch: dựng một server trung tâm giữ danh mục sản phẩm và tồn kho thành phẩm.
Portal đẩy phát sinh sau khi sản xuất, VPS bán hàng đẩy phát sinh sau khi bán.

Quyết định đã chốt:

| Vấn đề | Quyết định |
|---|---|
| KiotViet | Bỏ hẳn — central là nguồn tồn duy nhất |
| Ai tạo SKU | Portal (mã sinh từ thiết kế / IE) |
| Màu có bắt buộc | Không — chỉ một số dòng hàng có màu |
| 102 dòng `SxSku` hiện tại | Đánh `is_active=False` khi sinh lại, giữ để truy vết |
| Màu phối nhiều tông | Cấp mã riêng cho từng tổ hợp, không thêm cột phụ |
| Quy tắc mã tổ hợp | Ghép mã chính–phụ theo thứ tự xuất hiện, vd. `NVY-WHT` |
| Size | Áp cho tất cả sản phẩm; dòng không có size thì ghi `NOSIZE` |
| Size `OS` | Tách: phụ kiện giữ `OS`, hàng theo yêu cầu chuyển `NOSIZE` |
| Giới tính | Thuộc tính riêng của SKU, tách khỏi size |
| Dòng không suy được màu | Chốt `NOCOLOR`, giữ `color_label` gốc làm dấu vết để rà lại |
| Cách triển khai | Management command mặc định xem trước, `--apply` mới ghi |

## 2. Hiện trạng

Portal đang có ba định danh sản phẩm không nối với nhau:

| Bảng | Dòng | Khóa neo | Ghi chú |
|---|---|---|---|
| `kv_product` | 5.971 | `kiotviet_id` | Bản mirror thô từ KiotViet |
| `kho_sp_product` | 5.677 | `kiotviet_id` | 100% `sync_source='kiotviet'`; `color_code` rỗng toàn bộ |
| `san_xuat_sxsku` | 102 | `sku_code` | 0 dòng nối với danh mục; có dữ liệu rác |

Phép nối thử nghiệm giữa `san_xuat_sxsku` và `kho_sp_product`:

- Khớp tuyệt đối `sku_code = code`: **0 / 5.677**
- Khớp bộ ba style + màu + size: **0**
- Khớp qua token `SPxxxxxx` trong style: **7 dòng**

Kết luận: không nối được bằng script. Phải chuẩn hóa từ vựng trước.

## 3. Bốn vấn đề gốc

**Cấu trúc mã style khác nhau.** Sản xuất dùng `SP000077`, danh mục dùng
`JP-SET-00-SP000077`. Bản thân `SxSku` cũng không nhất quán: trong 7 mã style có 3
định dạng, và một mã là chuỗi `DỊCH VỤ IN TÊN CHỮ THEO YÊU CẦU` (sinh ra 5 SKU rác).

**Danh mục thiếu chiều màu.** `kho_sp_product.color_code` rỗng ở cả 5.677 dòng. Nhưng
`color_label` thì có sẵn ở 5.589 dòng — màu đã nằm đúng cột, chỉ thiếu mã và sai
hoa/thường. Đây là lý do việc backfill về sau dễ hơn dự kiến rất nhiều: tra từ điển
trên `color_label` chính xác hơn hẳn bóc chuỗi từ tên sản phẩm.

**Từ vựng size lệch.** Danh mục dùng `XXL`/`XXXL`, sản xuất dùng `2XL`/`3XL` — cùng
một size, hai cách viết. Tệ hơn, bảng từ điển `san_xuat_sxsize` chứa **cả `XXL` và
`2XL` như hai bản ghi riêng**, với `sort_order` sai (`XXL`=60, `3XL`=70, `2XL`=80 →
2XL xếp sau 3XL).

**Size đang gánh nhiều thang đo khác nhau.** 27% danh mục dùng size số, và có cả
size lẫn giới tính trong một chuỗi (`XL-NỮ`). Không thể so sánh hay sắp xếp `M` với
`13` trong cùng một danh sách phẳng.

## 4. Mô hình chuẩn đề xuất

**`sku_code` là mã bất biến, không mang ý nghĩa.** Hiện code đang bị *parse* để suy
ra style/màu/size, và đó là nguồn gốc của phần lớn sự lệch. Đề xuất: central lưu
`style_code`, `color_code`, `size_code` thành **cột riêng biệt**, còn `sku_code` chỉ
là khóa nghiệp vụ duy nhất, không bao giờ tách chuỗi để lấy thông tin.

**Size có thang đo (`size_scale`) và áp cho mọi sản phẩm.** Không dùng một danh sách phẳng:

| Thang đo | Giá trị chuẩn | Dòng danh mục | Ghi chú |
|---|---|---|---|
| `ALPHA` | XS, S, M, L, XL, 2XL, 3XL, 4XL, 5XL, 6XL | 4.105 | Quần áo người lớn |
| `NUM` | 1, 3, 5, 7, 9, 11, 13, 15 | 1.527 | **Size trẻ em** (xem mục 5) |
| `OS` | `OS` | 40 | Một size thật: vớ, balo, nón, băng thấm mồ hôi, túi đựng giày |
| `NONE` | `NOSIZE` | 4 | Hàng may theo yêu cầu, hàng sale, dịch vụ, phụ phí |

Còn đúng 1 dòng giữ giá trị thô `39X54CM` (Lịch Euro 2024) — đây là kích thước vật lý
chứ không phải size, nên để nguyên chờ nghiệp vụ quyết chứ không tự đổi.

Size có giới tính — tách thành `size_code` + `gender`:

| Đang dùng | `size_code` | `gender` | Số dòng |
|---|---|---|---|
| `S-NAM`, `M-NAM`, `L-NAM`, `XL-NAM`, `XXL-NAM` | `S`/`M`/`L`/`XL`/`2XL` | `NAM` | 21 |
| `M-NỮ`, `L-NỮ`, `XL-NỮ`, `XXL-NỮ` | `M`/`L`/`XL`/`2XL` | `NU` | 17 |

Lưu ý: KiotViet ghi `XL-Nữ` còn danh mục ghi `XL-NỮ` — cần chuẩn hóa chữ hoa/thường
khi nạp.

**Màu luôn có giá trị, kể cả khi không có màu.** Dòng không xác định được màu mang mã
`NOCOLOR`, song song với `NOSIZE` bên size. Nhờ vậy bộ ba style–màu–size luôn đủ chiều
và không cần xử lý riêng giá trị rỗng. Mã rỗng giờ chỉ còn nghĩa "chưa chạy chuẩn hóa".

## 5. Thang size `NUM` là size trẻ em

Đã xác minh bằng dữ liệu. Nhóm hàng của 1.527 dòng dùng size số:

| Nhóm hàng | Dòng |
|---|---|
| BÓNG ĐÁ TRẺ EM | 736 |
| Hàng theo yêu cầu | 288 |
| TRẺ EM | 144 |
| PEGASUS | 50 |
| CAMO TRẺ EM | 48 |
| STRIKER | 47 |
| ROCKFIRE - TRẺ EM / JUMPER - TRẺ EM | 40 mỗi nhóm |

Toàn bộ nằm trong hai họ mã `JP-SET-SC-SP` (1.422 dòng) và `JP-SET-BB-SP` (105 dòng).
Giá trị chỉ gồm số lẻ 1–15, đúng kiểu size theo tuổi.

## 6. Bảng quy đổi size

| Giá trị đang dùng | Chuẩn | Nguồn |
|---|---|---|
| `S`, `M`, `L`, `XL` | giữ nguyên | cả hai |
| `XXL` | `2XL` | danh mục |
| `XXXL` | `3XL` | danh mục |
| `4XL`, `5XL`, `6XL` | giữ nguyên | danh mục |
| `XS`, `2XL`, `3XL` | giữ nguyên | sản xuất |

## 7. Bảng mã màu và kết quả đã áp

22 mã màu đơn — 8 mã cũ trong `san_xuat_sxcolor` và 14 mã nghiệp vụ duyệt ngày
20/08/2026:

| Màu | Mã | Màu | Mã | Màu | Mã |
|---|---|---|---|---|---|
| Đen | `BLK` | Vàng | `YEL` | Xanh da | `SKY` |
| Trắng | `WHT` | Cam | `ORG` | Cổ vịt | `TEA` |
| Xanh đen | `NVY` | Xanh biển | `SEA` | Tím | `PPL` |
| Đỏ | `RED` | Xanh bích | `TRQ` | Xanh ngọc | `JAD` |
| Xám | `GRY` | Hồng | `PNK` | Xanh lý | `LIM` |
| Be | `BEG` | Lông công | `PCK` | Xanh chuối | `LGN` |
| Xanh dương | `BLU` | Kem | `CRM` | | |
| Xanh lá | `GRN` | Đô | `MRN` | | |

Tổ hợp nhiều tông ghép mã theo thứ tự xuất hiện trong tên gốc, nên `NVY-WHT` khác
`WHT-NVY`. Sinh tự động, không cần bảng khai báo tay. Tám tổ hợp phát sinh từ dữ liệu
thật: `WHT-PNK`, `WHT-BLK`, `WHT-ORG`, `WHT-NVY`, `WHT-GRN`, `WHT-TRQ`, `BLK-PNK`,
`BLK-SKY`.

Kết quả chạy `kho_sp_normalize_vocabulary --apply` trên production:

| Việc | Kết quả |
|---|---|
| Danh mục size | 21 mã chuẩn, thêm `scale`; `XXL` chuyển `is_active=False`; `2XL` về đúng trước `3XL` |
| Danh mục màu | 31 bản ghi (22 màu đơn + 8 tổ hợp + `NOCOLOR`) |
| Gán mã màu thật | 5.316 / 5.677 SKU (93,6%) |
| Chốt `NOCOLOR` | 361 SKU (6,4%) — không còn dòng nào bỏ trống |
| Chuẩn hóa `size_label` | 1.052 SKU (`XXL`→`2XL` 746, `XXXL`→`3XL` 264, còn lại tách giới tính) |
| Tách `gender` | 38 SKU (21 `NAM`, 17 `NU`) |

Trong 5.316 SKU gán được màu, 5.304 tra trực tiếp từ `color_label`; 12 SKU lấy từ tên
sản phẩm vì nhãn màu bị ghi thiếu — ví dụ nhãn ghi `đen xanh` còn tên ghi đủ
`Street đen xanh da` nên kết quả là `BLK-SKY`.

### Ba cái bẫy trong dữ liệu và cách xử lý

1. **"Băng đô" không phải màu đô.** Cụm này là loại sản phẩm; nếu so khớp chuỗi con
   thì 19 dòng băng đô bị gán `MRN`. Đã loại bằng danh sách cụm-không-phải-màu.
2. **Tên màu chồng nhau.** `đen xanh da` có thể đọc thành `Đen xanh` + `Xanh da`.
   Xử lý bằng quét trái-nhất-dài-nhất một lượt, nên không sinh khớp chồng.
3. **Nhãn màu ghi lửng.** `xanh`, `trắng xanh`, `đen chuối` — thiếu phần định danh nên
   không đủ thành tên màu chuẩn. Những dòng này **không đoán**, để trống `color_code`.
   Chỉ nhận màu từ nguồn khác khi nguồn đó vừa làm rõ đúng từ còn lửng, vừa giữ nguyên
   các màu đã chắc.

## 8. Việc còn cần nghiệp vụ quyết định

361 SKU đang mang `NOCOLOR`. Đây là giá trị tạm để không chặn việc sinh lại `SxSku`:
phần lớn số này **thực tế có màu**, chỉ là nhãn ghi lửng. `color_label` gốc được giữ
nguyên (vd. `color_code=NOCOLOR` nhưng `color_label='xanh'`) nên tìm lại được dễ dàng.
Khi bổ sung màu mới vào từ vựng rồi chạy lại, các dòng này tự động chuyển sang mã thật.

Đã gom thành 71 nhóm trong [color-review.csv](./color-review.csv) — mỗi nhóm chỉ cần
điền một màu.

| Nhóm | SKU | Vấn đề |
|---|---|---|
| Nhãn ghi `xanh` | 160 | Thiếu định danh sắc xanh |
| Nhãn trống | 88 | Áo bóng đá sọc, không ghi màu |
| Nhãn ghi `trắng xanh` | 77 | Thiếu định danh sắc xanh |
| Nhãn ghi `đen xanh` | 30 | Thiếu định danh sắc xanh |
| Nhãn ghi `đen chuối` | 6 | "Chuối" chưa có trong từ vựng |
| `39X54CM` | 1 | Kích thước vật lý, không phải size |

Tên sản phẩm cho thấy phần lớn thiếu **màu mới chưa có mã**: `xanh két` (Man City),
`xanh rêu` (MU), `xanh vịt` (Wolves, Zentic), `xanh lục` (Argon), `xám xanh` (Motion),
`xanh đỏ` (Barca). Cần nghiệp vụ đặt tên và cấp mã cho nhóm này trước, phần còn lại
sẽ tự khớp.

Hai việc nhỏ đi kèm:

- 88 dòng nhãn trống là áo bóng đá sọc hai tông (Argentina, Barca, Juve) — cần chốt
  coi sọc là tổ hợp hai màu hay một màu chủ đạo.
- 1 dòng `39X54CM` (Lịch Euro 2024) cần một thuộc tính kích thước riêng, hoặc chấp
  nhận chuyển sang `NOSIZE` và ghi kích thước vào mô tả.

## 9. Thứ tự triển khai

| # | Việc | Trạng thái |
|---|---|---|
| 1 | Nghiệp vụ duyệt từ vựng size và màu | Xong 20/08/2026 |
| 2 | Từ điển chuẩn trong code + `SxSize.scale` + `Product.gender` | Xong |
| 3 | Sửa `san_xuat_sxsize`: gộp `XXL` vào `2XL`, sửa `sort_order` | Xong |
| 4 | Backfill `color_code`, chuẩn hóa `size_label`, tách `gender` | Xong — 100% có giá trị |
| 5 | Sinh lại `SxSku` từ danh mục đã chuẩn hóa | Xong (mục 10) |
| 6 | Nghiệp vụ điền `color-review.csv`, bổ sung màu mới rồi chạy lại | Chạy song song, không chặn |
| 7 | Thiết kế schema tồn kho ở central | Xong — [inventory-schema.md](./inventory-schema.md) |

## 10. Sinh lại `SxSku` từ danh mục

Lệnh `rebuild_sku_from_catalog` (mặc định xem trước, `--apply` mới ghi) lấy
`kho_sp_product` làm nguồn sự thật: mỗi thành phẩm **đang dùng** sinh đúng một SKU.

| Việc | Kết quả |
|---|---|
| SKU sinh mới | 2.900 — bằng đúng số thành phẩm đang dùng |
| Nối `Product.sx_sku` | 2.900, không còn dòng nào chưa nối |
| SKU cũ ngừng dùng | 102, đánh `is_active=False` kèm ghi chú, không xóa |
| Lệch `sku_code` | 0 — `SxSku.sku_code` luôn bằng `Product.code` |

`sku_code` giữ nguyên `Product.code` chứ không ghép lại từ style–màu–size. Đây là quy
ước đã có sẵn: cả `kho_san_pham/forms.py` và `product_import_export.py` đều truyền
`sku_code=product.code` rồi gán ngược `product.code = sx.sku_code`. Nhờ vậy Portal chỉ
có **một** chuỗi định danh SKU, không sinh thêm một hệ mã thứ hai phải đối soát.

### Giới tính phải nằm trong khóa định danh

Lần chạy thử đầu tiên lộ ra 7 cặp sản phẩm bị gộp thành một SKU: quần cầu lông Lighting
bản nam và bản nữ cùng style, cùng màu, cùng size. Nguyên nhân là ràng buộc duy nhất của
`SxSku` chỉ gồm style–màu–size, không có giới tính — đúng cái sai mà quyết định "giới
tính là thuộc tính riêng của SKU" nhắm tới.

Đã sửa: thêm `SxSku.gender` và đổi ràng buộc duy nhất thành
**style–màu–size–giới tính**. `get_or_create_sku` cũng nhận thêm tham số `gender`, và
màu rỗng nay quy về `NOCOLOR` để SKU do form sinh không lệch khóa với SKU dựng từ danh
mục. Hiện có 26 SKU đang dùng mang giới tính.

### Hai điều cần biết khi chạy lại

Lệnh **chỉ xét sản phẩm `is_active=True`**, và đây là điều kiện bắt buộc chứ không phải
tùy chọn: nếu tính cả 2.777 sản phẩm đã tắt thì gặp 37 cặp trùng khóa. Đó là lỗi dữ liệu
có sẵn — mỗi cặp gồm một mã cũ đặt tay đã tắt (`JP-SET-SC-SP8516421-TRNG-XXL`) cộng một
mã KiotViet đang dùng (`SP8516489`), 36 cặp trong đó là "QA bóng đá Just Play SC02".

Sản phẩm được bật lại về sau không cần chạy lệnh: luồng form gọi `get_or_create_sku` sẽ
tự sinh SKU khi lưu.

```bash
docker compose run --rm web python manage.py rebuild_sku_from_catalog          # xem trước
docker compose run --rm web python manage.py rebuild_sku_from_catalog --apply  # ghi DB
```

Command chuẩn hóa **chạy lại được nhiều lần** và chỉ ghi phần thay đổi, nên sau khi
nghiệp vụ bổ sung màu mới vào `sku_vocabulary.py` thì chạy lại là đủ. Cũng nên chạy
định kỳ sau mỗi lần đồng bộ KiotViet, vì sản phẩm mới về vẫn mang giá trị thô:

```bash
docker compose run --rm web python manage.py kho_sp_normalize_vocabulary          # xem trước
docker compose run --rm web python manage.py kho_sp_normalize_vocabulary --apply  # ghi DB
```
