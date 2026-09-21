from django.urls import path, reverse
from django.views.generic import RedirectView

from . import views
from . import views_adjustment
from . import views_issue
from . import views_material
from . import views_print
from . import views_receipt
from . import views_reports
from . import views_settings
from . import views_disposal
from . import views_doc_attachment
from . import views_transfer
from . import views_supplier


class StockRedirectView(RedirectView):
    """Giữ namespace kho_npl / kho_vat_tu khi redirect bookmark cũ."""

    query_string = True

    def get_redirect_url(self, *args, **kwargs):
        name = self.pattern_name
        if name and name.startswith('kho_npl:'):
            ns = 'kho_npl'
            if self.request.resolver_match and self.request.resolver_match.namespace:
                ns = self.request.resolver_match.namespace
            name = f'{ns}:{name.split(":", 1)[1]}'
        url = reverse(name, args=args, kwargs=kwargs)
        if url and self.query_string:
            qs = self.request.META.get('QUERY_STRING', '')
            if qs:
                url = f'{url}&{qs}' if '?' in url else f'{url}?{qs}'
        return url


app_name = 'kho_npl'

urlpatterns = [
    path('', views.hub_redirect, name='hub'),
    path('tong-quan/', views.overview, name='overview'),
    path('tong-quan/xuat-excel/', views.overview_export, name='overview_export'),
    path('the-kho/', views.stock_cards, name='stock_cards'),
    path('canh-bao/', views.stock_alerts, name='stock_alerts'),
    path('danh-muc/', views_material.material_list, name='material_list'),
    path('danh-muc/xuat-excel/', views_material.material_export, name='material_export'),
    path('danh-muc/mau-excel/', views_material.material_import_template, name='material_import_template'),
    path('danh-muc/nhap-excel/', views_material.material_import, name='material_import'),
    path('ton-kho-npl/', StockRedirectView.as_view(pattern_name='kho_npl:material_stock', permanent=True)),
    path('ton-kho-npl/xuat-excel/', StockRedirectView.as_view(pattern_name='kho_npl:material_stock_export', permanent=True)),
    path('ton-kho-npl/<int:pk>/', StockRedirectView.as_view(pattern_name='kho_npl:material_stock_detail', permanent=True)),
    path('ton-kho/', views_material.material_stock_list, name='material_stock'),
    path('ton-kho/xuat-excel/', views_material.material_stock_export, name='material_stock_export'),
    path('ton-kho/<int:pk>/', views_material.material_stock_detail, name='material_stock_detail'),
    path('danh-muc/them/', views_material.material_create, name='material_create'),
    path('danh-muc/<int:pk>/', views_material.material_detail, name='material_detail'),
    path('danh-muc/<int:pk>/sua/', views_material.material_edit, name='material_edit'),
    path('danh-muc/<int:pk>/ngung/', views_material.material_deactivate, name='material_deactivate'),
    path('danh-muc/<int:pk>/xoa/', views_material.material_delete, name='material_delete'),
    path('api/tim-npl/', StockRedirectView.as_view(pattern_name='kho_npl:material_search', permanent=True)),
    path('api/tim-hang/', views_material.material_search, name='material_search'),
    path('api/tim-ma-sp/', views_issue.product_code_search, name='product_code_search'),
    path('api/tim-nhan-vien/', views_issue.recipient_search, name='recipient_search'),
    path('api/tim-ncc/', views_supplier.supplier_search, name='supplier_search'),
    path('api/them-ncc/', views_supplier.supplier_quick_create, name='supplier_quick_create'),
    path('api/ton-npl/', StockRedirectView.as_view(pattern_name='kho_npl:balance_lookup', permanent=True)),
    path('api/ton-kho/', views_material.balance_lookup, name='balance_lookup'),
    path('api/lo-hang/', views_material.batch_lookup, name='batch_lookup'),
    path('chung-tu-file/<int:pk>/xoa/', views_doc_attachment.doc_attachment_delete, name='doc_attachment_delete'),
    path('phieu-nhap/', views_receipt.receipt_list, name='receipt_list'),
    path('phieu-nhap/them/', views_receipt.receipt_create, name='receipt_create'),
    path('phieu-nhap/<int:pk>/', views_receipt.receipt_detail, name='receipt_detail'),
    path('phieu-nhap/<int:pk>/sua/', views_receipt.receipt_edit, name='receipt_edit'),
    path('phieu-nhap/<int:pk>/in/', views_print.print_receipt, name='receipt_print'),
    path('phieu-nhap/<int:pk>/ghi-chu/', views_receipt.receipt_update_notes, name='receipt_update_notes'),
    path('phieu-nhap/<int:pk>/ghi-chu-dong/', views_receipt.receipt_update_line_notes, name='receipt_update_line_notes'),
    path('phieu-nhap/<int:pk>/chung-tu/', views_receipt.receipt_replace_attachment, name='receipt_replace_attachment'),
    path('phieu-nhap/<int:pk>/ghi-so/', views_receipt.receipt_post, name='receipt_post'),
    path('phieu-nhap/<int:pk>/huy/', views_receipt.receipt_cancel, name='receipt_cancel'),
    path('phieu-xuat/', views_issue.issue_list, name='issue_list'),
    path('phieu-xuat/them/', views_issue.issue_create, name='issue_create'),
    path('phieu-xuat/<int:pk>/', views_issue.issue_detail, name='issue_detail'),
    path('phieu-xuat/<int:pk>/sua/', views_issue.issue_edit, name='issue_edit'),
    path('phieu-xuat/<int:pk>/in/', views_print.print_issue, name='issue_print'),
    path('phieu-xuat/<int:pk>/ghi-chu/', views_issue.issue_update_notes, name='issue_update_notes'),
    path('phieu-xuat/<int:pk>/ghi-chu-dong/', views_issue.issue_update_line_notes, name='issue_update_line_notes'),
    path('phieu-xuat/<int:pk>/chung-tu/', views_issue.issue_replace_attachment, name='issue_replace_attachment'),
    path('phieu-xuat/<int:pk>/ghi-so/', views_issue.issue_post, name='issue_post'),
    path('phieu-xuat/<int:pk>/huy/', views_issue.issue_cancel, name='issue_cancel'),
    path('chuyen-kho/', views_transfer.transfer_hub, name='transfer_hub'),
    path('chuyen-kho/them/', views_transfer.transfer_create, name='transfer_create'),
    path('chuyen-kho/<int:pk>/', views_transfer.transfer_detail, name='transfer_detail'),
    path('chuyen-kho/<int:pk>/sua/', views_transfer.transfer_edit, name='transfer_edit'),
    path('chuyen-kho/<int:pk>/in/', views_print.print_transfer, name='transfer_print'),
    path('chuyen-kho/<int:pk>/chung-tu/', views_transfer.transfer_replace_attachment, name='transfer_replace_attachment'),
    path('chuyen-kho/<int:pk>/gui/', views_transfer.transfer_send, name='transfer_send'),
    path('chuyen-kho/<int:pk>/nhan/', views_transfer.transfer_receive, name='transfer_receive'),
    path('chuyen-kho/<int:pk>/huy/', views_transfer.transfer_cancel, name='transfer_cancel'),
    path('phieu-huy/', views_disposal.disposal_list, name='disposal_list'),
    path('phieu-huy/them/', views_disposal.disposal_create, name='disposal_create'),
    path('phieu-huy/<int:pk>/', views_disposal.disposal_detail, name='disposal_detail'),
    path('phieu-huy/<int:pk>/sua/', views_disposal.disposal_edit, name='disposal_edit'),
    path('phieu-huy/<int:pk>/in/', views_print.print_disposal, name='disposal_print'),
    path('phieu-huy/<int:pk>/chung-tu/', views_disposal.disposal_replace_attachment, name='disposal_replace_attachment'),
    path('phieu-huy/<int:pk>/ghi-so/', views_disposal.disposal_post, name='disposal_post'),
    path('phieu-huy/<int:pk>/huy/', views_disposal.disposal_cancel, name='disposal_cancel'),
    # Phiếu kiểm kê (= StockAdjustment chọn lọc). Bookmark cũ /dieu-chinh/ → redirect.
    path('kiem-ke/', views_adjustment.adjustment_list, name='adjustment_list'),
    path('kiem-ke/them/', views_adjustment.adjustment_create, name='adjustment_create'),
    path('kiem-ke/<int:pk>/', views_adjustment.adjustment_detail, name='adjustment_detail'),
    path('kiem-ke/<int:pk>/in/', views_print.print_adjustment, name='adjustment_print'),
    path('kiem-ke/<int:pk>/chung-tu/', views_adjustment.adjustment_replace_attachment, name='adjustment_replace_attachment'),
    path('kiem-ke/<int:pk>/duyet/', views_adjustment.adjustment_approve, name='adjustment_approve'),
    path('kiem-ke/<int:pk>/tu-choi/', views_adjustment.adjustment_reject, name='adjustment_reject'),
    path('dieu-chinh/', StockRedirectView.as_view(pattern_name='kho_npl:adjustment_list', permanent=False)),
    path('dieu-chinh/them/', StockRedirectView.as_view(pattern_name='kho_npl:adjustment_create', permanent=False)),
    path('dieu-chinh/<int:pk>/', StockRedirectView.as_view(pattern_name='kho_npl:adjustment_detail', permanent=False)),
    path(
        'dieu-chinh/<int:pk>/chung-tu/',
        StockRedirectView.as_view(pattern_name='kho_npl:adjustment_replace_attachment', permanent=False),
    ),
    path('dieu-chinh/<int:pk>/duyet/', StockRedirectView.as_view(pattern_name='kho_npl:adjustment_approve', permanent=False)),
    path('dieu-chinh/<int:pk>/tu-choi/', StockRedirectView.as_view(pattern_name='kho_npl:adjustment_reject', permanent=False)),
    path('bao-cao/', views_reports.report_hub, name='report_hub'),
    path('bao-cao/xuat-excel/', views_reports.report_export, name='report_export'),
    path('bao-cao/ton-kho/', StockRedirectView.as_view(pattern_name='kho_npl:report_hub', permanent=False)),
    path('bao-cao/ton-kho/xuat-excel/', StockRedirectView.as_view(pattern_name='kho_npl:report_export', permanent=False)),
    path('bao-cao/can-bao/', StockRedirectView.as_view(pattern_name='kho_npl:report_hub', permanent=False)),
    path('bao-cao/can-bao/xuat-excel/', StockRedirectView.as_view(pattern_name='kho_npl:report_export', permanent=False)),
    path('bao-cao/bien-dong/', StockRedirectView.as_view(pattern_name='kho_npl:report_hub', permanent=False)),
    path('bao-cao/bien-dong/xuat-excel/', StockRedirectView.as_view(pattern_name='kho_npl:report_export', permanent=False)),
    path('bao-cao/xuat-lsx/', StockRedirectView.as_view(pattern_name='kho_npl:report_hub', permanent=False)),
    path('bao-cao/xuat-lsx/xuat-excel/', StockRedirectView.as_view(pattern_name='kho_npl:report_export', permanent=False)),
    path('bao-cao/kiem-ke/', StockRedirectView.as_view(pattern_name='kho_npl:report_hub', permanent=False)),
    path('bao-cao/kiem-ke/xuat-excel/', StockRedirectView.as_view(pattern_name='kho_npl:report_export', permanent=False)),
    path('bao-cao/so-kho/', StockRedirectView.as_view(pattern_name='kho_npl:report_hub', permanent=False)),
    path('bao-cao/so-kho/xuat-excel/', StockRedirectView.as_view(pattern_name='kho_npl:report_export', permanent=False)),
    path('thiet-lap/', views.settings_hub, name='settings_hub'),
    path('thiet-lap/<slug:section>/', views_settings.settings_list, name='settings_list'),
    path('thiet-lap/<slug:section>/them/', views_settings.settings_create, name='settings_create'),
    path('thiet-lap/<slug:section>/<int:pk>/sua/', views_settings.settings_edit, name='settings_edit'),
    path('thiet-lap/<slug:section>/<int:pk>/ngung/', views_settings.settings_deactivate, name='settings_deactivate'),
]
