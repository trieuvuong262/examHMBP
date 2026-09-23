"""Người thân đi cùng trên một đăng ký, tối đa 3 người."""

from company_trip.models import TripRelative

MAX_RELATIVES = 3


def replace_registration_relatives(reg, people: list[dict]) -> None:
    TripRelative.objects.filter(registration=reg).delete()
    TripRelative.objects.bulk_create([
        TripRelative(
            registration=reg,
            position=index,
            full_name=person['full_name'],
            cccd=person['cccd'],
            phone=person['phone'],
            gender=person['gender'],
            date_of_birth=person['date_of_birth'],
        )
        for index, person in enumerate(people[:MAX_RELATIVES], start=1)
    ])
