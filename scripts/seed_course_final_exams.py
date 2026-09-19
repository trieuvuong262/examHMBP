"""Gop 270 de theo bai hoc thanh 4 bai thi cuoi khoa (khoa 4,5,6,7).

Moi de: 10 TN 1 dap an (0.4) + 9 TN nhieu dap an (0.5) + 1 tu luan (1.5) = 10 diem.
Thoi gian: 19/09/2026 00:00 -> 19/09/2027 00:00 (Asia/Ho_Chi_Minh), 60 phut.
Doi tuong: assigned_users cua khoa; gan Course.final_exam.
"""
from __future__ import annotations

import random
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from assessment.models import Choice, Competency, Exam, Question
from training.models import Course

COURSE_IDS = (4, 5, 6, 7)
OLD_MARKER = "SEED:COURSE_LESSON_EXAM"
MARKER = "SEED:COURSE_FINAL_EXAM"
TZ = ZoneInfo("Asia/Ho_Chi_Minh")
START = timezone.make_aware(datetime(2026, 9, 19, 0, 0, 0), TZ)
END = timezone.make_aware(datetime(2027, 9, 19, 0, 0, 0), TZ)
DURATION = 60
SHORT = {4: "Inkscape", 5: "Kdenlive", 6: "LibreOffice", 7: "Blender"}

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

ESSAYS = {
    4: (
        "Bạn nhận file logo JustPlay (SVG Inkscape) để ra 3 đầu: (1) decal cắt vinyl, "
        "(2) in offset tờ rơi A4, (3) PNG web 2x. Hãy lập checklist kỹ thuật theo từng đầu ra: "
        "khi nào phải outline/Union, clip khác mask chỗ nào, RGB/CMYK, hairline, ảnh link/embed, "
        "kiểm tra lỗ chữ (O, A, 8) và số node. Nêu 2 lỗi nếu bỏ checklist và cách phát hiện "
        "trước khi gửi xưởng — không viết chung chung, phải gắn với quy trình sản xuất."
    ),
    5: (
        "Khách nội bộ cần clip 16:9 cho portal và bản 9:16 cho mạng xã hội. Nguồn 4K H.265, "
        "có logo PNG alpha và subtitle tiếng Việt. Hãy thiết kế pipeline Kdenlive từ ingest đến "
        "giao file: proxy, color correction khác grading, reframe 9:16, QC phụ đề, master khác "
        "bản web. Giải thích khi nào không được lấy H.264 CRF làm bản master, và 3 điểm bắt buộc "
        "duyệt 1:1 trước khi bàn giao."
    ),
    6: (
        "Phòng đào tạo cần SOP ~20 trang (Writer) kèm phụ lục tính chi phí đào tạo (Calc), "
        "xuất PDF in và gửi DOCX cho đối tác. Hãy mô tả: tổ chức Paragraph/Page Style và ToC "
        "(cấm direct formatting), cách khóa số liệu Calc (named range, INDEX/MATCH, ROUND, "
        "locale ngày tháng), và những mất mát điển hình khi round-trip ODT → DOCX phải kiểm tra "
        "thủ công trước khi gửi ra ngoài."
    ),
    7: (
        "JustPlay cần render sản phẩm nhựa thể thao (dielectric, không phải kim loại) rồi ghép "
        "vào ảnh studio thật. Trình bày pipeline: topology trước rig/subsurf, Apply Scale, "
        "PBR (metallic/roughness/color space), khi nào dùng Cycles so với EEVEE, shadow catcher "
        "và camera match, xuất animation an toàn. Nêu 3 lỗi khiến viewport đẹp nhưng vỡ lúc "
        "F12/export, và cách kiểm tra trước khi giao file .blend + EXR."
    ),
}

# Cau hoi kho, chon loc — khong random.
CURATED_SINGLE = {
    4: [0, 1, 2, 3, 4, 5, 8, 14, 17, 19],
    5: [0, 1, 2, 3, 4, 5, 6, 8, 15, 16],
    7: [0, 1, 2, 3, 4, 5, 7, 9, 11, 21],
}
CURATED_MULTI = {
    4: [0, 1, 3, 5, 7, 9, 10, 13, 14],
    5: [0, 1, 2, 3, 4, 5, 6, 8, 14],
    7: [0, 1, 2, 3, 4, 5, 6, 10, 14],
}


