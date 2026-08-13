from __future__ import annotations

from django import forms

_DATE_SM = {"class": "form-control form-control-sm jp-date-vn", "type": "date"}


class StandardCostSheetCreateForm(forms.Form):
    name = forms.CharField(
        max_length=200,
        label="Tên bảng",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    date_from = forms.DateField(
        label="Từ ngày",
        widget=forms.DateInput(attrs=_DATE_SM),
    )
    date_to = forms.DateField(
        label="Đến ngày",
        widget=forms.DateInput(attrs=_DATE_SM),
    )
    code = forms.CharField(
        max_length=40,
        required=False,
        label="Mã GTDM",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    product_codes = forms.CharField(
        required=False,
        label="Mã SP (tùy chọn, cách nhau bởi dấu phẩy)",
        widget=forms.TextInput(
            attrs={"class": "form-control form-control-sm", "placeholder": "Để trống = tất cả BOM active"},
        ),
    )
    notes = forms.CharField(
        required=False,
        label="Ghi chú",
        widget=forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 3}),
    )

    def clean(self):
        cleaned = super().clean()
        date_from = cleaned.get("date_from")
        date_to = cleaned.get("date_to")
        if date_from and date_to and date_from > date_to:
            raise forms.ValidationError("Từ ngày phải ≤ đến ngày.")
        raw = (cleaned.get("product_codes") or "").strip()
        if raw:
            cleaned["product_code_list"] = [p.strip() for p in raw.split(",") if p.strip()]
        else:
            cleaned["product_code_list"] = None
        return cleaned


class OrderPlanCostCreateForm(forms.Form):
    name = forms.CharField(
        max_length=200,
        label="Tên bảng",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    date_from = forms.DateField(
        label="Từ ngày",
        widget=forms.DateInput(attrs=_DATE_SM),
    )
    date_to = forms.DateField(
        label="Đến ngày",
        widget=forms.DateInput(attrs=_DATE_SM),
    )
    kv_order_code = forms.CharField(
        max_length=64,
        required=False,
        label="Mã đơn (Portal hoặc KV)",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "VD: DH000123"}),
    )
    kv_order_kiotviet_id = forms.IntegerField(
        required=False,
        label="KV order id",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "min": "1"}),
    )
    standard_sheet = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label="Bảng GT định mức (tùy chọn)",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    code = forms.CharField(
        max_length=40,
        required=False,
        label="Mã GTĐH",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    notes = forms.CharField(
        required=False,
        label="Ghi chú",
        widget=forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        from san_xuat.hub_models import SxStandardCostSheet

        super().__init__(*args, **kwargs)
        self.fields["standard_sheet"].queryset = (
            SxStandardCostSheet.objects.filter(
                is_demo=False,
                status=SxStandardCostSheet.STATUS_CONFIRMED,
            )
            .order_by("-date_from", "-pk")
        )

    def clean(self):
        cleaned = super().clean()
        date_from = cleaned.get("date_from")
        date_to = cleaned.get("date_to")
        if date_from and date_to and date_from > date_to:
            raise forms.ValidationError("Từ ngày phải ≤ đến ngày.")
        code = (cleaned.get("kv_order_code") or "").strip()
        kid = cleaned.get("kv_order_kiotviet_id")
        if not code and not kid:
            raise forms.ValidationError("Nhập mã đơn Portal / KV hoặc KV order id.")
        return cleaned


class CostTypeForm(forms.Form):
    code = forms.CharField(
        max_length=40,
        label="Mã loại CP",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "VD: CP_VC"}),
    )
    name = forms.CharField(
        max_length=120,
        label="Tên loại CP",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    sort_order = forms.IntegerField(
        min_value=0,
        initial=100,
        label="Thứ tự",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "min": "0"}),
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
