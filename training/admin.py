from django.contrib import admin
from .models import CourseCategory, Course, Chapter, Lesson, Enrollment, LessonProgress

class LessonInline(admin.StackedInline):
    model = Lesson
    extra = 1 
    fields = ('title', 'lesson_type', 'video_url', 'video_file', 'attachment', 'content', 'order', 'duration_estimate')


class ChapterAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'order')
    list_filter = ('course',)
    search_fields = ('title',)
    inlines = [LessonInline]  

class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'is_active', 'created_at')
    list_filter = ('category', 'is_active')
    search_fields = ('title', 'description')
    filter_horizontal = ('assigned_users',) 

class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('user', 'course', 'get_progress_percent', 'is_completed', 'enrolled_at')
    list_filter = ('is_completed', 'course')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'course__title')

    def get_progress_percent(self, obj):
        return f"{obj.progress_percent}%"
    
    get_progress_percent.short_description = "Tiến độ học"

class LessonProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'lesson', 'is_completed', 'completed_at')
    list_filter = ('is_completed',)
    search_fields = ('user__username', 'lesson__title')

admin.site.register(CourseCategory)
admin.site.register(Course, CourseAdmin)
admin.site.register(Chapter, ChapterAdmin)
admin.site.register(Lesson)
admin.site.register(Enrollment, EnrollmentAdmin)
admin.site.register(LessonProgress, LessonProgressAdmin)