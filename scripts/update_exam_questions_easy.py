"""Thay cau hoi 4 de cuoi khoa bang bo de hon (van dung kien thuc khoa hoc)."""
from __future__ import annotations

from django.db import transaction

from assessment.models import Choice, Competency, Question
from training.models import Course

COURSE_IDS = (4, 5, 6, 7)
SHORT = {4: "Inkscape", 5: "Kdenlive", 6: "LibreOffice", 7: "Blender"}


def pack(q_type, content, answers=None, correct=None):
    pts = {"single": 0.4, "multiple": 0.5, "essay": 1.5}[q_type]
    if q_type == "essay":
        return {"content": content, "q_type": q_type, "points": pts, "choices": []}
    if isinstance(correct, int):
        correct = (correct,)
    correct = set(correct or ())
    return {
        "content": content,
        "q_type": q_type,
        "points": pts,
        "choices": [(t, i in correct) for i, t in enumerate(answers or [])],
    }


def S(content, answers, correct):
    return pack("single", content, answers, correct)


def M(content, answers, correct):
    return pack("multiple", content, answers, correct)


BANKS = {
    4: {
        "single": [
            S(
                "Trong Inkscape, Fill và Stroke khác nhau chỗ nào?",
                [
                    "Fill là màu tô bên trong hình, Stroke là đường viền.",
                    "Fill là đường viền, Stroke là màu nền trang.",
                    "Hai cái giống nhau, chỉ khác tên menu.",
                    "Fill chỉ dùng cho chữ, Stroke chỉ dùng cho ảnh.",
                ],
                0,
            ),
            S(
                "Muốn nhân bản một đối tượng, thao tác phổ biến nhất là gì?",
                [
                    "Duplicate (Ctrl+D) hoặc Copy + Paste.",
                    "Xóa đối tượng rồi vẽ lại từ đầu.",
                    "Chỉ có thể Save As file mới.",
                    "Phải Convert to bitmap trước.",
                ],
                0,
            ),
            S(
                "Công cụ nào dùng để sửa các điểm (node) trên đường path?",
                [
                    "Node tool (chỉnh node / F2).",
                    "Text tool.",
                    "Dropper (pipette) chọn màu.",
                    "Zoom tool.",
                ],
                0,
            ),
            S(
                "Muốn viết chữ trong Inkscape, nên dùng công cụ nào?",
                [
                    "Text tool (công cụ văn bản).",
                    "Bezier / Pen tool.",
                    "Spray tool.",
                    "Calligraphy tool bắt buộc.",
                ],
                0,
            ),
            S(
                "Khi nào nên xuất PNG, khi nào giữ SVG?",
                [
                    "PNG cho ảnh web/xem nhanh (pixel); SVG giữ vector, sửa được về sau.",
                    "PNG luôn nét hơn SVG khi phóng to.",
                    "SVG không gửi được cho người khác.",
                    "Hai định dạng hoàn toàn giống nhau.",
                ],
                0,
            ),
            S(
                "Layer (lớp) trong Inkscape dùng để làm gì?",
                [
                    "Tách nhóm đối tượng (ví dụ chữ / hình / nền) để ẩn, khóa, chỉnh cho dễ.",
                    "Tự động xuất PDF.",
                    "Chỉ đổi đơn vị mm/px.",
                    "Xóa hết hướng dẫn (guides).",
                ],
                0,
            ),
            S(
                "Path > Union dùng khi nào?",
                [
                    "Gộp nhiều hình chồng nhau thành một hình.",
                    "Tách chữ thành từng ký tự.",
                    "Đổi màu stroke.",
                    "Xoay trang tài liệu.",
                ],
                0,
            ),
            S(
                "Align and Distribute giúp việc gì?",
                [
                    "Căn đều, căn giữa, căn trái/phải các đối tượng cho thẳng hàng.",
                    "Tô gradient.",
                    "Tạo mã QR.",
                    "Cắt ảnh nền tự động.",
                ],
                0,
            ),
            S(
                "Trước khi gửi file Inkscape cho đồng nghiệp, nên kiểm tra điều gì?",
                [
                    "Font chữ, ảnh có đính kèm (embed) hoặc gửi kèm thư mục ảnh, nội dung không bị tràn trang.",
                    "Chỉ cần xem thumbnail Windows là đủ.",
                    "Bắt buộc đổi sang JPEG.",
                    "Xóa hết layer cho file nhẹ.",
                ],
                0,
            ),
            S(
                "Document Properties nên đặt đơn vị nào khi làm file in ấn khổ giấy?",
                [
                    "mm (hoặc đơn vị khớp khổ in), và kiểm tra kích thước trang.",
                    "Luôn để px, không cần quan tâm khổ.",
                    "Chỉ cm mới in được.",
                    "Đơn vị không ảnh hưởng file xuất.",
                ],
                0,
            ),
        ],
        "multiple": [
            M(
                "Những thao tác cơ bản khi chỉnh một hình trong Inkscape?",
                [
                    "Di chuyển (Move).",
                    "Scale (phóng to/thu nhỏ).",
                    "Rotate (xoay).",
                    "Bắt buộc Trace Bitmap mọi hình.",
                ],
                (0, 1, 2),
            ),
            M(
                "Có thể đổi màu đối tượng bằng cách nào?",
                [
                    "Chọn Fill/Stroke trên thanh dưới hoặc hộp thoại Fill and Stroke.",
                    "Dùng Dropper lấy màu từ chỗ khác.",
                    "Chọn swatch/mẫu màu.",
                    "Chỉ đổi được màu khi xuất PNG.",
                ],
                (0, 1, 2),
            ),
            M(
                "Inkscape thường xuất được những định dạng nào?",
                [
                    "SVG",
                    "PNG",
                    "PDF",
                    "File dự án Blender (.blend)",
                ],
                (0, 1, 2),
            ),
            M(
                "Khi làm logo chữ, những bước nào hợp lý?",
                [
                    "Gõ text, chọn font, chỉnh khoảng cách chữ.",
                    "Căn giữa trên trang.",
                    "Xuất PNG để xem nhanh.",
                    "Bắt buộc mesh gradient cho mọi logo.",
                ],
                (0, 1, 2),
            ),
            M(
                "Những việc nên làm để file gọn, dễ sửa?",
                [
                    "Đặt tên layer/đối tượng rõ ràng.",
                    "Xóa đối tượng ẩn không dùng.",
                    "Group các phần thuộc về nhau.",
                    "Nhân bản 200 lần rồi Union tất cả.",
                ],
                (0, 1, 2),
            ),
            M(
                "Snap (hít điểm) hữu ích khi nào?",
                [
                    "Căn cạnh hình cho khớp nhau.",
                    "Bắt đúng node/góc khi vẽ.",
                    "Căn theo lưới (grid).",
                    "Tự động viết nội dung marketing.",
                ],
                (0, 1, 2),
            ),
            M(
                "Ảnh trong file Inkscape có thể ở dạng nào?",
                [
                    "Nhúng (embed) trong file SVG.",
                    "Liên kết (link) tới file ảnh bên ngoài.",
                    "Vẽ vector thay vì ảnh nếu làm logo đơn giản.",
                    "Chỉ chấp nhận ảnh RAW máy ảnh.",
                ],
                (0, 1, 2),
            ),
            M(
                "Trước khi in hoặc cắt decal, nên kiểm tra?",
                [
                    "Chữ không bị cắt cụt.",
                    "Kích thước thật (mm) đúng yêu cầu.",
                    "Đường cắt/viền còn đủ rõ.",
                    "Bật hết bộ lọc mờ (blur) cho sắc nét hơn.",
                ],
                (0, 1, 2),
            ),
            M(
                "Công cụ nào thường dùng khi vẽ logo đơn giản?",
                [
                    "Hình có sẵn (rectangle, ellipse).",
                    "Bezier / Pen để vẽ path.",
                    "Text tool.",
                    "Physics simulation 3D.",
                ],
                (0, 1, 2),
            ),
        ],
        "essay": (
            "Hãy nêu các bước tạo một logo chữ đơn giản trong Inkscape (tối thiểu 5 bước: "
            "tạo trang, gõ chữ, chọn font/màu, căn giữa, xuất file). Viết thêm 1 lưu ý khi "
            "gửi file cho đồng nghiệp (font hoặc ảnh)."
        ),
    },
    5: {
        "single": [
            S(
                "Timeline trong Kdenlive dùng để làm gì?",
                [
                    "Sắp xếp, cắt, chồng video/audio theo thời gian.",
                    "Chỉ để đổi tên file.",
                    "Chỉ để tải plugin.",
                    "Xóa hẳn file gốc trên máy.",
                ],
                0,
            ),
            S(
                "Muốn cắt bỏ đoạn thừa của clip, cách làm cơ bản là gì?",
                [
                    "Đặt con trỏ ở điểm cắt, dùng công cụ cắt/razor rồi xóa phần không cần.",
                    "Phải quay lại video từ đầu.",
                    "Chỉ cắt được khi đã xuất mp4.",
                    "Kéo thanh volume là cắt video.",
                ],
                0,
            ),
            S(
                "Proxy clip dùng khi nào?",
                [
                    "Khi máy chạy nặng với video 4K: edit bản nhẹ, xuất vẫn dùng bản gốc.",
                    "Proxy thay thế vĩnh viễn file gốc.",
                    "Bắt buộc với mọi clip 720p.",
                    "Proxy chỉ dùng cho audio.",
                ],
                0,
            ),
            S(
                "Transition (chuyển cảnh) cần điều kiện gì để chạy mượt?",
                [
                    "Hai clip phải chồng/đủ phần dư (handle), không cắt sát quá.",
                    "Chỉ cần đổi tên clip thành Transition.",
                    "Bắt buộc GPU RTX.",
                    "Chỉ dùng được với ảnh PNG.",
                ],
                0,
            ),
            S(
                "Color correction khác color grading ở mức đơn giản?",
                [
                    "Correction chỉnh sáng/trắng cho đúng; grading tạo style màu (ấm, lạnh…).",
                    "Hai khái niệm hoàn toàn trùng nhau.",
                    "Grading chỉ chỉnh âm thanh.",
                    "Correction chỉ dùng khi xuất dọc 9:16.",
                ],
                0,
            ),
            S(
                "Muốn làm video dọc (9:16) từ clip ngang, nên làm gì?",
                [
                    "Đổi khung dự án 9:16 rồi crop/reframe theo chủ thể, không kéo giãn méo hình.",
                    "Stretch cho kín khung, méo cũng được.",
                    "Xoay điện thoại lúc xuất là đủ.",
                    "Kdenlive không làm được video dọc.",
                ],
                0,
            ),
            S(
                "Subtitle (phụ đề) sau khi tạo bằng speech-to-text nên làm gì?",
                [
                    "Đọc lại, sửa lỗi chính tả/tên riêng, chỉnh thời điểm hiện chữ.",
                    "Tin 100%, xuất luôn không cần xem.",
                    "Phụ đề tự burn vào file gốc, không sửa được.",
                    "Chỉ hiện khi dùng proxy.",
                ],
                0,
            ),
            S(
                "Khi xuất video giao khách, nên kiểm tra điều nào trước?",
                [
                    "Xem lại cắt, tiếng, chữ; chắc đang xuất bản gốc (không nhầm proxy).",
                    "Xóa hết hiệu ứng cho file nhẹ.",
                    "Xuất file .kdenlive gửi khách xem luôn.",
                    "Tắt audio để lên top YouTube.",
                ],
                0,
            ),
            S(
                "Picture-in-picture (hình trong hình) thường làm bằng cách nào?",
                [
                    "Để clip phụ trên track trên, thu nhỏ/đặt góc bằng Transform/Composite.",
                    "Bắt buộc hai project riêng rồi ghép Windows.",
                    "Chỉ làm được với ảnh, không với video.",
                    "Crop timeline thành 2 project.",
                ],
                0,
            ),
            S(
                "File dự án Kdenlive (.kdenlive) khác file mp4 xuất ra chỗ nào?",
                [
                    "File dự án lưu cách dựng, vẫn cần clip gốc; mp4 là video đã render.",
                    "Hai file giống nhau, đổi đuôi là được.",
                    "Xóa clip gốc vẫn mở .kdenlive đầy đủ hình.",
                    "mp4 mới sửa được timeline.",
                ],
                0,
            ),
        ],
        "multiple": [
            M(
                "Một quy trình dựng clip ngắn thường có những bước nào?",
                [
                    "Nhập footage vào project.",
                    "Cắt bỏ đoạn thừa trên timeline.",
                    "Xuất (render) ra mp4.",
                    "Xóa file gốc ngay khi kéo vào timeline.",
                ],
                (0, 1, 2),
            ),
            M(
                "Audio cần chú ý những gì?",
                [
                    "Không để tiếng rè / quá to bị vỡ.",
                    "Lời thoại nghe rõ hơn nhạc nền.",
                    "Cắt tiếng thừa, khoảng lặng dài.",
                    "Tắt hết tiếng để video nhẹ.",
                ],
                (0, 1, 2),
            ),
            M(
                "Khi máy preview giật, có thể làm gì?",
                [
                    "Bật proxy.",
                    "Giảm độ phân giải preview.",
                    "Tắt bớt hiệu ứng lúc edit.",
                    "Tăng timeline thành 8K.",
                ],
                (0, 1, 2),
            ),
            M(
                "Phụ đề tốt nên đảm bảo?",
                [
                    "Đúng nội dung, ít lỗi chính tả.",
                    "Hiện đủ lâu để đọc.",
                    "Không che mặt người nói nếu có thể.",
                    "Font càng nhỏ càng chuyên nghiệp.",
                ],
                (0, 1, 2),
            ),
            M(
                "Khi làm clip cho mạng xã hội (dọc) nên?",
                [
                    "Khung 9:16.",
                    "Chủ thể nằm trong vùng an toàn (không sát mép).",
                    "Chữ to, dễ đọc trên điện thoại.",
                    "Giữ nguyên letterbox đen dày cho 'đúng điện ảnh'.",
                ],
                (0, 1, 2),
            ),
            M(
                "Những thành phần thường có trên timeline?",
                [
                    "Video track",
                    "Audio track",
                    "Title / subtitle",
                    "File Excel kế toán",
                ],
                (0, 1, 2),
            ),
            M(
                "Trước khi render giao việc, nên?",
                [
                    "Xem lại toàn bộ 1 lần.",
                    "Kiểm tra profile xuất (nơi lưu, độ phân giải).",
                    "Giữ bản dự án + footage để sửa sau.",
                    "Đổi FPS lung tung cho 'mượt hơn'.",
                ],
                (0, 1, 2),
            ),
            M(
                "Hiệu ứng hay dùng cho clip nội bộ?",
                [
                    "Cắt / dissolve chuyển cảnh đơn giản.",
                    "Chữ tiêu đề.",
                    "Chỉnh sáng cho clip tối.",
                    "Xóa người trong video bằng AI cho mọi shot handheld.",
                ],
                (0, 1, 2),
            ),
            M(
                "Logo PNG đè lên video, nên nhớ?",
                [
                    "Đặt track phía trên.",
                    "Chỉnh kích thước/vị trí cho vừa.",
                    "Kiểm tra nền trong suốt (alpha) hiện đúng.",
                    "Luôn kéo giãn logo cho méo để kín khung.",
                ],
                (0, 1, 2),
            ),
        ],
        "essay": (
            "Hãy viết quy trình dựng một video ngắn trong Kdenlive (khoảng 5–7 bước): "
            "từ tạo project, nhập clip, cắt đoạn thừa, thêm chữ hoặc chuyển cảnh, kiểm tra tiếng, "
            "đến lúc xuất file. Viết thêm 1 lỗi hay gặp khi máy chạy chậm và cách xử lý."
        ),
    },
    6: {
        "single": [
            S(
                "LibreOffice Writer dùng chủ yếu để làm gì?",
                [
                    "Soạn thảo văn bản: thông báo, SOP, biên bản, thư.",
                    "Tính bảng lương phức tạp như spreadsheet.",
                    "Dựng phim.",
                    "Vẽ 3D.",
                ],
                0,
            ),
            S(
                "LibreOffice Calc giống nhất phần mềm nào?",
                [
                    "Bảng tính (như Excel): số liệu, công thức, biểu đồ.",
                    "Phần mềm chỉnh ảnh.",
                    "Trình duyệt web.",
                    "Trình soạn thảo chỉ gõ chữ, không có ô.",
                ],
                0,
            ),
            S(
                "Vì sao nên dùng Heading / style có sẵn thay vì chỉ bôi đậm, tăng cỡ chữ tay?",
                [
                    "Dễ sửa đồng loạt, làm mục lục tự động, tài liệu thống nhất.",
                    "Style làm file nặng hơn bôi đậm tay.",
                    "Heading không hiện khi in.",
                    "PDF không nhận style.",
                ],
                0,
            ),
            S(
                "Mục lục (Table of Contents) lấy nội dung từ đâu?",
                [
                    "Từ các đoạn gán style Heading (Heading 1, 2…), rồi cập nhật mục lục.",
                    "Từ những dòng in đậm bất kỳ.",
                    "Từ comment.",
                    "Phải gõ tay từng dòng, không tự được.",
                ],
                0,
            ),
            S(
                "Trong Calc, công thức bắt đầu bằng ký tự nào?",
                [
                    "Dấu = (ví dụ =A1+B1).",
                    "Dấu #.",
                    "Dấu @ bắt buộc mọi ô.",
                    "Không cần dấu, gõ SUM là chạy.",
                ],
                0,
            ),
            S(
                "VLOOKUP / FIND & REPLACE: cách tra cứu đơn giản đúng nhất?",
                [
                    "Dùng hàm tra cứu (VLOOKUP hoặc INDEX/MATCH) theo mã; hoặc Ctrl+H thay thế chữ.",
                    "Xóa hết cột rồi gõ lại.",
                    "Calc không tìm được chữ.",
                    "Chỉ in ra giấy rồi dò tay.",
                ],
                0,
            ),
            S(
                "Khi nhập ngày tháng từ CSV, lỗi hay gặp là gì?",
                [
                    "Ngày bị đảo tháng/ngày vì định dạng locale khác nhau.",
                    "Calc tự đổi mọi ngày thành chữ 'OK'.",
                    "CSV không mở được trong Calc.",
                    "Ngày luôn đúng bất kể cách gõ.",
                ],
                0,
            ),
            S(
                "Track Changes trong Writer dùng khi nào?",
                [
                    "Khi nhiều người sửa SOP: thấy chỗ sửa, chấp nhận hoặc từ chối.",
                    "Khi vẽ biểu đồ.",
                    "Khi tính tổng cột.",
                    "Chỉ dùng cho mail merge nhãn.",
                ],
                0,
            ),
            S(
                "Nên lưu file gốc Writer/Calc bằng định dạng nào?",
                [
                    "ODT / ODS (định dạng gốc LibreOffice); xuất DOCX/XLSX khi đối tác cần.",
                    "Chỉ JPG.",
                    "Luôn chỉ PDF, không giữ file gốc.",
                    ".blend",
                ],
                0,
            ),
            S(
                "Căn lề, số trang, header/footer nằm ở đâu về mặt ý tưởng?",
                [
                    "Thuộc kiểu trang (Page Style) / phần đầu-cuối trang, không phải gõ tay từng trang.",
                    "Phải copy text box số trang cho từng tờ.",
                    "Writer không có số trang.",
                    "Chỉ hiện khi mở bằng Word.",
                ],
                0,
            ),
        ],
        "multiple": [
            M(
                "Những việc phù hợp với Writer?",
                [
                    "Viết thông báo nội bộ.",
                    "Làm SOP có heading và mục lục.",
                    "Trộn thư / nhãn (mail merge) danh sách tên.",
                    "Mô phỏng vật lý 3D.",
                ],
                (0, 1, 2),
            ),
            M(
                "Những việc phù hợp với Calc?",
                [
                    "Bảng theo dõi số liệu.",
                    "Tính tổng, trung bình bằng công thức.",
                    "Làm biểu đồ cột/đường.",
                    "Cắt video 4K.",
                ],
                (0, 1, 2),
            ),
            M(
                "Khi dán nội dung từ web/Word vào Writer, nên?",
                [
                    "Xóa định dạng trực tiếp nếu bị loạn font.",
                    "Gán lại style Heading/Body.",
                    "Kiểm tra mục lục sau khi dán.",
                    "Giữ nguyên 5 loại font lẫn trong một đoạn cho 'đẹp'.",
                ],
                (0, 1, 2),
            ),
            M(
                "Một bảng Calc 'dễ dùng' thường có?",
                [
                    "Hàng tiêu đề rõ.",
                    "Mỗi cột một loại dữ liệu (số riêng, chữ riêng).",
                    "Không gộp ô lung tung ở vùng số liệu.",
                    "Trộn chữ và số trong cùng một ô tổng.",
                ],
                (0, 1, 2),
            ),
            M(
                "Trước khi in/PDF từ Writer, nên kiểm tra?",
                [
                    "Lề, số trang, ngắt trang.",
                    "Hình không đè chữ.",
                    "Font tiếng Việt hiện đúng.",
                    "Tắt hết heading để PDF nhẹ.",
                ],
                (0, 1, 2),
            ),
            M(
                "Trong Calc, những hàm rất hay dùng?",
                [
                    "SUM",
                    "AVERAGE",
                    "IF",
                    "RENDER_CYCLES",
                ],
                (0, 1, 2),
            ),
            M(
                "Bảo vệ dữ liệu bảng tính có thể gồm?",
                [
                    "Khóa sheet, chỉ cho sửa vài ô nhập.",
                    "Data Validity (chỉ cho chọn trong danh sách).",
                    "Đặt tên vùng (named range) cho dễ hiểu.",
                    "Xóa công thức, chỉ giữ số để 'an toàn hơn luôn'.",
                ],
                (0, 1, 2),
            ),
            M(
                "Header/Footer nên chứa gì?",
                [
                    "Tên tài liệu.",
                    "Số trang.",
                    "Ngày hoặc phiên bản nếu cần.",
                    "Toàn bộ SOP 20 trang trong footer.",
                ],
                (0, 1, 2),
            ),
            M(
                "Khi gửi file cho người dùng Word/Excel, nên?",
                [
                    "Xuất thêm DOCX/XLSX nếu họ không có LibreOffice.",
                    "Mở lại file đã xuất để xem có lệch không.",
                    "Giữ bản ODT/ODS gốc.",
                    "Đổi đuôi .odt thành .docx trong Windows là đủ, không cần Export.",
                ],
                (0, 1, 2),
            ),
        ],
        "essay": (
            "Hãy cho biết Writer dùng khi nào, Calc dùng khi nào (mỗi bên 2 ví dụ việc văn phòng). "
            "Nêu 3 thói quen làm tài liệu cho sạch: dùng style/heading, đặt tên file rõ, "
            "và kiểm tra trước khi in hoặc gửi đi."
        ),
    },
    7: {
        "single": [
            S(
                "Ba thao tác biến đổi cơ bản trong Blender là gì?",
                [
                    "Move (G), Rotate (R), Scale (S).",
                    "Fill, Stroke, Trace.",
                    "Cut, Mix, Proxy.",
                    "SUM, IF, VLOOKUP.",
                ],
                0,
            ),
            S(
                "Object Mode khác Edit Mode ở điểm nào?",
                [
                    "Object Mode chỉnh cả object (vị trí/xoay/scale); Edit Mode sửa mesh (vertex, cạnh, mặt).",
                    "Hai mode hoàn toàn giống nhau.",
                    "Edit Mode chỉ đổi màu đèn.",
                    "Object Mode không di chuyển được object.",
                ],
                0,
            ),
            S(
                "Phím tắt phổ biến để thêm mesh có sẵn (Cube, UV Sphere…)?",
                [
                    "Shift+A (Add).",
                    "Ctrl+S (đó là lưu file).",
                    "H (ẩn).",
                    "X chỉ thêm camera.",
                ],
                0,
            ),
            S(
                "Render ảnh tĩnh khác viewport (cửa sổ 3D) chỗ nào?",
                [
                    "Render (F12) ra ảnh cuối theo engine; viewport chỉ xem trước, chất lượng/ánh sáng có thể khác.",
                    "Viewport chính là file PNG giao khách.",
                    "F12 xóa mesh.",
                    "Render không cần đèn và camera.",
                ],
                0,
            ),
            S(
                "Modifier Subdivision Surface dùng để làm gì (mức cơ bản)?",
                [
                    "Làm bề mặt mịn hơn bằng cách chia nhỏ mesh (xem trước, chưa hẳn apply).",
                    "Tự động rig nhân vật.",
                    "Xuất video TikTok.",
                    "Đổi ngôn ngữ giao diện.",
                ],
                0,
            ),
            S(
                "Vì sao hay nhắc Apply Scale (Ctrl+A) trước khi làm tiếp?",
                [
                    "Scale khác 1 dễ làm bevel, modifier, animation lệch.",
                    "Apply Scale xóa luôn model.",
                    "Chỉ camera mới cần apply.",
                    "Blender tự apply khi bấm Play.",
                ],
                0,
            ),
            S(
                "Cycles khác EEVEE ở mức hiểu đơn giản?",
                [
                    "Cycles tính ánh sáng thật hơn, thường chậm; EEVEE nhanh, gần realtime, chất lượng khác một chút.",
                    "EEVEE luôn giống từng pixel với Cycles.",
                    "Cycles không render được ảnh tĩnh.",
                    "Hai engine không chọn được trong Scene.",
                ],
                0,
            ),
            S(
                "Muốn xuất animation an toàn, nên xuất thế nào?",
                [
                    "Xuất chuỗi ảnh (PNG/EXR) rồi ghép video; tránh chỉ encode một file dài dễ mất nếu crash.",
                    "Chỉ lưu .blend là khách xem được phim.",
                    "Play trong viewport rồi quay màn hình là chuẩn studio.",
                    "Animation không cần frame range.",
                ],
                0,
            ),
            S(
                "Shade Smooth dùng để làm gì?",
                [
                    "Làm bóng mượt trên bề mặt, không đổi topology mesh.",
                    "Giảm số vertex xuống 4.",
                    "Tự cap mọi lỗ mesh.",
                    "Đổi metallic thành 1.",
                ],
                0,
            ),
            S(
                "File .blend nên nhớ điều gì?",
                [
                    "Là file dự án: mesh, vật liệu, animation; nên Save As/version, đừng chỉ giữ 1 bản.",
                    "Gửi .blend là khách luôn xem được như mp4.",
                    "Xóa texture vẫn giữ nguyên mọi ảnh.",
                    ".blend chỉ chứa screenshot viewport.",
                ],
                0,
            ),
        ],
        "multiple": [
            M(
                "Giao diện Blender thường có những vùng nào?",
                [
                    "3D Viewport",
                    "Outliner (danh sách object)",
                    "Properties (tab modifier, material, render…)",
                    "Timeline Kdenlive",
                ],
                (0, 1, 2),
            ),
            M(
                "Trong Edit Mode có thể chọn?",
                [
                    "Vertex",
                    "Edge",
                    "Face",
                    "Clip proxy Kdenlive",
                ],
                (0, 1, 2),
            ),
            M(
                "Trước khi render giao ảnh, nên kiểm tra?",
                [
                    "Camera nhìn đúng góc.",
                    "Có đèn, không bị tối đen.",
                    "Output folder và định dạng ảnh.",
                    "Xóa hết material cho nhẹ máy.",
                ],
                (0, 1, 2),
            ),
            M(
                "Những modifier hay gặp khi mới học?",
                [
                    "Subdivision Surface",
                    "Mirror",
                    "Boolean (cắt/ghép hình)",
                    "Mail Merge Writer",
                ],
                (0, 1, 2),
            ),
            M(
                "Lưu file làm việc tốt gồm?",
                [
                    "Ctrl+S thường xuyên.",
                    "Save As bản có ngày/phiên bản.",
                    "Đặt tên object rõ (Cube.023 nên đổi tên).",
                    "Chỉ nhớ undo, không cần lưu.",
                ],
                (0, 1, 2),
            ),
            M(
                "Material PBR cơ bản thường có?",
                [
                    "Base Color",
                    "Roughness (nhám/bóng)",
                    "Metallic (0 với nhựa, 1 với kim loại)",
                    "Fill and Stroke của Inkscape.",
                ],
                (0, 1, 2),
            ),
            M(
                "Khi mesh bị lỗ / Boolean hỏng, hướng xử lý đơn giản?",
                [
                    "Kiểm tra mặt bị lật (normals).",
                    "Khép lỗ (fill) nếu mesh hở.",
                    "Lưu bản trước khi boolean.",
                    "Shade Smooth sẽ tự vá mọi lỗ.",
                ],
                (0, 1, 2),
            ),
            M(
                "Làm nhân vật cử động (mức hiểu) cần?",
                [
                    "Armature / bones (rig).",
                    "Gắn mesh với xương (weight).",
                    "Keyframe animation.",
                    "Chỉ bấm Shade Smooth là nhân vật tự đi.",
                ],
                (0, 1, 2),
            ),
            M(
                "Khi máy chậm trong viewport, có thể?",
                [
                    "Giảm mức Subdivision lúc edit.",
                    "Ẩn object không dùng.",
                    "Dùng EEVEE/viewport shading đơn giản hơn.",
                    "Subdiv level 6 cho mọi cube.",
                ],
                (0, 1, 2),
            ),
        ],
        "essay": (
            "Hãy nêu phím tắt Move, Rotate, Scale và sự khác nhau giữa Object Mode với Edit Mode. "
            "Sau đó viết 4 bước xuất một ảnh render tĩnh (chọn camera, bật đèn, F12, lưu file). "
            "Thêm 1 lời khuyên khi file nặng hoặc máy chậm."
        ),
    },
}

