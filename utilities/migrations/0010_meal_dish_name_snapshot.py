from datetime import date

from django.db import migrations, models


# Tên món theo audit (thiray đổi danh mục) — trước khi đổi tên lần sau.
NAMES_FOR_MEAL_DATE = {
    # Đặt tối 22 / ăn sáng 23
    date(2026, 7, 23): {
        1: 'Cá mó chiên',
        2: 'Cơm gà chiên nước mắm',
        3: 'Canh Xương khoai tây cà rốt',
        4: 'Đậu que xào thịt',
        5: 'Cơm chay',
    },
    # Đặt tối 23 / ăn sáng 24 (tên sau khi đổi chiều 23)
    date(2026, 7, 24): {
        1: 'Cá ngừ kho cà',
        2: 'Xíu mại',
        3: 'Canh Xương nấu cải chua',
        4: 'Thịt kho trứng cút',
        5: 'Cơm chay',
    },
}


def forwards(apps, schema_editor):
    MealOrder = apps.get_model('utilities', 'MealOrder')
    MealDayOffering = apps.get_model('utilities', 'MealDayOffering')
    MealDish = apps.get_model('utilities', 'MealDish')

    dish_names = dict(MealDish.objects.values_list('id', 'name'))

    for order in MealOrder.objects.all().iterator():
        mapped = NAMES_FOR_MEAL_DATE.get(order.meal_date, {}).get(order.dish_id)
        name = mapped or dish_names.get(order.dish_id) or ''
        if name and order.dish_name != name:
            MealOrder.objects.filter(pk=order.pk).update(dish_name=name)

    for row in MealDayOffering.objects.filter(is_offered=True).iterator():
        mapped = NAMES_FOR_MEAL_DATE.get(row.meal_date, {}).get(row.dish_id)
        name = mapped or dish_names.get(row.dish_id) or ''
        if name and row.dish_name != name:
            MealDayOffering.objects.filter(pk=row.pk).update(dish_name=name)


def backwards(apps, schema_editor):
    MealOrder = apps.get_model('utilities', 'MealOrder')
    MealDayOffering = apps.get_model('utilities', 'MealDayOffering')
    MealOrder.objects.all().update(dish_name='')
    MealDayOffering.objects.all().update(dish_name='')


class Migration(migrations.Migration):

    dependencies = [
        ('utilities', '0009_salary_advance_one_per_month'),
    ]

    operations = [
        migrations.AddField(
            model_name='mealdayoffering',
            name='dish_name',
            field=models.CharField(blank=True, max_length=120, verbose_name='Tên món (snapshot)'),
        ),
        migrations.AddField(
            model_name='mealorder',
            name='dish_name',
            field=models.CharField(blank=True, max_length=120, verbose_name='Tên món (snapshot)'),
        ),
        migrations.RunPython(forwards, backwards),
    ]
