from utilities.models import MealPushSubscription
for row in MealPushSubscription.objects.all():
    print(row.pk, row.user_id, row.endpoint[:60], (row.user_agent or '')[:40])
