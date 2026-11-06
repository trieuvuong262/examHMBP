# Architecture Map

Công cụ này kết hợp Django introspection và AST tĩnh để tạo bản đồ nhanh của PortalJustPlay.

## Chạy

Từ thư mục `PortalJustPlay/`:

```powershell
python manage.py architecture_map
```

Mặc định kết quả nằm trong `architecture_output/`. Chọn thư mục khác:

```powershell
python manage.py architecture_map --output docs/architecture/generated
```

Chỉ quét một hoặc nhiều app:

```powershell
python manage.py architecture_map --app kho_npl --app san_xuat
```

Tìm function theo tên:

```powershell
python manage.py architecture_map --open-function post_gc_progress
```

## File sinh ra

- `architecture.json`: dữ liệu đầy đủ về app, URL, model/table, Python module và function.
- `index.html`: trang tìm kiếm local cho model và function.
- `models.mmd`: sơ đồ quan hệ model dạng Mermaid ER diagram.
- `apps.mmd`: sơ đồ app cơ bản dạng Mermaid.

## Cách dùng khi sửa code

1. Chạy lại map sau khi thay đổi route, view, service hoặc model.
2. Tìm function trong `index.html` hoặc dùng `--open-function`.
3. Xem `calls`, `model_names` và `file:line` để xác định vùng cần kiểm tra.
4. Nếu thay đổi model/field, xem `models.mmd`, migration tương ứng và test app.
5. Dùng CodeGraph `callers`, `callees`, `impact` để xác minh sâu hơn trước khi sửa workflow.
6. Dùng Silk/Debug Toolbar để xác nhận các bảng thực sự được truy vấn trong một request.

## Checklist bắt buộc khi thêm/sửa chức năng

### Trước khi sửa

- Chạy `python manage.py architecture_map --app <app>` hoặc `--open-function <name>`.
- Dùng CodeGraph `context`, `callers`, `callees`, `impact` cho symbol hiện hữu.
- Xác định chuỗi `URL → view/API → form/serializer → service → model/table → template/response`.
- Kiểm tra permission, audit log, worker/RQ, signal, integration ngoài và test liên quan.
- Xác định có cần migration, test mới, cập nhật map/changelog hay approval của người dùng hay không.

### Sau khi sửa

- Chạy lại architecture map và kiểm tra blast radius mới.
- Chạy `python manage.py check`.
- Chạy test hẹp của app hoặc workflow bị ảnh hưởng.
- Chạy `python -m compileall -q <changed-python-files>`.
- Chạy `git diff --check`.
- Cập nhật `docs/AI_CODEBASE_MAP.md` nếu route/module/workflow/data relationship thay đổi.
- Cập nhật `docs/AI_CHANGELOG.md` nếu thay đổi kiến trúc, workflow, module, integration hoặc agent policy.
- Báo rõ các kiểm tra bị bỏ qua, index cũ và giới hạn phân tích tĩnh.

Không dùng report sinh tự động làm căn cứ duy nhất cho thay đổi dữ liệu hoặc workflow nhạy cảm.

## Giới hạn

Đây là phân tích tĩnh bổ trợ, không thay thế CodeGraph hoặc runtime tracing. AST không thể giải quyết hoàn hảo alias, decorator, dynamic import, reflection, query tạo động hoặc function gọi qua biến. `model_names` chỉ là gợi ý từ các biểu thức phổ biến như `Model.objects...`; cần kiểm tra source và graph trước khi dùng làm căn cứ thay đổi dữ liệu.

Không commit output sinh tự động nếu repository không muốn lưu snapshot; có thể thêm `architecture_output/` vào `.gitignore` khi cần.
