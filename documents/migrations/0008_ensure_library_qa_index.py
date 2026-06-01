"""Đảm bảo index lịch sử Hỏi đáp AI tồn tại — sửa DB prod bị lệch migration."""

from django.db import migrations


def ensure_qa_chat_index(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT to_regclass('public.documents_libraryqachatmessage')"
        )
        if not cursor.fetchone()[0]:
            return
        cursor.execute(
            """
            SELECT 1 FROM pg_indexes
            WHERE schemaname = 'public'
              AND indexname = 'documents_l_user_id_6a8f2d_idx'
            """
        )
        if cursor.fetchone():
            return
        cursor.execute(
            """
            CREATE INDEX documents_l_user_id_6a8f2d_idx
            ON documents_libraryqachatmessage (user_id, created_at)
            """
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0007_document_original_file'),
    ]

    operations = [
        migrations.RunPython(ensure_qa_chat_index, noop),
    ]
