import bleach # Thư viện chống XSS
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator # Thư viện chặn đuôi file lạ
from assessment.models import Exam 
from ckeditor.fields import RichTextField

class CourseCategory(models.Model):
    name = models.CharField(max_length=255, verbose_name="Tên danh mục")
    description = models.TextField(blank=True, verbose_name="Mô tả")

    class Meta:
        verbose_name = "Danh mục khóa học"
        verbose_name_plural = "Danh mục khóa học"

    def __str__(self):
        return self.name

class Course(models.Model):
    category = models.ForeignKey(CourseCategory, on_delete=models.SET_NULL, null=True, related_name='courses', verbose_name="Danh mục")
    title = models.CharField(max_length=255, verbose_name="Tiêu đề khóa học")
    description = models.TextField(verbose_name="Mô tả khóa học")
    
    # VÁ LỖI 5: Giới hạn chỉ cho phép up ảnh bìa đúng chuẩn
    thumbnail = models.ImageField(
        upload_to='course_thumbnails/', 
        null=True, blank=True, 
        verbose_name="Ảnh bìa",
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp'])]
    )
    
    final_exam = models.ForeignKey(Exam, on_delete=models.SET_NULL, null=True, blank=True, related_name='related_courses', verbose_name="Kỳ thi cuối khóa")
    assigned_users = models.ManyToManyField(User, related_name='assigned_courses', blank=True, verbose_name="Nhân viên được giao")
    is_active = models.BooleanField(default=True, verbose_name="Đang hoạt động")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Ngày tạo")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Cập nhật lần cuối")

    class Meta:
        verbose_name = "Khóa học"
        verbose_name_plural = "Khóa học"

    def __str__(self):
        return self.title

class Chapter(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='chapters', verbose_name="Khóa học")
    title = models.CharField(max_length=255, verbose_name="Tên chương/Tuần")
    order = models.PositiveIntegerField(default=0, verbose_name="Thứ tự sắp xếp")

    class Meta:
        verbose_name = "Chương học"
        verbose_name_plural = "Chương học"
        ordering = ['order']

    def __str__(self):
        return f"{self.course.title} - {self.title}"

class Lesson(models.Model):
    LESSON_TYPES = (
        ('video', 'Video bài giảng'),
        ('pdf', 'Tài liệu PDF'),
        ('reading', 'Bài viết/Văn bản'),
    )

    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='lessons', verbose_name="Chương")
    title = models.CharField(max_length=255, verbose_name="Tiêu đề bài học")
    lesson_type = models.CharField(max_length=20, choices=LESSON_TYPES, verbose_name="Loại bài học")
    content = RichTextField(blank=True, null=True, verbose_name="Nội dung bài học")
    video_url = models.URLField(blank=True, null=True, verbose_name="Đường dẫn Video (YouTube/Drive)")
    
    # VÁ LỖI 5: Cấp chứng minh thư cho file đính kèm. 
    # Ai up file có đuôi .exe, .php, .html, .bat là báo lỗi không cho lưu!
    attachment = models.FileField(
        upload_to='course_materials/', 
        null=True, blank=True, 
        verbose_name="Tài liệu đính kèm",
        validators=[FileExtensionValidator(allowed_extensions=[
            'pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'zip', 'rar'
        ])]
    )
    
    order = models.PositiveIntegerField(default=0, verbose_name="Thứ tự bài học")
    duration_estimate = models.IntegerField(default=0, verbose_name="Thời gian dự kiến (phút)")

    class Meta:
        verbose_name = "Bài học"
        verbose_name_plural = "Bài học"
        ordering = ['order']

    def __str__(self):
        return self.title
        
    # VÁ LỖI 11: Chặn đứng mã độc XSS từ CKEditor trước khi lưu vào Database
    def save(self, *args, **kwargs):
        if self.content:
            # Danh sách các thẻ HTML an toàn (được phép giữ lại)
            allowed_tags = [
                'p', 'b', 'i', 'u', 'em', 'strong', 'a', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                'ul', 'ol', 'li', 'br', 'span', 'div', 'table', 'tbody', 'thead', 'tr', 'td', 'th',
                'blockquote', 'code', 'pre', 'hr', 'img'
            ]
            # Danh sách các thuộc tính an toàn (Ví dụ thẻ <a> thì được có 'href')
            allowed_attributes = {
                '*': ['class', 'style'], # Cho phép class và style trên mọi thẻ
                'a': ['href', 'target', 'rel'],
                'img': ['src', 'alt', 'width', 'height']
            }
            
            # Hàm bleach.clean sẽ "quét" và gọt sạch mọi thẻ <script>, <iframe> độc hại
            self.content = bleach.clean(
                self.content,
                tags=allowed_tags,
                attributes=allowed_attributes,
                strip=True # Gọt mất phần mã độc thay vì mã hóa nó
            )
            
        super(Lesson, self).save(*args, **kwargs)

class Enrollment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='enrollments', verbose_name="Nhân viên")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrolled_students', verbose_name="Khóa học")
    enrolled_at = models.DateTimeField(auto_now_add=True, verbose_name="Ngày tham gia")
    is_completed = models.BooleanField(default=False, verbose_name="Đã hoàn thành")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Ngày hoàn thành")

    class Meta:
        verbose_name = "Ghi danh học tập"
        verbose_name_plural = "Ghi danh học tập"
        unique_together = ('user', 'course')

    @property
    def progress_percent(self):
        total_lessons = Lesson.objects.filter(chapter__course=self.course).count()
        if total_lessons == 0: 
            return 0
        
        completed_lessons = LessonProgress.objects.filter(
            user=self.user, 
            lesson__chapter__course=self.course, 
            is_completed=True
        ).count()
        
        return round((completed_lessons / total_lessons) * 100, 1)

class LessonProgress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Nhân viên")
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, verbose_name="Bài học")
    is_completed = models.BooleanField(default=False, verbose_name="Hoàn tất")
    completed_at = models.DateTimeField(auto_now=True, verbose_name="Lần xem cuối")

    class Meta:
        verbose_name = "Tiến độ bài học"
        verbose_name_plural = "Tiến độ bài học"
        unique_together = ('user', 'lesson')