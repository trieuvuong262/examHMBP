from django.contrib.auth import get_user_model
from equipment.models import Device

User = get_user_model()
print("devices:", Device.objects.count())
print("assigned_user FK:", Device.objects.exclude(assigned_user=None).count())
print("assigned_text sample:", list(Device.objects.exclude(assigned_user_text="").values_list("assigned_user_text", flat=True)[:20]))
for u in User.objects.all()[:5]:
    from equipment.services.agent_install import user_is_in_equipment_registry, is_exempt_from_agent_gate
    print(u.username, "exempt=", is_exempt_from_agent_gate(u), "in_registry=", user_is_in_equipment_registry(u))
