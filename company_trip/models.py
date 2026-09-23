from django.conf import settings
from django.db import models
from ckeditor.fields import RichTextField

from company_trip.constants import (
    BREAKFAST_CHOICES,
    ROOM_CHOICES,
    ROOM_ORGANIZER,
    ROUTE_CHOICES,
    SHOPPING_CHOICES,
    STATUS_CHOICES,
    STATUS_REGISTERED,
    TRIP_DATES_DISPLAY,
    TRIP_DESTINATION,
    TRIP_END,
    TRIP_START,
    TRIP_TITLE,
    VEGETARIAN_CHOICES,
)


class TripSettings(models.Model):
    """Singleton pk=1 — cấu hình chuyến đi."""

    title = models.CharField(max_length=255, default=TRIP_TITLE, verbose_name='Tên sự kiện')
    destination = models.CharField(max_length=255, default=TRIP_DESTINATION, verbose_name='Điểm đến')
    start_date = models.DateField(default=TRIP_START, verbose_name='Ngày bắt đầu')
    end_date = models.DateField(default=TRIP_END, verbose_name='Ngày kết thúc')
    registration_open = models.BooleanField(default=True, verbose_name='Mở đăng ký')
    dates_display = models.CharField(
        max_length=64,
        default=TRIP_DATES_DISPLAY,
        verbose_name='Chuỗi ngày hiển thị',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Cấu hình Company Trip'
        verbose_name_plural = 'Cấu hình Company Trip'

    def __str__(self):
        return self.title

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class TripRegistration(models.Model):
    profile = models.OneToOneField(
        'hrm.Profile',
        on_delete=models.CASCADE,
        related_name='company_trip_registration',
        verbose_name='Nhân viên',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='company_trip_registrations',
        verbose_name='Tài khoản',
    )
    # Snapshot
    full_name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    gender = models.CharField(max_length=10, blank=True)
    department_name = models.CharField(max_length=150, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)

    room_type = models.CharField(
        max_length=64,
        choices=ROOM_CHOICES,
        default=ROOM_ORGANIZER,
        verbose_name='Loại phòng',
    )
    companion1 = models.ForeignKey(
        'hrm.Profile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='trip_companion1_of',
        verbose_name='Người cùng phòng 1',
    )
    companion2 = models.ForeignKey(
        'hrm.Profile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='trip_companion2_of',
        verbose_name='Người cùng phòng 2',
    )
    companion1_name = models.CharField(max_length=255, blank=True)
    companion2_name = models.CharField(max_length=255, blank=True)
    companion_confirmed = models.BooleanField(default=False, verbose_name='Đồng nghiệp đã xác nhận')
    companion_confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name='Thời điểm xác nhận')
    companion_email = models.EmailField(blank=True, verbose_name='Email đồng nghiệp')

    relative_full_name = models.CharField(max_length=255, blank=True, verbose_name='Họ tên người thân')
    relative_cccd = models.CharField(max_length=20, blank=True, verbose_name='Số CCCD người thân')
    relative_phone = models.CharField(max_length=32, blank=True, verbose_name='SĐT người thân')
    relative_gender = models.CharField(max_length=10, blank=True, verbose_name='Giới tính người thân')
    relative_date_of_birth = models.DateField(null=True, blank=True, verbose_name='Ngày sinh người thân')

    room_key = models.CharField(max_length=32, blank=True, db_index=True, verbose_name='Mã phòng')

    vegetarian = models.CharField(
        max_length=32,
        choices=VEGETARIAN_CHOICES,
        default='Không ăn chay',
        verbose_name='Ăn chay',
    )
    allergy_note = models.TextField(blank=True, verbose_name='Dị ứng')
    pickup_point = models.CharField(max_length=255, blank=True, verbose_name='Điểm đón')
    breakfast_choice = models.CharField(
        max_length=64,
        choices=BREAKFAST_CHOICES,
        default='Không ăn sáng',
        verbose_name='Ăn sáng',
    )
    route = models.CharField(
        max_length=255,
        choices=ROUTE_CHOICES,
        blank=True,
        verbose_name='Lộ trình',
    )
    detail_route = models.TextField(blank=True, verbose_name='Chi tiết lộ trình')
    shopping = models.CharField(
        max_length=32,
        choices=SHOPPING_CHOICES,
        default='Tham gia',
        verbose_name='Mua sắm chợ Đầm Nại',
    )
    note = models.TextField(blank=True, verbose_name='Ghi chú')
    organized_committee = models.BooleanField(default=False, verbose_name='BTC sắp xếp phòng')

    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_REGISTERED,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Đăng ký Company Trip'
        verbose_name_plural = 'Đăng ký Company Trip'

    def __str__(self):
        return f'{self.full_name or self.profile_id} ({self.status})'

    @property
    def relative_names_display(self) -> str:
        names = [item.full_name for item in self.relatives.all() if item.full_name]
        if not names and self.relative_full_name:
            return self.relative_full_name
        return ', '.join(names)


