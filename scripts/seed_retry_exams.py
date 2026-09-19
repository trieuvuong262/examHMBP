"""Tao 4 de thi lai (khoa 4-7) — bo cau hoi khac de chinh, thang 100.

Chay SAU migrate 0013. Khong gan hoc vien; chi gan khi truot < 50d.
"""
from __future__ import annotations

import random
from pathlib import Path

from django.db import transaction

from assessment.models import Choice, Competency, Exam, Question
from training.models import Course

COURSE_IDS = (4, 5, 6, 7)
MARKER = "SEED:COURSE_RETRY_EXAM"
SHORT = {4: "Inkscape", 5: "Kdenlive", 6: "LibreOffice", 7: "Blender"}
PTS = {"single": 4, "multiple": 5, "essay": 15}

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
        Path("/app/scripts/seed_lesson_exams.py"),
    ]
    src = next((p for p in candidates if p.exists()), None)
    if src is None:
        raise FileNotFoundError("Khong tim thay seed_lesson_exams.py")
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
        points=PTS[spec["q_type"]],
    )
    pairs = list(spec["choices"])
    random.Random(q.id + 97).shuffle(pairs)
    Choice.objects.bulk_create(
        [
            Choice(question=q, text=text[:500], is_correct=ok, sort_order=idx)
            for idx, (text, ok) in enumerate(pairs, start=1)
        ]
    )
    return q


def seed_one(course, banks):
    source = course.final_exam
    if source is None:
        return {"course": course.id, "skip": "no_final"}
    existing = source.retry_exams.filter(is_active=True).first()
    if existing:
        return {"course": course.id, "skip": "exists", "exam_id": existing.id, "title": existing.title}

    singles, multiples = specs_for_course(course.id, banks)
    if len(singles) != 10 or len(multiples) != 9:
        raise ValueError(f"Khoa {course.id}: {len(singles)} single / {len(multiples)} multiple")

    short = SHORT[course.id]
    comp = Competency.objects.create(
        name=f"[KH{course.id}] {short} — Thi lại",
        description=f"Đề thi lại cuối khóa — {course.title}",
    )
    questions = [create_mc(comp, s) for s in singles]
    questions += [create_mc(comp, m) for m in multiples]
    questions.append(
        Question.objects.create(
            competency=comp,
            content=ESSAYS[course.id],
            q_type="essay",
            points=PTS["essay"],
        )
    )
    retry = Exam.objects.create(
        title=f"Thi lại cuối khóa · {short}",
        description=(
            f"Bài kiểm tra lại cho học viên chưa đạt 50/100 điểm. "
            f"Thời gian 60 phút, 20 câu (thang 100). {MARKER}"
        ),
        start_time=source.start_time,
        end_time=source.end_time,
        duration_minutes=source.duration_minutes or 60,
        is_active=True,
        issue_certificate=True,
        pass_score=50,
        certificate_template=source.certificate_template,
        retry_of=source,
    )
    retry.replace_questions(questions)
    pts = sum(q.points for q in questions)
    return {
        "course": course.id,
        "exam_id": retry.id,
        "title": retry.title,
        "n": len(questions),
        "pts": pts,
        "source": source.id,
    }


print("SEED_RETRY_EXAMS_START")
banks = load_banks()
with transaction.atomic():
    rows = []
    for cid in COURSE_IDS:
        course = Course.objects.get(id=cid)
        rows.append(seed_one(course, banks))
print("SEED_RETRY_EXAMS_DONE")
for row in rows:
    print(row)