DESCS = {
    4: (
        "Bài kiểm tra cuối khóa Inkscape. Thời gian làm bài 60 phút, gồm 20 câu "
        "(trắc nghiệm và 1 câu tự luận). Nội dung đánh giá thao tác thiết kế vector "
        "đã học trong khóa."
    ),
    5: (
        "Bài kiểm tra cuối khóa Kdenlive. Thời gian làm bài 60 phút, gồm 20 câu "
        "(trắc nghiệm và 1 câu tự luận). Nội dung đánh giá kỹ năng dựng phim cơ bản: "
        "cắt dựng, chữ/phụ đề và xuất file."
    ),
    6: (
        "Bài kiểm tra cuối khóa LibreOffice (Writer và Calc). Thời gian làm bài 60 phút, "
        "gồm 20 câu (trắc nghiệm và 1 câu tự luận). Nội dung đánh giá kỹ năng soạn thảo "
        "văn bản và xử lý bảng tính."
    ),
    7: (
        "Bài kiểm tra cuối khóa Blender. Thời gian làm bài 60 phút, gồm 20 câu "
        "(trắc nghiệm và 1 câu tự luận). Nội dung đánh giá thao tác 3D cơ bản: "
        "biến đổi đối tượng, chỉnh mesh và render."
    ),
}


