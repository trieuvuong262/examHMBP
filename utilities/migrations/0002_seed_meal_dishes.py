from django.db import migrations

DEFAULT_MEAL_DISHES = [
    'Cơm sườn nướng',
    'Cơm gà xối mỡ',
    'Cơm thịt kho tàu',
    'Cơm cá kho',
    'Cơm chả cá',
    'Cơm bò lúc lắc',
    'Cơm sườn bì chả',
    'Cơm gà kho',
    'Cơm cá chiên',
    'Cơm thịt nướng',
    'Cơm tam giác chả',
    'Cơm bún chả Hà Nội',
    'Cơm xá xíu',
    'Cơm heo quay',
    'Cơm cá thu sốt cà',
    'Cơm đậu phụ sốt cà',
    'Cơm trứng ốp la',
    'Cơm chay (đậu hũ + rau)',
    'Cơm gà rang muối',
    'Cơm sườn sụn rim',
]


def seed_meal_dishes(apps, schema_editor):
    MealDish = apps.get_model('utilities', 'MealDish')
    for idx, name in enumerate(DEFAULT_MEAL_DISHES, start=1):
        MealDish.objects.get_or_create(
            name=name,
            defaults={'sort_order': idx, 'is_active': True},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('utilities', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_meal_dishes, migrations.RunPython.noop),
    ]
