from django.conf import settings
from django.db import models
from django.utils import timezone


class Feedback(models.Model):
    submitter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='feedbacks_submitted',
    )
    title = models.CharField('Tiêu đề', max_length=200)
    body = models.TextField('Nội dung')
    is_anonymous = models.BooleanField('Gửi ẩn danh', default=False)
    viewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='feedbacks_viewed',
        verbose_name='Người xem',
    )
    viewed_at = models.DateTimeField('Thời điểm xem', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Góp ý'
        verbose_name_plural = 'Góp ý'

    def __str__(self):
        return self.title

    @property
    def is_viewed(self):
        return self.viewed_at is not None

    def submitter_display(self):
        if self.is_anonymous:
            return 'Ẩn danh'
        user = self.submitter
        return user.get_full_name() or user.username

    def viewer_display(self):
        if not self.viewed_by_id:
            return ''
        user = self.viewed_by
        return user.get_full_name() or user.username

    def mark_viewed_by(self, user):
        if self.viewed_at:
            return
        self.viewed_by = user
        self.viewed_at = timezone.now()
        self.save(update_fields=['viewed_by', 'viewed_at'])
