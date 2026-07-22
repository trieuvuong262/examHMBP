from __future__ import annotations

from decimal import Decimal

from django import forms

_DATE_SM = {"class": "form-control form-control-sm jp-date-vn", "type": "date"}


class OverallPlanCreateForm(forms.Form):
    code = forms.CharField(
        max_length=40,
        required=False,
        label="Mã KHTT",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    name = forms.CharField(
        max_length=200,
        label="Tên kế hoạch",
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
    notes = forms.CharField(
        required=False,
        label="Ghi chú",
        widget=forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 3}),
    )


class OverallPlanLineForm(forms.Form):
    product_code = forms.CharField(
        max_length=60,
        label="Mã SP",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "VD: SP008073"}),
    )
    product_name = forms.CharField(
        required=False,
        max_length=255,
        label="Tên SP",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    qty_planned = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="SL kế hoạch",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.01", "min": "0.01"}),
    )
    qty_required = forms.DecimalField(
        required=False,
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0"),
        label="SL yêu cầu",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.01", "min": "0"}),
    )
    capacity_per_day = forms.DecimalField(
        required=False,
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0"),
        label="Công suất/ngày",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.01", "min": "0"}),
    )


class ImportKvOrderForm(forms.Form):
    kv_order_code = forms.CharField(
        max_length=64,
        required=False,
        label="Mã đơn KV",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "VD: DH000123"}),
    )
    kv_order_kiotviet_id = forms.IntegerField(
        required=False,
        label="KV order id",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "min": "1"}),
    )

    def clean(self):
        cleaned = super().clean()
        code = (cleaned.get("kv_order_code") or "").strip()
        kid = cleaned.get("kv_order_kiotviet_id")
        if not code and not kid:
            raise forms.ValidationError("Nhập mã đơn KV hoặc KV order id.")
        return cleaned


class MaterialPlanExplodeForm(forms.Form):
    overall_plan = forms.ModelChoiceField(
        queryset=None,
        label="KHTT nguồn",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    code = forms.CharField(
        max_length=40,
        required=False,
        label="Mã KHNVL",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    name = forms.CharField(
        required=False,
        max_length=200,
        label="Tên",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )

    def __init__(self, *args, **kwargs):
        from san_xuat.hub_models import SxOverallPlan

        super().__init__(*args, **kwargs)
        self.fields["overall_plan"].queryset = (
            SxOverallPlan.objects.filter(is_demo=False, status=SxOverallPlan.STATUS_CONFIRMED)
            .order_by("-date_from", "-pk")
        )


class NplPurchaseRequestCreateForm(forms.Form):
    material_plan = forms.ModelChoiceField(
        queryset=None,
        label="KHNVL nguồn",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    code = forms.CharField(
        max_length=40,
        required=False,
        label="Mã YCM",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    due_date = forms.DateField(
        required=False,
        label="Hạn mua",
        widget=forms.DateInput(attrs=_DATE_SM),
    )
    only_shortfall = forms.BooleanField(
        required=False,
        initial=True,
        label="Chỉ lấy dòng thiếu hụt",
    )
    notes = forms.CharField(
        required=False,
        label="Ghi chú",
        widget=forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        from san_xuat.hub_models import SxMaterialPlan, SxOverallPlan

        super().__init__(*args, **kwargs)
        self.fields["material_plan"].queryset = (
            SxMaterialPlan.objects.filter(is_demo=False, status=SxOverallPlan.STATUS_CONFIRMED)
            .select_related("overall_plan")
            .order_by("-created_at", "-pk")
        )


class DetailPlanExplodeForm(forms.Form):
    overall_plan = forms.ModelChoiceField(
        queryset=None,
        label="KHTT nguồn",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    code = forms.CharField(
        max_length=40,
        required=False,
        label="Mã KHCT",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    name = forms.CharField(
        required=False,
        max_length=200,
        label="Tên",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )

    def __init__(self, *args, **kwargs):
        from san_xuat.hub_models import SxOverallPlan

        super().__init__(*args, **kwargs)
        self.fields["overall_plan"].queryset = (
            SxOverallPlan.objects.filter(is_demo=False, status=SxOverallPlan.STATUS_CONFIRMED)
            .order_by("-date_from", "-pk")
        )


class PurchaseOrderCreateForm(forms.Form):
    purchase_request = forms.ModelChoiceField(
        queryset=None,
        label="YCM nguồn",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    supplier_name = forms.CharField(
        max_length=200,
        required=False,
        label="Nhà cung cấp",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    code = forms.CharField(
        max_length=40,
        required=False,
        label="Mã DMH",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    notes = forms.CharField(
        required=False,
        label="Ghi chú",
        widget=forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        from san_xuat.hub_models import SxNplPurchaseRequest

        super().__init__(*args, **kwargs)
        self.fields["purchase_request"].queryset = (
            SxNplPurchaseRequest.objects.filter(
                is_demo=False,
                status=SxNplPurchaseRequest.STATUS_APPROVED,
            )
            .select_related("material_plan")
            .order_by("-created_at", "-pk")
        )
