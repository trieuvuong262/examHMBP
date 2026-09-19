from assessment.models import CertificateTemplate

t = CertificateTemplate.objects.filter(is_default=True).first() or CertificateTemplate.objects.first()
if t:
    t.heading = "CERTIFICATE"
    t.ribbon_text = "OF COMPLETION"
    t.presented_label = "This certificate is proudly presented to"
    t.body_text = (
        "Chứng nhận đã hoàn thành chương trình «{exam_title}» với kết quả {score} điểm. "
        "Cấp tại JustPlay ngày {date}."
    )
    t.issuer_name = "JustPlay.vn"
    t.issuer_title = "Ban Đào tạo"
    t.save()
    print("UPDATED", t.id, t.name, t.ribbon_text)
else:
    print("NO_TEMPLATE")
