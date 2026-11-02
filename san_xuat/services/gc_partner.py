"""Đối tác gia công (GĐ1) — CRUD đối tác, tài khoản cổng pn, bảng giá GC."""

from __future__ import annotations

import re
import secrets
import string
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from san_xuat.partner_models import GcPartner, GcPartnerAccount, GcPriceRule


class GcPartnerError(Exception):
    pass


_USERNAME_RE = re.compile(r'^[a-z0-9._-]{3,60}$')


def generate_password(length: int = 10) -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        pwd = ''.join(secrets.choice(alphabet) for _ in range(length))
        if any(c.isdigit() for c in pwd) and any(c.isalpha() for c in pwd):
            return pwd


def normalize_username(raw: str) -> str:
    username = (raw or '').strip().lower()
    if not _USERNAME_RE.match(username):
        raise GcPartnerError('Tên đăng nhập 3–60 ký tự: chữ thường, số, dấu . _ -')
    return username


def active_partners():
    return GcPartner.objects.filter(is_active=True).order_by('name', 'code')


def partner_choices(*, team_slug: str = '', include_id: int | None = None) -> list[tuple[str, str]]:
    """Đối tác đang hợp tác; ưu tiên đối tác nhận công đoạn `team_slug`."""
    slug = (team_slug or '').strip().lower()
    qs = GcPartner.objects.filter(Q(is_active=True) | Q(pk=include_id or 0)).order_by('name', 'code')
    matched, others = [], []
    for p in qs:
        row = (str(p.pk), f'{p.name} ({p.code})')
        if slug and slug in (p.team_slugs or []):
            matched.append(row)
        else:
            others.append(row)
    return matched + others


# --- Tài khoản ---


@transaction.atomic
def create_partner_account(
    *, partner: GcPartner, username: str, full_name: str = '', phone: str = '',
    role: str = GcPartnerAccount.ROLE_STAFF, password: str = '', created_by=None,
) -> tuple[GcPartnerAccount, str]:
    username = normalize_username(username)
    if GcPartnerAccount.objects.filter(username=username).exists():
        raise GcPartnerError(f'Tên đăng nhập "{username}" đã tồn tại.')
    raw = (password or '').strip() or generate_password()
    if len(raw) < 8:
        raise GcPartnerError('Mật khẩu tối thiểu 8 ký tự.')
    acc = GcPartnerAccount(
        partner=partner,
        username=username,
        full_name=(full_name or '').strip(),
        phone=(phone or '').strip(),
        role=role if role in dict(GcPartnerAccount.ROLE_CHOICES) else GcPartnerAccount.ROLE_STAFF,
        must_change_password=True,
        created_by=created_by if getattr(created_by, 'pk', None) else None,
    )
    acc.set_password(raw)
    acc.save()
    return acc, raw


def reset_partner_password(account: GcPartnerAccount) -> str:
    raw = generate_password()
    account.set_password(raw)
    account.must_change_password = True
    account.failed_logins = 0
    account.locked_until = None
    account.save(update_fields=['password', 'must_change_password', 'failed_logins', 'locked_until'])
    return raw


def toggle_partner_account(account: GcPartnerAccount) -> bool:
    account.is_active = not account.is_active
    account.save(update_fields=['is_active'])
    return account.is_active


# --- Bảng giá ---


def validate_price_rule(rule: GcPriceRule) -> None:
    if rule.valid_to and rule.valid_to < rule.valid_from:
        raise GcPartnerError('Ngày kết thúc phải sau ngày bắt đầu hiệu lực.')
    overlap = GcPriceRule.objects.filter(
        partner_id=rule.partner_id,
        team_slug=rule.team_slug,
        product_code__iexact=rule.product_code or '',
        status=GcPriceRule.STATUS_APPROVED,
    ).exclude(pk=rule.pk or 0)
    end = rule.valid_to or date.max
    for other in overlap:
        other_end = other.valid_to or date.max
        if other.valid_from <= end and rule.valid_from <= other_end:
            raise GcPartnerError(
                f'Trùng hiệu lực với giá đã duyệt {other.unit_price:,.0f}đ '
                f'từ {other.valid_from:%d/%m/%Y}. Đặt "Đến ngày" cho giá cũ trước.'
            )


@transaction.atomic
def approve_price_rule(rule: GcPriceRule, *, user) -> GcPriceRule:
    rule = GcPriceRule.objects.select_for_update().get(pk=rule.pk)
    if rule.status == GcPriceRule.STATUS_APPROVED:
        return rule
    validate_price_rule(rule)
    rule.status = GcPriceRule.STATUS_APPROVED
    rule.approved_by = user if getattr(user, 'pk', None) else None
    rule.approved_at = timezone.now()
    rule.save(update_fields=['status', 'approved_by', 'approved_at'])
    return rule


def resolve_gc_price(
    *, partner_id: int | None, product_code: str, team_slug: str, on_date=None,
) -> GcPriceRule | None:
    """Giá đã duyệt hiệu lực tại ngày: ưu tiên giá theo mã SP, sau đó giá chung công đoạn."""
    if not partner_id:
        return None
    day = on_date or timezone.localdate()
    qs = GcPriceRule.objects.filter(
        partner_id=partner_id,
        team_slug=(team_slug or '').strip().lower(),
        status=GcPriceRule.STATUS_APPROVED,
        valid_from__lte=day,
    ).filter(Q(valid_to__isnull=True) | Q(valid_to__gte=day))
    code = (product_code or '').strip()
    if code:
        hit = qs.filter(product_code__iexact=code).order_by('-valid_from', '-pk').first()
        if hit:
            return hit
    return qs.filter(product_code='').order_by('-valid_from', '-pk').first()


def partner_stats(partner: GcPartner) -> dict:
    from django.db.models import Count, Sum

    from san_xuat.hub_models import SxSubcontractOrder

    qs = partner.subcontract_orders.exclude(status=SxSubcontractOrder.STATUS_CANCELLED)
    agg = qs.aggregate(
        n=Count('pk'),
        qty=Sum('qty'),
        received=Sum('qty_received'),
        fee=Sum('service_fee'),
    )
    open_n = qs.filter(
        status__in=[SxSubcontractOrder.STATUS_DRAFT, SxSubcontractOrder.STATUS_SENT],
    ).count()
    return {
        'orders': agg['n'] or 0,
        'open_orders': open_n,
        'qty': agg['qty'] or Decimal('0'),
        'received': agg['received'] or Decimal('0'),
        'fee': agg['fee'] or Decimal('0'),
    }
