from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0006_library_qa_chat_message'),
    ]

    operations = [
        migrations.AddField(
            model_name='document',
            name='original_file',
            field=models.FileField(
                blank=True,
                help_text='Bản gốc tuỳ chọn — nhân viên có thể xem (PDF) hoặc tải về.',
                null=True,
                upload_to='documents/originals/%Y/%m/',
                verbose_name='File gốc',
            ),
        ),
        migrations.AddField(
            model_name='document',
            name='original_filename',
            field=models.CharField(blank=True, max_length=255, verbose_name='Tên file gốc'),
        ),
    ]
