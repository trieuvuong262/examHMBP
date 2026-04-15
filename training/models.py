from django.db import models
from django.contrib.auth.models import User
from assessment.models import Exam  # Import Exam để làm bài thi cuối khóa

# 1. Danh mục khóa học (VD: Kỹ năng mềm, Quy trình Y khoa...)
class CourseCategory(models.Model):
    name = models.CharField(max_length=255, verbose_name="Tên danh mục")
    description = models.TextField(blank=True, verbose_name="Mô tả")

    class Meta:
        verbose_name_plural = "Danh mục khóa học"

    def __str__(self):
        return self.name

# 2. Khóa học tổng thể
class Course(models.Model):
    category = models.ForeignKey(CourseCategory, on_delete=models.SET_NULL, null=True, related_name='courses')
    title = models.CharField(max_length=255, verbose_name="Tên khóa học")
    description = models.TextField(verbose_name="Mô tả khóa học")
    thumbnail = models.ImageField(upload_to='course_thumbnails/', null=True, blank=True, verbose_name="Ảnh bìa")
    
    # Liên kết với hệ thống đánh giá: Thi xong khóa học
    final_exam = models.ForeignKey(Exam, on_delete=models.SET_NULL, null=True, blank=True, 
                                   related_name='related_courses', verbose_name="Kỳ thi cuối khóa")
    
    # Phân quyền nhân viên được xem khóa học này
    assigned_users = models.ManyToManyField(User, related_name='assigned_courses', blank=True)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

# 3. Chương/Tuần (Để chia nhỏ bài học giống Coursera)
class Chapter(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='chapters')
    title = models.CharField(max_length=255, verbose_name="Tên chương/Tuần")
    order = models.PositiveIntegerField(default=0, verbose_name="Thứ tự sắp xếp")

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.course.title} - {self.title}"

# 4. Bài học chi tiết
class Lesson(models.Model):
    LESSON_TYPES = (
        ('video', 'Video bài giảng'),
        ('pdf', 'Tài liệu PDF'),
        ('reading', 'Bài viết/Văn bản'),
    )

    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='lessons')
    title = models.CharField(max_length=255, verbose_name="Tiêu đề bài học")
    lesson_type = models.CharField(max_length=20, choices=LESSON_TYPES)
    
    # Nội dung linh hoạt
    content = models.TextField(blank=True, verbose_name="Nội dung văn bản")
    video_url = models.URLField(blank=True, null=True, verbose_name="Link Video (YouTube/Drive)")
    attachment = models.FileField(upload_to='course_materials/', null=True, blank=True, verbose_name="Tài liệu đính kèm (PDF/Doc)")
    
    order = models.PositiveIntegerField(default=0, verbose_name="Thứ tự bài học")
    duration_estimate = models.IntegerField(default=0, verbose_name="Thời gian dự kiến (phút)")

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.title

# 5. Theo dõi ghi danh và tiến độ khóa học
class Enrollment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='enrollments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrolled_students')
    enrolled_at = models.DateTimeField(auto_now_add=True)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('user', 'course')

    # Hàm tính % tiến độ học tập
    @property
    def progress_percent(self):
        total_lessons = Lesson.objects.filter(chapter__course=self.course).count()
        if total_lessons == 0: return 0
        
        completed_lessons = LessonProgress.objects.filter(
            user=self.user, 
            lesson__chapter__course=self.course, 
            is_completed=True
        ).count()
        
        return round((completed_lessons / total_lessons) * 100, 1)

# 6. Theo dõi tiến độ từng bài học (Để đánh dấu tích xanh ✅)
class LessonProgress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'lesson')