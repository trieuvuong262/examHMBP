"""Tao 1 bai kiem tra / 1 bai hoc cho 4 khoa 4,5,6,7 tren VPS.

Moi de: 10 TN 1 dap an (0.4) + 9 TN nhieu dap an (0.5) + 1 tu luan (1.5) = 10 diem.
Thoi gian: 19/09/2026 00:00 -> 19/09/2027 00:00 (Asia/Ho_Chi_Minh), 60 phut.
Doi tuong: assigned_users cua khoa.
"""
from __future__ import annotations

import random
from datetime import datetime
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from assessment.models import Choice, Competency, Exam, ExamQuestion, Question
from training.models import Course, Lesson

COURSE_IDS = (4, 5, 6, 7)
MARKER = "SEED:COURSE_LESSON_EXAM"
TZ = ZoneInfo("Asia/Ho_Chi_Minh")
START = timezone.make_aware(datetime(2026, 9, 19, 0, 0, 0), TZ)
END = timezone.make_aware(datetime(2027, 9, 19, 0, 0, 0), TZ)
DURATION = 60
SHORT = {4: "Inkscape", 5: "Kdenlive", 6: "LibreOffice", 7: "Blender"}

ESSAY_TEMPLATES = (
    (
        "Dựa trên bài «{title}» của khóa {course}, hãy mô tả quy trình thao tác chuẩn "
        "(tối thiểu 5 bước), nêu 2 sai lầm kỹ thuật dễ làm hỏng file sản xuất, và cách "
        "kiểm tra kết quả trước khi bàn giao cho bộ phận in ấn / truyền thông JustPlay."
    ),
    (
        "Phân tích vì sao kỹ thuật trong bài «{title}» dễ thất bại trên máy cấu hình thấp "
        "hoặc file lớn. Đề xuất pipeline thay thế đạt chất lượng tương đương, nêu rõ "
        "tham số then chốt phải giữ và tham số được phép giảm."
    ),
    (
        "So sánh hai cách tiếp cận để đạt kết quả như bài «{title}». Nêu khi nào chọn "
        "cách nào trong công việc thực tế (deadline gấp, file phải chỉnh sửa lại, xuất "
        "đa định dạng). Kết luận phải có tiêu chí quyết định, không mô tả chung chung."
    ),
)


def pack(q_type, content, answers=None, correct=None):
    pts = {"single": 0.4, "multiple": 0.5, "essay": 1.5}[q_type]
    if q_type == "essay":
        return {"content": content, "q_type": q_type, "points": pts, "choices": []}
    if isinstance(correct, int):
        correct = (correct,)
    correct = set(correct or ())
    choices = [(text, i in correct) for i, text in enumerate(answers or [])]
    return {"content": content, "q_type": q_type, "points": pts, "choices": choices}


def S(content, answers, correct):
    return pack("single", content, answers, correct)


def M(content, answers, correct):
    return pack("multiple", content, answers, correct)


