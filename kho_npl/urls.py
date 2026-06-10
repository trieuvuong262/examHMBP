from django.urls import path

from . import views
from . import views_adjustment
from . import views_issue
from . import views_material
from . import views_receipt
from . import views_reports
from . import views_settings
from . import views_stocktake
from . import views_disposal
from . import views_transfer

app_name = 'kho_npl'

urlpatterns = [
    path('', views.hub_redirect, name='hub'),
    path('tong-quan/', views.overview, name='overview'),
    path('the-kho/', views.stock_cards, name='stock_cards'),
    path('canh-bao/', views.stock_alerts, name='stock_alerts'),
    path('danh-muc/', views_material.material_list, name='material_list'),
    path('danh-muc/xuat-excel/', views_material.material_export, name='material_export'),
    path('danh-muc/mau-excel/', views_material.material_import_template, name='material_import_template'),
    path('danh-muc/nhap-excel/', views_material.material_import, name='material_import'),
    path('ton-kho-npl/', views_material.material_stock_list, name='material_stock'),
    path('danh-muc/them/', views_material.material_create, name='material_create'),
    path('danh-muc/<int:pk>/', views_material.material_detail, name='material_detail'),
    path('danh-muc/<int:pk>/sua/', views_material.material_edit, name='material_edit'),
    path('danh-muc/<int:pk>/ngung/', views_material.material_deactivate, name='material_deactivate'),
    path('phieu-nhap/', views_receipt.receipt_list, name='receipt_list'),
    path('phieu-nhap/them/', views_receipt.receipt_create, name='receipt_create'),
    path('phieu-nhap/<int:pk>/', views_receipt.receipt_detail, name='receipt_detail'),
    path('phieu-nhap/<int:pk>/sua/', views_receipt.receipt_edit, name='receipt_edit'),
    path('phieu-nhap/<int:pk>/ghi-so/', views_receipt.receipt_post, name='receipt_post'),
    path('phieu-nhap/<int:pk>/huy/', views_receipt.receipt_cancel, name='receipt_cancel'),
    path('phieu-xuat/', views_issue.issue_list, name='issue_list'),
    path('phieu-xuat/them/', views_issue.issue_create, name='issue_create'),
    path('phieu-xuat/<int:pk>/', views_issue.issue_detail, name='issue_detail'),
    path('phieu-xuat/<int:pk>/sua/', views_issue.issue_edit, name='issue_edit'),
    path('phieu-xuat/<int:pk>/ghi-so/', views_issue.issue_post, name='issue_post'),
    path('phieu-xuat/<int:pk>/huy/', views_issue.issue_cancel, name='issue_cancel'),
    path('chuyen-kho/', views_transfer.transfer_hub, name='transfer_hub'),
    path('chuyen-kho/them/', views_transfer.transfer_create, name='transfer_create'),
    path('chuyen-kho/<int:pk>/', views_transfer.transfer_detail, name='transfer_detail'),
    path('chuyen-kho/<int:pk>/sua/', views_transfer.transfer_edit, name='transfer_edit'),
    path('chuyen-kho/<int:pk>/gui/', views_transfer.transfer_send, name='transfer_send'),
    path('chuyen-kho/<int:pk>/nhan/', views_transfer.transfer_receive, name='transfer_receive'),
    path('chuyen-kho/<int:pk>/huy/', views_transfer.transfer_cancel, name='transfer_cancel'),
    path('phieu-huy/', views_disposal.disposal_list, name='disposal_list'),
    path('phieu-huy/them/', views_disposal.disposal_create, name='disposal_create'),
    path('phieu-huy/<int:pk>/', views_disposal.disposal_detail, name='disposal_detail'),
    path('phieu-huy/<int:pk>/sua/', views_disposal.disposal_edit, name='disposal_edit'),
    path('phieu-huy/<int:pk>/ghi-so/', views_disposal.disposal_post, name='disposal_post'),
    path('phieu-huy/<int:pk>/huy/', views_disposal.disposal_cancel, name='disposal_cancel'),
    path('dieu-chinh/', views_adjustment.adjustment_list, name='adjustment_list'),
    path('dieu-chinh/them/', views_adjustment.adjustment_create, name='adjustment_create'),
    path('dieu-chinh/<int:pk>/', views_adjustment.adjustment_detail, name='adjustment_detail'),
    path('dieu-chinh/<int:pk>/duyet/', views_adjustment.adjustment_approve, name='adjustment_approve'),
    path('dieu-chinh/<int:pk>/tu-choi/', views_adjustment.adjustment_reject, name='adjustment_reject'),
    path('kiem-ke/', views_stocktake.stocktake_list, name='stocktake_list'),
    path('kiem-ke/them/', views_stocktake.stocktake_create, name='stocktake_create'),
    path('kiem-ke/<int:pk>/', views_stocktake.stocktake_detail, name='stocktake_detail'),
    path('kiem-ke/<int:pk>/bat-dau/', views_stocktake.stocktake_start, name='stocktake_start'),
    path('kiem-ke/<int:pk>/nhap-so/', views_stocktake.stocktake_count, name='stocktake_count'),
    path('kiem-ke/<int:pk>/tai-ton/', views_stocktake.stocktake_reload, name='stocktake_reload'),
    path('bao-cao/', views_reports.report_hub, name='report_hub'),
    path('bao-cao/ton-kho/', views_reports.report_stock, name='report_stock'),
    path('bao-cao/ton-kho/xuat-excel/', views_reports.report_stock_export, name='report_stock_export'),
    path('bao-cao/can-bao/', views_reports.report_alerts, name='report_alerts'),
    path('bao-cao/can-bao/xuat-excel/', views_reports.report_alerts_export, name='report_alerts_export'),
    path('bao-cao/bien-dong/', views_reports.report_movement, name='report_movement'),
    path('bao-cao/bien-dong/xuat-excel/', views_reports.report_movement_export, name='report_movement_export'),
    path('bao-cao/xuat-lsx/', views_reports.report_issue_lsx, name='report_issue_lsx'),
    path('bao-cao/xuat-lsx/xuat-excel/', views_reports.report_issue_lsx_export, name='report_issue_lsx_export'),
    path('bao-cao/kiem-ke/', views_reports.report_stocktake_history, name='report_stocktake_history'),
    path('bao-cao/kiem-ke/xuat-excel/', views_reports.report_stocktake_history_export, name='report_stocktake_history_export'),
    path('bao-cao/so-kho/', views_reports.report_ledger, name='report_ledger'),
    path('bao-cao/so-kho/xuat-excel/', views_reports.report_ledger_export, name='report_ledger_export'),
    path('thiet-lap/', views.settings_hub, name='settings_hub'),
    path('thiet-lap/<slug:section>/', views_settings.settings_list, name='settings_list'),
    path('thiet-lap/<slug:section>/them/', views_settings.settings_create, name='settings_create'),
    path('thiet-lap/<slug:section>/<int:pk>/sua/', views_settings.settings_edit, name='settings_edit'),
    path('thiet-lap/<slug:section>/<int:pk>/ngung/', views_settings.settings_deactivate, name='settings_deactivate'),
]
