from django.conf import settings
from django.db import models


class Feedback(models.Model):
    submitter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='feedbacks_submitted',
    )
    title = models.CharField('Tiêu đề', max_length=200)
    body = models.TextField('Nội dung')
    is_anonymous = models.BooleanField('Gửi ẩn danh', default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Góp ý'
        verbose_name_plural = 'Góp ý'

    def __str__(self):
        return self.title

    def submitter_display(self):
        if self.is_anonymous:
            return 'Ẩn danh'
        user = self.submitter
        return user.get_full_name() or user.username
