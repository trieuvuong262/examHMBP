"""Forms giai đoạn 3 — giao việc, năng lực, đóng gói, thuê GC, truy xuất."""

from __future__ import annotations

from decimal import Decimal

from django import forms
from django.forms import formset_factory

_DATE_SM = {"class": "form-control form-control-sm jp-date-vn", "type": "date"}


class TraceLookupForm(forms.Form):
    query = forms.CharField(
        max_length=80,
        label="Mã tra cứu",
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-sm",
                "placeholder": "LSX · YCX · YCNTP · lô · GC · giao việc…",
                "autocomplete": "off",
            },
        ),
    )


class WorkAssignmentCreateForm(forms.Form):
    production_order = forms.ModelChoiceField(
        queryset=None,
        label="Lệnh sản xuất",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    work_center = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label="Tổ/chuyền",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    title = forms.CharField(
        max_length=200,
        label="Tiêu đề",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    process_name = forms.CharField(
        max_length=120,
        required=False,
        label="Công đoạn",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    assignee = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label="Người nhận portal",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    assignee_label = forms.CharField(
        max_length=120,
        required=False,
        label="Nhãn người/tổ (hiển thị)",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    due_date = forms.DateField(
        required=False,
        label="Hạn",
        widget=forms.DateInput(attrs=_DATE_SM),
    )
    create_portal_task = forms.BooleanField(
        required=False,
        initial=True,
        label="Tạo công việc module Công việc",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    notes = forms.CharField(
        required=False,
        label="Ghi chú",
        widget=forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 2}),
    )

    def __init__(self, *args, assigner=None, **kwargs):
        from django.contrib.auth import get_user_model

        from san_xuat.hub_models import SxProductionOrder, SxWorkCenter

        super().__init__(*args, **kwargs)
        self.fields["production_order"].queryset = (
            SxProductionOrder.objects.filter(is_demo=False)
            .exclude(status=SxProductionOrder.STATUS_CANCELLED)
            .order_by("-order_date", "-pk")
        )
        self.fields["work_center"].queryset = SxWorkCenter.objects.filter(
            is_demo=False, is_active=True,
        ).order_by("code")
        User = get_user_model()
        qs = User.objects.filter(is_active=True).order_by("first_name", "username")
        if assigner is not None:
            try:
                from hrm.permissions import get_task_assignable_users

                qs = get_task_assignable_users(assigner)
            except Exception:
                pass
        self.fields["assignee"].queryset = qs
        self.fields["assignee"].label_from_instance = (
            lambda u: (u.get_full_name() or u.username)
        )


class WorkCenterForm(forms.Form):
    code = forms.CharField(
        max_length=40,
        label="Mã",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    name = forms.CharField(
        max_length=120,
        label="Tên tổ/chuyền",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    capacity_per_day = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0"),
        label="Năng lực/ngày",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.01", "min": "0"}),
    )
    uom_label = forms.CharField(
        max_length=40,
        required=False,
        initial="cái",
        label="Đơn vị tính",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    team_label = forms.CharField(
        max_length=80,
        required=False,
        label="Nhãn tổ (khớp thống kê sản xuất)",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
        help_text="Để trống = dùng tên tổ/chuyền.",
    )
    headcount = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=2000,
        initial=0,
        label="Số nhân sự",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "min": "0"}),
        help_text="Đồng bộ HR sẽ ghi đè số này.",
    )
    shift_minutes_per_head = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=1440,
        initial=480,
        label="Phút làm việc / người / ngày",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "min": "0"}),
        help_text="480 phút = 8 giờ một ca.",
    )
    efficiency_pct = forms.DecimalField(
        required=False,
        max_digits=5,
        decimal_places=2,
        min_value=Decimal("0"),
        max_value=Decimal("200"),
        initial=Decimal("100"),
        label="Tải (%)",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.5", "min": "0", "max": "200"}),
        help_text="80 = thiếu người; 100 = bình thường; 150 = tăng ca. Nhân vào quỹ phút hữu ích.",
    )
    is_active = forms.BooleanField(
        required=False,
        initial=True,
        label="Đang dùng",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    notes = forms.CharField(
        required=False,
        label="Ghi chú",
        widget=forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 2}),
    )


class PackingCreateForm(forms.Form):
    production_order = forms.ModelChoiceField(
        queryset=None,
        label="Lệnh sản xuất",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    fg_receipt = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label="Yêu cầu nhập thành phẩm (tùy chọn)",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    qty = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0"),
        required=False,
        initial=Decimal("0"),
        label="Số lượng tổng (nếu không nhập dòng)",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.01", "min": "0"}),
    )
    pack_date = forms.DateField(
        label="Ngày đóng gói",
        widget=forms.DateInput(attrs=_DATE_SM),
    )
    carton_count = forms.IntegerField(
        min_value=0,
        initial=0,
        required=False,
        label="Số thùng/kiện (tổng)",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "min": "0"}),
    )
    lot_code = forms.CharField(
        max_length=60,
        required=False,
        label="Mã lô (trống = tự sinh khi xác nhận)",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    notes = forms.CharField(
        required=False,
        label="Ghi chú",
        widget=forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 2}),
    )

    def __init__(self, *args, **kwargs):
        from san_xuat.hub_models import SxFgReceiptRequest, SxProductionOrder

        super().__init__(*args, **kwargs)
        self.fields["production_order"].queryset = (
            SxProductionOrder.objects.filter(is_demo=False)
            .exclude(status=SxProductionOrder.STATUS_CANCELLED)
            .order_by("-order_date", "-pk")
        )
        self.fields["fg_receipt"].queryset = (
            SxFgReceiptRequest.objects.filter(is_demo=False)
            .select_related("production_order")
            .order_by("-request_date", "-pk")[:200]
        )
        self.fields["fg_receipt"].label_from_instance = (
            lambda fg: f"{fg.code} · lệnh {fg.production_order.code if fg.production_order_id else '—'}"
        )
        self.fields["production_order"].label_from_instance = (
            lambda mo: f"{mo.code} · {mo.product_code} · SL {mo.qty}"
        )


