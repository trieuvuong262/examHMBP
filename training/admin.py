from django.contrib import admin
from .models import CourseCategory, Course, Chapter, Lesson, Enrollment, LessonProgress

# 1. Cấu hình Inline để thêm Bài học ngay trong lúc tạo Chương
class LessonInline(admin.StackedInline):
    model = Lesson
    extra = 1  # Số lượng form bài học trống hiển thị sẵn
    fields = ('title', 'lesson_type', 'video_url', 'attachment', 'content', 'order', 'duration_estimate')

# 2. Cấu hình Admin cho Chương (Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'order')
    list_filter = ('course',)
    search_fields = ('title',)
    inlines = [LessonInline]  # Gắn LessonInline vào đây

# 3. Cấu hình Admin cho Khóa học (Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'is_active', 'created_at')
    list_filter = ('category', 'is_active')
    search_fields = ('title', 'description')
    filter_horizontal = ('assigned_users',)  # Cột chọn nhân viên giao diện đẹp

# 4. Cấu hình Admin cho Ghi danh & Tiến độ (Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('user', 'course', 'get_progress_percent', 'is_completed', 'enrolled_at')
    list_filter = ('is_completed', 'course')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'course__title')

    # Hàm lấy phần trăm tiến độ để hiển thị an toàn trên Admin
    def get_progress_percent(self, obj):
        return f"{obj.progress_percent}%"
    
    # Đặt tiêu đề cho cột hiển thị trên Admin
    get_progress_percent.short_description = "Tiến độ học"

# 5. Cấu hình Admin cho Tiến độ bài học chi tiết (LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'lesson', 'is_completed', 'completed_at')
    list_filter = ('is_completed',)
    search_fields = ('user__username', 'lesson__title')

# Đăng ký tất cả các models vào hệ thống Admin
admin.site.register(CourseCategory)
admin.site.register(Course, CourseAdmin)
admin.site.register(Chapter, ChapterAdmin)
admin.site.register(Lesson)
admin.site.register(Enrollment, EnrollmentAdmin)
admin.site.register(LessonProgress, LessonProgressAdmin)