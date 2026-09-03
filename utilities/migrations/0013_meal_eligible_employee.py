from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_employed_as_eligible(apps, schema_editor):
    MealEligibleEmployee = apps.get_model('utilities', 'MealEligibleEmployee')
    app_label, model_name = settings.AUTH_USER_MODEL.split('.')
    User = apps.get_model(app_label, model_name)
    ids = list(
        User.objects.filter(is_active=True, profile__is_employed=True).values_list('id', flat=True)
    )
    MealEligibleEmployee.objects.bulk_create(
        [MealEligibleEmployee(employee_id=pk) for pk in ids],
        ignore_conflicts=True,
    )


def unseed_eligible(apps, schema_editor):
    MealEligibleEmployee = apps.get_model('utilities', 'MealEligibleEmployee')
    MealEligibleEmployee.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0012_profile_is_employed'),
        ('utilities', '0012_salary_advance_open_times'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='MealEligibleEmployee',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('employee', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='meal_order_eligibility',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Nhân viên',
                )),
            ],
            options={
                'verbose_name': 'Người được đặt cơm',
                'verbose_name_plural': 'Người được đặt cơm',
                'ordering': ['employee__username'],
            },
        ),
        migrations.RunPython(seed_employed_as_eligible, unseed_eligible),
    ]
