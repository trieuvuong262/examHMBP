from django.urls import path
from django.views.generic import RedirectView

from equipment import views_inventory_scan
from audit import views_rustdesk_setup
from . import views, views_nas_download

app_name = 'documents'

urlpatterns = [
    path('admin/', views.admin_hub, name='admin_hub'),
    path('admin/categories/', views.admin_category_list, name='admin_categories'),
    path('admin/categories/add/', views.admin_category_create, name='admin_category_create'),
    path('admin/categories/<int:pk>/edit/', views.admin_category_edit, name='admin_category_edit'),
    path('admin/categories/<int:pk>/delete/', views.admin_category_delete, name='admin_category_delete'),
    path('admin/documents/', views.admin_document_list, name='admin_documents'),
    path('admin/documents/add/', views.admin_document_create, name='admin_document_create'),
    path('admin/documents/<int:pk>/edit/', views.admin_document_edit, name='admin_document_edit'),
    path('admin/documents/<int:pk>/delete/', views.admin_document_delete, name='admin_document_delete'),
    path(
        'admin/hoi-dap/',
        RedirectView.as_view(pattern_name='audit:qa_assistant', permanent=True),
        name='admin_qa_settings',
    ),
    path('hoi-dap/', views.qa_chat, name='qa'),
    path('hoi-dap/suggest/', views.qa_suggest_initial, name='qa_suggest_initial'),
    path('hoi-dap/ask/', views.qa_ask, name='qa_ask'),
    path('cau-hinh-rustdesk/tai/', views_rustdesk_setup.rustdesk_download_setup, name='rustdesk_download'),
    path('cau-hinh-rustdesk/', views_rustdesk_setup.rustdesk_install_page, name='rustdesk_config'),
    path('tai-nas/tai/', views_nas_download.nas_download_setup, name='nas_download_setup'),
    path('tai-nas/', views_nas_download.nas_download_page, name='nas_download'),
    path('quet-thiet-bi/tai/', views_inventory_scan.equipment_scan_download, name='equipment_scan_download'),
    path('quet-thiet-bi/', views_inventory_scan.equipment_scan_page, name='equipment_scan_config'),
    path('file/<int:pk>/xem/', views.document_file_view, name='file_view'),
    path('file/<int:pk>/tai/', views.document_file_download, name='file_download'),
    path('', views.browse, name='browse'),
    path('<slug:category_slug>/', views.browse, name='browse_category'),
    path('<slug:category_slug>/<slug:doc_slug>/', views.browse, name='browse_document'),
]
