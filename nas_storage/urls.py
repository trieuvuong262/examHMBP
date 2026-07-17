from django.urls import path

from nas_storage import views
from nas_storage import views_nas_download
from nas_storage import views_permissions as perm_views

app_name = 'nas_storage'

urlpatterns = [
    path('', views.browse, name='browse'),
    path('chia-se/tao/', views.create_share, name='share_create'),
    path('chia-se/<uuid:token>/', views.open_share, name='share_open'),
    path('xem-truoc/', views.preview_file, name='preview'),
    path('tai-xuong/', views.download, name='download'),
    path('xoa/', views.delete_entry, name='delete'),
    path('cai-dat/', views_nas_download.nas_download_page, name='nas_download'),
    path('cai-dat/raidrive/', views_nas_download.nas_raidrive_download, name='raidrive_download'),
    path('cai-dat/tai/', views_nas_download.nas_download_setup, name='nas_download_setup'),
    # Phân quyền thư mục NAS
    path('phan-quyen/', perm_views.permissions_hub, name='permissions_hub'),
    path('phan-quyen/ap-dung-tat-ca/', perm_views.apply_all_acl, name='apply_all_acl'),
    path('phan-quyen/nhom/', perm_views.group_list, name='group_list'),
    path('phan-quyen/nhom/them/', perm_views.group_edit, name='group_create'),
    path('phan-quyen/nhom/<int:pk>/', perm_views.group_edit, name='group_edit'),
    path('phan-quyen/thu-muc/', perm_views.folder_list, name='folder_list'),
    path('phan-quyen/thu-muc/quet/', perm_views.import_shares_from_nas, name='import_shares'),
    path('phan-quyen/thu-muc/them/', perm_views.folder_edit, name='folder_create'),
    path('phan-quyen/thu-muc/<int:parent_pk>/them-con/', perm_views.folder_child_create, name='folder_child_create'),
    path('phan-quyen/thu-muc/<int:pk>/', perm_views.folder_edit, name='folder_edit'),
    path('phan-quyen/thu-muc/<int:pk>/xoa/', perm_views.folder_delete, name='folder_delete'),
    path('phan-quyen/thu-muc/<int:pk>/quyen/', perm_views.folder_permissions, name='folder_permissions'),
    path('phan-quyen/thu-muc/<int:folder_pk>/quyen/them/', perm_views.permission_edit, name='permission_create'),
    path('phan-quyen/thu-muc/<int:folder_pk>/quyen/<int:pk>/', perm_views.permission_edit, name='permission_edit'),
    path('phan-quyen/thu-muc/<int:folder_pk>/quyen/<int:pk>/xoa/', perm_views.permission_delete, name='permission_delete'),
    path('phan-quyen/thu-muc/<int:pk>/ap-dung/', perm_views.apply_folder_acl, name='apply_folder_acl'),
    path('phan-quyen/truy-cap-rieng/', perm_views.special_access_list, name='special_access_list'),
    path('phan-quyen/truy-cap-rieng/ap-dung-tat-ca/', perm_views.apply_all_user_acl, name='apply_all_user_acl'),
    path('phan-quyen/truy-cap-rieng/acl/<int:pk>/ap-dung/', perm_views.apply_user_acl, name='apply_user_acl'),
    path('phan-quyen/truy-cap-rieng/<int:user_id>/', perm_views.special_access_edit, name='special_access_edit'),
]
