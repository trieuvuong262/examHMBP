from django.apps import AppConfig


class NasStorageConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'nas_storage'
    verbose_name = 'Thư mục NAS'

    def ready(self):
        import nas_storage.signals  # noqa: F401
