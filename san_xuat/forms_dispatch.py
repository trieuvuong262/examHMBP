from __future__ import annotations

from decimal import Decimal

from django import forms
from django.forms import formset_factory

_SELECT_SM = {"class": "form-select form-select-sm"}
_INPUT_SM = {"class": "form-control form-control-sm"}
_DATE_SM = {"class": "form-control form-control-sm jp-date-vn", "type": "date"}
_PRODUCT_CODE_SELECT = {
    "class": "form-select form-select-sm jp-sx-product-code-select",
    "data-placeholder": "Gõ mã SX hoặc tên sản phẩm…",
}


def _product_code_choices(extra_value: str = "") -> list[tuple[str, str]]:
    """Choices TomSelect — chọn mã SX gốc từ kho SP."""
    choices: list[tuple[str, str]] = [("", "— Chọn mã SX (kho SP) —")]
    code = (extra_value or "").strip()
    if not code:
        return choices
    from san_xuat.services.products import resolve_product_ref

    ref = resolve_product_ref(code)
    label_code = ref.code if ref else code
    label = f"{label_code} — {ref.name}" if ref and ref.name else label_code
    choices.append((label_code, label))
    return choices


def _bom_version_choices(product_code: str = "") -> list[tuple[str, str]]:
    """Các hồ sơ thiết kế (BOM version) của mã SX — dùng để gắn LSX + lấy tổ/công đoạn."""
    choices: list[tuple[str, str]] = [("", "— Chọn hồ sơ thiết kế —")]
    code = (product_code or "").strip()
    if not code:
        return choices
    from san_xuat.models import ProductTechDoc

    doc = ProductTechDoc.objects.filter(product_code__iexact=code).first()
    if not doc:
        return choices
    for bom in doc.bom_versions.prefetch_related("process_steps").order_by("created_at", "id"):
        n_steps = bom.process_steps.count()
        note = (bom.notes or "").strip()
        label = bom.version_label or f"#{bom.pk}"
        if n_steps:
            label = f"{label} · {n_steps} công đoạn"
        if note:
            label = f"{label} — {note[:40]}"
        choices.append((str(bom.pk), label))
    return choices


def _process_defaults_from_bom(bom) -> tuple[str, str]:
    """(team_label, process_name) từ công đoạn đầu của hồ sơ/BOM."""
    if bom is None:
        return "", ""
    step = (
        bom.process_steps.select_related("work_center")
        .order_by("sequence", "id")
        .first()
    )
    if not step:
        return "", ""
    process_name = (step.process_name or "").strip()
    team = ""
    wc = step.work_center
    if wc:
        team = (wc.team_label or wc.name or "").strip()
    return team, process_name


def work_center_team_choices(*, extra_value: str = "") -> list[tuple[str, str]]:
    """Choices tổ/chuyền = bộ phận HR phòng SẢN XUẤT (HRD-*)."""
    from san_xuat.services.capacity_from_hrm import hr_work_centers_qs

    choices: list[tuple[str, str]] = [("", "— Chọn tổ / chuyền —")]
    seen: set[str] = set()
    for center in hr_work_centers_qs():
        value = (center.team_label or center.name or "").strip()
        if not value or value.casefold() in seen:
            continue
        seen.add(value.casefold())
        label = center.name if center.name != value else value
        if center.name and center.name != value:
            label = f"{center.name}"
        choices.append((value, label))
    extra = (extra_value or "").strip()
    if extra and extra.casefold() not in seen:
        choices.append((extra, f"{extra} (đang dùng)"))
    return choices


def mo_manager_candidate_options() -> list[dict]:
    """User picker options: tổ trưởng / trưởng bộ phận / trưởng phòng / giám đốc.

    Không gồm tài khoản admin / superuser.
    """
    from django.contrib.auth import get_user_model
    from django.db.models import Q

    from hrm.permissions import MANAGER_ROLES

    User = get_user_model()
    qs = (
        User.objects.filter(
            is_active=True,
            profile__role__in=MANAGER_ROLES,
        )
        .exclude(Q(is_superuser=True) | Q(username__iexact="admin"))
        .select_related("profile")
        .order_by("profile__full_name", "username")[:400]
    )
    rows: list[dict] = []
    for u in qs:
        if getattr(u, "is_superuser", False):
            continue
        if (u.username or "").strip().casefold() == "admin":
            continue
        profile = getattr(u, "profile", None)
        if profile is not None and hasattr(profile, "is_employed") and not profile.is_employed:
            continue
        label = ""
        if profile is not None:
            label = (getattr(profile, "full_name", None) or "").strip()
        if not label:
            label = (u.get_full_name() or "").strip() or u.username
        role = ""
        if profile is not None:
            getter = getattr(profile, "get_role_display", None)
            if callable(getter):
                role = getter() or ""
            else:
                role = getattr(profile, "role", "") or ""
        rows.append({"id": u.pk, "label": label, "role": role})
    return rows


