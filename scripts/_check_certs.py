from assessment.models import CertificateTemplate, Exam
print('templates', CertificateTemplate.objects.count())
print('issue', list(Exam.objects.filter(id__in=[4, 5, 6, 7]).values_list('id', 'issue_certificate', 'pass_score')))