INKSCAPE = {
    "single": [
        S(
            "Trong Inkscape, khác biệt then chốt giữa Clip và Mask khi xuất SVG sang máy in RIP là gì?",
            [
                "Clip cắt theo hình học của clip-path (vector), Mask điều khiển độ đục theo độ sáng/alpha của đối tượng mask — RIP cũ thường rasterize mask và làm mất nét.",
                "Clip và Mask đều là clipping path chuẩn SVG 1.1 nên RIP luôn giữ vector.",
                "Mask luôn giữ vector, Clip luôn bị rasterize.",
                "Hai lệnh này chỉ khác nhau về shortcut, cấu trúc XML giống nhau.",
            ],
            0,
        ),
        S(
            "Một clone (Edit > Clone) bị lệch vị trí sau khi xoay object gốc. Nguyên nhân đúng nhất?",
            [
                "Clone kế thừa transform của gốc qua thuộc tính href; xoay gốc làm hệ tọa độ clone đổi theo, trừ khi đã Unlink hoặc dùng tiled clones với rotation riêng.",
                "Clone luôn độc lập transform, lỗi do snap-to-grid.",
                "Phải Convert to bitmap trước khi xoay gốc.",
                "Chỉ xảy ra khi file dùng đơn vị px thay vì mm.",
            ],
            0,
        ),
        S(
            "Path > Difference và Path > Exclusion khác nhau thế nào trên hai path tự cắt?",
            [
                "Difference trừ path trên khỏi path dưới (hướng phụ thuộc z-order). Exclusion lấy phần không chồng và giữ cả hai miền còn lại, fill-rule ảnh hưởng lỗ.",
                "Hai lệnh cho ra path giống hệt nếu fill màu khác nhau.",
                "Exclusion luôn xóa path trên, Difference luôn union.",
                "Chỉ Exclusion mới tạo compound path; Difference tạo group.",
            ],
            0,
        ),
        S(
            "Fill rule evenodd so với nonzero khi vẽ logo có vòng lồng (donut, chữ O, hình 8)?",
            [
                "evenodd tạo lỗ theo số lần path bao quanh lẻ/chẵn; nonzero phụ thuộc hướng path (clockwise/counterclockwise). Đổi hướng node có thể đóng/mở lỗ với nonzero.",
                "evenodd luôn tô đặc, nonzero luôn trong suốt.",
                "Chỉ nonzero dùng được với Stroke to Path.",
                "Hai fill-rule chỉ khác nhau khi xuất PDF/X-1a.",
            ],
            0,
        ),
        S(
            "Khi nào Object to Path là bước gần như không đảo ngược được và phải nhân bản trước?",
            [
                "Text, shapes (rect/ellipse có rx), và object đang gắn Live Path Effect — chuyển path sẽ mất live parameters (kerning, LPE stack).",
                "Mọi path Bézier đều mất editability sau Object to Path.",
                "Chỉ ảnh hưởng stroke width.",
                "Chỉ cần thiết khi dùng Mesh Gradient.",
            ],
            0,
        ),
        S(
            "Live Path Effect Pattern along Path khác Bend LPE ở điểm nào khi uốn chữ theo đường cong?",
            [
                "Pattern along Path đặt bản sao pattern theo tiếp tuyến và có thể lặp/stretch; Bend biến dạng envelope của chính object đó theo skeleton, không nhân bản motif.",
                "Hai LPE là alias của nhau từ bản 1.3.",
                "Bend chỉ chạy trên bitmap, Pattern along Path chỉ trên text.",
                "Pattern along Path luôn rasterize; Bend luôn vector.",
            ],
            0,
        ),
        S(
            "Mesh gradient của Inkscape khi xuất SVG 1.1 thuần cho trình duyệt cũ thường gặp gì?",
            [
                "Mesh không nằm trong SVG 1.1 đầy đủ; nhiều viewer bỏ mesh hoặc cần Inkscape SVG. In ấn thường phải convert mesh thành bitmap hoặc xấp xỉ bằng nhiều linear/radial.",
                "Mọi trình duyệt hiện đại render mesh giống Inkscape pixel-perfect.",
                "Mesh tự động chuyển CSS3 conic-gradient khi Save As Plain SVG.",
                "Chỉ cần bật Cairo renderer là mesh thành chuẩn SVG 2.",
            ],
            0,
        ),
        S(
            "Trace Bitmap: Multiple scans (colors) so với Brightness cutoff khi vector hóa logo 2 màu?",
            [
                "Logo 2 màu sạch nên Brightness cutoff (1 scan) rồi Union/Simplify; Multiple scans tạo nhiều path chồng theo palette, dễ rác node và lệch màu spot.",
                "Multiple scans luôn cho ít node hơn cutoff.",
                "Brightness cutoff không dùng được với PNG có alpha.",
                "Hai chế độ cho path topology giống nhau, chỉ khác fill.",
            ],
            0,
        ),
        S(
            "Stroke 'Hairline' / 0.000 mm khi gửi file cắt CNC/laser từ Inkscape nghĩa là gì?",
            [
                "Nhiều RIP/laser hiểu hairline là đường cắt không tô, không scale theo zoom; stroke có bề dày thật sẽ bị xem là khắc (engrave) hoặc in.",
                "Hairline luôn xuất thành 0.265 pt trong PDF nên máy cắt bỏ qua.",
                "Hairline chỉ là preview, file xuất luôn 1 px.",
                "Phải convert hairline thành rectangle 0.1 mm mới cắt được.",
            ],
            0,
        ),
        S(
            "Ảnh Link so với Embed trong Inkscape khi chuyển file cho xưởng khác?",
            [
                "Link giữ href tới file ngoài — thiếu file thì mất ảnh; Embed nhồi base64/XML làm file nặng nhưng tự chứa. In ấn nên embed hoặc pack vào thư mục tương đối có kiểm tra.",
                "Link luôn an toàn hơn vì SVG chuẩn cấm embed.",
                "Embed tự nén JPEG 80% nên luôn nhẹ hơn link.",
                "Hai cách giống nhau sau Save As Optimized SVG.",
            ],
            0,
        ),
        S(
            "Align and Distribute: 'Relative to Last selected' khác 'Page' khi căn 12 icon theo một key object?",
            [
                "Last selected lấy bbox của object chọn sau cùng làm chuẩn; Page căn theo trang. Muốn key object làm gốc phải click nó cuối cùng, không Shift-click lung tung.",
                "Last selected và Page luôn trùng nếu document origin ở góc dưới trái.",
                "Chỉ Page mới căn được text.",
                "Last selected bỏ qua transform matrix.",
            ],
            0,
        ),
        S(
            "Chữ cần outline để cắt decal: thứ tự đúng để tránh lỗ hổng giữa nét?",
            [
                "Object to Path → Stroke to Path (nếu có stroke) → Union các path chồng → Simplify vừa phải → kiểm tra fill-rule.",
                "Union trước Object to Path để giữ kerning.",
                "Chỉ cần Stroke to Path, không Union.",
                "Convert to bitmap 300dpi rồi Trace, đó là cách chuẩn decal.",
            ],
            0,
        ),
        S(
            "Filter Effects bị cắt cụt ở mép object khi zoom/export vì sao?",
            [
                "Vùng filter mặc định là bbox + %; glow/drop-shadow tràn ra ngoài bị clip theo filter region. Phải nới Coordinates/Dimensions trong Filter Editor.",
                "Cairo luôn clip filter theo page, không sửa được.",
                "Chỉ xảy ra với feGaussianBlur stdDeviation > 2.",
                "Phải tắt antialiasing trong Document Properties.",
            ],
            0,
        ),
        S(
            "Tiled Clones khác Spray tool khi làm họa tiết lặp cho vải/decal?",
            [
                "Tiled Clones là instance theo lưới/symmetries, sửa gốc là cả pattern đổi; Spray rải bản sao/clone rời, khó đồng bộ. Họa tiết cần edit lại về sau nên tiled clones.",
                "Spray tạo tiled clones đúng chuẩn SVG pattern.",
                "Tiled Clones luôn rasterize khi > 100 bản.",
                "Hai công cụ ghi cùng một thuộc tính inkscape:tiled.",
            ],
            0,
        ),
        S(
            "Xuất PDF cho in offset CMYK từ Inkscape, hạn chế thực tế là gì?",
            [
                "Inkscape làm việc RGB/sRGB; PDF/PostScript xuất qua Cairo, spot/CMYK không phải luồng prepress đầy đủ. Màu spot cần giả lập hoặc đưa sang Scribus/Illustrator để gán swatch.",
                "Inkscape xuất PDF/X-4 CMYK native từ bản 1.2.",
                "Chỉ cần chọn Color > CMYK trong Fill dialog là PDF thành CMYK device.",
                "ICC overlay trong SVG 1.1 được RIP luôn tôn trọng.",
            ],
            0,
        ),
        S(
            "Markers (arrow) bị méo hoặc không theo tiếp tuyến ở góc nhọn vì?",
            [
                "Marker định hướng theo mid-node tangent; góc nhọn/node trùng làm tangent bất định. Cần thêm node, đổi start/mid/end marker, hoặc Stroke to Path rồi chỉnh tay.",
                "Markers luôn scale theo stroke-width sai — phải khóa viewBox marker.",
                "Chỉ xảy ra khi dùng dash array.",
                "PDF exporter bỏ markers, nên luôn convert trước.",
            ],
            0,
        ),
        S(
            "Path > Simplify làm hỏng chữ/logo vì?",
            [
                "Simplify giảm node theo threshold, dễ phá continuities (cusp → smooth) và làm lệch điểm tiếp xúc. Logo nên simplify từng phần, giữ cusp corners.",
                "Simplify chỉ xóa node trùng, không đổi hình.",
                "Phải simplify trước Trace Bitmap.",
                "Threshold 0.0001 luôn an toàn với mọi logo.",
            ],
            0,
        ),
        S(
            "viewBox khác width/height trên thẻ SVG khi nhúng web/in?",
            [
                "viewBox định hệ tọa độ user space; width/height là viewport. Lệch tỉ lệ làm letterbox/stretch. File in nên khớp mm thật với viewBox.",
                "viewBox chỉ dùng preview Inkscape, không ghi ra file.",
                "width/height px luôn thắng viewBox khi in.",
                "Hai thuộc tính phải luôn bằng nhau theo pixel.",
            ],
            0,
        ),
        S(
            "Shape Builder (bản mới) so với Boolean cổ điển khi dựng icon phức tạp?",
            [
                "Shape Builder cắt/gộp vùng tương tác nhanh nhưng vẫn tạo path topology mới; Boolean từng bước kiểm soát z-order rõ hơn, dễ debug lỗ. File sản xuất nên kiểm tra node sau Shape Builder.",
                "Shape Builder không tạo path mới, chỉ clip nhóm.",
                "Boolean cổ điển đã bị gỡ từ 1.3, bắt buộc Shape Builder.",
                "Hai cách luôn ra XML giống hệt.",
            ],
            0,
        ),
        S(
            "Vì sao chỉnh XML Editor (sodipodi:namedview, inkscape:groupmode) nguy hiểm trên file đang chia sẻ?",
            [
                "Thuộc tính namespace Inkscape/Sodipodi không phải SVG thuần; xóa nhầm làm mất guide, layer, page. File 'Plain SVG' sẽ mất nhiều metadata này.",
                "XML Editor chỉ đọc, không ghi.",
                "Mọi thay đổi XML tự validate schema SVG 2.",
                "namedview bắt buộc cho trình duyệt, không được xóa.",
            ],
            0,
        ),
        S(
            "Perspective/Envelope LPE khác thủ công Path > Perspective khi mockup bao bì?",
            [
                "LPE giữ object gốc live, chỉnh mesh sau được; thủ công bake path, khó sửa copy. LPE có thể vỡ khi xuất Plain SVG hoặc mở phần mềm khác.",
                "Thủ công luôn live hơn LPE.",
                "Hai cách ghi cùng inkscape:perspective.",
                "LPE perspective là chuẩn SVG 2 filter.",
            ],
            0,
        ),
        S(
            "Layer vs Group khi làm file nhiều hệ màu (in + web + cắt)?",
            [
                "Layer là group có inkscape:groupmode=layer, ẩn/lock theo UI; output SVG vẫn là group. Tổ chức layer theo công đoạn (cut/print/dieline) hơn là group lung tung.",
                "Layer xuất thành SVG <layer>, Group thành <g>, RIP đọc layer name.",
                "Group không thể clip, Layer mới clip được.",
                "Chỉ Layer mới đặt blend mode.",
            ],
            0,
        ),
    ],
    "multiple": [
        M(
            "Những thao tác nào giữ được khả năng chỉnh sửa live (không bake) trong Inkscape?",
            [
                "Giữ text là text, chưa Object to Path.",
                "Dùng Live Path Effects thay vì Boolean ngay trên bản gốc.",
                "Stroke to Path trên bản gốc duy nhất.",
                "Clone/Tiled clones thay vì Duplicate hàng loạt rồi Union.",
                "Trace Bitmap rồi Simplify 5 lần liên tiếp.",
            ],
            (0, 1, 3),
        ),
        M(
            "Khi xuất file cắt decal/vinyl, những điều nào đúng?",
            [
                "Outline chữ, Union, kiểm tra compound path và lỗ (O, A, 8).",
                "Stroke cắt nên hairline hoặc bề dày máy cắt hiểu là cut.",
                "Drop-shadow SVG filter sẽ được plotter cắt như vector.",
                "Tránh mask/blur nếu máy chỉ đọc path.",
                "CMYK spot luôn cần cho đường cắt.",
            ],
            (0, 1, 3),
        ),
        M(
            "Tình huống nào nên Embed ảnh thay vì Link?",
            [
                "Gửi một file SVG cho đối tác không có thư mục tài nguyên.",
                "File sẽ lưu NAS rồi mở từ máy khác với path Windows khác.",
                "Ảnh stock 80MB đang chỉnh màu hàng ngày, cần linked để Lightroom ghi đè.",
                "Cần SVG nhỏ nhất cho web, ảnh để CDN riêng (lúc này nên link/href).",
            ],
            (0, 1),
        ),
        M(
            "Dấu hiệu XML/file Inkscape đang 'bẩn' và dễ vỡ khi mở phần mềm khác?",
            [
                "Nhiều inkscape:path-effect, sodipodi:nodetypes trên path đã bake dở.",
                "Group lồng 10 cấp, transform chồng matrix.",
                "Chỉ dùng path thuần, fill hex, không LPE.",
                "Filter phức tạp + mask + clip lồng nhau.",
            ],
            (0, 1, 3),
        ),
        M(
            "Những phát biểu đúng về Guides, Grids và Snap khi dựng icon pixel-perfect?",
            [
                "Snap to cusp nodes + bounding box giúp khớp cạnh.",
                "Grid px với origin lệch 0.5px dễ làm nét mờ khi export PNG.",
                "Guides luôn xuất sang SVG và trình duyệt hiện chúng.",
                "Disable snap to grids khi căn theo key object bằng Align.",
            ],
            (0, 1, 3),
        ),
        M(
            "Khi nào Path > Combine khác Path > Union?",
            [
                "Combine tạo compound path, giữ subpath riêng (lỗ phụ thuộc fill-rule/hướng).",
                "Union cố gắng trộn thành miền tô, thường xóa chồng lấn.",
                "Hai lệnh luôn xóa z-order như nhau.",
                "Combine không đổi fill-rule; hiểu hướng path trước khi combine logo.",
            ],
            (0, 1, 3),
        ),
        M(
            "Yếu tố nào ảnh hưởng chất lượng export PNG từ Inkscape?",
            [
                "DPI / export area (drawing vs page vs selection).",
                "Antialiasing và filter region bị clip.",
                "Số lượng undo history trong file.",
                "Transform không applied làm blur khi rasterize.",
            ],
            (0, 1, 3),
        ),
        M(
            "Cách đúng để giữ nét sắc khi scale logo vector lên biển lớn?",
            [
                "Giữ vector, không rasterize sớm.",
                "Stroke dùng đơn vị thật (mm) và cân nhắc hairline vs bề dày vật lý.",
                "Scale bằng transform bitmap 72dpi.",
                "Kiểm tra stroke 'scale with object' khi nhân bản nhiều size.",
            ],
            (0, 1, 3),
        ),
        M(
            "Live Path Effects nào thường dùng cho mockup chữ/packaging và cần bake trước khi gửi xưởng ngoài?",
            [
                "Bend / Pattern along Path / Envelope Deformation / Perspective.",
                "Boolean Difference đã bake sẵn thì không còn LPE.",
                "Corns/Fillet Chamfer trên path gốc live.",
                "Gaussian blur filter (đây không phải LPE path, nhưng cũng không live ngoài Inkscape).",
            ],
            (0, 2),
        ),
        M(
            "Thao tác an toàn trước khi Save As Plain SVG cho web?",
            [
                "Bake LPE cần thiết, Object to Path nếu font không nhúng.",
                "Gỡ namespace thừa, kiểm tra ảnh embed/link.",
                "Giữ nguyên sodipodi:namedview để Chrome snap grid.",
                "Flatten filters nặng thành bitmap nếu browser không hỗ trợ.",
            ],
            (0, 1, 3),
        ),
        M(
            "Những lỗi màu thường gặp khi đưa file Inkscape sang in offset?",
            [
                "RGB/sRGB không khớp swatch Pantone.",
                "Gradient mesh bị flatten xấu.",
                "Spot color native đầy đủ như AI.",
                "Đen giàu (rich black) không kiểm soát được như prepress chuyên dụng.",
            ],
            (0, 1, 3),
        ),
        M(
            "Khi tách nền ảnh trong Inkscape, hướng tiếp cận nào hợp lý?",
            [
                "Trace bitmap nếu nền phẳng, logo rõ.",
                "Clip/mask vector nếu cần mép sắc.",
                "Gaussian blur 50px luôn tách nền tốt hơn clip.",
                "Ảnh phức tạp nên tách ở GIMP/Krita rồi đặt linked/embedded.",
            ],
            (0, 1, 3),
        ),
        M(
            "Text-on-path: phát biểu đúng?",
            [
                "Text vẫn live nếu chưa Object to Path; sửa path thì chữ chạy theo.",
                "Start offset và phía path (left/right) đổi vị trí chữ.",
                "Object to Path chữ trên path rồi vẫn đổi font được.",
                "Xuất sang AI/Corel có thể mất liên kết text-on-path.",
            ],
            (0, 1, 3),
        ),
        M(
            "Tối ưu số node trước khi cắt CNC?",
            [
                "Simplify có kiểm soát, giữ cusp.",
                "Tránh duplicate path chồng làm dao cắt 2 lần.",
                "Thêm node ngẫu nhiên để máy cắt chính xác hơn.",
                "Join node hở, đóng path cắt kín.",
            ],
            (0, 1, 3),
        ),
        M(
            "Document Properties quan trọng với file in ấn JustPlay?",
            [
                "Default units mm, page size đúng khổ.",
                "Background trong suốt vs trắng khi export PNG.",
                "Display unit chỉ ảnh hưởng UI, không đổi tọa độ file nếu viewBox sai.",
                "Scale 1 user unit = 1 px luôn đúng cho bản in 3 mét.",
            ],
            (0, 1, 2),
        ),
    ],
}