def bom_process_choices(bom, *, extra_value: str = "") -> list[tuple[str, str]]:
    """Choices công đoạn từ danh mục chung (+ giá trị đang dùng).

    `bom` giữ tham số để tương thích chỗ gọi cũ; danh mục không phụ thuộc BOM.
    """
    from san_xuat.services.process_catalog import process_catalog_choices

    _ = bom
    return process_catalog_choices(extra_value=extra_value)


def _clean_standard_process_name(raw_name: str) -> str:
    from san_xuat.services.process_catalog import resolve_standard_process_name

    name = (raw_name or "").strip()
    if not name:
        return ""
    standard = resolve_standard_process_name(name)
    if not standard:
        raise forms.ValidationError("Công đoạn phải chọn từ thư viện chuẩn Công đoạn / IE.")
    return standard


class ProductionOrderCreateForm(forms.Form):
    product_code = forms.ChoiceField(
        label="Mã SX",
        choices=[],
        widget=forms.Select(attrs=_PRODUCT_CODE_SELECT),
    )
    code = forms.CharField(
        max_length=100,
        required=False,
        label="Mã lệnh sản xuất",
        widget=forms.TextInput(attrs={
            **_INPUT_SM,
            "disabled": True,
            "placeholder": "Tự sinh sau khi chọn mã SX",
        }),
    )
    bom_version = forms.ChoiceField(
        required=False,
        label="Hồ sơ thiết kế",
        choices=[],
        widget=forms.Select(attrs={
            **_SELECT_SM,
            "id": "id_bom_version",
            "class": f"{_SELECT_SM['class']} jp-mo-bom-version",
        }),
    )
    qty = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=False,
        widget=forms.NumberInput(attrs={
            **_INPUT_SM,
            "step": "0.01",
            "min": "0.01",
            "class": f"{_INPUT_SM['class']} jp-mo-qty-total",
        }),
        label="Số lượng tổng",
    )
    order_date = forms.DateField(
        label="Ngày lập",
        widget=forms.DateInput(attrs=_DATE_SM),
    )
    due_date = forms.DateField(
        required=False,
        label="Hạn",
        widget=forms.DateInput(attrs=_DATE_SM),
    )
    planned_start = forms.DateField(
        required=False,
        label="Bắt đầu dự kiến",
        widget=forms.DateInput(attrs=_DATE_SM),
    )
    planned_end = forms.DateField(
        required=False,
        label="Kết thúc dự kiến",
        widget=forms.DateInput(attrs=_DATE_SM),
    )
    team_label = forms.ChoiceField(
        required=False,
        label="Tổ / chuyền",
        choices=[],
        widget=forms.Select(attrs=_SELECT_SM),
    )
    process_name = forms.ChoiceField(
        required=False,
        label="Công đoạn",
        choices=[],
        widget=forms.Select(attrs={
            **_SELECT_SM,
            "class": f"{_SELECT_SM['class']} jp-sx-process-select",
        }),
    )
    notes = forms.CharField(
        required=False,
        label="Ghi chú",
        widget=forms.Textarea(attrs={**_INPUT_SM, "rows": 3}),
    )
    is_sample = forms.BooleanField(
        required=False,
        label="Lệnh sản xuất mẫu",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, bom=None, **kwargs):
        super().__init__(*args, **kwargs)
        data = args[0] if args else None
        extra_team = ""
        extra_process = ""
        extra_product = ""
        if data is not None:
            extra_team = data.get("team_label") or ""
            extra_process = data.get("process_name") or ""
            extra_product = data.get("product_code") or ""
        elif self.initial:
            extra_team = self.initial.get("team_label") or ""
            extra_process = self.initial.get("process_name") or ""
            extra_product = self.initial.get("product_code") or ""
        if bom is None and extra_product:
            from san_xuat.models import ProductTechDoc
            from san_xuat.services.bom import get_working_bom

            tech = ProductTechDoc.objects.filter(product_code__iexact=extra_product.strip()).first()
            if tech:
                bom = get_working_bom(tech)
        self.fields["product_code"].choices = _product_code_choices(extra_product)
        self.fields["team_label"].choices = work_center_team_choices(extra_value=extra_team)
        self.fields["process_name"].choices = bom_process_choices(bom, extra_value=extra_process)
        self.fields["bom_version"].choices = _bom_version_choices(extra_product)

    def clean_product_code(self):
        code = (self.cleaned_data.get("product_code") or "").strip()
        if not code:
            raise forms.ValidationError("Chọn mã sản phẩm từ kho sản phẩm.")
        from san_xuat.models import ProductTechDoc
        from san_xuat.services.products import resolve_product_ref

        ref = resolve_product_ref(code)
        if not ref:
            raise forms.ValidationError(f"Mã {code} không có trong kho sản phẩm.")
        # Giữ mã hồ sơ đã có (tương thích hồ sơ cũ neo mã KV)
        for candidate in (code, ref.code):
            existing = (
                ProductTechDoc.objects.filter(product_code__iexact=candidate)
                .values_list("product_code", flat=True)
                .first()
            )
            if existing:
                return existing
        return ref.code

    def clean_bom_version(self):
        raw = (self.cleaned_data.get("bom_version") or "").strip()
        if not raw:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            raise forms.ValidationError("Hồ sơ thiết kế không hợp lệ.")

    def clean_process_name(self):
        return _clean_standard_process_name(self.cleaned_data.get("process_name"))

    def clean(self):
        cleaned = super().clean()
        return cleaned


