from django.contrib import admin

from .models import Document, DocumentCategory


class DocumentInline(admin.TabularInline):
    model = Document
    extra = 0
    fields = ('title', 'slug', 'content_type', 'sort_order', 'is_active')


@admin.register(DocumentCategory)
class DocumentCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'sort_order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [DocumentInline]


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'content_type', 'sort_order', 'is_active', 'updated_at')
    list_filter = ('category', 'content_type', 'is_active')
    search_fields = ('title', 'slug', 'summary')
    prepopulated_fields = {'slug': ('title',)}