KDENLIVE = {
    "single": [
        S(
            "Proxy clip trong Kdenlive khác timeline preview resolution ở điểm nào?",
            [
                "Proxy là file mã hóa nhẹ song song từng clip (thường GOP intra), dùng khi edit; preview resolution chỉ scale playback timeline, không tạo file thay thế. Render cuối phải đảm bảo dùng bản full-res, không nhầm proxy.",
                "Preview resolution ghi đè file gốc trên đĩa.",
                "Proxy luôn được burn vào export H.264.",
                "Hai khái niệm là một trong bản 24.x.",
            ],
            0,
        ),
        S(
            "Affine, Transform, và Composite & Transform: chọn nào khi zoom keyframe + rotate trên clip có alpha?",
            [
                "Composite & Transform (hoặc Transform) xử lý position/scale/rotate/opacity trên compositor hiện đại; Affine cũ dễ sai origin và interpolat. Alpha cần composition mode đúng (Alpha in / Over).",
                "Affine luôn chất lượng cao hơn vì dùng GPU Lanczos.",
                "Transform không interpolate keyframe.",
                "Ba effect là alias, chỉ khác tên menu.",
            ],
            0,
        ),
        S(
            "Keyframe interpolation Linear vs Smooth vs Discrete khi làm zoom-punch?",
            [
                "Linear đều vận tốc; Smooth (Catmull-Rom/Bezier) dễ overshoot ở đầu/cuối; Discrete giữ giá trị đến keyframe sau (hold). Punch-in sắc nên Discrete hoặc Bezier chỉnh handle, tránh Smooth mặc định.",
                "Smooth không bao giờ overshoot.",
                "Discrete mới là easing cubic chuẩn.",
                "Interpolation chỉ áp dụng audio pan.",
            ],
            0,
        ),
        S(
            "Vectorscope và Waveform dùng để làm gì khi color grade trong Kdenlive?",
            [
                "Waveform xem luma/RGB legal range (crush/clip); Vectorscope xem hue/saturation, skin line. Grade theo scope chứ không chỉ mắt trên màn sRGB lệch.",
                "Vectorscope đo bitrate audio.",
                "Waveform chỉ hiện khi dùng proxy.",
                "Hai scope chỉ hoạt động trên render cuối.",
            ],
            0,
        ),
        S(
            "Mix clips (same track transition) khác transition 2 track cổ điển?",
            [
                "Mix trên cùng track (slip/overlap) gọn hơn cho cắt thoại; transition 2 track cần clip trên/dưới và composition. Mix vẫn là transition với duration, dễ vỡ nếu clip không đủ handle (media không còn đầu/đuôi).",
                "Mix không cần handle media.",
                "2-track transition không dùng được với audio.",
                "Mix tự động render lossless.",
            ],
            0,
        ),
        S(
            "Object Mask / rotoscope trong Kdenlive 24+ dựa trên gì, hạn chế chính?",
            [
                "Thường dựa model tách đối tượng (SAM-like) + mask keyframe; tóc/motion blur/occlusion làm mask nhảy. Phải refine, feather, và tracking lại từng shot, không tin một click.",
                "Mask luôn optical-flow hoàn hảo 100% frame.",
                "Chỉ chạy trên GPU NVIDIA, CPU không mask được.",
                "Object mask bake vào file gốc.",
            ],
            0,
        ),
        S(
            "Speech-to-text generate subtitles: nguồn lỗi điển hình?",
            [
                "Model Whisper (size/language), audio ồn, nhạc nền, nói chồng. Timeline subtitle là text clip — phải proofread; timecode lệch nếu speed-change/pitch trước khi transcribe.",
                "Kdenlive nhận 100% tiếng Việt không cần model.",
                "Subtitle luôn burn vào video khi tạo.",
                "Chỉ hoạt động với clip proxy.",
            ],
            0,
        ),
        S(
            "Text-based editing khác cắt trên timeline thông thường?",
            [
                "Cắt theo transcript: xóa câu là xóa đoạn media tương ứng. Lỗi nhận lời → cắt nhầm. Vẫn phải vào timeline chỉnh J-cut, B-roll, music.",
                "Text-based editing xuất SRT rồi xóa video gốc.",
                "Nó thay thế hoàn toàn keyframe effect.",
                "Chỉ dùng cho vertical 9:16.",
            ],
            0,
        ),
        S(
            "Color Correction vs Color Grading trong pipeline Kdenlive?",
            [
                "Correction đưa shot về cân bằng/exposure/white chuẩn; Grading tạo look (teal-orange, film). Làm grade trước khi shots match nhau sẽ loang màu khi cut.",
                "Hai thuật ngữ hoàn toàn trùng trong MLT.",
                "Grading phải luôn trước correction.",
                "Chỉ Lift/Gamma/Gain là correction, Curves là grade — đảo thứ tự không ảnh hưởng.",
            ],
            0,
        ),
        S(
            "Nested sequence / timeline lồng: lợi và hại?",
            [
                "Gói shot phức tạp thành clip con, tái sử dụng; hại là khó chỉnh effect bên trong, render preview nặng, audio bus dễ lệch. Nên nest khi shot 'xong', không nest quá sớm.",
                "Nest luôn làm render nhanh hơn vì cache 2 lần.",
                "Kdenlive cấm nest quá 1 cấp.",
                "Nest chuyển mọi clip sang proxy 240p.",
            ],
            0,
        ),
        S(
            "Picture-in-picture bằng Crop + Transform khác dùng Composite keyframes?",
            [
                "Crop cắt vùng nguồn trước khi scale, tránh scale nhiễu vùng thừa; Transform/Composite đặt vị trí lớp trên. PIP cần motion smooth và border/shadow tách lớp.",
                "Crop sau Transform luôn sắc hơn.",
                "PIP bắt buộc 2 project riêng.",
                "Alpha của crop luôn premultiplied sai, không dùng được.",
            ],
            0,
        ),
        S(
            "Glitch / Zoom transition bị 'nhảy' vì?",
            [
                "Thiếu handle (clip không overlap đủ), effect dùng resolution khác FPS, hoặc keyframe gắn clip-time vs composition-time. Cần overlap, match FPS project, và render test 1:1.",
                "Glitch bắt buộc GPU OpenGL 4.6.",
                "Chỉ xảy ra với proxy.",
                "Zoom transition không dùng keyframe.",
            ],
            0,
        ),
        S(
            "Video noise reduction trước hay sau scale/grade?",
            [
                "NR trên footage gốc (trước scale up) hiệu quả hơn; NR sau grade có thể ăn vào grain look. NR mạnh tạo soap-opera/mất detail tóc — phải soi 100%.",
                "NR luôn cuối pipeline trước H.264.",
                "NR chỉ chạy trên audio hiss.",
                "Temporal NR không cần motion estimation, nên để sau speed ramp.",
            ],
            0,
        ),
        S(
            "Convert ngang 16:9 sang dọc 9:16 đúng cách trong Kdenlive?",
            [
                "Đổi project/profile 1080x1920, dùng Transform/Crop keyframe (reframe) theo subject, không stretch. Background blur/PIP nếu cần giữ context.",
                "Stretch 16:9 cho kín khung là chuẩn TikTok.",
                "Chỉ cần xoay clip 90° metadata.",
                "Export letterbox rồi app mobile tự crop lossless.",
            ],
            0,
        ),
        S(
            "Keyframe interpolation trên effect 'Transform' khi làm teleport/cut-on-action?",
            [
                "Teleport cần Discrete/hold opacity hoặc hard cut; interpolate smooth giữa 2 vị trí sẽ 'trượt' nhân vật. Cut-on-action khớp motion vector hai phía cắt.",
                "Smooth interpolation làm teleport sắc hơn.",
                "Teleport bắt buộc Optical Flow retiming.",
                "Chỉ Mix clips mới teleport được.",
            ],
            0,
        ),
        S(
            "Render profile: khi nào chọn lossless/FFVhuff/DNxHR thay vì H.264 CRF?",
            [
                "Master/archival, roundtrip color, hoặc footage sẽ grade/re-export nhiều lần. H.264 CRF cho deliver web. Không master bằng H.264 thế hệ dài hạn nếu còn chỉnh.",
                "H.264 CRF 17 luôn lossless toán học.",
                "DNxHR không dùng được trên Windows.",
                "Lossless luôn file nhỏ hơn H.264 vì intra.",
            ],
            0,
        ),
        S(
            "Alpha operation Premultiply vs Straight khi overlay logo PNG?",
            [
                "PNG thường straight alpha; compositor MLT/FFmpeg lệch premultiply gây viền đen/sáng. Cần effect alpha correct, màu viền (unpremultiply) khớp background.",
                "PNG không có alpha, phải key green.",
                "Premultiply chỉ cho ProRes 4444.",
                "Kdenlive tự convert mọi PNG sang premultiplied sRGB tuyến tính.",
            ],
            0,
        ),
        S(
            "Timer countdown trong Kdenlive nên làm bằng?",
            [
                "Title clip / template animation hoặc counter effect với keyframe; burn-in khác file data. FPS project phải khớp để số không skip frame.",
                "Luôn dùng speech-to-text đếm ngược.",
                "Countdown chỉ render được 24fps.",
                "Phải xuất từng frame PNG rồi import image sequence mới đếm đúng.",
            ],
            0,
        ),
        S(
            "Vertical workspace layout chủ yếu giải quyết gì?",
            [
                "Monitor + timeline cho footage 9:16, tránh waste pixel preview. Không đổi pixel aspect của clip nguồn; vẫn phải reframe nếu nguồn 16:9.",
                "Tự crop mọi clip thành 9:16.",
                "Đổi color space thành Rec.2020.",
                "Bắt buộc cho speech-to-text.",
            ],
            0,
        ),
        S(
            "Remove object (inpainting/clone) trên video ổn định khi nào?",
            [
                "Nền tĩnh, camera locked, object không che overlap phức tạp. Camera move/parallax cần track + clean plate. Kdenlive không thay thế mocha/After Effects cho shot khó.",
                "Mọi handheld 4K đều inpaint hoàn hảo.",
                "Chỉ cần một frame clone cho cả shot 10s.",
                "Object mask + blur 200px luôn xóa người sạch.",
            ],
            0,
        ),
        S(
            "Subtitle animation 'smooth' bị stutter vì?",
            [
                "Title là resolution/refresh theo frame video; animation quá nhiều keyframe + preview low-res. Font hinting, motion blur giả. Render full quality để đánh giá.",
                "SRT không animate được nên phải luôn dùng ASS/Kdenlive title.",
                "Stutter chỉ do CPU, GPU không liên quan decode.",
                "Smooth interpolation subtitle bắt buộc 60fps project.",
            ],
            0,
        ),
        S(
            "Color management: rec.709 footage trên project mismatch?",
            [
                "Gán sai color space làm gamma shift (washed/too dark). Giữ timeline/rec.709 cho web; HDR/HLG cần pipeline riêng, không nhồi effect gamma lung tung.",
                "Kdenlive tự nhận mọi log profile camera.",
                "sRGB và Rec.709 gamma giống hệt, không bao giờ lệch.",
                "Proxy luôn convert sang ACES.",
            ],
            0,
        ),
    ],
    "multiple": [
        M(
            "Trước khi render giao khách, checklist nào bắt buộc?",
            [
                "Duyệt 1:1 các cut, audio peak, subtitle typo.",
                "Đảm bảo render dùng full-res không nhầm proxy.",
                "Xóa toàn bộ keyframe để file nhẹ.",
                "Match profile (resolution, FPS, color) với brief.",
            ],
            (0, 1, 3),
        ),
        M(
            "Khi nào nên dùng proxy?",
            [
                "H.265 4K GOP dài, máy decode yếu.",
                "Nhiều effect GPU/CPU trên timeline.",
                "Footage đã ProRes Proxy sẵn từ camera.",
                "Mọi file 720p H.264 8Mbps đều bắt buộc proxy.",
            ],
            (0, 1, 2),
        ),
        M(
            "Thành phần làm transition/glitch/zoom bị fail?",
            [
                "Không đủ handle media.",
                "FPS clip ≠ FPS project.",
                "Composition track bị disable.",
                "Tên clip có dấu tiếng Việt.",
            ],
            (0, 1, 2),
        ),
        M(
            "Color grade an toàn cho da người?",
            [
                "Theo skin line trên vectorscope, không đẩy sat quá.",
                "Match shot trước khi LUT look nặng.",
                "Tăng contrast bằng clip waveform hai đầu.",
                "Dùng cùng white balance logic giữa các camera.",
            ],
            (0, 1, 3),
        ),
        M(
            "Subtitle/speech-to-text: việc cần làm sau generate?",
            [
                "Proofread tiếng Việt, tên riêng, số liệu.",
                "Chỉnh in/out tránh cut chữ giữa tiếng.",
                "Xuất SRT backup.",
                "Tin 100% model large-v3 không cần đọc.",
            ],
            (0, 1, 2),
        ),
        M(
            "Cách reframe 16:9 → 9:16 đúng kỹ thuật?",
            [
                "Keyframe Transform theo subject.",
                "Giữ headroom/lead room.",
                "Stretch non-uniform cho kín khung.",
                "Blur nền / split screen nếu mất context.",
            ],
            (0, 1, 3),
        ),
        M(
            "Audio trong Kdenlive dễ sai ở đâu?",
            [
                "Peak clip > 0 dBFS khi normalize lung tung.",
                "Desync khi speed change không preserve pitch/timebase.",
                "Mix clip video không đụng audio handles.",
                "Export stereo thành mono do profile.",
            ],
            (0, 1, 3),
        ),
        M(
            "Effect nào liên quan matte/alpha?",
            [
                "Rotoscope / Object Mask.",
                "Alpha operations / composite modes.",
                "Hue shift trên fill.",
                "Crop tạo vùng trong suốt khi PIP.",
            ],
            (0, 1, 3),
        ),
        M(
            "Mastering deliverables JustPlay (web + nội bộ)?",
            [
                "H.264/H.265 + audio AAC theo spec kênh.",
                "Giữ project + backup media, không chỉ mp4 cuối.",
                "Xóa proxy ngay lập tức trước khi archive.",
                "Ghi phiên bản (date, editor) trong tên file.",
            ],
            (0, 1, 3),
        ),
        M(
            "Text glow / title: yếu tố ảnh hưởng render?",
            [
                "Filter region / quality preview vs full.",
                "Color space làm glow 'bẩn'.",
                "Font không nhúng khi mở máy khác.",
                "Glow luôn vector nên không bao giờ rasterize.",
            ],
            (0, 1, 2),
        ),
        M(
            "Nested timeline nên dùng khi?",
            [
                "Shot VFX đã chốt, tái sử dụng nhiều lần.",
                "Muốn giảm lộn xộn track.",
                "Audio master chưa mix xong nhưng nest video+audio chung một chiều.",
                "Cần chỉnh từng cut bên trong hàng ngày (nên chưa nest).",
            ],
            (0, 1),
        ),
        M(
            "Noise reduction: phát biểu đúng?",
            [
                "Temporal NR cần footage ổn định/ít motion.",
                "NR trước upscale.",
                "NR tối đa luôn tốt hơn cho YouTube.",
                "Soát 100% vùng tóc, text, grain.",
            ],
            (0, 1, 3),
        ),
        M(
            "Keyframe interpolation nên chọn Discrete khi?",
            [
                "Cắt đèn/teleport/hold pose.",
                "Giữ giá trị đến khung sau, không nội suy.",
                "Muốn bounce easing tự nhiên.",
                "Tránh overshoot của Smooth.",
            ],
            (0, 1, 3),
        ),
        M(
            "Lỗi thường gặp khi remove người/object?",
            [
                "Parallax nền, bóng, reflection.",
                "Mask nhảy ở motion blur.",
                "Clean plate thiếu.",
                "Proxy 360p vẫn xóa object 4K sạch pixel-perfect.",
            ],
            (0, 1, 2),
        ),
        M(
            "Project profile (resolution/FPS) sai sẽ kéo theo?",
            [
                "Retiming/stutter.",
                "Transition duration lệch.",
                "Audio sample rate luôn tự 96 kHz.",
                "Render crop/letterbox không mong muốn.",
            ],
            (0, 1, 3),
        ),
    ],
}

