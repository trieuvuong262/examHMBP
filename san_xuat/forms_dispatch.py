from __future__ import annotations

from decimal import Decimal

from django import forms

_SELECT_SM = {"class": "form-select form-select-sm"}
_INPUT_SM = {"class": "form-control form-control-sm"}
_DATE_SM = {"class": "form-control form-control-sm jp-date-vn", "type": "date"}
_PRODUCT_CODE_SELECT = {
    "class": "form-select form-select-sm jp-sx-product-code-select",
    "data-placeholder": "Gõ mã hoặc tên hàng hoá…",
}


def _product_code_choices(extra_value: str = "") -> list[tuple[str, str]]:
    """Choices TomSelect — chỉ giữ giá trị đã chọn (load remote từ hàng hoá KV)."""
    choices: list[tuple[str, str]] = [("", "— Chọn hàng hoá —")]
    code = (extra_value or "").strip()
    if not code:
        return choices
    from san_xuat.services.products import resolve_kv_product_ref

    ref = resolve_kv_product_ref(code)
    label = f"{code} — {ref.name}" if ref and ref.name else code
    choices.append((code, label))
    return choices


def work_center_team_choices(*, extra_value: str = "") -> list[tuple[str, str]]:
    """Choices tổ/chuyền từ Năng lực SX (SxWorkCenter)."""
    from san_xuat.hub_models import SxWorkCenter

    choices: list[tuple[str, str]] = [("", "— Chọn tổ / chuyền —")]
    seen: set[str] = set()
    for center in SxWorkCenter.objects.filter(is_active=True, is_demo=False).order_by("name"):
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


def bom_process_choices(bom, *, extra_value: str = "") -> list[tuple[str, str]]:
    """Choices công đoạn từ danh mục chung (+ giá trị đang dùng).

    `bom` giữ tham số để tương thích chỗ gọi cũ; danh mục không phụ thuộc BOM.
    """
    from san_xuat.services.process_catalog import process_catalog_choices

    _ = bom
    return process_catalog_choices(extra_value=extra_value)


class ProductionOrderCreateForm(forms.Form):
    code = forms.CharField(
        max_length=40,
        required=False,
        help_text="Để trống thì hệ thống tự sinh mã.",
        widget=forms.TextInput(attrs=_INPUT_SM),
        label="Mã lệnh sản xuất",
    )
    product_code = forms.ChoiceField(
        label="Mã sản phẩm",
        choices=[],
        widget=forms.Select(attrs=_PRODUCT_CODE_SELECT),
    )
    qty = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        widget=forms.NumberInput(attrs={**_INPUT_SM, "step": "0.01", "min": "0.01"}),
        label="Số lượng",
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

    def clean_product_code(self):
        code = (self.cleaned_data.get("product_code") or "").strip()
        if not code:
            raise forms.ValidationError("Chọn mã sản phẩm từ hàng hoá.")
        from san_xuat.services.products import find_kv_product

        if not find_kv_product(code):
            raise forms.ValidationError(f"Mã {code} không có trong hàng hoá KiotViet.")
        return code


class ProductionOrderUpdateForm(forms.Form):
    qty = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        widget=forms.NumberInput(attrs={**_INPUT_SM, "step": "0.01", "min": "0.01"}),
        label="Số lượng",
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
    team_label = forms.CharField(
        required=False,
        label="Tổ / chuyền",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "VD: Tổ May 1"}),
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
        help_text="Tự ghép Style–Màu–Size (vd. JP-TEE-260001-NVY-M). Có thể sửa tay.",
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from san_xuat.services.sku_catalog import color_choices, size_choices

        data = args[0] if args else None
        extra_process = ""
        extra_color = ""
        extra_size = ""
        if data is not None:
            extra_process = data.get("process_name") or ""
            extra_color = data.get("color_code") or ""
            extra_size = data.get("size_label") or ""
        elif self.initial:
            extra_process = self.initial.get("process_name") or ""
            extra_color = self.initial.get("color_code") or ""
            extra_size = self.initial.get("size_label") or ""
        self.fields["process_name"].choices = bom_process_choices(None, extra_value=extra_process)
        self.fields["color_code"].choices = color_choices(extra_code=extra_color)
        self.fields["size_label"].choices = size_choices(extra_code=extra_size)

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


class FgReceiptCreateForm(forms.Form):
    code = forms.CharField(
        max_length=40,
        required=False,
        label="Mã yêu cầu nhập thành phẩm",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    qty = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Số lượng nhập thành phẩm",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.01", "min": "0.01"}),
    )
    notes = forms.CharField(
        required=False,
        label="Ghi chú",
        widget=forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 3}),
    )


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