class TripRelative(models.Model):
    """Người thân đi cùng — tối đa 3 người trên một đăng ký."""

    registration = models.ForeignKey(
        TripRegistration,
        on_delete=models.CASCADE,
        related_name='relatives',
        verbose_name='Đăng ký',
    )
    position = models.PositiveSmallIntegerField(verbose_name='Thứ tự')
    full_name = models.CharField(max_length=255, verbose_name='Họ tên')
    cccd = models.CharField(max_length=20, verbose_name='Số CCCD')
    phone = models.CharField(max_length=32, verbose_name='Số điện thoại')
    gender = models.CharField(max_length=10, verbose_name='Giới tính')
    date_of_birth = models.DateField(verbose_name='Ngày sinh')

    class Meta:
        ordering = ['position']
        constraints = [
            models.UniqueConstraint(
                fields=['registration', 'position'],
                name='uniq_trip_relative_position',
            ),
        ]
        verbose_name = 'Người thân'
        verbose_name_plural = 'Người thân'

    def __str__(self):
        return self.full_name


DEFAULT_TRIP_EMAIL_SUBJECT = 'Thư mời tham gia Kế hoạch du lịch nghỉ mát {{ year }} - Just Play'
DEFAULT_TRIP_EMAIL_BODY = """
<p>Kính gửi {{ gender_prefix }} <strong>{{ fullname }}</strong>,</p>
<p>Sau những tháng ngày làm việc đầy nhiệt huyết, Ban Giám Đốc trân trọng gửi đến {{ gender_prefix }} lời mời đặc biệt tham gia chương trình <strong>Company Trip {{ year }}</strong> — một chuyến đi bùng nổ hứa hẹn sẽ "refresh" năng lượng, gắn kết tình đồng đội và tạo nên những kỷ niệm khó quên!</p>
<p>Chuyến đi lần này được thiết kế riêng với vô vàn hoạt động độc đáo và hấp dẫn đang chờ đón {{ gender_prefix }}:</p>
<ul>
<li><strong>Teambuilding bãi biển sôi động:</strong> Cùng nhau vượt qua các thử thách, "phá đảo" bờ cát trắng và xây dựng tinh thần đồng đội vững chắc.</li>
<li><strong>Gala Dinner &amp; minigame tưng bừng:</strong> Một đêm tiệc ấm cúng, sang trọng nhưng không kém phần vui nhộn, nơi chúng ta có thể giao lưu, "cháy" hết mình và nhận về những phần quà bất ngờ.</li>
<li><strong>Khám phá danh lam thắng cảnh:</strong> Đắm mình vào vẻ đẹp thiên nhiên hùng vĩ và trải nghiệm văn hóa độc đáo tại những điểm đến hấp dẫn.</li>
</ul>
<p>Và còn rất nhiều bất ngờ khác đang chờ đón {{ gender_prefix }} khám phá!</p>
<p>Sự hiện diện của {{ gender_prefix }} chính là yếu tố quan trọng nhất, là niềm vui và động lực to lớn để Company Trip {{ year }} thành công rực rỡ!</p>
<p><strong>Thông tin chuyến đi cơ bản của {{ gender_prefix }}:</strong></p>
<ul>
<li><strong>Địa điểm đón:</strong> {{ pickup }}</li>
<li><strong>Thời gian tập trung:</strong> {{ gather_time }}</li>
<li><strong>Thời gian:</strong> {{ dates }}</li>
<li><strong>Địa điểm:</strong> {{ location }}</li>
<li><strong>Resort:</strong> {{ resort }}</li>
<li><strong>Loại phòng nghỉ:</strong> {{ room_type }}</li>
<li><strong>Đồng hành cùng:</strong> {{ companions }}</li>
</ul>
{{ itinerary }}
<p>{{ gender_prefix }} vui lòng đăng ký tại: <a href="{{ register_url }}">{{ register_url }}</a></p>
<p>Hãy cùng chuẩn bị tinh thần cho một chuyến đi thật đáng nhớ, {{ gender_prefix }} nhé!</p>
<p>Trân trọng,<br>Phòng Hành chính Nhân sự</p>
""".strip()


class TripEmailTemplate(models.Model):
    subject = models.CharField(
        max_length=255,
        default=DEFAULT_TRIP_EMAIL_SUBJECT,
        verbose_name='Tiêu đề',
    )
    body = RichTextField(
        blank=True,
        verbose_name='Nội dung HTML',
        help_text=(
            'Biến: {{ fullname }}, {{ gender_prefix }}, {{ dates }}, {{ destination }}, '
            '{{ location }}, {{ resort }}, {{ pickup }}, {{ gather_time }}, {{ itinerary }}, '
            '{{ register_url }}, {{ title }}, {{ year }}, {{ room_type }}, {{ companions }}, '
            '{{ phone }}, {{ department }}'
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Mẫu email Company Trip'
        verbose_name_plural = 'Mẫu email Company Trip'

    def __str__(self):
        return self.subject[:80]

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        if not (obj.body or '').strip():
            obj.subject = DEFAULT_TRIP_EMAIL_SUBJECT
            obj.body = DEFAULT_TRIP_EMAIL_BODY
            obj.save(update_fields=['subject', 'body', 'updated_at'])
        return obj