BLENDER = {
    "single": [
        S(
            "N-gon trên bề mặt cong sắp Subdivision Surface — rủi ro chính?",
            [
                "N-gon chia không đoán trước, tạo shading pinching/artifact khi subdivide. Mesh deform/animation nên tứ giác (quad) có flow; n-gon chỉ chấp nhận vùng phẳng khuất.",
                "N-gon luôn subdivide đẹp hơn quad.",
                "Cycles bỏ qua n-gon, chỉ EEVEE lỗi.",
                "N-gon bắt buộc cho Boolean chuẩn.",
            ],
            0,
        ),
        S(
            "Shade Smooth + Auto Smooth (angle) khác Weighted Normal modifier?",
            [
                "Auto Smooth tách split normals theo góc cạnh; Weighted Normal tái phân bổ vertex normal (thường sau bevel) để shading cứng/mềm có kiểm soát, không chỉ theo angle.",
                "Hai cái ghi cùng custom split normals, luôn trùng.",
                "Weighted Normal chỉ cho sculpt.",
                "Auto Smooth không ảnh hưởng export FBX.",
            ],
            0,
        ),
        S(
            "Modifier stack: Subdivision trước hay Boolean trước trên hard-surface?",
            [
                "Boolean trên mesh thấp (trước subsurf) dễ sạch hơn; subsurf trước boolean làm operand nặng, dễ vỡ. Bevel sau boolean cần topology hỗ trợ. Thứ tự stack là pipeline, không 'càng nhiều càng tốt'.",
                "Luôn Subdivision trước mọi modifier.",
                "Boolean sau Armature deform luôn an toàn.",
                "Thứ tự modifier không ảnh hưởng applied mesh.",
            ],
            0,
        ),
        S(
            "Cycles so với EEVEE về caustics và light linking (bản mới)?",
            [
                "Cycles path-trace caustics/GI chính xác hơn; EEVEE rasterize, screen-space, hạn chế caustics. Light linking/receiver tùy phiên bản — không giả định EEVEE = Cycles preview pixel.",
                "EEVEE tính caustics unbiased như Cycles.",
                "Light linking chỉ có trên Workbench.",
                "Hai engine dùng cùng sampling seed nên noise giống nhau.",
            ],
            0,
        ),
        S(
            "Geometry Nodes: Field khác Anonymous Attribute?",
            [
                "Field là function trên domain (vertex/face) evaluate theo context; anonymous attribute lưu data không tên, truyền trong node tree. Nhầm field với constant làm instancing/scale sai.",
                "Field chỉ là tên khác của vertex group.",
                "Anonymous attribute xuất FBX thành UV2.",
                "Hai khái niệm chỉ có trong Shader Nodes.",
            ],
            0,
        ),
        S(
            "IK pole target dùng để làm gì, khi rig chân bị xoắn?",
            [
                "Pole target khóa hướng khớp gối/khuỷu trong IK. Xoắn thường do pole lệch, roll xương, hoặc IK không giữ chain length. Phải chỉnh bone roll + pole angle, không xoay mesh bù.",
                "Pole target chỉ ẩn controller, không đổi IK.",
                "Xoắn IK sửa bằng Shade Smooth.",
                "Pole bắt buộc trùng origin world.",
            ],
            0,
        ),
        S(
            "Alembic vs USD khi gửi shot animation ra ngoài?",
            [
                "Alembic mạnh cache mesh/deform theo frame, ít shader/rig; USD giữ hierarchy, variant, material binding (tùy exporter). Chọn theo pipeline đối tác, không export 'cái nào cũng được'.",
                "USD không cache mesh deform.",
                "Alembic giữ armature IK live.",
                "Hai format luôn nhúng Cycles shader graph.",
            ],
            0,
        ),
        S(
            "Color management: Filmic/AgX vs Standard sRGB khi lookdev?",
            [
                "Filmic/AgX map HDR view, highlight roll-off; Standard clip highlight. Texture albedo sRGB vs Non-Color (roughness/normal) gán sai làm PBR chết. Render display ≠ lưu linear EXR.",
                "Standard luôn physically correct hơn AgX.",
                "Normal map phải sRGB mới đúng tangent.",
                "EXR multilayer đã tone-map AgX sẵn.",
            ],
            0,
        ),
        S(
            "Multires so với Subdivision Surface khi sculpt nhân vật?",
            [
                "Multires lưu displace/sculpt levels trên mesh, bake normal/displacement; Subsurf modifier procedural, không giữ sculpt layer như Multires. Apply nhầm level làm mất detail hoặc file phình.",
                "Subsurf lưu sculpt layers tốt hơn Multires.",
                "Hai modifier không thể cùng stack.",
                "Multires chỉ EEVEE.",
            ],
            0,
        ),
        S(
            "Non-manifold mesh làm Boolean/3D print thất bại vì?",
            [
                "Lỗ, normals lật, cạnh T-junction, interior face — volume không kín. Boolean Manifold/Exact cần mesh hợp lệ; 3D print cần solid. Mesh Analysis / Select Non Manifold trước khi cắt.",
                "Non-manifold chỉ ảnh hưởng UV unwrap.",
                "Cycles không render non-manifold.",
                "Recalculate normals luôn đủ, không cần xóa interior face.",
            ],
            0,
        ),
        S(
            "GPU OptiX vs CUDA vs CPU trong Cycles?",
            [
                "OptiX (NVIDIA RTX) nhanh nhờ RT core, đôi khi khác noise/feature (denoise); CUDA tương thích rộng hơn; CPU chậm nhưng ổn định RAM lớn. Driver/feature (light tree, OIDN) có thể lệch kết quả nhẹ.",
                "Ba backend luôn bit-exact cùng seed.",
                "OptiX không chạy denoise.",
                "CPU Cycles không hỗ trợ shader Principled.",
            ],
            0,
        ),
        S(
            "Apply Scale trước animation/parenting vì sao bắt buộc?",
            [
                "Scale ≠ 1 làm modifier (bevel, solidify), physics, IK, normals, instance lệch. Ctrl+A Apply Scale khi modeling xong, trước rig. Keyframe scale object khác deform bone.",
                "Apply Scale xóa animation location.",
                "Blender tự apply scale khi render.",
                "Chỉ camera cần apply scale.",
            ],
            0,
        ),
        S(
            "Follow Path: evaluation time vs constraint offset, offset object?",
            [
                "Curve path animation dùng Follow Path constraint hoặc parent Follow Path; scale curve, radius, và animate mapping. Offset frame lệch FPS. Apply curve scale; animate offset không animate object location tay song song.",
                "Follow Path luôn dùng physics rigid body.",
                "Evaluation time chỉ cho Geometry Nodes.",
                "Path constraint bỏ qua curve tilt.",
            ],
            0,
        ),
        S(
            "Skin modifier rig (create armature) hạn chế?",
            [
                "Skin tạo mesh + xương theo connectivity, topology xấu → weight xấu. Chỉ blockout/organic thô; production character cần retopo + bind có kiểm soát.",
                "Skin modifier = production rig chuẩn AAA.",
                "Create Armature từ Skin giữ shapekey facial.",
                "Skin không tạo vertex group.",
            ],
            0,
        ),
        S(
            "Compositing 3D vào ảnh (virtual staging): camera matching then chốt?",
            [
                "Khớp focal length, sensor, distortion, horizon, light HDRI/shadow catcher, color space ảnh nền. Sai focal làm parallax vỡ khi camera move. Shadow catcher + film transparent.",
                "Chỉ cần import ảnh làm plane, không cần camera match.",
                "EEVEE SSR thay thế HDRI lighting.",
                "Focal length không ảnh hưởng perspective match.",
            ],
            0,
        ),
        S(
            "Merge (M) vs Connect (J) vs Fill (F) trong Edit Mode?",
            [
                "Merge gộp vertex (collapse/center); J cắt/nối cạnh giữa vertex; F tạo face/edge. Nhầm Merge thành Fill làm mất topology. Bridge Edge Loops cho hai loop.",
                "J và F luôn trùng trên 2 vertex.",
                "Merge không ảnh hưởng UV.",
                "Fill luôn tạo n-gon đẹp cho subsurf.",
            ],
            0,
        ),
        S(
            "Increase mesh density: Subdivide / Loop Cut / Sculpt Dyntopo / Voxel remesh — chọn khi nào?",
            [
                "Loop cut giữ quad flow; Subdivide đều mặt; Dyntopo thêm tam giác theo stroke (phá quads); Voxel remesh topology mới, mất UVs/sharp. Production: retopo sau sculpt dense.",
                "Voxel remesh luôn giữ UV.",
                "Dyntopo giữ quad loop hoàn hảo.",
                "Loop cut và dyntopo là một thuật toán.",
            ],
            0,
        ),
        S(
            "Lock objects (selection/visibility/render) khác hide?",
            [
                "Hide (H) ẩn viewport; disable render trong outliner (camera icon) mới khỏi render; lock select tránh chọn nhầm. Nhầm hide với disable render làm object biến khi F12.",
                "H luôn ẩn cả render.",
                "Lock location khóa render visibility.",
                "Collection hide viewport = hide render mặc định luôn.",
            ],
            0,
        ),
        S(
            "Render animation vs still: output then chốt để không mất khung?",
            [
                "Animation xuất image sequence (EXR/PNG) rồi encode; tránh FFmpeg thẳng dài giờ (crash mất hết). Still: samples, denoise, color depth. Frame range, overwrite, placeholder.",
                "FFmpeg H.264 luôn an toàn hơn PNG sequence.",
                "EEVEE animation không cần consistent sampling.",
                "Motion blur still và animation cùng một shutter không cần scene FPS.",
            ],
            0,
        ),
        S(
            "Cap holes / fill hole trên mesh hở trước Boolean?",
            [
                "Lỗ làm Boolean/volume sai. Grid Fill, F, Bridge, hoặc extrude/scale 0. Kiểm tra normals. Không che lỗ bằng Solidify nếu topology không kín.",
                "Boolean Exact bỏ qua lỗ.",
                "Shade Flat tự cap holes.",
                "Chỉ 3D print mới cần kín, Boolean thì không.",
            ],
            0,
        ),
        S(
            "Instancing (collection instance / GN instance) vs Duplicate?",
            [
                "Instance chia mesh data, nhẹ RAM/viewport; Duplicate độc lập. Apply/export có thể realize instances. Sửa mesh gốc ăn theo instance — đúng khi modular, nguy hiểm khi quên.",
                "Instance luôn xuất FBX thành một mesh gộp không tùy chọn.",
                "Duplicate nhẹ RAM hơn instance.",
                "GN instance không render trong Cycles.",
            ],
            0,
        ),
        S(
            "Principled BSDF: Metallic 0.5 trên nhựa JustPlay — sai vì?",
            [
                "Metallic là 0 hoặc 1 với PBR dielectric/metal; 0.5 tạo vật liệu không tồn tại, look 'dirty metal'. Nhựa: metallic 0, roughness/specular/coat. Texture metallic phải Non-Color.",
                "Metallic 0.5 là chuẩn nhựa ABS.",
                "EEVEE bỏ qua metallic.",
                "Specular và metallic cộng tuyến tính nên 0.5 luôn đúng.",
            ],
            0,
        ),
    ],
    "multiple": [
        M(
            "Trước khi rig character, mesh cần?",
            [
                "Apply Rotation/Scale.",
                "Topology quad flow khớp biến dạng (khớp gối/khuỷu).",
                "Xóa vertex group/armature cũ xung đột.",
                "Giữ 20 shapekey từ boolean chưa apply.",
            ],
            (0, 1, 2),
        ),
        M(
            "Export sang DCC/engine: kiểm tra?",
            [
                "Forward/up axis, unit scale (m).",
                "Apply modifiers hay giữ stack (tùy pipeline).",
                "UV, normal, material assignment.",
                "Mọi node Geometry luôn bake tự động không cần realize.",
            ],
            (0, 1, 2),
        ),
        M(
            "Cycles sampling thực tế?",
            [
                "Noise threshold / max samples.",
                "Denoise (OIDN/OptiX) có thể nát texture nhỏ — soi 100%.",
                "Clamp indirect giảm firefly, có thể làm tối GI.",
                "Samples 1 luôn đủ với AgX.",
            ],
            (0, 1, 2),
        ),
        M(
            "Sculpt production path đúng?",
            [
                "Sculpt dense → retopo → UV → bake maps.",
                "Multires/displacement nếu cần detail.",
                "Voxel remesh giữa chừng sẽ mất UV nếu đã unwrap.",
                "Dyntopo cuối cùng rồi UV ngay không retopo.",
            ],
            (0, 1, 2),
        ),
        M(
            "Animation render an toàn?",
            [
                "Xuất EXR/PNG sequence.",
                "Overwrite/placeholder, disk đủ chỗ.",
                "Motion blur + consistent FPS.",
                "Chỉ encode H.264 một lần duy nhất, xóa file .blend.",
            ],
            (0, 1, 2),
        ),
        M(
            "Boolean hard-surface sạch hơn khi?",
            [
                "Mesh manifold, normals đúng.",
                "Operand đơn giản, cắt không vuốt n-gon vùng cong.",
                "Solver Exact/Manifold phù hợp phiên bản.",
                "Bevel modifier trước boolean luôn đẹp hơn sau.",
            ],
            (0, 1, 2),
        ),
        M(
            "UV unwrap lỗi điển hình?",
            [
                "Seam đặt sai, stretch (checker).",
                "Scale không apply trước unwrap.",
                "Overlap island khi texture unique.",
                "UDIM tự sửa mọi overlap.",
            ],
            (0, 1, 2),
        ),
        M(
            "Lighting lookdev?",
            [
                "HDRI + 3-point có kiểm soát.",
                "Khớp color management view transform.",
                "Shadow catcher khi ghép ảnh.",
                "Strength HDRI 1000 luôn cinematic.",
            ],
            (0, 1, 2),
        ),
        M(
            "Geometry Nodes instances?",
            [
                "Realize Instances khi cần unique mesh/UV/export.",
                "Field vs constant quyết định scale từng điểm.",
                "Named attribute giao tiếp shader/GN.",
                "Instance luôn tách material per-face tự động.",
            ],
            (0, 1, 2),
        ),
        M(
            "Armature deform lỗi weight?",
            [
                "Normalize weights, xóa group thừa.",
                "Bone heat bind thất bại vùng khớp — phải weight paint.",
                "Scale chưa apply làm envelope sai.",
                "Shade Smooth sửa weight.",
            ],
            (0, 1, 2),
        ),
        M(
            "EEVEE hạn chế so với Cycles (phải biết để không hứa khách)?",
            [
                "Screen-space reflection/refraction, probe, shadow map.",
                "Caustics/GI không đầy đủ như path trace.",
                "Volume/hair có khác biệt chất lượng.",
                "EEVEE luôn khớp pixel Cycles nếu cùng samples.",
            ],
            (0, 1, 2),
        ),
        M(
            "File .blend nặng/chậm viewport vì?",
            [
                "Modifier nặng (subsurf 4, GN).",
                "Undos, packed textures 8k không cần.",
                "Overlays + auto smooth trên mesh dense.",
                "Tên object tiếng Việt.",
            ],
            (0, 1, 2),
        ),
        M(
            "Path animation / rolling ball type shot?",
            [
                "Follow Path + curve tilt/radius.",
                "Animate along path, không keyframe location xung đột.",
                "Rigid body có thể thay constraint nếu cần va chạm.",
                "Shade Smooth làm bóng lăn đúng vật lý.",
            ],
            (0, 1, 2),
        ),
        M(
            "Khi tách/cắt mesh (separate, bisect, knife)?",
            [
                "Separate by loose/selection tạo object mới.",
                "Normals/UVs có thể cần chỉnh lại.",
                "Bisect fill tạo mặt, có thể n-gon.",
                "Knife luôn manifold và giữ shapekey.",
            ],
            (0, 1, 2),
        ),
        M(
            "PBR texture setup đúng?",
            [
                "Albedo sRGB; roughness/metallic/normal Non-Color.",
                "Normal map OpenGL vs DirectX (Y flip).",
                "Displacement cần đủ subdivision / adaptive.",
                "Mọi map JPEG 4:2:0 đều lossless cho normal.",
            ],
            (0, 1, 2),
        ),
    ],
}

