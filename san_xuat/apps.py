from django.apps import AppConfig


class SanXuatConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'san_xuat'
    verbose_name = 'Tài liệu sản xuất'

    def ready(self):
        from san_xuat.services.route_sheet import connect_route_sheet_signals
        connect_route_sheet_signals()