class PackingLineForm(forms.Form):
    color_code = forms.ChoiceField(
        required=False,
        label="Màu",
        choices=[],
        widget=forms.Select(attrs={"class": "form-select form-select-sm jp-sx-color-select"}),
    )
    size_label = forms.ChoiceField(
        required=False,
        label="Size",
        choices=[],
        widget=forms.Select(attrs={"class": "form-select form-select-sm jp-sx-size-select"}),
    )
    sku_code = forms.CharField(
        max_length=100,
        required=False,
        label="SKU",
        widget=forms.TextInput(attrs={
            "class": "form-control form-control-sm jp-sx-sku-code",
            "placeholder": "STYLE-COLOR-SIZE",
            "readonly": True,
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
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.01", "min": "0"}),
    )
    carton_count = forms.IntegerField(
        min_value=0,
        required=False,
        initial=0,
        label="Thùng",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "min": "0"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from san_xuat.services.sku_catalog import color_choices, size_choices

        data = args[0] if args else None
        extra_color = ""
        extra_size = ""
        if data is not None:
            extra_color = data.get("color_code") or ""
            extra_size = data.get("size_label") or ""
        elif self.initial:
            extra_color = self.initial.get("color_code") or ""
            extra_size = self.initial.get("size_label") or ""
        self.fields["color_code"].choices = color_choices(extra_code=extra_color, blank_label="—")
        self.fields["size_label"].choices = size_choices(extra_code=extra_size, blank_label="—")

    def clean(self):
        cleaned = super().clean()
        from san_xuat.services.sku_catalog import color_label_for

        color_code = (cleaned.get("color_code") or "").strip()
        if color_code and not cleaned.get("color_label"):
            cleaned["color_label"] = color_label_for(color_code)
        return cleaned


PackingLineFormSet = formset_factory(PackingLineForm, extra=3, can_delete=False)


class SubcontractCreateForm(forms.Form):
    vendor_name = forms.CharField(
        max_length=200,
        label="Đơn vị gia công",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    product_code = forms.CharField(
        max_length=60,
        label="Mã sản phẩm",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    product_name = forms.CharField(
        max_length=255,
        required=False,
        label="Tên sản phẩm",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    process_name = forms.CharField(
        max_length=120,
        required=False,
        label="Công đoạn gia công",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    qty = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Số lượng",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.01", "min": "0.01"}),
    )
    order_date = forms.DateField(
        label="Ngày",
        widget=forms.DateInput(attrs=_DATE_SM),
    )
    due_date = forms.DateField(
        required=False,
        label="Hạn",
        widget=forms.DateInput(attrs=_DATE_SM),
    )
    production_order = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label="Lệnh sản xuất nguồn (tùy chọn)",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    notes = forms.CharField(
        required=False,
        label="Ghi chú",
        widget=forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 2}),
    )

    def __init__(self, *args, **kwargs):
        from san_xuat.hub_models import SxProductionOrder

        super().__init__(*args, **kwargs)
        self.fields["production_order"].queryset = (
            SxProductionOrder.objects.filter(is_demo=False).order_by("-order_date", "-pk")
        )


class SubcontractMaterialLineForm(forms.Form):
    material_code = forms.CharField(
        max_length=60,
        required=False,
        label="Mã nguyên phụ liệu / bán thành phẩm",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    material_name = forms.CharField(
        max_length=255,
        required=False,
        label="Tên",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    qty = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0"),
        required=False,
        label="Số lượng",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.01", "min": "0"}),
    )
    uom_label = forms.CharField(
        max_length=40,
        required=False,
        initial="cái",
        label="Đơn vị tính",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    lot_code = forms.CharField(
        max_length=60,
        required=False,
        label="Lô",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )


SubcontractOutLineFormSet = formset_factory(SubcontractMaterialLineForm, extra=3, can_delete=False)


class SubcontractReceiveForm(forms.Form):
    qty_received = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Số lượng nhận lại",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.01", "min": "0.01"}),
    )
    material_code = forms.CharField(
        max_length=60,
        required=False,
        label="Mã bán thành phẩm / thành phẩm nhận (tùy chọn)",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    material_name = forms.CharField(
        max_length=255,
        required=False,
        label="Tên",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    lot_code = forms.CharField(
        max_length=60,
        required=False,
        label="Lô nhận",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