class ProductionOrderUpdateForm(forms.Form):
    qty = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=False,
        widget=forms.NumberInput(attrs={
            **_INPUT_SM,
            "step": "0.01",
            "min": "0.01",
            "class": f"{_INPUT_SM['class']} jp-mo-qty-total",
        }),
        label="Số lượng tổng",
    )
    due_date = forms.DateField(
        required=False,
        label="Hạn",
        widget=forms.DateInput(attrs=_DATE_SM),
    )
    planned_start = forms.DateField(
        required=False,
        label="Bắt đầu dự kiến",
        widget=forms.DateInput(attrs=_DATE_SM),
    )
    planned_end = forms.DateField(
        required=False,
        label="Kết thúc dự kiến",
        widget=forms.DateInput(attrs=_DATE_SM),
    )
    team_label = forms.ChoiceField(
        required=False,
        label="Tổ / chuyền",
        choices=[],
        widget=forms.Select(attrs=_SELECT_SM),
    )
    process_name = forms.ChoiceField(
        required=False,
        label="Công đoạn",
        choices=[],
        widget=forms.Select(attrs={
            **_SELECT_SM,
            "class": f"{_SELECT_SM['class']} jp-sx-process-select",
        }),
    )
    notes = forms.CharField(
        required=False,
        label="Ghi chú",
        widget=forms.TextInput(attrs={
            **_INPUT_SM,
            "placeholder": "Ghi chú (tuỳ chọn)",
        }),
    )

    def __init__(self, *args, bom=None, **kwargs):
        super().__init__(*args, **kwargs)
        data = args[0] if args else None
        extra_team = ""
        extra_process = ""
        if data is not None:
            extra_team = data.get("team_label") or ""
            extra_process = data.get("process_name") or ""
        elif self.initial:
            extra_team = self.initial.get("team_label") or ""
            extra_process = self.initial.get("process_name") or ""
        self.fields["team_label"].choices = work_center_team_choices(extra_value=extra_team)
        self.fields["process_name"].choices = bom_process_choices(bom, extra_value=extra_process)

    def clean_process_name(self):
        return _clean_standard_process_name(self.cleaned_data.get("process_name"))


class MaterialIssueApproveForm(forms.Form):
    attachment = forms.FileField(
        required=False,
        label="Chứng từ (tuỳ chọn)",
        widget=forms.ClearableFileInput(attrs={
            "class": "form-control form-control-sm",
            "accept": "image/*,.pdf,.doc,.docx,.xls,.xlsx",
        }),
    )