def load_banks():
    candidates = [
        Path("/host/root/tmp/seed_lesson_exams.py"),
        Path("/backup-source/scripts/seed_lesson_exams.py"),
        Path("/opt/portaljustplay/scripts/seed_lesson_exams.py"),
        Path("scripts/seed_lesson_exams.py"),
        Path("/tmp/seed_lesson_exams.py"),
    ]
    src = next((p for p in candidates if p.exists()), None)
    if src is None:
        raise FileNotFoundError("Khong tim thay seed_lesson_exams.py de nap ngan hang cau hoi")
    text = src.read_text(encoding="utf-8")
    start = text.index("def pack")
    end = text.index("def bank_for_lesson")
    ns = {}
    exec(text[start:end], ns)
    return ns


def specs_for_course(cid, banks):
    if cid == 6:
        singles = [banks["WRITER"]["single"][i] for i in (0, 1, 4, 5, 9)] + [
            banks["CALC"]["single"][i] for i in (0, 4, 5, 7, 8)
        ]
        multiples = [banks["WRITER"]["multiple"][i] for i in (0, 1, 2, 4, 8)] + [
            banks["CALC"]["multiple"][i] for i in (0, 1, 2, 6)
        ]
        return singles, multiples
    return (
        [banks[SHORT[cid].upper()]["single"][i] for i in CURATED_SINGLE[cid]],
        [banks[SHORT[cid].upper()]["multiple"][i] for i in CURATED_MULTI[cid]],
    )


def create_mc(comp, spec):
    q = Question.objects.create(
        competency=comp,
        content=spec["content"],
        q_type=spec["q_type"],
        points=spec["points"],
    )
    pairs = list(spec["choices"])
    random.Random(q.id).shuffle(pairs)
    Choice.objects.bulk_create(
        [
            Choice(question=q, text=text[:500], is_correct=ok, sort_order=idx)
            for idx, (text, ok) in enumerate(pairs, start=1)
        ]
    )
    return q


def cleanup():
    titles = [f"Kiểm tra cuối khóa · {SHORT[cid]}" for cid in COURSE_IDS]
    n_old = Exam.objects.filter(description__contains=OLD_MARKER).count()
    finals = Exam.objects.filter(description__contains=MARKER) | Exam.objects.filter(title__in=titles)
    n_final = finals.distinct().count()
    Exam.objects.filter(description__contains=OLD_MARKER).delete()
    Exam.objects.filter(description__contains=MARKER).delete()
    Exam.objects.filter(title__in=titles).delete()
    n_comp = 0
    for cid in COURSE_IDS:
        qs = Competency.objects.filter(name__startswith=f"[KH{cid}]")
        n_comp += qs.count()
        qs.delete()
    return n_old, n_final, n_comp


def seed_one(course, banks):
    short = SHORT[course.id]
    singles, multiples = specs_for_course(course.id, banks)
    if len(singles) != 10 or len(multiples) != 9:
        raise ValueError(f"Khoa {course.id}: {len(singles)} single / {len(multiples)} multiple")

    comp = Competency.objects.create(
        name=f"[KH{course.id}] {short}",
        description=f"Đề thi cuối khóa — {course.title}",
    )
    questions = [create_mc(comp, s) for s in singles]
    questions += [create_mc(comp, m) for m in multiples]
    essay = Question.objects.create(
        competency=comp,
        content=ESSAYS[course.id],
        q_type="essay",
        points=1.5,
    )
    questions.append(essay)

    exam = Exam.objects.create(
        title=f"Kiểm tra cuối khóa · {short}",
        description=DESCS[course.id],
        start_time=START,
        end_time=END,
        duration_minutes=DURATION,
        is_active=True,
    )
    exam.replace_questions(questions)
    users = list(course.assigned_users.all())
    if users:
        exam.assigned_users.set(users)
    course.final_exam = exam
    course.save(update_fields=["final_exam"])
    pts = sum(q.points for q in questions)
    return {
        "course": course.id,
        "title": exam.title,
        "exam_id": exam.id,
        "users": len(users),
        "n": len(questions),
        "pts": pts,
        "usernames": [u.username for u in users],
    }


print("SEED_COURSE_FINALS_START")
banks = load_banks()
with transaction.atomic():
    deleted = cleanup()
    print("DELETED_LESSON_EXAMS", deleted[0], "OLD_FINALS", deleted[1], "COMPS", deleted[2])
    rows = []
    for cid in COURSE_IDS:
        course = Course.objects.get(id=cid)
        rows.append(seed_one(course, banks))

print("SEED_COURSE_FINALS_DONE")
for row in rows:
    print(
        "C", row["course"],
        "exam", row["exam_id"],
        row["title"],
        "n", row["n"],
        "pts", row["pts"],
        "users", row["usernames"],
    )
print("REMAINING_LESSON_EXAMS", Exam.objects.filter(description__contains=OLD_MARKER).count())
print("FINAL_EXAMS", Exam.objects.filter(description__contains=MARKER).count())