WRITER = {
    "single": [
        S(
            "Trong LibreOffice Writer, khác biệt then chốt giữa Paragraph Style, Character Style và Direct Formatting?",
            [
                "Style là định dạng có tên, tái dùng, sửa 1 chỗ ăn cả tài liệu; Direct Formatting (Ctrl+B tay) đè lên style, làm hỏng tut đồng bộ. Character Style áp trên đoạn con; Paragraph Style cho cả đoạn, gồm indents/spacing.",
                "Direct Formatting luôn thắng khi xuất PDF/A nên nên dùng hết.",
                "Character Style đổi page size.",
                "Paragraph Style không chứa font, chỉ alignment.",
            ],
            0,
        ),
        S(
            "Mục lục (ToC) không cập nhật heading mới — nguyên nhân đúng?",
            [
                "ToC lấy từ outline level của paragraph style (Heading 1..), không phải chữ to in đậm tay. Direct formatting không vào ToC. Phải dùng style đúng, rồi Update index.",
                "ToC chỉ đọc comment.",
                "Phải xuất DOC rồi mở lại mới sinh ToC.",
                "ToC cấm tiếng Việt.",
            ],
            0,
        ),
        S(
            "Master Document (.odm) so với Section trong một file .odt?",
            [
                "Master ghép nhiều file con, phù hợp sách/tài liệu lớn nhiều tác giả; Section chia vùng trong 1 file (cột, link, protect). Master dễ vỡ liên kết path; Section dễ hơn với tài liệu vừa.",
                "Section thay thế master hoàn toàn, ODM đã bỏ.",
                "Master không hỗ trợ ToC chung.",
                "File con của master phải là DOCX.",
            ],
            0,
        ),
        S(
            "Cross-reference bị 'Error' sau khi xóa heading?",
            [
                "Tham chiếu trỏ bookmark/heading đã mất. Phải xóa/reinsert field, không gõ số chương tay. Nên cross-ref theo numbered heading, update fields khi mở file.",
                "Error chỉ do font Times.",
                "PDF export xóa mọi cross-ref hợp lệ.",
                "Cross-ref không dùng được với outline numbering.",
            ],
            0,
        ),
        S(
            "Mail Merge: nguồn dữ liệu và field?",
            [
                "Kết nối spreadsheet/CSV/DB, chèn merge fields, preview rồi output thư/nhãn. Locale CSV (dấu phẩy/chấm phẩy) lệch làm sai cột. Phải khớp tên field, không copy giá trị tĩnh.",
                "Mail merge chỉ gõ tay từng tên trong bảng.",
                "ODT không merge được, phải DOC.",
                "Merge fields tự tạo database JustPlay.",
            ],
            0,
        ),
        S(
            "Track Changes vs Comment khi rà soát SOP nội bộ?",
            [
                "Track Changes ghi sửa trên text (accept/reject); Comment thảo luận không đổi nội dung. In/PDF có thể ẩn markup — phải chọn hiện revision. Không vừa track vừa gõ đè không record.",
                "Comment tự accept thành text.",
                "Track Changes mất khi lưu ODT.",
                "Hai tính năng trùng nhau trên Writer 24.",
            ],
            0,
        ),
        S(
            "Page Style (First Page, Left/Right) khác Insert Manual Break?",
            [
                "Page Style mô tả lề/header/footer/page number theo kiểu trang; Manual break (với style) chuyển sang kiểu khác (trang bìa → nội dung). Chỉ tăng font heading không đổi page style.",
                "Page Style chỉ đổi màu nền, không header.",
                "Manual break xóa ToC.",
                "First Page style tự áp mọi trang chẵn.",
            ],
            0,
        ),
        S(
            "List Style tách khỏi Paragraph Style — tại sao SOP hay loạn số?",
            [
                "Writer gắn numbering qua list style; copy đoạn từ Word mang direct numbering. Restart numbering, levels lệch. Nên một list style chuẩn, gắn vào Heading/Body, không bấm toolbar numbering lung tung.",
                "List style không liên quan outline.",
                "Numbering Word luôn convert 1-1 sang Writer.",
                "Restart numbering xóa list style toàn tài liệu.",
            ],
            0,
        ),
        S(
            "Fields (date, filename, conditional text) khi xuất PDF?",
            [
                "Field được evaluate lúc update/export; conditional hidden text có thể vẫn 'có' trong file nguồn. PDF thường flatten giá trị hiện thời, không còn field động. Phải Update Fields trước khi xuất bản.",
                "PDF giữ mọi field Writer live.",
                "Date field luôn khóa ngày tạo file, không update.",
                "Conditional text bị cấm trong ODT.",
            ],
            0,
        ),
        S(
            "Round-trip ODT ↔ DOCX: mất mát điển hình?",
            [
                "Page style, fields, master doc, smart drawing, macros, tinh chỉnh ToC/index. Định dạng 'gần đúng' ≠ giống. Tài liệu gốc pháp lý/SOP nên giữ ODT master, DOCX chỉ khi bắt buộc.",
                "DOCX round-trip lossless với mọi page style.",
                "Chỉ mất ảnh, không mất style.",
                "Writer 24 embed Word engine nên không lệch.",
            ],
            0,
        ),
    ],
    "multiple": [
        M(
            "Thao tác nào thuộc quy trình Writer 'sạch style'?",
            [
                "Dùng Heading 1–n cho cấu trúc.",
                "Clear Direct Formatting khi dán từ web/Word.",
                "Gõ số chương bằng tay cho chắc.",
                "Cập nhật ToC/Index trước khi PDF.",
            ],
            (0, 1, 3),
        ),
        M(
            "Header/Footer đúng kỹ thuật?",
            [
                "Gắn với Page Style, có thể khác nhau first/left/right.",
                "Field page number, document title.",
                "Vẽ text box tay trên mỗi trang cho số trang.",
                "Same content on first page thường tắt cho bìa.",
            ],
            (0, 1, 3),
        ),
        M(
            "Khi làm biểu mẫu SOP JustPlay trên Writer?",
            [
                "Content controls/fields, protected sections nếu cần.",
                "Table với style, không merge lung tung phá accessibility.",
                "Ảnh logo embed hoặc link có quy ước thư mục.",
                "Track Changes để trống, mọi người sửa direct.",
            ],
            (0, 1, 2),
        ),
        M(
            "Nguyên nhân file Writer chậm/nặng?",
            [
                "Ảnh embed độ phân giải máy ảnh gốc.",
                "Undo/history + rất nhiều OLE.",
                "Hàng nghìn direct formatting.",
                "Tên file tiếng Việt.",
            ],
            (0, 1, 2),
        ),
        M(
            "Numbered headings + ToC?",
            [
                "Outline numbering gắn paragraph style.",
                "ToC include outline levels phù hợp.",
                "Cập nhật sau khi thêm chương.",
                "In đậm 18pt thay Heading 1 vẫn vào ToC.",
            ],
            (0, 1, 2),
        ),
        M(
            "Mail merge dễ vỡ khi?",
            [
                "CSV delimiter/locale sai.",
                "Tên cột ≠ field.",
                "Nguồn file bị lock Excel.",
                "Preview một record là đủ, không cần test record cuối.",
            ],
            (0, 1, 2),
        ),
        M(
            "Bảo mật/rà soát tài liệu?",
            [
                "Track changes + comments có quy trình accept.",
                "Redact thông tin nhạy cảm trước PDF công khai.",
                "Properties/metadata còn tên tác giả.",
                "PDF luôn xóa metadata Writer.",
            ],
            (0, 1, 2),
        ),
        M(
            "Hình ảnh/khung (frame) trong Writer?",
            [
                "Anchor (to paragraph/page/character) quyết định nhảy trang.",
                "Wrap mode ảnh hưởng text flow.",
                "Frame style tái sử dụng.",
                "Anchor to page luôn tốt cho sách dài.",
            ],
            (0, 1, 2),
        ),
        M(
            "Xuất PDF từ Writer cho in/lưu trữ?",
            [
                "PDF/A khi cần lưu trữ dài hạn.",
                "Embed fonts, kiểm tra tiếng Việt.",
                "Xem trước markup ẩn.",
                "Hybrid PDF luôn chỉnh sửa lossless như ODT.",
            ],
            (0, 1, 2),
        ),
    ],
}