class ProductionStatCreateForm(forms.Form):
    code = forms.CharField(
        max_length=40,
        required=False,
        label="Mã thống kê sản xuất",
        help_text="Để trống thì hệ thống tự sinh mã.",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    stat_date = forms.DateField(
        label="Ngày ghi nhận",
        widget=forms.DateInput(attrs=_DATE_SM),
    )
    process_name = forms.ChoiceField(
        required=False,
        label="Công đoạn",
        choices=[],
        widget=forms.Select(attrs={
            "class": "form-select form-select-sm jp-sx-process-select",
        }),
    )
    qty_good = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0"),
        label="Số lượng đạt",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.01", "min": "0"}),
    )
    qty_defect = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0"),
        label="Số lượng lỗi",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.01", "min": "0"}),
    )
    team_label = forms.ChoiceField(
        required=False,
        label="Tổ / chuyền",
        choices=[],
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    size_label = forms.ChoiceField(
        required=False,
        label="Size",
        choices=[],
        widget=forms.Select(attrs={"class": "form-select form-select-sm jp-sx-size-select"}),
    )
    color_code = forms.ChoiceField(
        required=False,
        label="Màu",
        choices=[],
        widget=forms.Select(attrs={"class": "form-select form-select-sm jp-sx-color-select"}),
    )
    sku_code = forms.CharField(
        required=False,
        label="SKU",
        help_text="Tự ghép Mã SX–Màu–Size (vd. JP-TEE-260001-NVY-M). Có thể sửa tay.",
        widget=forms.TextInput(attrs={
            "class": "form-control form-control-sm jp-sx-sku-code",
            "placeholder": "STYLE-COLOR-SIZE",
            "readonly": True,
        }),
    )
    color_label = forms.CharField(
        required=False,
        label="Tên màu (snapshot)",
        widget=forms.HiddenInput(),
    )
    notes = forms.CharField(
        required=False,
        label="Ghi chú",
        widget=forms.TextInput(attrs={
            "class": "form-control form-control-sm",
            "placeholder": "Ghi chú (tuỳ chọn)",
        }),
    )

    def __init__(self, *args, mo=None, mo_step=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from san_xuat.services.sku_catalog import color_choices, size_choices

        data = args[0] if args else None
        extra_process = ""
        extra_team = ""
        extra_color = ""
        extra_size = ""
        if data is not None:
            extra_process = data.get("process_name") or ""
            extra_team = data.get("team_label") or ""
            extra_color = data.get("color_code") or ""
            extra_size = data.get("size_label") or ""
        elif self.initial:
            extra_process = self.initial.get("process_name") or ""
            extra_team = self.initial.get("team_label") or ""
            extra_color = self.initial.get("color_code") or ""
            extra_size = self.initial.get("size_label") or ""

        bom = getattr(mo, "bom_version", None) if mo is not None else None

        # Công đoạn: nếu vào từ bước LSX hoặc user thường → chỉ bước được phân
        process_choices = None
        if mo_step is not None:
            process_choices = [
                ("", "— Chọn công đoạn —"),
                (mo_step.process_name, mo_step.process_name),
            ]
            self.fields["process_name"].widget.attrs["readonly"] = True
            self.fields["process_name"].disabled = False
        elif mo is not None and user is not None and not getattr(user, "is_superuser", False):
            from san_xuat.hub_models import SxMoProcessStep

            allowed = (
                SxMoProcessStep.objects.filter(production_order=mo, assignees__user=user)
                .order_by("sequence", "id")
                .distinct()
            )
            process_choices = [("", "— Chọn công đoạn —")] + [
                (s.process_name, s.process_name) for s in allowed
            ]
            if extra_process and extra_process not in {v for v, _ in process_choices}:
                process_choices.append((extra_process, f"{extra_process} (đang dùng)"))

        if process_choices is not None:
            self.fields["process_name"].choices = process_choices
        else:
            self.fields["process_name"].choices = bom_process_choices(bom, extra_value=extra_process)

        self.fields["team_label"].choices = work_center_team_choices(extra_value=extra_team)
        if mo_step is not None and mo_step.team_label:
            # Khóa tổ theo bước
            team = mo_step.team_label
            self.fields["team_label"].choices = work_center_team_choices(extra_value=team)

        mo_color_choices: list[tuple[str, str]] | None = None
        mo_size_choices: list[tuple[str, str]] | None = None
        if mo is not None:
            lines = list(mo.lines.all())
            if lines:
                colors: dict[str, str] = {}
                sizes: list[str] = []
                seen_sizes: set[str] = set()
                for ln in lines:
                    c = (ln.color_code or "").strip().upper()
                    if c and c not in colors:
                        colors[c] = (ln.color_label or c).strip() or c
                    s = (ln.size_label or "").strip().upper()
                    if s and s not in seen_sizes:
                        seen_sizes.add(s)
                        sizes.append(s)
                mo_color_choices = [("", "— Chọn màu —")] + [
                    (code, f"{code} — {name}" if name and name != code else code)
                    for code, name in colors.items()
                ]
                mo_size_choices = [("", "— Chọn size —")] + [(s, s) for s in sizes]
                extra_c = (extra_color or "").strip().upper()
                if extra_c and extra_c not in colors:
                    mo_color_choices.append((extra_c, f"{extra_c} (đang dùng)"))
                extra_s = (extra_size or "").strip().upper()
                if extra_s and extra_s not in seen_sizes:
                    mo_size_choices.append((extra_s, f"{extra_s} (đang dùng)"))

        self.fields["color_code"].choices = mo_color_choices or color_choices(extra_code=extra_color)
        self.fields["size_label"].choices = mo_size_choices or size_choices(extra_code=extra_size)

    def clean_process_name(self):
        return _clean_standard_process_name(self.cleaned_data.get("process_name"))

    def clean(self):
        cleaned = super().clean()
        qty_good = cleaned.get("qty_good") or Decimal("0")
        qty_defect = cleaned.get("qty_defect") or Decimal("0")
        if qty_good <= 0 and qty_defect <= 0:
            raise forms.ValidationError("Phải nhập ít nhất Số lượng đạt hoặc Số lượng lỗi lớn hơn 0.")
        from san_xuat.services.sku_catalog import color_label_for

        color_code = (cleaned.get("color_code") or "").strip()
        if color_code and not cleaned.get("color_label"):
            cleaned["color_label"] = color_label_for(color_code)
        return cleaned


def production_stat_initial_from_mo(mo) -> dict:
    """Giá trị mặc định form TKSX khi mở từ LSX (?mo=)."""
    from django.utils import timezone

    initial: dict = {"stat_date": timezone.localdate(), "qty_good": Decimal("0"), "qty_defect": Decimal("0")}
    if mo is None:
        return initial

    team = (mo.team_label or "").strip()
    process = (mo.process_name or "").strip()
    if not team or not process:
        t2, p2 = _process_defaults_from_bom(getattr(mo, "bom_version", None))
        team = team or t2
        process = process or p2
    if team:
        initial["team_label"] = team
    if process:
        initial["process_name"] = process

    remaining = (mo.qty or Decimal("0")) - (mo.qty_done or Decimal("0"))
    if remaining < 0:
        remaining = Decimal("0")

    lines = list(mo.lines.all())
    if len(lines) == 1:
        ln = lines[0]
        if (ln.color_code or "").strip():
            initial["color_code"] = (ln.color_code or "").strip().upper()
            initial["color_label"] = (ln.color_label or "").strip()
        if (ln.size_label or "").strip():
            initial["size_label"] = (ln.size_label or "").strip().upper()
        if (ln.sku_code or "").strip():
            initial["sku_code"] = (ln.sku_code or "").strip().upper()
        initial["qty_good"] = ln.qty or remaining
    elif lines:
        colors = {
            (ln.color_code or "").strip().upper()
            for ln in lines
            if (ln.color_code or "").strip()
        }
        sizes = {
            (ln.size_label or "").strip().upper()
            for ln in lines
            if (ln.size_label or "").strip()
        }
        if len(colors) == 1:
            code = next(iter(colors))
            initial["color_code"] = code
            for ln in lines:
                if (ln.color_code or "").strip().upper() == code:
                    initial["color_label"] = (ln.color_label or "").strip()
                    break
        if len(sizes) == 1:
            initial["size_label"] = next(iter(sizes))
        # Nhiều SKU: không điền sẵn SL tổng — user chọn màu/size rồi nhập SL
        initial["qty_good"] = Decimal("0")
    else:
        initial["qty_good"] = remaining if remaining > 0 else (mo.qty or Decimal("0"))

    return initial


def fg_warehouse_choices(*, extra_value: str = "") -> list[tuple[str, str]]:
    """Kho nhập thành phẩm: chi nhánh KiotViet, không có thì vị trí kho portal."""
    choices: list[tuple[str, str]] = [("", "— Chọn kho nhập —")]
    seen: set[str] = set()

    def _add(value: str, label: str) -> None:
        if not value or value in seen:
            return
        seen.add(value)
        choices.append((value, label))

    try:
        from kiotviet.models import KvBranch
        from kiotviet.sync_service import current_retailer

        qs = KvBranch.objects.filter(is_deleted=False)
        retailer = current_retailer()
        if retailer is not None:
            qs = qs.filter(retailer=retailer)
        for branch in qs.order_by("branch_name", "branch_code"):
            label = (branch.branch_name or branch.branch_code or "").strip() or f"Kho #{branch.pk}"
            _add(f"kv:{branch.pk}", label)
    except Exception:
        pass
    if len(choices) == 1:
        try:
            from kho_npl.models import WarehouseLocation

            for loc in WarehouseLocation.objects.filter(is_active=True).order_by("code"):
                _add(f"loc:{loc.pk}", loc.display_label())
        except Exception:
            pass
    extra = (extra_value or "").strip()
    if extra and extra not in seen:
        _add(extra, extra)
    return choices


class FgReceiptCreateForm(forms.Form):
    production_order = forms.ModelChoiceField(
        queryset=None,
        label="Lệnh sản xuất nguồn",
        widget=forms.Select(attrs=_SELECT_SM),
    )
    received_by = forms.ModelChoiceField(
        queryset=None,
        label="Người nhập",
        widget=forms.Select(attrs={
            "class": "form-select form-select-sm jp-sx-employee-select",
            "data-placeholder": "Gõ tên hoặc mã nhân viên…",
            "data-browse-on-open": "1",
        }),
    )
    warehouse_code = forms.ChoiceField(
        label="Kho nhập",
        choices=[],
        widget=forms.Select(attrs=_SELECT_SM),
    )
    product_code = forms.CharField(
        required=False,
        label="Mã sản phẩm",
        widget=forms.TextInput(attrs={
            **_INPUT_SM,
            "class": "form-control-plaintext form-control-sm px-0",
            "readonly": True,
            "tabindex": "-1",
            "placeholder": "Tự điền khi chọn lệnh",
        }),
    )
    product_name = forms.CharField(
        required=False,
        label="Tên sản phẩm",
        widget=forms.TextInput(attrs={
            "class": "form-control-plaintext form-control-sm px-0",
            "readonly": True,
            "tabindex": "-1",
        }),
    )
    qty = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0"),
        required=False,
        label="Số lượng nhập",
        widget=forms.NumberInput(attrs={
            **_INPUT_SM,
            "step": "0.01",
            "min": "0",
            "class": f"{_INPUT_SM['class']} jp-ycntp-qty-total",
            "readonly": True,
        }),
    )
    request_date = forms.DateField(
        label="Ngày yêu cầu",
        widget=forms.DateInput(attrs=_DATE_SM),
    )
    notes = forms.CharField(
        required=False,
        label="Ghi chú",
        widget=forms.TextInput(attrs=_INPUT_SM),
    )

    def __init__(self, *args, extra_mo=None, operator=None, **kwargs):
        from django.contrib.auth import get_user_model
        from hrm.user_search import issue_recipient_label
        from san_xuat.hub_models import SxProductionOrder

        super().__init__(*args, **kwargs)
        User = get_user_model()
        selected_user_id = None
        if self.is_bound:
            raw = self.data.get(self.add_prefix("received_by"))
            if raw and str(raw).isdigit():
                selected_user_id = int(raw)
        elif self.initial.get("received_by"):
            raw = self.initial.get("received_by")
            selected_user_id = getattr(raw, "pk", raw)
        elif operator is not None and getattr(operator, "pk", None):
            selected_user_id = operator.pk
            self.initial.setdefault("received_by", operator)
        self.fields["received_by"].queryset = (
            User.objects.filter(pk=selected_user_id) if selected_user_id else User.objects.none()
        )
        self.fields["received_by"].label_from_instance = issue_recipient_label
        self.fields["received_by"].empty_label = None

        extra_wh = ""
        if self.is_bound:
            extra_wh = (self.data.get(self.add_prefix("warehouse_code")) or "").strip()
        elif self.initial:
            extra_wh = (self.initial.get("warehouse_code") or "").strip()
        self.fields["warehouse_code"].choices = fg_warehouse_choices(extra_value=extra_wh)
        real_wh = [c for c in self.fields["warehouse_code"].choices if c[0]]
        if len(real_wh) == 1 and not extra_wh:
            self.initial.setdefault("warehouse_code", real_wh[0][0])

        eligible = SxProductionOrder.objects.filter(
            is_demo=False,
            status__in=(
                SxProductionOrder.STATUS_IN_PROGRESS,
                SxProductionOrder.STATUS_DONE,
            ),
        )
        extra_pk = None
        if extra_mo is not None:
            extra_pk = getattr(extra_mo, "pk", extra_mo)
        elif self.is_bound:
            raw = self.data.get(self.add_prefix("production_order"))
            if raw and str(raw).isdigit():
                extra_pk = int(raw)
        elif self.initial:
            raw = self.initial.get("production_order")
            extra_pk = getattr(raw, "pk", raw) if raw else None
        qs = eligible
        if extra_pk:
            qs = (SxProductionOrder.objects.filter(pk=extra_pk) | eligible).distinct()
        self.fields["production_order"].queryset = qs.order_by("-order_date", "-pk")
        self.fields["production_order"].empty_label = "— Chọn lệnh sản xuất —"
        self.fields["production_order"].label_from_instance = (
            lambda mo: f"{mo.code} · {mo.product_code}"
            + (f" — {mo.product_name}" if mo.product_name else "")
        )

    def clean_production_order(self):
        from san_xuat.hub_models import SxProductionOrder

        mo = self.cleaned_data.get("production_order")
        if not mo:
            raise forms.ValidationError("Chọn lệnh sản xuất nguồn.")
        if mo.status not in (
            SxProductionOrder.STATUS_IN_PROGRESS,
            SxProductionOrder.STATUS_DONE,
        ):
            raise forms.ValidationError(
                "Chỉ lập yêu cầu khi lệnh đang sản xuất hoặc đã hoàn thành."
            )
        return mo

    def clean_warehouse_code(self):
        code = (self.cleaned_data.get("warehouse_code") or "").strip()
        if not code:
            raise forms.ValidationError("Chọn kho nhập.")
        labels = dict(self.fields["warehouse_code"].choices)
        self._warehouse_name = labels.get(code) or code
        return code

    def clean(self):
        cleaned = super().clean()
        cleaned["warehouse_name"] = getattr(self, "_warehouse_name", "") or ""
        return cleaned


class FgReceiptLineForm(forms.Form):
    color_code = forms.ChoiceField(
        required=False,
        label="Màu",
        choices=[],
        widget=forms.Select(attrs={
            "class": "form-select form-select-sm jp-sx-color-select",
        }),
    )
    size_label = forms.ChoiceField(
        required=False,
        label="Size",
        choices=[],
        widget=forms.Select(attrs={
            "class": "form-select form-select-sm jp-sx-size-select",
        }),
    )
    sku_code = forms.CharField(
        max_length=100,
        required=False,
        label="SKU",
        widget=forms.TextInput(attrs={
            "class": "form-control form-control-sm jp-sx-sku-code",
            "placeholder": "Mã SX–Màu–Size",
            "readonly": True,
            "tabindex": "-1",
        }),
    )
    color_label = forms.CharField(
        max_length=40,
        required=False,
        widget=forms.HiddenInput(),
    )
    qty = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0"),
        required=False,
        label="Số lượng",
        widget=forms.NumberInput(attrs={
            "class": "form-control form-control-sm jp-so-qty-total",
            "step": "0.01",
            "min": "0",
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from san_xuat.services.sku_catalog import color_choices, size_choices

        extra_color = ""
        extra_size = ""
        if self.is_bound:
            extra_color = (self.data.get(self.add_prefix("color_code")) or "").strip()
            extra_size = (self.data.get(self.add_prefix("size_label")) or "").strip()
        elif self.initial:
            extra_color = (self.initial.get("color_code") or "").strip()
            extra_size = (self.initial.get("size_label") or "").strip()
        self.fields["color_code"].choices = color_choices(extra_code=extra_color, blank_label="—")
        self.fields["size_label"].choices = size_choices(extra_code=extra_size, blank_label="—")

    def clean(self):
        cleaned = super().clean()
        from san_xuat.services.sku_catalog import color_label_for

        color_code = (cleaned.get("color_code") or "").strip()
        if color_code and not cleaned.get("color_label"):
            cleaned["color_label"] = color_label_for(color_code)
        qty = cleaned.get("qty")
        if qty and qty > 0 and not (
            (cleaned.get("sku_code") or "").strip()
            or color_code
            or (cleaned.get("size_label") or "").strip()
        ):
            self.add_error("color_code", "Chọn màu / size cho dòng nhập.")
        return cleaned


def make_fg_receipt_line_formset(*, data=None, initial=None):
    extra = 0 if initial else 1
    factory = formset_factory(FgReceiptLineForm, extra=extra, can_delete=True)
    if data is not None:
        return factory(data, prefix="lines")
    return factory(prefix="lines", initial=initial or None)


FgReceiptLineFormSet = formset_factory(FgReceiptLineForm, extra=1, can_delete=True)


class FgReceiptLinkKvForm(forms.Form):
    kv_purchase_code = forms.CharField(
        max_length=64,
        required=False,
        label="Mã phiếu nhập KiotViet",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "VD: PN000123"}),
    )
    kv_purchase_kiotviet_id = forms.IntegerField(
        required=False,
        label="Mã số phiếu nhập KiotViet",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "min": "1"}),
    )

    def clean(self):
        cleaned = super().clean()
        code = (cleaned.get("kv_purchase_code") or "").strip()
        kid = cleaned.get("kv_purchase_kiotviet_id")
        if not code and not kid:
            raise forms.ValidationError("Nhập mã phiếu nhập KV hoặc Mã số phiếu nhập KiotViet.")
        return cleaned


