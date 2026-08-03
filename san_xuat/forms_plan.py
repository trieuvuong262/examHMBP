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
    plan_method = forms.ChoiceField(
        label="Phương án sản xuất",
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
    )
    date_from = forms.DateField(
        label="Từ ngày",
        widget=forms.DateInput(attrs=_DATE_SM),
    )
    date_to = forms.DateField(
        label="Đến ngày",
        widget=forms.DateInput(attrs=_DATE_SM),
    )
    mps_bucket = forms.ChoiceField(
        required=False,
        label="Chu kỳ lịch trình (MPS)",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    frozen_until = forms.DateField(
        required=False,
        label="Đóng băng đến ngày (MPS)",
        widget=forms.DateInput(attrs=_DATE_SM),
    )
    apply_netting = forms.BooleanField(
        required=False,
        initial=True,
        label="Trừ tồn thành phẩm và hàng đang sản xuất",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    notes = forms.CharField(
        required=False,
        label="Ghi chú",
        widget=forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from san_xuat.hub_models import SxOverallPlan

        self.fields["plan_method"].choices = SxOverallPlan.METHOD_CHOICES
        self.fields["mps_bucket"].choices = SxOverallPlan.BUCKET_CHOICES
        if not self.is_bound:
            self.fields["plan_method"].initial = SxOverallPlan.METHOD_MTO
            self.fields["mps_bucket"].initial = SxOverallPlan.BUCKET_WEEK

    def clean(self):
        cleaned = super().clean()
        from san_xuat.hub_models import SxOverallPlan

        date_from = cleaned.get("date_from")
        date_to = cleaned.get("date_to")
        if date_from and date_to and date_from > date_to:
            self.add_error("date_to", "Ngày kết thúc phải sau ngày bắt đầu.")
        frozen = cleaned.get("frozen_until")
        if frozen:
            if cleaned.get("plan_method") != SxOverallPlan.METHOD_MPS:
                cleaned["frozen_until"] = None
            elif date_to and frozen > date_to:
                self.add_error("frozen_until", "Không được vượt quá ngày kết thúc kỳ.")
        return cleaned


class MtoLoadOrdersForm(forms.Form):
    """Chọn nhiều đơn đặt hàng KiotViet để nạp nhu cầu."""

    kv_order_ids = forms.CharField(
        label="Đơn đặt hàng",
        widget=forms.HiddenInput(),
        help_text="Danh sách id đơn KiotViet, phân tách bằng dấu phẩy.",
    )
    replace = forms.BooleanField(
        required=False,
        initial=True,
        label="Thay toàn bộ dòng hiện có",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def clean_kv_order_ids(self):
        raw = (self.cleaned_data.get("kv_order_ids") or "").strip()
        ids = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
        bad = [p for p in ids if not p.isdigit()]
        if bad:
            raise forms.ValidationError("Danh sách đơn không hợp lệ.")
        if not ids:
            raise forms.ValidationError("Chọn ít nhất một đơn đặt hàng.")
        return [int(p) for p in ids]


class MtsLoadForm(forms.Form):
    """Chọn mã SP thiếu tồn để nạp vào kế hoạch."""

    product_codes = forms.CharField(
        required=False,
        label="Mã sản phẩm",
        widget=forms.HiddenInput(),
        help_text="Để trống = lấy toàn bộ mã đang dưới mức tồn tối thiểu.",
    )
    replace = forms.BooleanField(
        required=False,
        initial=True,
        label="Thay toàn bộ dòng hiện có",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def clean_product_codes(self):
        raw = (self.cleaned_data.get("product_codes") or "").strip()
        if not raw:
            return []
        return [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]


class MpsLineForm(forms.Form):
    """Nhập một ô lịch trình chủ (mã SP × kỳ)."""

    product_code = forms.CharField(
        max_length=60,
        label="Mã SP",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "VD: SP008073"}),
    )
    bucket_start = forms.DateField(
        label="Kỳ",
        widget=forms.DateInput(attrs=_DATE_SM),
    )
    qty = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Sản lượng",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.01", "min": "0.01"}),
    )


class StockPolicyForm(forms.Form):
    """Chính sách tồn thành phẩm (MTS)."""

    product_code = forms.CharField(
        max_length=60,
        label="Mã sản phẩm",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "VD: SP008073"}),
    )
    product_name = forms.CharField(
        required=False,
        max_length=255,
        label="Tên sản phẩm",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    min_stock = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0"),
        label="Tồn tối thiểu",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "1", "min": "0"}),
    )
    max_stock = forms.DecimalField(
        required=False,
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0"),
        label="Tồn mục tiêu",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "1", "min": "0"}),
    )
    lead_time_days = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=365,
        initial=0,
        label="Thời gian chờ (ngày)",
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "min": "0"}),
    )
    is_active = forms.BooleanField(
        required=False,
        initial=True,
        label="Đang áp dụng",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def clean(self):
        cleaned = super().clean()
        min_stock = cleaned.get("min_stock") or Decimal("0")
        max_stock = cleaned.get("max_stock") or Decimal("0")
        if max_stock and max_stock < min_stock:
            self.add_error("max_stock", "Tồn mục tiêu phải lớn hơn hoặc bằng tồn tối thiểu.")
        return cleaned


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
    supplier = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label="Nhà cung cấp (danh mục kho)",
        help_text="Chọn để tạo được phiếu nhập kho NPL trực tiếp từ đơn mua hàng.",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    supplier_name = forms.CharField(
        max_length=200,
        required=False,
        label="Nhà cung cấp (tự nhập)",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    expected_date = forms.DateField(
        required=False,
        label="Ngày hàng về dự kiến",
        widget=forms.DateInput(attrs={"class": "form-control form-control-sm", "type": "date"}),
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
        from kho_npl.models import Supplier
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
        self.fields["supplier"].queryset = Supplier.objects.filter(is_active=True).order_by("name")


class PoReceiptForm(forms.Form):
    """Tạo phiếu nhập kho NPL từ đơn mua hàng."""

    receipt_date = forms.DateField(
        required=False,
        label="Ngày nhập",
        widget=forms.DateInput(attrs={"class": "form-control form-control-sm", "type": "date"}),
    )
    location = forms.ModelChoiceField(
        queryset=None,
        label="Vị trí nhập",
        help_text="Chọn đúng kho nhận hàng — phiếu nhập sẽ cộng tồn vào vị trí này.",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    notes = forms.CharField(
        required=False,
        label="Ghi chú",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )

    def __init__(self, *args, **kwargs):
        from kho_npl.models import WarehouseLocation

        super().__init__(*args, **kwargs)
        self.fields["location"].queryset = (
            WarehouseLocation.objects.filter(is_active=True).order_by("code")
        )
        if not self.is_bound and not self.initial.get("location"):
            from san_xuat.services.po_receipt import default_receipt_location

            suggested = default_receipt_location()
            if suggested is not None:
                self.fields["location"].initial = suggested.pk
