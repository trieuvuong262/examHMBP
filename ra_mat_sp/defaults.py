"""Checklist mẫu mặc định theo mốc T-90 → D+1 (nạp khi cài app hoặc khôi phục ở Thiết lập)."""

# (nhóm, offset ngày, công việc, kết quả cần có, quan trọng, điều kiện Go/No-Go)
# Điều kiện có dữ liệu ở module khác do hệ thống tự kiểm khi duyệt Go, không đánh dấu blocker ở đây.
# Đầu việc kho vận vẫn là điều kiện Go vì chưa có trạng thái "sẵn sàng giao hàng" ở module kho.
DEFAULT_CHECKLIST = (
    ('product', -90, 'Khóa thiết kế và mẫu chuẩn', 'Phiên bản thiết kế và mẫu chuẩn đã duyệt', True, False),
    ('product', -90, 'Khóa Techpack, BOM và giá thành', 'Techpack, BOM và giá thành đã chốt', True, False),
    ('price', -90, 'Chốt mục tiêu ra mắt: sản lượng, doanh thu, ngân sách và kênh bán', 'Mục tiêu đã ghi trên kế hoạch', True, False),
    ('production', -60, 'Chuẩn bị nguyên phụ liệu và đưa vào sản xuất', 'Nguyên phụ liệu và lệnh sản xuất', True, False),
    ('marketing', -60, 'Chuẩn bị hình ảnh và video', 'Ảnh sản phẩm và video', True, False),
    ('production', -60, 'Lập kế hoạch sản xuất đúng tiến độ ra mắt', 'Lệnh sản xuất có hạn hoàn thành', True, False),
    ('channel', -30, 'Giới thiệu đại lý, catalogue và nhận đặt trước', 'Catalogue và đơn đặt trước', True, False),
    ('price', -30, 'Chốt giá bán và chính sách đại lý', 'Giá bán lẻ và giá sỉ đã duyệt', True, False),
    ('marketing', -14, 'Hoàn thiện nội dung bán hàng và catalogue', 'Mô tả sản phẩm và catalogue', True, False),
    ('channel', -14, 'Tạo sản phẩm và kiểm tra các kênh bán', 'SKU trên kênh bán', True, False),
    ('product', -14, 'Khóa mã sản phẩm, màu, size và mã vạch', 'SKU trên Thư viện sản phẩm', True, False),
    ('logistics', -7, 'Kiểm tra tồn kho đạt mức tối thiểu', 'Tồn kho theo mã, màu và size', True, False),
    ('logistics', -7, 'Kho vận và giao hàng đã sẵn sàng', 'Phương án giao hàng', True, True),
    ('approval', -2, 'Họp và trình duyệt Go/No-Go', 'Biên bản họp Go/No-Go', True, False),
    ('channel', 0, 'Mở bán chính thức trên các kênh', 'Sản phẩm đang mở bán', True, False),
    ('marketing', 0, 'Đăng bài ra mắt và chạy truyền thông', 'Bài đăng ngày ra mắt', False, False),
    ('channel', 1, 'Kiểm tra giá, tồn kho, hình ảnh và trạng thái mở bán', 'Biên bản kiểm tra D+1', True, False),
    ('logistics', 1, 'Xử lý lệch tồn và giao hàng sau ngày đầu', 'Đề xuất bổ sung', False, False),
)

# Dòng mẫu cũ — ngừng dùng khi nạp bộ mốc chuẩn. Việc đã làm trên kế hoạch không bị xóa.
RETIRED_TITLES = (
    'Chốt danh sách sản phẩm ra mắt và hồ sơ thiết kế liên quan',
    'Chốt mục tiêu ra mắt: sản lượng, doanh thu, kênh bán',
    'Định vị sản phẩm, khách hàng mục tiêu, thông điệp chính',
    'Duyệt mẫu chuẩn và tài liệu kỹ thuật',
    'Lập kế hoạch sản xuất đợt đầu',
    'Đặt nguyên phụ liệu chính',
    'Lên kế hoạch truyền thông ra mắt',
    'Chốt giá thành và giá bán lẻ / sỉ',
    'Tạo mã Style / SKU / mã vạch trên danh mục sản phẩm',
    'NPL về đủ, đưa vào chuyền sản xuất',
    'Chụp ảnh sản phẩm, quay video',
    'Lên kế hoạch phân bổ hàng theo kênh / cửa hàng',
    'Hoàn thành sản xuất, kiểm tra chất lượng đạt',
    'Hoàn thiện nội dung: bài đăng, mô tả sản phẩm, banner',
    'Đưa sản phẩm lên KiotViet / website (chưa mở bán)',
    'Đào tạo nhân viên bán hàng về sản phẩm mới',
    'Nhập kho thành phẩm đủ số lượng ra mắt',
    'Phân phối hàng về cửa hàng / kho kênh online',
    'Teaser / thông báo trước ra mắt',
    'Kiểm tra trưng bày, giá, tồn tại điểm bán',
    'Lên lịch đăng bài / quảng cáo ngày ra mắt',
    'Mở bán chính thức trên các kênh',
    'Đăng bài ra mắt, chạy quảng cáo',
    'Theo dõi tồn sau ngày đầu, bổ sung hàng thiếu',
)


def load_default_checklist(TemplateItem) -> int:
    created = 0
    current = set()
    for idx, (group, offset, title, deliverable, high, blocker) in enumerate(DEFAULT_CHECKLIST):
        current.add((group, offset, title))
        _obj, was_created = TemplateItem.objects.get_or_create(
            group=group,
            offset_days=offset,
            title=title,
            defaults={
                'deliverable': deliverable,
                'importance': 'high' if high else 'normal',
                'is_go_blocker': blocker,
                'sort_order': (idx + 1) * 10,
                'is_active': True,
            },
        )
        created += int(was_created)
    for item in TemplateItem.objects.filter(title__in=RETIRED_TITLES, is_active=True):
        if (item.group, item.offset_days, item.title) in current:
            continue
        item.is_active = False
        item.save(update_fields=['is_active'])
    return created