CALC = {
    "single": [
        S(
            "INDEX/MATCH khác VLOOKUP ở điểm then chốt trên bảng nhân sự/kho?",
            [
                "INDEX/MATCH không đòi cột khóa nằm trái, bền khi chèn cột; VLOOKUP theo vị trí cột số, dễ vỡ. MATCH type (0 exact vs approximate) sai làm lấy nhầm. Nên khóa bảng (absolute) và exact match.",
                "VLOOKUP luôn nhanh và an toàn hơn INDEX/MATCH.",
                "MATCH type 1 (approximate) luôn đúng với mã SKU không sắp xếp.",
                "INDEX không trả về ô, chỉ số thứ tự in ra text.",
            ],
            0,
        ),
        S(
            "Array formula (CSE / native dynamic) vs SUMPRODUCT trong Calc?",
            [
                "Array xử lý dải nhiều ô một công thức; SUMPRODUCT nhân-cộng có điều kiện không luôn cần CSE. Nhầm range lệch kích thước #VALUE!. Calc vs Excel khác nhau ở dynamic arrays — không copy nguyên workbook giả định Excel 365.",
                "SUMPRODUCT không bao giờ là array.",
                "Mọi công thức Calc đều dynamic spill như Excel 365.",
                "CSE chỉ dùng cho DATE().",
            ],
            0,
        ),
        S(
            "Data Validity (danh sách) khác AutoFilter?",
            [
                "Validity chặn/khuyến nghị giá trị nhập (list, range, custom formula); Filter chỉ ẩn hàng lúc xem. Validity không thay thế ràng buộc DB. List nguồn nên named range, không hardcode 3 ô.",
                "AutoFilter ngăn nhập sai.",
                "Validity tự tạo pivot.",
                "List validity xuất CSV thành constraint SQL.",
            ],
            0,
        ),
        S(
            "Goal Seek vs Solver?",
            [
                "Goal Seek một biến, một mục tiêu; Solver nhiều biến, ràng buộc, hàm mục tiêu (tuyến/phi tuyến). Solver cần model đúng (không circular lung tung). Kết quả local optimum, phải hiểu giả định.",
                "Hai công cụ trùng thuật toán Simplex luôn.",
                "Goal Seek giải được mọi ràng buộc tuyến tính.",
                "Solver cấm ô chứa công thức.",
            ],
            0,
        ),
        S(
            "ROUND, ROUNDDOWN, và làm tròn ngân hàng — bẫy tiền tệ?",
            [
                "ROUND half-away/half-even tùy cấu hình/locale; cộng nhiều dòng đã ROUND khác ROUND tổng. Tiền tệ nên làm tròn theo quy tắc kế toán, giữ raw precision, ROUND ở bước trình bày/hạch toán.",
                "ROUNDDOWN và ROUND giống nhau với số dương.",
                "Calc luôn banker's rounding như IEEE mọi hàm.",
                "Làm tròn 2 chữ số trước khi cộng VAT không bao giờ lệch.",
            ],
            0,
        ),
        S(
            "DATEVALUE / ngày tháng lệch vì locale?",
            [
                "Chuỗi '19/09/2026' phụ thuộc locale DMY vs MDY; import CSV US làm đảo tháng. Nên nhập DATE(y,m,d) hoặc serial, không concatenate text ngày. Filter/pivot theo text ngày là sai.",
                "Calc luôn ISO-8601 bất chấp locale.",
                "DATEVALUE bỏ qua timezone nên luôn đúng.",
                "Định dạng hiển thị ô đổi giá trị serial.",
            ],
            0,
        ),
        S(
            "Named range vs Database range (Data → Define Range)?",
            [
                "Named range tham chiếu công thức; Database range phục vụ sort/filter/subtotal/form, có header. Pivot/DataPilot thường lấy bảng có header sạch, không merged cells.",
                "Hai khái niệm trùng trong Calc 24.",
                "Named range không dùng trong công thức được.",
                "Database range bắt buộc SQL.",
            ],
            0,
        ),
        S(
            "Pivot (DataPilot) không cập nhật nguồn mới?",
            [
                "Cache/nguồn cố định range cũ; hàng mới ngoài range. Cần nguồn named range linh hoạt hoặc định nghĩa lại, rồi Refresh. Merged header phá pivot. Không copy giá trị pivot như nguồn sự thật nếu nguồn đổi.",
                "Pivot luôn live binding mọi hàng sheet.",
                "Chèn cột giữa nguồn không bao giờ vỡ field.",
                "DataPilot cấm tiếng Việt ở header.",
            ],
            0,
        ),
        S(
            "Conditional formatting công thức: tham chiếu tương đối?",
            [
                "Công thức viết như cho ô góc trên-trái của dải; $ khóa cột/hàng. Sai relative làm highlight lệch cả bảng. Phải test vài ô, không chỉ ô đầu.",
                "CF công thức luôn tuyệt đối theo named range, không relative.",
                "CF không chấp nhận công thức, chỉ giá trị.",
                "Apply to dải không ảnh hưởng evaluation.",
            ],
            0,
        ),
        S(
            "Circular reference và iterative calculation?",
            [
                "Circular vô tình (ô tự trỏ) cho 0/lỗi; iterative chủ đích (mô hình) phải bật Iterations, giới hạn bước. Không bật iterative toàn workbook để 'chéo' lỗi thiết kế.",
                "Calc tự giải mọi circular như hệ tuyến tính.",
                "Circular không ảnh hưởng Solver.",
                "Iteration mặc định bật 1000 bước.",
            ],
            0,
        ),
    ],
    "multiple": [
        M(
            "Bảng Calc 'sạch dữ liệu' trước pivot?",
            [
                "Một hàng header, không merge.",
                "Một kiểu dữ liệu mỗi cột (số không lẫn text '1 000').",
                "Không tổng cộng xen giữa nguồn.",
                "Trang trí màu thay cho giá trị trạng thái là đủ.",
            ],
            (0, 1, 2),
        ),
        M(
            "LOOKUP an toàn?",
            [
                "Exact match cho mã.",
                "INDEX/MATCH hoặc XLOOKUP (nếu có) bền chèn cột.",
                "Khóa $ range.",
                "Approximate VLOOKUP trên SKU không sort.",
            ],
            (0, 1, 2),
        ),
        M(
            "CSV import vừa phải?",
            [
                "Chọn delimiter, charset (UTF-8), decimal locale.",
                "Cột mã không mất số 0 đầu (text).",
                "Ngày parse đúng DMY.",
                "Double-click CSV luôn đúng với file kế toán US.",
            ],
            (0, 1, 2),
        ),
        M(
            "Bảo vệ sheet/công thức?",
            [
                "Protect sheet, unlock ô nhập.",
                "Ẩn công thức nếu cần.",
                "Validity trên ô nhập.",
                "Protect thay thế backup versioning.",
            ],
            (0, 1, 2),
        ),
        M(
            "Hàm điều kiện (SUMIF, COUNTIFS, AVERAGEIF)?",
            [
                "Range cùng kích thước.",
                "Tiêu chí text/số/wildcard hiểu đúng.",
                "Không lẫn khoảng trống và 0.",
                "SUMIF tự bỏ qua hàng ẩn filter giống SUBTOTAL.",
            ],
            (0, 1, 2),
        ),
        M(
            "In ấn/PDF từ Calc?",
            [
                "Print ranges, page break preview.",
                "Repeat header rows.",
                "Scale to page vs cắt cột.",
                "Page style không liên quan header.",
            ],
            (0, 1, 2),
        ),
        M(
            "Lỗi tiền tệ/số?",
            [
                "Text số do dấu phân cách nghìn.",
                "Làm tròn từng dòng vs tổng.",
                "VAT/thuế ROUND theo quy tắc.",
                "Định dạng hiển thị 2 chữ số đổi serial gốc.",
            ],
            (0, 1, 2),
        ),
        M(
            "Đặt tên (Define Name) tốt?",
            [
                "Tên không khoảng trắng, phạm vi sheet vs document.",
                "Dùng trong validity/công thức dễ đọc.",
                "Tránh tên trùng hàm (DATE, INDIRECT).",
                "Tên luôn nhanh hơn ô A1 không điều kiện.",
            ],
            (0, 1, 2),
        ),
        M(
            "Khi nào nên tách sheet 'raw / calc / output'?",
            [
                "Raw không công thức tay phá nguồn.",
                "Calc chứa model.",
                "Output in/PDF khóa format.",
                "Gộp tất cả vào 1 sheet để VLOOKUP nhanh hơn luôn.",
            ],
            (0, 1, 2),
        ),
    ],
}


