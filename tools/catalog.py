"""Danh sách công cụ hiển thị trên trang chủ."""

PORTAL_TOOLS = (
    {
        'slug': 'pdf-word',
        'name': 'PDF → Word',
        'description': 'Chuyển file PDF sang tài liệu Word (.docx).',
        'icon': 'bi-file-earmark-word',
        'accent': 'blue',
        'url_name': 'tools:pdf_to_word',
        'group': 'documents',
    },
    {
        'slug': 'office-pdf',
        'name': 'Word / Excel → PDF',
        'description': 'Chuyển tài liệu Word hoặc Excel sang PDF.',
        'icon': 'bi-file-earmark-pdf',
        'accent': 'indigo',
        'url_name': 'tools:office_to_pdf',
        'group': 'documents',
    },
    {
        'slug': 'ocr',
        'name': 'OCR ảnh',
        'description': 'Nhận dạng chữ trong ảnh — tiếng Việt & tiếng Anh.',
        'icon': 'bi-type',
        'accent': 'purple',
        'url_name': 'tools:ocr',
        'group': 'documents',
    },
    {
        'slug': 'compress',
        'name': 'Nén ảnh',
        'description': 'Giảm dung lượng JPG/PNG/WebP mà vẫn giữ chất lượng.',
        'icon': 'bi-file-earmark-zip',
        'accent': 'green',
        'url_name': 'tools:compress_image',
        'group': 'images',
    },
    {
        'slug': 'convert-format',
        'name': 'Đổi định dạng ảnh',
        'description': 'Chuyển JPG, PNG, WebP, GIF sang định dạng khác.',
        'icon': 'bi-arrow-repeat',
        'accent': 'teal',
        'url_name': 'tools:convert_image_format',
        'group': 'images',
    },
    {
        'slug': 'watermark',
        'name': 'Watermark ảnh',
        'description': 'Đóng dấu chữ hoặc logo lên ảnh trước khi chia sẻ.',
        'icon': 'bi-droplet-half',
        'accent': 'cyan',
        'url_name': 'tools:watermark_image',
        'group': 'images',
    },
    {
        'slug': 'qr',
        'name': 'Tạo mã QR',
        'description': 'Tạo mã QR từ link, văn bản hoặc số điện thoại.',
        'icon': 'bi-qr-code',
        'accent': 'red',
        'url_name': 'tools:qr_generator',
        'group': 'utility',
    },
    {
        'slug': 'notes',
        'name': 'Ghi chú',
        'description': 'Ghi chú cá nhân — lưu trên tài khoản của bạn.',
        'icon': 'bi-sticky',
        'accent': 'amber',
        'url_name': 'tools:notes',
        'group': 'utility',
    },
    {
        'slug': 'schedule-reminder',
        'name': 'Nhắc lịch',
        'description': 'Nhắc việc cá nhân — thông báo đúng giờ (hàng tuần hoặc một lần).',
        'icon': 'bi-alarm',
        'accent': 'red',
        'url_name': 'tools:schedule_reminder',
        'group': 'utility',
    },
)

PORTAL_TOOL_GROUPS = (
    {
        'key': 'documents',
        'title': 'Tài liệu',
        'subtitle': 'PDF, Word, Excel, OCR',
        'icon': 'bi-file-earmark-text',
        'accent': 'blue',
    },
    {
        'key': 'images',
        'title': 'Ảnh',
        'subtitle': 'Nén, đổi định dạng, watermark',
        'icon': 'bi-image',
        'accent': 'green',
    },
    {
        'key': 'utility',
        'title': 'Tiện ích',
        'subtitle': 'QR, ghi chú, nhắc lịch',
        'icon': 'bi-lightning-charge',
        'accent': 'amber',
    },
)


def get_portal_tool_groups():
    """Nhóm công cụ cho trang chủ — giữ thứ tự trong PORTAL_TOOLS."""
    by_slug = {tool['slug']: tool for tool in PORTAL_TOOLS}
    ordered_slugs = [tool['slug'] for tool in PORTAL_TOOLS]
    groups = []
    for group in PORTAL_TOOL_GROUPS:
        tools = [
            by_slug[slug]
            for slug in ordered_slugs
            if by_slug[slug].get('group') == group['key']
        ]
        groups.append({**group, 'tools': tools})
    return groups
