from django.apps import AppConfig


class ThietKeSpConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'thiet_ke_sp'
    verbose_name = 'Thiết kế sản phẩm'

    def ready(self):
        from thiet_ke_sp.services.nas_layout import connect_signals

        connect_signals()