def create_mc(comp, spec):
    q = Question.objects.create(
        competency=comp,
        content=spec["content"],
        q_type=spec["q_type"],
        points=spec["points"],
    )
    Choice.objects.bulk_create(
        [
            Choice(question=q, text=text[:500], is_correct=ok, sort_order=idx)
            for idx, (text, ok) in enumerate(spec["choices"], start=1)
        ]
    )
    return q


print("EASY_EXAMS_START")
with transaction.atomic():
    for cid in COURSE_IDS:
        course = Course.objects.get(id=cid)
        exam = course.final_exam
        if exam is None:
            print("SKIP_NO_EXAM", cid)
            continue
        bank = BANKS[cid]
        if len(bank["single"]) != 10 or len(bank["multiple"]) != 9:
            raise ValueError(f"C{cid} bank size {len(bank['single'])}/{len(bank['multiple'])}")

        old_ids = list(exam.questions.values_list("id", flat=True))
        short = SHORT[cid]
        comp, _ = Competency.objects.get_or_create(
            name=f"[KH{cid}] {short}",
            defaults={"description": f"Đề thi cuối khóa — {course.title}"},
        )
        questions = [create_mc(comp, s) for s in bank["single"]]
        questions += [create_mc(comp, m) for m in bank["multiple"]]
        questions.append(
            Question.objects.create(
                competency=comp,
                content=bank["essay"],
                q_type="essay",
                points=1.5,
            )
        )
        exam.replace_questions(questions)
        exam.description = DESCS[cid]
        exam.save(update_fields=["description"])
        Question.objects.filter(id__in=old_ids).delete()
        pts = sum(q.points for q in questions)
        types = [q.q_type for q in questions]
        print("OK", cid, exam.id, "n", len(questions), "pts", pts, "types", types)

print("EASY_EXAMS_DONE")
