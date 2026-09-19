from training.models import Course

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

for cid, text in DESCS.items():
    course = Course.objects.get(id=cid)
    exam = course.final_exam
    if not exam:
        print("MISSING", cid)
        continue
    exam.description = text
    exam.save(update_fields=["description"])
    print("OK", cid, exam.id, exam.title)
    print(" ", text[:80], "...")
