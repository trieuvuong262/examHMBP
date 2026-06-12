import os
import sys
import threading

from django.apps import AppConfig


def _should_warm_background_removal() -> bool:
    argv = sys.argv
    if len(argv) > 1 and argv[1] in {
        'test',
        'migrate',
        'makemigrations',
        'shell',
        'collectstatic',
        'check',
        'warm_remove_bg',
    }:
        return False
    if os.environ.get('DISABLE_RMBG_WARM') == '1':
        return False
    return True


class ToolsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tools'
    verbose_name = 'Công cụ'

    def ready(self):
        if not _should_warm_background_removal():
            return

        def _warm():
            try:
                from tools.services import warm_background_removal
                warm_background_removal()
            except Exception:
                # Worker vẫn chạy; request đầu sẽ thử lại tải mô hình.
                pass

        threading.Thread(target=_warm, daemon=True, name='rmbg-warm').start()
