from django.urls import path

from nas_storage import views

app_name = 'nas_storage'

urlpatterns = [
    path('', views.browse, name='browse'),
    path('dong-bo/', views.sync_list, name='sync'),
    path('chia-se/tao/', views.create_share, name='share_create'),
    path('chia-se/<uuid:token>/', views.open_share, name='share_open'),
    path('tai-xuong/', views.download, name='download'),
    path('tai-len/', views.upload, name='upload'),
    path('xoa/', views.delete_entry, name='delete'),
]
