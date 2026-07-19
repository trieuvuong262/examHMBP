from __future__ import annotations

from decimal import Decimal

from django import forms


class ProductionOrderCreateForm(forms.Form):
    code = forms.CharField(
        max_length=40,
        required=False,
        help_text="Để trống thì hệ thống tự sinh mã.",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
        label="Mã lệnh sản xuất",
    )
    product_code = forms.CharField(
        max_length=60,
        label="Mã sản phẩm",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "VD: SP008073"}),
    )
    qty = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.01", "min": "0.01"}),
        label="Số lượng",
    )
    order_date = forms.DateField(
        label="Ngày lập",
        widget=forms.DateInput(attrs={"class": "form-control form-control-sm", "type": "date"}),
    )
    due_date = forms.DateField(
        required=False,
        label="Hạn",
        widget=forms.DateInput(attrs={"class": "form-control form-control-sm", "type": "date"}),
    )
    planned_start = forms.DateField(
        required=False,
        label="Bắt đầu dự kiến",
        widget=forms.DateInput(attrs={"class": "form-control form-control-sm", "type": "date"}),
    )
    planned_end = forms.DateField(
        required=False,
        label="Kết thúc dự kiến",
        widget=forms.DateInput(attrs={"class": "form-control form-control-sm", "type": "date"}),
    )
    team_label = forms.CharField(
        required=False,
        label="Tổ / công đoạn",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "VD: Tổ May 1"}),
    )
    notes = forms.CharField(
        required=False,
        label="Ghi chú",
        widget=forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 3}),
    )
    is_sample = forms.BooleanField(
        required=False,
        label="Lệnh sản xuất mẫu",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )


class ProductionOrderUpdateForm(forms.Form):
    qty = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.01", "min": "0.01"}),
        label="Số lượng",
    )
    due_date = forms.DateField(
        required=False,
        label="Hạn",
        widget=forms.DateInput(attrs={"class": "form-control form-control-sm", "type": "date"}),
    )
    planned_start = forms.DateField(
        required=False,
        label="Bắt đầu dự kiến",
        widget=forms.DateInput(attrs={"class": "form-control form-control-sm", "type": "date"}),
    )
    planned_end = forms.DateField(
        required=False,
        label="Kết thúc dự kiến",
        widget=forms.DateInput(attrs={"class": "form-control form-control-sm", "type": "date"}),
    )
    team_label = forms.CharField(
        required=False,
        label="Tổ / công đoạn",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "VD: Tổ May 1"}),
    )
    notes = forms.CharField(
        required=False,
        label="Ghi chú",
        widget=forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 3}),
    )


class MaterialIssueApproveForm(forms.Form):
    attachment = forms.FileField(
        required=False,
        label="Chứng từ (tùy chọn — có thì hệ thống sẽ xuất kho thật ngay)",
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
        widget=forms.DateInput(attrs={"class": "form-control form-control-sm", "type": "date"}),
    )
    process_name = forms.CharField(
        required=False,
        label="Công đoạn",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "VD: May thân áo"}),
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
    size_label = forms.CharField(
        required=False,
        label="Size",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "S/M/L"}),
    )
    sku_code = forms.CharField(
        required=False,
        label="SKU",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    color_label = forms.CharField(
        required=False,
        label="Màu",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    notes = forms.CharField(
        required=False,
        label="Ghi chú",
        widget=forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 3}),
    )

    def clean(self):
        cleaned = super().clean()
        qty_good = cleaned.get("qty_good") or Decimal("0")
        qty_defect = cleaned.get("qty_defect") or Decimal("0")
        if qty_good <= 0 and qty_defect <= 0:
            raise forms.ValidationError("Phải nhập ít nhất Số lượng đạt hoặc Số lượng lỗi lớn hơn 0.")
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
        widget=forms.DateInput(attrs={"class": "form-control form-control-sm", "type": "date"}),
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
        widget=forms.DateInput(attrs={"class": "form-control form-control-sm", "type": "date"}),
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
        widget=forms.DateInput(attrs={"class": "form-control form-control-sm", "type": "date"}),
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
        widget=forms.DateInput(attrs={"class": "form-control form-control-sm", "type": "date"}),
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
        widget=forms.DateInput(attrs={"class": "form-control form-control-sm", "type": "date"}),
    )
    planned_end = forms.DateField(
        required=False,
        label="Kết thúc",
        widget=forms.DateInput(attrs={"class": "form-control form-control-sm", "type": "date"}),
    )
    team_label = forms.CharField(
        required=False,
        label="Tổ",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