def bank_for_lesson(course_id: int, lesson: Lesson) -> dict:
    if course_id == 4:
        return INKSCAPE
    if course_id == 5:
        return KDENLIVE
    if course_id == 7:
        return BLENDER
    title = (lesson.title or "").lower()
    chapter = (lesson.chapter.title or "").lower()
    blob = f"{title} {chapter}"
    if "calc" in blob:
        return CALC
    return WRITER


def create_mc_questions(comp, specs):
    questions = []
    for spec in specs:
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
        questions.append(q)
    return questions


def exam_title(course, lesson) -> str:
    short = SHORT.get(course.id, "KH")
    ch_order = lesson.chapter.order
    raw = f"KT · {short} · C{ch_order}-B{lesson.order}: {lesson.title}"
    return raw[:255]


def exam_description(course, lesson) -> str:
    return (
        f"{MARKER}:c{course.id}:l{lesson.id}\n"
        f"Bài kiểm tra sau bài học: {lesson.title}\n"
        f"Khóa: {course.title}\n"
        "Đối tượng: nhân viên đã được gán vào khóa (đối tượng đã học).\n"
        "10 câu TN một đáp án (0.4) + 9 câu TN nhiều đáp án (0.5) + 1 câu tự luận (1.5)."
    )


def pick_questions(rng, singles, multiples):
    s = rng.sample(singles, 10)
    m = rng.sample(multiples, 9)
    return s + m


