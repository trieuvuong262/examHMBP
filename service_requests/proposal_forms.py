"""Form đề xuất chung (thanh toán, nhân sự, sửa chữa, cấp phát).

Bố cục, trường bắt buộc và điều kiện hiển thị khai báo một chỗ trong ``LAYOUT``.
Template, validate server, dấu * và nhãn trang chi tiết đều đọc từ đây
để không lệch nhau.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django import forms
from django.db.models import Q

from .models import ServiceRequest

EMPTY_CHOICE = [('', '— Chọn —')]


@dataclass(frozen=True)
class Cond:
    """Trường chỉ hiển thị khi ``field`` có giá trị thuộc ``values``."""

    field: str
    values: frozenset

    def holds(self, value) -> bool:
        return str(value or '') in self.values


def when(field: str, *values: str) -> Cond:
    return Cond(field, frozenset(values))


@dataclass(frozen=True)
class FieldSpec:
    name: str
    col: str = 'col-md-6'
    # Bắt buộc khi trường đang hiển thị (show_when None → luôn hiển thị).
    required: bool = False
    show_when: Cond | None = None


@dataclass(frozen=True)
class Section:
    title: str
    icon: str
    fields: tuple


S = ServiceRequest

LAYOUT = {
    S.SUBTYPE_PAYMENT: (
        Section('Thông tin chi', 'bi-cash-coin', (
            FieldSpec('payment_kind', 'col-md-4', required=True),
            FieldSpec('payment_amount', 'col-md-4', required=True),
            FieldSpec('due_date', 'col-md-4', required=True),
            FieldSpec('advance_settle_date', 'col-md-4', required=True,
                      show_when=when('payment_kind', 'advance')),
            FieldSpec('advance_ref', 'col-md-8', required=True,
                      show_when=when('payment_kind', 'reimbursement')),
            FieldSpec('invoice_no', 'col-md-8',
                      show_when=when('payment_kind', 'payment', 'reimbursement')),
        )),
        Section('Người nhận tiền', 'bi-person-badge', (
            FieldSpec('payee', 'col-md-8', required=True),
            FieldSpec('payment_method', 'col-md-4', required=True),
            FieldSpec('bank_account', 'col-12', required=True,
                      show_when=when('payment_method', 'transfer')),
        )),
    ),
    # Yêu cầu ứng viên — duyệt xong tạo vị trí tuyển dụng «Nháp» (recruitment).
    S.SUBTYPE_CANDIDATE: (
        Section('Vị trí cần tuyển', 'bi-person-plus', (
            FieldSpec('position', 'col-md-6', required=True),
            FieldSpec('headcount', 'col-md-3', required=True),
            FieldSpec('desired_date', 'col-md-3', required=True),
            FieldSpec('target_department', 'col-md-6', required=True),
            FieldSpec('target_division', 'col-md-6'),
            FieldSpec('recruit_reason', 'col-md-6', required=True),
        )),
        Section('Yêu cầu ứng viên', 'bi-person-check', (
            FieldSpec('candidate_requirements', 'col-12', required=True),
        )),
    ),
    # Tuyển dụng đã tách sang «Yêu cầu ứng viên» — loại này chỉ còn điều chuyển.
    S.SUBTYPE_HR: (
        Section('Điều chuyển', 'bi-arrow-left-right', (
            FieldSpec('transfer_employee', 'col-md-6', required=True),
            FieldSpec('new_position', 'col-md-6'),
            FieldSpec('from_department', 'col-md-4', required=True),
            FieldSpec('to_department', 'col-md-4', required=True),
            FieldSpec('effective_date', 'col-md-4', required=True),
        )),
    ),
    S.SUBTYPE_REPAIR: (
        Section('Sự cố', 'bi-exclamation-triangle', (
            FieldSpec('incident_category', 'col-md-6', required=True),
            FieldSpec('priority', 'col-md-6', required=True),
            FieldSpec('location_text', 'col-md-8', required=True),
            FieldSpec('occurred_on', 'col-md-4'),
            FieldSpec('blocks_work', 'col-12'),
        )),
        Section('Thiết bị / tài sản', 'bi-pc-display', (
            FieldSpec('equipment_label', 'col-md-6'),
            FieldSpec('equipment_serial', 'col-md-6'),
        )),
    ),
    S.SUBTYPE_ACCOUNT: (
        Section('Nội dung cấp phát', 'bi-laptop', (
            FieldSpec('account_kind', 'col-md-6', required=True),
            FieldSpec('needed_date', 'col-md-6', required=True),
            FieldSpec('system_name', 'col-md-6', required=True, show_when=when('account_kind', 'account')),
            FieldSpec('access_level', 'col-md-6', show_when=when('account_kind', 'account')),
            FieldSpec('device_spec', 'col-12', required=True, show_when=when('account_kind', 'computer')),
            FieldSpec('email_address', 'col-md-6', show_when=when('account_kind', 'email')),
        )),
        Section('Người được cấp', 'bi-person', (
            FieldSpec('target_user', 'col-md-6', required=True),
            FieldSpec('target_employee_code', 'col-md-3'),
            FieldSpec('account_department', 'col-md-3', required=True),
        )),
    ),
}

DESCRIPTION_LABELS = {
    S.SUBTYPE_PAYMENT: 'Nội dung chi / lý do',
    S.SUBTYPE_CANDIDATE: 'Mô tả công việc',
    S.SUBTYPE_HR: 'Lý do điều chuyển',
    S.SUBTYPE_REPAIR: 'Mô tả hiện tượng sự cố',
    S.SUBTYPE_ACCOUNT: 'Mục đích sử dụng',
}

TITLE_PLACEHOLDERS = {
    S.SUBTYPE_PAYMENT: 'VD: Thanh toán tiền điện tháng 9',
    S.SUBTYPE_CANDIDATE: 'VD: Tuyển 3 công nhân may chuyền 2',
    S.SUBTYPE_HR: 'VD: Điều chuyển nhân viên sang chuyền 3',
    S.SUBTYPE_REPAIR: 'VD: Máy may chuyền 2 không chạy',
    S.SUBTYPE_ACCOUNT: 'VD: Cấp email cho nhân viên mới',
}


def _department_queryset():
    from hrm.models import Department

    return Department.objects.order_by('sort_order', 'name')


def _date_input():
    return forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')


class GeneralProposalForm(forms.Form):
    """Form các loại đề xuất phi mua hàng.

    Mọi field riêng theo loại đều ``required=False`` ở mức field; bắt buộc
    thực tế được quyết định trong ``clean()`` dựa trên ``LAYOUT`` + điều kiện hiển thị.
    """

    title = forms.CharField(label='Tiêu đề', max_length=200)
    description = forms.CharField(label='Nội dung chi tiết', widget=forms.Textarea(attrs={'rows': 4}))

    # --- Thanh toán / tạm ứng / hoàn ứng ---
    payment_kind = forms.ChoiceField(
        label='Hình thức', required=False,
        choices=EMPTY_CHOICE + [
            ('payment', 'Thanh toán'),
            ('advance', 'Tạm ứng'),
            ('reimbursement', 'Hoàn ứng'),
        ],
    )
    payment_amount = forms.DecimalField(
        label='Số tiền (VNĐ)', required=False, min_value=Decimal('1'), max_digits=14, decimal_places=0,
        widget=forms.NumberInput(attrs={'min': 1, 'step': 1, 'placeholder': 'VD: 5000000', 'inputmode': 'numeric'}),
    )
    due_date = forms.DateField(label='Ngày cần chi', required=False, widget=_date_input())
    advance_settle_date = forms.DateField(label='Ngày dự kiến hoàn ứng', required=False, widget=_date_input())
    advance_ref = forms.CharField(
        label='Phiếu tạm ứng đã nhận', required=False, max_length=200,
        widget=forms.TextInput(attrs={'placeholder': 'Số phiếu / ngày tạm ứng trước đó'}),
    )
    invoice_no = forms.CharField(
        label='Số hóa đơn / chứng từ', required=False, max_length=200,
        widget=forms.TextInput(attrs={'placeholder': 'VD: HĐ 0001234'}),
    )
    payee = forms.CharField(
        label='Người / đơn vị thụ hưởng', required=False, max_length=200,
        widget=forms.TextInput(attrs={'placeholder': 'Tên người hoặc đơn vị nhận tiền'}),
    )
    payment_method = forms.ChoiceField(
        label='Phương thức', required=False,
        choices=EMPTY_CHOICE + [('transfer', 'Chuyển khoản'), ('cash', 'Tiền mặt')],
    )
    bank_account = forms.CharField(
        label='Số tài khoản · Ngân hàng', required=False, max_length=200,
        widget=forms.TextInput(attrs={'placeholder': 'VD: 0123456789 · Vietcombank CN Bình Dương'}),
    )

    # --- Tuyển dụng / điều chuyển ---
    hr_kind = forms.ChoiceField(
        label='Loại yêu cầu', required=False,
        choices=EMPTY_CHOICE + [('recruit', 'Tuyển dụng'), ('transfer', 'Điều chuyển')],
    )
    position = forms.CharField(
        label='Vị trí / chức danh', required=False, max_length=200,
        widget=forms.TextInput(attrs={'placeholder': 'VD: Công nhân may, Nhân viên kho'}),
    )
    target_department = forms.ModelChoiceField(
        label='Phòng ban cần nhân sự', required=False, queryset=None, empty_label='— Chọn —',
    )
    target_division = forms.ModelChoiceField(
        label='Bộ phận', required=False, queryset=None, empty_label='— Cả phòng ban —',
    )
    headcount = forms.IntegerField(
        label='Số lượng', required=False, min_value=1, max_value=500,
        widget=forms.NumberInput(attrs={'min': 1, 'placeholder': 'VD: 2'}),
    )
    recruit_reason = forms.ChoiceField(
        label='Lý do tuyển', required=False,
        choices=EMPTY_CHOICE + [
            ('replacement', 'Thay thế nhân sự nghỉ việc'),
            ('addition', 'Bổ sung định biên'),
            ('expansion', 'Mở rộng sản xuất / dự án mới'),
        ],
    )
    desired_date = forms.DateField(label='Ngày cần nhân sự', required=False, widget=_date_input())
    candidate_requirements = forms.CharField(
        label='Yêu cầu ứng viên', required=False,
        widget=forms.Textarea(attrs={'rows': 2, 'placeholder': 'Kinh nghiệm, kỹ năng, độ tuổi... (tuỳ chọn)'}),
    )
    transfer_employee = forms.CharField(
        label='Nhân viên được điều chuyển', required=False, max_length=200,
        widget=forms.TextInput(attrs={'placeholder': 'Họ tên – Mã NV'}),
    )
    new_position = forms.CharField(
        label='Vị trí mới', required=False, max_length=200,
        widget=forms.TextInput(attrs={'placeholder': 'Bỏ trống nếu giữ nguyên'}),
    )
    from_department = forms.ModelChoiceField(
        label='Từ phòng ban', required=False, queryset=None, empty_label='— Chọn —',
    )
    to_department = forms.ModelChoiceField(
        label='Đến phòng ban', required=False, queryset=None, empty_label='— Chọn —',
    )
    effective_date = forms.DateField(label='Ngày hiệu lực', required=False, widget=_date_input())

    # --- Sửa chữa máy móc / IT / CSVC ---
    incident_category = forms.ChoiceField(
        label='Loại sự cố', required=False,
        choices=EMPTY_CHOICE + [
            ('hw', 'Phần cứng máy tính'),
            ('sw', 'Phần mềm'),
            ('network', 'Mạng / Internet'),
            ('account', 'Tài khoản / quyền truy cập'),
            ('machine', 'Máy móc / thiết bị sản xuất'),
            ('facility', 'Cơ sở vật chất'),
            ('other', 'Khác'),
        ],
    )
    priority = forms.ChoiceField(
        label='Mức độ ưu tiên', required=False,
        choices=EMPTY_CHOICE + list(ServiceRequest.PRIORITY_CHOICES),
        initial=ServiceRequest.PRIORITY_NORMAL,
    )
    location_text = forms.CharField(
        label='Vị trí', required=False, max_length=200,
        widget=forms.TextInput(attrs={'placeholder': 'VD: Xưởng may — Chuyền 2'}),
    )
    occurred_on = forms.DateField(label='Ngày phát sinh', required=False, widget=_date_input())
    blocks_work = forms.BooleanField(label='Sự cố đang làm dừng công việc / sản xuất', required=False)
    equipment_label = forms.CharField(
        label='Tên / mã thiết bị', required=False, max_length=200,
        widget=forms.TextInput(attrs={'placeholder': 'VD: Máy may Juki DDL-8700'}),
    )
    equipment_serial = forms.CharField(
        label='Serial', required=False, max_length=100,
        widget=forms.TextInput(attrs={'placeholder': 'Số serial (nếu có)'}),
    )

    # --- Cấp phát tài khoản / máy tính / email ---
    account_kind = forms.ChoiceField(
        label='Loại cấp phát', required=False,
        choices=EMPTY_CHOICE + [
            ('account', 'Tài khoản hệ thống'),
            ('computer', 'Máy tính'),
            ('email', 'Email'),
            ('other', 'Khác'),
        ],
    )
    needed_date = forms.DateField(label='Ngày cần cấp', required=False, widget=_date_input())
    system_name = forms.CharField(
        label='Hệ thống / phần mềm', required=False, max_length=200,
        widget=forms.TextInput(attrs={'placeholder': 'VD: Portal, phần mềm kế toán, NAS'}),
    )
    access_level = forms.CharField(
        label='Quyền cần cấp', required=False, max_length=200,
        widget=forms.TextInput(attrs={'placeholder': 'VD: Xem, nhập liệu, quản trị'}),
    )
    device_spec = forms.CharField(
        label='Loại máy / cấu hình', required=False,
        widget=forms.Textarea(attrs={'rows': 2, 'placeholder': 'VD: Laptop văn phòng, RAM 16GB, cài Office'}),
    )
    email_address = forms.CharField(
        label='Địa chỉ email đề xuất', required=False, max_length=200,
        widget=forms.TextInput(attrs={'placeholder': 'VD: ten.ho@justplay.vn'}),
    )
    target_user = forms.CharField(
        label='Họ tên người được cấp', required=False, max_length=200,
        widget=forms.TextInput(attrs={'placeholder': 'Tên nhân viên được cấp'}),
    )
    target_employee_code = forms.CharField(label='Mã NV', required=False, max_length=50)
    account_department = forms.ModelChoiceField(
        label='Phòng ban', required=False, queryset=None, empty_label='— Chọn —',
    )

    # Trường lưu vào cột model, không đưa vào extra_data.
    MODEL_FIELDS = frozenset({'payment_amount'})

    def __init__(self, *args, subtype=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from hrm.models import Division

        self.subtype = subtype
        self.user = user
        self.recruit_scope = None
        departments = _department_queryset()
        for name in ('target_department', 'from_department', 'to_department', 'account_department'):
            self.fields[name].queryset = departments
        divisions = Division.objects.filter(is_active=True, department__isnull=False).select_related('department')

        if subtype == S.SUBTYPE_CANDIDATE and user is not None:
            # Chỉ yêu cầu người cho phòng ban / bộ phận mình quản lý.
            from recruitment.permissions import managed_scope

            scope = managed_scope(user)
            self.recruit_scope = scope
            if not scope.all:
                div_dept_ids = set(
                    Division.objects.filter(pk__in=scope.division_ids).values_list('department_id', flat=True)
                )
                self.fields['target_department'].queryset = departments.filter(
                    pk__in=scope.department_ids | div_dept_ids,
                )
                divisions = divisions.filter(
                    Q(department_id__in=scope.department_ids) | Q(pk__in=scope.division_ids)
                )
        self.fields['target_division'].queryset = divisions.order_by('department__sort_order', 'sort_order', 'name')
        self.fields['target_division'].label_from_instance = lambda d: f'{d.department.name} · {d.name}'
        if subtype == S.SUBTYPE_CANDIDATE:
            self.fields['target_department'].label = 'Phòng ban'
            self.fields['candidate_requirements'].widget.attrs['rows'] = 3

        self.fields['title'].widget.attrs['placeholder'] = TITLE_PLACEHOLDERS.get(subtype, '')
        self.fields['description'].label = DESCRIPTION_LABELS.get(subtype, 'Nội dung chi tiết')

        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                css = 'form-check-input'
            elif isinstance(widget, forms.Select):
                css = 'form-select'
            else:
                css = 'form-control'
            widget.attrs['class'] = f"{widget.attrs.get('class', '')} {css}".strip()

    # ---- bố cục ----

    def layout(self):
        return LAYOUT.get(self.subtype, ())

    def specs(self):
        for section in self.layout():
            yield from section.fields

    def _controller_value(self, name):
        if hasattr(self, 'cleaned_data') and name in self.cleaned_data:
            return self.cleaned_data.get(name)
        return self[name].value()

    def is_visible(self, spec: FieldSpec) -> bool:
        if spec.show_when is None:
            return True
        return spec.show_when.holds(self._controller_value(spec.show_when.field))

    def sections(self):
        """Dữ liệu render cho template — mỗi trường kèm cờ bắt buộc và điều kiện hiển thị."""
        rendered = []
        for section in self.layout():
            fields = []
            for spec in section.fields:
                fields.append({
                    'field': self[spec.name],
                    'col': spec.col,
                    'required': spec.required,
                    'is_checkbox': isinstance(self.fields[spec.name].widget, forms.CheckboxInput),
                    'show_field': spec.show_when.field if spec.show_when else '',
                    'show_values': ','.join(sorted(spec.show_when.values)) if spec.show_when else '',
                    'visible': self.is_visible(spec),
                })
            controllers = {f['show_field'] for f in fields if f['show_field']}
            # Section toàn trường có điều kiện cùng controller → ẩn/hiện cả khối.
            section_show = ''
            section_values = ''
            if fields and len(controllers) == 1 and all(f['show_field'] for f in fields):
                values = {f['show_values'] for f in fields}
                if len(values) == 1:
                    section_show = fields[0]['show_field']
                    section_values = fields[0]['show_values']
            rendered.append({
                'title': section.title,
                'icon': section.icon,
                'fields': fields,
                'show_field': section_show,
                'show_values': section_values,
                'visible': any(f['visible'] for f in fields),
            })
        return rendered

    # ---- validate ----

    def clean(self):
        cleaned = super().clean()
        if self.subtype not in LAYOUT:
            raise forms.ValidationError('Loại đề xuất không hợp lệ.')

        for spec in self.specs():
            if not self.is_visible(spec):
                cleaned[spec.name] = None
                self.errors.pop(spec.name, None)
                continue
            if spec.required and cleaned.get(spec.name) in (None, '', False):
                if spec.name not in self.errors:
                    self.add_error(spec.name, 'Trường này là bắt buộc.')

        if self.subtype == S.SUBTYPE_CANDIDATE:
            self._clean_candidate_scope(cleaned)

        if self.subtype == S.SUBTYPE_HR:
            src, dst = cleaned.get('from_department'), cleaned.get('to_department')
            if src and dst and src == dst:
                self.add_error('to_department', 'Phòng ban mới phải khác phòng ban hiện tại.')

        if self.subtype == S.SUBTYPE_PAYMENT and cleaned.get('payment_kind') == 'advance':
            due, settle = cleaned.get('due_date'), cleaned.get('advance_settle_date')
            if due and settle and settle < due:
                self.add_error('advance_settle_date', 'Ngày hoàn ứng phải sau ngày nhận tạm ứng.')
        return cleaned

    def _clean_candidate_scope(self, cleaned):
        dept, div = cleaned.get('target_department'), cleaned.get('target_division')
        if div and dept and div.department_id != dept.pk:
            self.add_error('target_division', 'Bộ phận không thuộc phòng ban đã chọn.')
            return
        scope = self.recruit_scope
        if scope is None or not dept or scope.all:
            return
        in_scope = dept.pk in scope.department_ids or bool(div and div.pk in scope.division_ids)
        if not in_scope:
            self.add_error(
                'target_division' if dept.pk not in scope.department_ids else 'target_department',
                'Chỉ yêu cầu ứng viên cho phòng ban / bộ phận bạn quản lý.',
            )

    # ---- lưu ----

    def extra_data(self):
        """Gom trường riêng theo loại (đang hiển thị) thành dict nhãn dễ đọc để lưu ``extra_data``."""
        data = {}
        for spec in self.specs():
            if spec.name in self.MODEL_FIELDS or not self.is_visible(spec):
                continue
            value = self.cleaned_data.get(spec.name)
            if value in (None, '', False):
                continue
            field = self.fields[spec.name]
            if isinstance(field, forms.ModelChoiceField):
                value = str(value)
            elif isinstance(field, forms.ChoiceField):
                value = dict(field.choices).get(value, value)
            elif isinstance(field, forms.BooleanField):
                value = 'Có'
            elif hasattr(value, 'strftime'):
                value = value.strftime('%d/%m/%Y')
            data[spec.name] = value
        return data


def extra_field_labels(subtype) -> dict:
    """Nhãn hiển thị cho khoá extra_data của một loại đề xuất (trang chi tiết)."""
    labels = {}
    form_fields = GeneralProposalForm.base_fields
    for section in LAYOUT.get(subtype, ()):
        for spec in section.fields:
            labels[spec.name] = form_fields[spec.name].label
    if subtype == S.SUBTYPE_PURCHASE:
        labels.update(PURCHASE_EXTRA_LABELS)
    return labels


PURCHASE_EXTRA_LABELS = {
    'needed_by': 'Ngày cần hàng',
    'usage_location': 'Nơi sử dụng',
}
