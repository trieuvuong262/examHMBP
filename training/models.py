from django.db import models
from django.contrib.auth.models import User
from assessment.models import Exam 

# 1. Danh mục khóa học
class CourseCategory(models.Model):
    name = models.CharField(max_length=255, verbose_name="Tên danh mục")
    description = models.TextField(blank=True, verbose_name="Mô tả")

    class Meta:
        verbose_name = "Danh mục khóa học"
        verbose_name_plural = "Danh mục khóa học"

    def __str__(self):
        return self.name

# 2. Khóa học
class Course(models.Model):
    category = models.ForeignKey(CourseCategory, on_delete=models.SET_NULL, null=True, related_name='courses', verbose_name="Danh mục")
    title = models.CharField(max_length=255, verbose_name="Tiêu đề khóa học")
    description = models.TextField(verbose_name="Mô tả khóa học")
    thumbnail = models.ImageField(upload_to='course_thumbnails/', null=True, blank=True, verbose_name="Ảnh bìa")
    
    final_exam = models.ForeignKey(Exam, on_delete=models.SET_NULL, null=True, blank=True, 
                                   related_name='related_courses', verbose_name="Kỳ thi cuối khóa")
    
    assigned_users = models.ManyToManyField(User, related_name='assigned_courses', blank=True, verbose_name="Nhân viên được giao")
    
    is_active = models.BooleanField(default=True, verbose_name="Đang hoạt động")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Ngày tạo")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Cập nhật lần cuối")

    class Meta:
        verbose_name = "Khóa học"
        verbose_name_plural = "Khóa học"

    def __str__(self):
        return self.title

# 3. Chương/Tuần
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

# 4. Bài học
class Lesson(models.Model):
    LESSON_TYPES = (
        ('video', 'Video bài giảng'),
        ('pdf', 'Tài liệu PDF'),
        ('reading', 'Bài viết/Văn bản'),
    )

    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='lessons', verbose_name="Chương")
    title = models.CharField(max_length=255, verbose_name="Tiêu đề bài học")
    lesson_type = models.CharField(max_length=20, choices=LESSON_TYPES, verbose_name="Loại bài học")
    
    content = models.TextField(blank=True, verbose_name="Nội dung văn bản")
    video_url = models.URLField(blank=True, null=True, verbose_name="Đường dẫn Video (YouTube/Drive)")
    attachment = models.FileField(upload_to='course_materials/', null=True, blank=True, verbose_name="Tài liệu đính kèm")
    
    order = models.PositiveIntegerField(default=0, verbose_name="Thứ tự bài học")
    duration_estimate = models.IntegerField(default=0, verbose_name="Thời gian dự kiến (phút)")

    class Meta:
        verbose_name = "Bài học"
        verbose_name_plural = "Bài học"
        ordering = ['order']

    def __str__(self):
        return self.title

# 5. Ghi danh & Tiến độ
# 5. Ghi danh & Tiến độ
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

    # THÊM ĐOẠN NÀY VÀO: Hàm tự động tính toán % tiến độ
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
# 6. Tiến độ từng bài học
class LessonProgress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Nhân viên")
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, verbose_name="Bài học")
    is_completed = models.BooleanField(default=False, verbose_name="Hoàn tất")
    completed_at = models.DateTimeField(auto_now=True, verbose_name="Lần xem cuối")

    class Meta:
        verbose_name = "Tiến độ bài học"
        verbose_name_plural = "Tiến độ bài học"
        unique_together = ('user', 'lesson')