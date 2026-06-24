from django.urls import path

from . import views

app_name = 'tools'

urlpatterns = [
    path('pdf-word/', views.pdf_to_word, name='pdf_to_word'),
    path('word-excel-pdf/', views.office_to_pdf, name='office_to_pdf'),
    path('ocr/', views.ocr_tool, name='ocr'),
    path('nen-anh/', views.compress_image_view, name='compress_image'),
    path('doi-dinh-dang-anh/', views.convert_image_format_view, name='convert_image_format'),
    path('watermark-anh/', views.watermark_image_view, name='watermark_image'),
    path('ma-qr/', views.qr_generator, name='qr_generator'),
    path('ghi-chu/', views.notes_page, name='notes'),
    path('ghi-chu/them/', views.note_quick_add, name='note_quick_add'),
    path('api/ghi-chu/', views.notes_api, name='notes_api'),
    path('api/ghi-chu/<int:pk>/', views.note_detail_api, name='note_detail_api'),
    path('nhac-lich/', views.schedule_reminder_page, name='schedule_reminder'),
    path('nhac-lich/<int:pk>/xoa/', views.schedule_reminder_delete, name='schedule_reminder_delete'),
]
