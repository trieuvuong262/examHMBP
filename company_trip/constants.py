"""Company Trip 2026 — Vĩnh Hy."""

from datetime import date

TRIP_YEAR = 2026
TRIP_TITLE = 'Company Trip 2026 — Vĩnh Hy'
TRIP_DESTINATION = 'Vịnh Vĩnh Hy'
TRIP_START = date(2026, 11, 22)
TRIP_END = date(2026, 11, 23)
TRIP_DATES_DISPLAY = '22–23/11/2026'
DEFAULT_PICKUP_POINT = '19 Chiến Lược'

ROOM_ORGANIZER = 'Ban tổ chức tự sắp xếp'
ROOM_RELATIVE = 'Đăng ký chung với người thân'
ROOM_COLLEAGUE = 'Đăng ký với đồng nghiệp'
ROOM_CHOICES = [
    (ROOM_ORGANIZER, ROOM_ORGANIZER),
    (ROOM_RELATIVE, ROOM_RELATIVE),
    (ROOM_COLLEAGUE, ROOM_COLLEAGUE),
]

VEGETARIAN_CHOICES = [
    ('Ăn chay', 'Ăn chay'),
    ('Không ăn chay', 'Không ăn chay'),
]

BREAKFAST_CHOICES = [
    ('Bánh canh', 'Bánh canh'),
    ('Mì gói', 'Mì gói'),
    ('Bún bò', 'Bún bò'),
    ('Bánh mì ốp-la', 'Bánh mì ốp-la'),
    ('Không ăn sáng', 'Không ăn sáng'),
]

ROUTE_CHOICES = [
    ('Tham quan Vịnh Vĩnh Hy', 'Tham quan Vịnh Vĩnh Hy'),
    ('Tham quan Hang Rái', 'Tham quan Hang Rái'),
    ('Tham quan Vịnh Vĩnh Hy - Tham quan Hang Rái', 'Tham quan Vịnh Vĩnh Hy - Tham quan Hang Rái'),
    (
        'Không tham quan - Đợi tại vườn nho hoặc nhà hàng bến tàu',
        'Không tham quan - Đợi tại vườn nho hoặc nhà hàng bến tàu',
    ),
]

SHOPPING_CHOICES = [
    ('Tham gia', 'Tham gia'),
    ('Không tham gia', 'Không tham gia'),
]

STATUS_REGISTERED = 'registered'
STATUS_CANCELLED = 'cancelled'
STATUS_CHOICES = [
    (STATUS_REGISTERED, 'Đã đăng ký'),
    (STATUS_CANCELLED, 'Đã hủy'),
]
