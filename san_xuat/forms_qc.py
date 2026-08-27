from __future__ import annotations

from decimal import Decimal

from django import forms
from django.forms import formset_factory
from django.utils import timezone

from san_xuat.hub_models import (
    SxQcCriteria,
    SxQcCriteriaGroup,
    SxQcDefect,
    SxQcDefectGroup,
    SxQcInspection,
    SxQcInspectionCriteriaLine,
    SxQcRequest,
    SxQcSamplingMethod,
    SxQcStandardSet,
)


_FORM_CONTROL = {"class": "form-control form-control-sm"}
_FORM_SELECT = {"class": "form-select form-select-sm"}
_DATE_SM = {"class": "form-control form-control-sm jp-date-vn", "type": "date"}


class QcCriteriaGroupForm(forms.ModelForm):
    class Meta:
        model = SxQcCriteriaGroup
        fields = ("code", "name", "is_active")
        widgets = {
            "code": forms.TextInput(attrs=_FORM_CONTROL),
            "name": forms.TextInput(attrs=_FORM_CONTROL),
        }


class QcCriteriaForm(forms.ModelForm):
    class Meta:
        model = SxQcCriteria
        fields = ("code", "name", "team_slug", "group", "kind", "is_active")
        widgets = {
            "code": forms.TextInput(attrs=_FORM_CONTROL),
            "name": forms.TextInput(attrs=_FORM_CONTROL),
            "team_slug": forms.Select(attrs=_FORM_SELECT),
            "group": forms.Select(attrs=_FORM_SELECT),
            "kind": forms.Select(attrs=_FORM_SELECT),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["team_slug"].required = True
        self.fields["team_slug"].choices = [("", "— Chọn tổ —")] + list(
            SxQcCriteria.TEAM_SLUG_CHOICES
        )
        self.fields["team_slug"].help_text = "Tab phiếu kiểm tra sẽ hiện tiêu chuẩn của tổ này."


class QcSamplingMethodForm(forms.ModelForm):
    class Meta:
        model = SxQcSamplingMethod
        fields = ("code", "name", "method_type", "sample_value", "is_active")
        widgets = {
            "code": forms.TextInput(attrs=_FORM_CONTROL),
            "name": forms.TextInput(attrs=_FORM_CONTROL),
            "method_type": forms.TextInput(attrs={**_FORM_CONTROL, "placeholder": "VD: fixed_qty"}),
            "sample_value": forms.NumberInput(attrs={**_FORM_CONTROL, "step": "0.01", "min": "0"}),
        }


class QcStandardSetForm(forms.ModelForm):
    class Meta:
        model = SxQcStandardSet
        fields = ("code", "name", "product_code", "stage_name", "defect_tolerance_pct", "sampling_method", "is_active")
        widgets = {
            "code": forms.TextInput(attrs=_FORM_CONTROL),
            "name": forms.TextInput(attrs=_FORM_CONTROL),
            "product_code": forms.TextInput(attrs={**_FORM_CONTROL, "placeholder": "Để trống = áp dụng chung"}),
            "stage_name": forms.TextInput(attrs={**_FORM_CONTROL, "placeholder": "VD: May, hoàn thiện"}),
            "defect_tolerance_pct": forms.NumberInput(attrs={**_FORM_CONTROL, "step": "0.01", "min": "0"}),
            "sampling_method": forms.Select(attrs=_FORM_SELECT),
        }


class QcDefectGroupForm(forms.ModelForm):
    class Meta:
        model = SxQcDefectGroup
        fields = ("code", "name", "is_active")
        widgets = {
            "code": forms.TextInput(attrs=_FORM_CONTROL),
            "name": forms.TextInput(attrs=_FORM_CONTROL),
        }


class QcDefectForm(forms.ModelForm):
    class Meta:
        model = SxQcDefect
        fields = ("code", "name", "group", "severity", "is_active")
        widgets = {
            "code": forms.TextInput(attrs=_FORM_CONTROL),
            "name": forms.TextInput(attrs=_FORM_CONTROL),
            "group": forms.Select(attrs=_FORM_SELECT),
            "severity": forms.TextInput(attrs={**_FORM_CONTROL, "placeholder": "VD: minor / major"}),
        }


class QcRequestForm(forms.ModelForm):
    class Meta:
        model = SxQcRequest
        fields = (
            "code",
            "production_order",
            "product_code",
            "product_name",
            "stage_name",
            "team_slug",
            "qty",
            "request_date",
            "due_date",
            "status",
            "notes",
        )
        widgets = {
            "code": forms.TextInput(attrs={**_FORM_CONTROL, "placeholder": "Để trống = tự sinh"}),
            "production_order": forms.Select(attrs=_FORM_SELECT),
            "product_code": forms.TextInput(attrs=_FORM_CONTROL),
            "product_name": forms.TextInput(attrs=_FORM_CONTROL),
            "stage_name": forms.TextInput(attrs={**_FORM_CONTROL, "placeholder": "VD: May, hoàn thiện, QC thành phẩm"}),
            "team_slug": forms.HiddenInput(),
            "qty": forms.NumberInput(attrs={**_FORM_CONTROL, "step": "0.01", "min": "0.01"}),
            "request_date": forms.DateInput(attrs=_DATE_SM),
            "due_date": forms.DateInput(attrs=_DATE_SM),
            "status": forms.Select(
                attrs=_FORM_SELECT,
                choices=[
                    ("draft", "Nháp"),
                    ("open", "Mở"),
                    ("in_progress", "Đang kiểm"),
                    ("done", "Hoàn thành"),
                    ("cancelled", "Hủy"),
                ],
            ),
            "notes": forms.Textarea(attrs={**_FORM_CONTROL, "rows": 2}),
        }
        labels = {
            "stage_name": "Công đoạn",
            "production_order": "Lệnh sản xuất",
            "product_code": "Mã SP",
            "product_name": "Tên SP",
            "qty": "Số lượng",
            "request_date": "Ngày yêu cầu",
            "due_date": "Hạn kiểm",
            "status": "Trạng thái",
            "notes": "Ghi chú",
            "code": "Mã YCKT",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["production_order"].required = False
        self.fields["production_order"].queryset = self.fields["production_order"].queryset.order_by("-order_date", "-pk")
        self.fields["production_order"].empty_label = "— Không gắn LSX —"
        self.fields["code"].required = False
        self.fields["stage_name"].required = False
        self.fields["due_date"].required = False
        self.fields["notes"].required = False
        if not self.instance.pk:
            self.initial.setdefault("request_date", timezone.localdate())
            self.initial.setdefault("status", "open")


class QcInspectionCreateForm(forms.Form):
    qc_request = forms.ModelChoiceField(
        queryset=SxQcRequest.objects.none(),
        label="YCKT",
        widget=forms.Select(attrs=_FORM_SELECT),
    )
    standard_set = forms.ModelChoiceField(
        queryset=SxQcStandardSet.objects.none(),
        required=False,
        label="Bộ tiêu chuẩn",
        widget=forms.Select(attrs=_FORM_SELECT),
    )
    code = forms.CharField(
        required=False,
        label="Mã PKT",
        help_text="Để trống thì hệ thống tự sinh mã.",
        widget=forms.TextInput(attrs=_FORM_CONTROL),
    )
    inspected_at = forms.DateField(
        label="Ngày kiểm",
        widget=forms.DateInput(attrs=_DATE_SM),
    )
    notes = forms.CharField(
        required=False,
        label="Ghi chú",
        widget=forms.Textarea(attrs={**_FORM_CONTROL, "rows": 2}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["qc_request"].queryset = SxQcRequest.objects.filter(is_demo=False).order_by("-request_date", "-pk")
        self.fields["standard_set"].queryset = SxQcStandardSet.objects.filter(is_demo=False, is_active=True).order_by("code")
        self.fields["standard_set"].empty_label = "— Tự chọn theo mã SP nếu có —"
        self.initial.setdefault("inspected_at", timezone.localdate())


class QcInspectionFinalizeForm(forms.ModelForm):
    class Meta:
        model = SxQcInspection
        fields = ("qty_pass", "qty_fail", "notes")
        widgets = {
            "qty_pass": forms.NumberInput(attrs={**_FORM_CONTROL, "step": "0.01", "min": "0"}),
            "qty_fail": forms.NumberInput(attrs={**_FORM_CONTROL, "step": "0.01", "min": "0"}),
            "notes": forms.Textarea(attrs={**_FORM_CONTROL, "rows": 2}),
        }
        labels = {
            "qty_pass": "Số lượng hoàn thành",
            "qty_fail": "Số lượng lỗi",
            "notes": "Ghi chú",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["qty_pass"].localize = False
        self.fields["qty_fail"].localize = False
        self.fields["qty_pass"].widget.is_localized = False
        self.fields["qty_fail"].widget.is_localized = False

    def clean(self):
        cleaned = super().clean()
        qty_pass = cleaned.get("qty_pass") or 0
        qty_fail = cleaned.get("qty_fail") or 0
        if qty_pass < 0 or qty_fail < 0:
            raise forms.ValidationError("SL đạt/lỗi không được âm.")
        return cleaned


class QcInspectionCriteriaLineForm(forms.ModelForm):
    class Meta:
        model = SxQcInspectionCriteriaLine
        fields = ("is_pass", "notes")
        labels = {
            "is_pass": "Kết quả",
            "notes": "Ghi chú",
        }

    def __init__(self, *args, **kwargs):
        instance = kwargs.get("instance")
        if instance is not None and getattr(instance, "is_pass", None) is None:
            initial = dict(kwargs.get("initial") or {})
            initial.setdefault("is_pass", True)
            kwargs["initial"] = initial
        super().__init__(*args, **kwargs)
        self.fields["is_pass"].widget = forms.NullBooleanSelect(attrs=_FORM_SELECT)
        self.fields["is_pass"].widget.choices = [
            ("true", "Đạt"),
            ("false", "Không đạt"),
            ("unknown", "—"),
        ]
        self.fields["notes"].widget = forms.TextInput(attrs={**_FORM_CONTROL, "placeholder": "Ghi chú"})
        self.fields["notes"].required = False


class QcInspectionDefectLineForm(forms.Form):
    defect = forms.ModelChoiceField(
        queryset=SxQcDefect.objects.none(),
        label="Lỗi",
        widget=forms.Select(attrs=_FORM_SELECT),
    )
    qty = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0"),
        initial=Decimal("0"),
        label="SL lỗi",
        widget=forms.NumberInput(attrs={**_FORM_CONTROL, "step": "0.01", "min": "0"}),
    )
    notes = forms.CharField(
        required=False,
        label="Ghi chú",
        widget=forms.TextInput(attrs=_FORM_CONTROL),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["defect"].queryset = SxQcDefect.objects.filter(is_demo=False, is_active=True).order_by("code")


QcInspectionDefectLineFormSet = formset_factory(QcInspectionDefectLineForm, extra=3, can_delete=False)