def make_essay(comp, course, lesson, rng) -> Question:
    tmpl = rng.choice(ESSAY_TEMPLATES)
    content = tmpl.format(title=lesson.title, course=course.title)
    return Question.objects.create(
        competency=comp,
        content=content,
        q_type="essay",
        points=1.5,
    )


def cleanup_course(course):
    old_exams = Exam.objects.filter(description__contains=f"{MARKER}:c{course.id}:")
    n_old = old_exams.count()
    old_exams.delete()
    comp = Competency.objects.filter(name=f"[KH{course.id}] {SHORT.get(course.id, course.title)[:80]}").first()
    if comp:
        Question.objects.filter(competency=comp).delete()
    return n_old


def seed_course(course):
    deleted = cleanup_course(course)
    short = SHORT.get(course.id, course.title[:40])
    comp, _ = Competency.objects.get_or_create(
        name=f"[KH{course.id}] {short}",
        defaults={"description": f"Ngân hàng câu hỏi khóa {course.title}"},
    )
    lessons = list(
        Lesson.objects.filter(chapter__course=course)
        .select_related("chapter")
        .order_by("chapter__order", "order", "id")
    )
    users = list(course.assigned_users.all())
    created_exams = []
    banks_cache = {}
    last_exam = None

    for lesson in lessons:
        bank = bank_for_lesson(course.id, lesson)
        key = id(bank)
        if key not in banks_cache:
            banks_cache[key] = {
                "single": create_mc_questions(comp, bank["single"]),
                "multiple": create_mc_questions(comp, bank["multiple"]),
            }
        pool = banks_cache[key]
        rng = random.Random(lesson.id * 10007 + course.id)
        picked = pick_questions(rng, pool["single"], pool["multiple"])
        essay = make_essay(comp, course, lesson, rng)
        exam = Exam.objects.create(
            title=exam_title(course, lesson),
            description=exam_description(course, lesson),
            start_time=START,
            end_time=END,
            duration_minutes=DURATION,
            is_active=True,
        )
        exam.replace_questions(picked + [essay])
        if users:
            exam.assigned_users.set(users)
        created_exams.append(exam)
        last_exam = exam

    if last_exam:
        course.final_exam = last_exam
        course.save(update_fields=["final_exam"])

    return {
        "course": course.id,
        "deleted_exams": deleted,
        "lessons": len(lessons),
        "exams": len(created_exams),
        "users": len(users),
        "questions_bank": sum(len(v["single"]) + len(v["multiple"]) for v in banks_cache.values()),
        "final_exam": last_exam.id if last_exam else None,
    }


print("SEED_LESSON_EXAMS_START")
summaries = []
with transaction.atomic():
    for cid in COURSE_IDS:
        course = Course.objects.get(id=cid)
        summaries.append(seed_course(course))

print("SEED_LESSON_EXAMS_DONE")
for row in summaries:
    print(
        "course", row["course"],
        "lessons", row["lessons"],
        "exams", row["exams"],
        "users", row["users"],
        "bank_mc", row["questions_bank"],
        "deleted", row["deleted_exams"],
        "final_exam", row["final_exam"],
    )

# sanity: 20 questions, 10 points
from django.db.models import Sum

sample = Exam.objects.filter(description__contains=f"{MARKER}:c4:").first()
if sample:
    qs = sample.ordered_questions()
    n = qs.count()
    pts = sum(q.points for q in qs)
    types = list(qs.values_list("q_type", flat=True))
    print("SAMPLE_C4", sample.title[:80], "n", n, "pts", pts, "types", types)
