from django.contrib import admin

from .models import Model3D


@admin.register(Model3D)
class Model3DAdmin(admin.ModelAdmin):
    list_display = ('title', 'original_name', 'uploaded_by', 'created_at')
    search_fields = ('title', 'description', 'original_name')
    readonly_fields = ('original_name', 'file_size', 'uploaded_by', 'created_at', 'updated_at')