class WipHandoverCreateForm(forms.Form):
    production_order = forms.ModelChoiceField(
        queryset=None,
        label="Lệnh sản xuất",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    from_process = forms.CharField(
        max_length=120,
        label="Công đoạn gửi",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    to_process = forms.CharField(
        max_length=120,
        label="Công đoạn nhận",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    qty = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Số lượng bàn giao",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.01", "min": "0.01"}),
    )
    handover_date = forms.DateField(
        label="Ngày bàn giao",
        widget=forms.DateInput(attrs=_DATE_SM),
    )
    code = forms.CharField(
        max_length=40,
        required=False,
        label="Mã bàn giao",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    notes = forms.CharField(
        required=False,
        label="Ghi chú",
        widget=forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        from san_xuat.hub_models import SxProductionOrder

        super().__init__(*args, **kwargs)
        self.fields["production_order"].queryset = (
            SxProductionOrder.objects.filter(
                is_demo=False,
                status__in=[
                    SxProductionOrder.STATUS_RELEASED,
                    SxProductionOrder.STATUS_IN_PROGRESS,
                    SxProductionOrder.STATUS_DONE,
                ],
            )
            .order_by("-order_date", "-pk")
        )


class DisassemblyCreateForm(forms.Form):
    product_code = forms.CharField(
        max_length=60,
        label="Mã sản phẩm tháo",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    product_name = forms.CharField(
        max_length=255,
        required=False,
        label="Tên sản phẩm",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    qty = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Số lượng tháo",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.01", "min": "0.01"}),
    )
    order_date = forms.DateField(
        label="Ngày lệnh tháo dỡ",
        widget=forms.DateInput(attrs=_DATE_SM),
    )
    production_order = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label="Lệnh sản xuất nguồn (tùy chọn)",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    code = forms.CharField(
        max_length=40,
        required=False,
        label="Mã lệnh tháo dỡ",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    notes = forms.CharField(
        required=False,
        label="Ghi chú",
        widget=forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 3}),
    )
    # Dòng thu hồi đầu (MVP 1 dòng trên form tạo; thêm tiếp trên detail)
    material_code = forms.CharField(
        max_length=60,
        label="Mã nguyên phụ liệu thu hồi",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    material_qty = forms.DecimalField(
        max_digits=14,
        decimal_places=4,
        min_value=Decimal("0.0001"),
        label="Số lượng thu hồi",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.0001", "min": "0.0001"}),
    )

    def __init__(self, *args, **kwargs):
        from san_xuat.hub_models import SxProductionOrder

        super().__init__(*args, **kwargs)
        self.fields["production_order"].queryset = (
            SxProductionOrder.objects.filter(is_demo=False).order_by("-order_date", "-pk")
        )


class NplSurplusCreateForm(forms.Form):
    material_code = forms.CharField(
        max_length=60,
        label="Mã nguyên phụ liệu",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    material_name = forms.CharField(
        max_length=255,
        required=False,
        label="Tên nguyên phụ liệu",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    qty = forms.DecimalField(
        max_digits=14,
        decimal_places=4,
        min_value=Decimal("0.0001"),
        label="Số lượng thừa",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.0001", "min": "0.0001"}),
    )
    recorded_at = forms.DateField(
        label="Ngày ghi nhận",
        widget=forms.DateInput(attrs=_DATE_SM),
    )
    production_order = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label="Lệnh sản xuất (tùy chọn)",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    code = forms.CharField(
        max_length=40,
        required=False,
        label="Mã nguyên phụ liệu thừa",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    notes = forms.CharField(
        required=False,
        label="Ghi chú",
        widget=forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        from san_xuat.hub_models import SxProductionOrder

        super().__init__(*args, **kwargs)
        self.fields["production_order"].queryset = (
            SxProductionOrder.objects.filter(is_demo=False).order_by("-order_date", "-pk")
        )


class WipReturnCreateForm(forms.Form):
    production_order = forms.ModelChoiceField(
        queryset=None,
        label="Lệnh sản xuất",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    handover = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label="Bàn giao nguồn (đã xác nhận)",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    from_process = forms.CharField(
        max_length=120,
        required=False,
        label="Từ công đoạn (đang giữ)",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    to_process = forms.CharField(
        max_length=120,
        required=False,
        label="Về công đoạn (sửa)",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    qty = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Số lượng trả",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.01", "min": "0.01"}),
    )
    return_date = forms.DateField(
        label="Ngày trả",
        widget=forms.DateInput(attrs=_DATE_SM),
    )
    reason = forms.CharField(
        required=False,
        label="Lý do",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "VD: Lỗi đường may"}),
    )
    code = forms.CharField(
        max_length=40,
        required=False,
        label="Mã trả",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    notes = forms.CharField(
        required=False,
        label="Ghi chú",
        widget=forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 2}),
    )

    def __init__(self, *args, **kwargs):
        from san_xuat.hub_models import SxProductionOrder, SxWipHandover

        super().__init__(*args, **kwargs)
        self.fields["production_order"].queryset = (
            SxProductionOrder.objects.filter(
                is_demo=False,
                status__in=[
                    SxProductionOrder.STATUS_RELEASED,
                    SxProductionOrder.STATUS_IN_PROGRESS,
                    SxProductionOrder.STATUS_DONE,
                ],
            ).order_by("-order_date", "-pk")
        )
        self.fields["handover"].queryset = (
            SxWipHandover.objects.filter(is_demo=False, status=SxWipHandover.STATUS_DONE)
            .select_related("production_order")
            .order_by("-handover_date", "-pk")
        )
        self.fields["handover"].empty_label = "— Không gắn bàn giao —"


class ScheduleMoUpdateForm(forms.Form):
    production_order_id = forms.IntegerField(widget=forms.HiddenInput())
    planned_start = forms.DateField(
        required=False,
        label="Bắt đầu",
        widget=forms.DateInput(attrs=_DATE_SM),
    )
    planned_end = forms.DateField(
        required=False,
        label="Kết thúc",
        widget=forms.DateInput(attrs=_DATE_SM),
    )
    team_label = forms.CharField(
        required=False,
        label="Tổ",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
