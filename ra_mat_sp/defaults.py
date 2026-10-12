"""Checklist mẫu mặc định theo mốc T-90 → D+1 (nạp khi cài app hoặc khôi phục ở Thiết lập)."""

# (nhóm, offset ngày, công việc, kết quả cần có, quan trọng, điều kiện Go/No-Go)
DEFAULT_CHECKLIST = (
    ('product', -90, 'Chốt danh sách sản phẩm ra mắt và hồ sơ thiết kế liên quan', 'Danh sách hồ sơ thiết kế', True, False),
    ('price', -90, 'Chốt mục tiêu ra mắt: sản lượng, doanh thu, kênh bán', 'Mục tiêu đã duyệt', True, False),
    ('marketing', -90, 'Định vị sản phẩm, khách hàng mục tiêu, thông điệp chính', 'Brief định vị', False, False),
    ('product', -60, 'Duyệt mẫu chuẩn và tài liệu kỹ thuật', 'Mẫu chuẩn đã duyệt', True, True),
    ('production', -60, 'Lập kế hoạch sản xuất đợt đầu', 'Kế hoạch sản xuất', True, False),
    ('production', -60, 'Đặt nguyên phụ liệu chính', 'Đơn mua NPL', True, False),
    ('marketing', -60, 'Lên kế hoạch truyền thông ra mắt', 'Kế hoạch truyền thông', False, False),
    ('price', -30, 'Chốt giá thành và giá bán lẻ / sỉ', 'Bảng giá đã duyệt', True, True),
    ('product', -30, 'Tạo mã Style / SKU / mã vạch trên danh mục sản phẩm', 'SKU trên Thư viện sản phẩm', True, True),
    ('production', -30, 'NPL về đủ, đưa vào chuyền sản xuất', 'Lệnh sản xuất', True, False),
    ('marketing', -30, 'Chụp ảnh sản phẩm, quay video', 'Bộ ảnh / video', False, False),
    ('channel', -30, 'Lên kế hoạch phân bổ hàng theo kênh / cửa hàng', 'Bảng phân bổ', False, False),
    ('production', -14, 'Hoàn thành sản xuất, kiểm tra chất lượng đạt', 'Biên bản QC', True, True),
    ('marketing', -14, 'Hoàn thiện nội dung: bài đăng, mô tả sản phẩm, banner', 'Nội dung đã duyệt', False, False),
    ('channel', -14, 'Đưa sản phẩm lên KiotViet / website (chưa mở bán)', 'Sản phẩm trên KiotViet / web', True, True),
    ('channel', -14, 'Đào tạo nhân viên bán hàng về sản phẩm mới', 'Tài liệu đào tạo', False, False),
    ('logistics', -7, 'Nhập kho thành phẩm đủ số lượng ra mắt', 'Phiếu nhập kho', True, True),
    ('logistics', -7, 'Phân phối hàng về cửa hàng / kho kênh online', 'Phiếu chuyển hàng', True, False),
    ('marketing', -7, 'Teaser / thông báo trước ra mắt', 'Bài teaser', False, False),
    ('channel', -2, 'Kiểm tra trưng bày, giá, tồn tại điểm bán', 'Checklist cửa hàng', True, True),
    ('marketing', -2, 'Lên lịch đăng bài / quảng cáo ngày ra mắt', 'Lịch đăng bài', False, False),
    ('channel', 0, 'Mở bán chính thức trên các kênh', 'Sản phẩm hiển thị bán', True, False),
    ('marketing', 0, 'Đăng bài ra mắt, chạy quảng cáo', 'Bài đăng ra mắt', False, False),
    ('logistics', 1, 'Theo dõi tồn sau ngày đầu, bổ sung hàng thiếu', 'Đề xuất bổ sung', False, False),
)


def load_default_checklist(TemplateItem) -> int:
    created = 0
    for idx, (group, offset, title, deliverable, high, blocker) in enumerate(DEFAULT_CHECKLIST):
        _obj, was_created = TemplateItem.objects.get_or_create(
            group=group,
            offset_days=offset,
            title=title,
            defaults={
                'deliverable': deliverable,
                'importance': 'high' if high else 'normal',
                'is_go_blocker': blocker,
                'sort_order': (idx + 1) * 10,
            },
        )
        created += int(was_created)
    return created
