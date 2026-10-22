"""Công thức phiếu lương. Không đọc database.

Một công tương đương 8 giờ. Lương theo công đã gồm phép có lương và không gồm
nghỉ không lương, nên số tiền nghỉ không lương chỉ để giải thích, không trừ thêm.
"""

from decimal import Decimal, ROUND_HALF_UP

MINUTES_PER_CREDIT = Decimal('480')
_DONG = Decimal('1')


def money(value) -> Decimal:
    return Decimal(value or 0).quantize(_DONG, rounding=ROUND_HALF_UP)


def build_slip(
    *,
    base,
    meal,
    transport,
    phone,
    standard,
    payable,
    unpaid,
    ot_parts,
    bonus,
    penalty,
    advance,
) -> dict:
    standard = Decimal(standard or 0)
    payable = Decimal(payable or 0)
    unpaid = Decimal(unpaid or 0)
    base = Decimal(base or 0)
    daily = (base / standard) if standard else Decimal('0')
    work_pay = money(daily * payable)
    unpaid_pay = money(daily * unpaid)
    ot_pay = Decimal('0')
    for minutes, rate in ot_parts:
        if not minutes or not rate or not daily:
            continue
        hourly = daily / Decimal('8')
        ot_pay += hourly * (Decimal(minutes) / Decimal('60')) * Decimal(rate)
    ot_pay = money(ot_pay)
    meal = money(meal)
    transport = money(transport)
    phone = money(phone)
    bonus = money(bonus)
    penalty = money(penalty)
    advance = money(advance)
    net = work_pay + meal + transport + phone + ot_pay + bonus - penalty - advance
    return {
        'work_pay': work_pay,
        'unpaid_pay': unpaid_pay,
        'ot_pay': ot_pay,
        'meal_allowance': meal,
        'transport_allowance': transport,
        'phone_allowance': phone,
        'bonus': bonus,
        'penalty': penalty,
        'advance': advance,
        'net_pay': money(net),
    }
