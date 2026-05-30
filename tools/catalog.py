"""Danh sách công cụ hiển thị trên trang chủ."""

PORTAL_TOOLS = (
    {
        'slug': 'pdf-word',
        'name': 'PDF → Word',
        'description': 'Chuyển file PDF sang tài liệu Word (.docx).',
        'icon': 'bi-file-earmark-word',
        'accent': 'blue',
        'url_name': 'tools:pdf_to_word',
    },
    {
        'slug': 'ocr',
        'name': 'OCR ảnh',
        'description': 'Nhận dạng chữ trong ảnh — tiếng Việt & tiếng Anh.',
        'icon': 'bi-type',
        'accent': 'purple',
        'url_name': 'tools:ocr',
    },
    {
        'slug': 'compress',
        'name': 'Nén ảnh',
        'description': 'Giảm dung lượng JPG/PNG/WebP mà vẫn giữ chất lượng.',
        'icon': 'bi-file-earmark-zip',
        'accent': 'green',
        'url_name': 'tools:compress_image',
    },
    {
        'slug': 'remove-bg',
        'name': 'Xóa nền',
        'description': 'Tách chủ thể khỏi nền ảnh — xuất PNG trong suốt.',
        'icon': 'bi-scissors',
        'accent': 'pink',
        'url_name': 'tools:remove_background',
    },
    {
        'slug': 'qr',
        'name': 'Tạo mã QR',
        'description': 'Tạo mã QR từ link, văn bản hoặc số điện thoại.',
        'icon': 'bi-qr-code',
        'accent': 'red',
        'url_name': 'tools:qr_generator',
    },
    {
        'slug': 'notes',
        'name': 'Ghi chú',
        'description': 'Ghi chú cá nhân — lưu trên tài khoản của bạn.',
        'icon': 'bi-sticky',
        'accent': 'amber',
        'url_name': 'tools:notes',
    },
)
