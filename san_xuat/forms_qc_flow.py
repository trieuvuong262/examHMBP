"""Form phiếu QC inline / endline / preaudit."""

from __future__ import annotations

from django import forms
from django.utils import timezone

from san_xuat.hub_models import SxProductionOrder, SxQcFlowCheck
from san_xuat.services.progress_template import TEAM_SLUGS
from san_xuat.services.qc_flow import inline_stages_for_team, stage_belongs_to_team

_INPUT = {'class': 'form-control form-control-sm'}
_SELECT = {'class': 'form-select form-select-sm'}

TEAM_CHOICES = [('', '—')] + [(slug, label) for slug, _gk, _mk, label in TEAM_SLUGS]
AQL_CHOICES = [
    ('1.0', '1.0'),
    ('1.5', '1.5'),
    ('2.5', '2.5'),
    ('4.0', '4.0'),
]
LEVEL_CHOICES = [
    ('I', 'I'),
    ('II', 'II'),
    ('III', 'III'),
    ('S-4', 'S-4'),
]


class QcFlowCheckForm(forms.Form):
    production_order = forms.ModelChoiceField(
        label='Lệnh sản xuất',
        queryset=SxProductionOrder.objects.none(),
        widget=forms.Select(attrs=_SELECT),
    )
    team_slug = forms.ChoiceField(
        label='Tổ',
        required=False,
        choices=TEAM_CHOICES,
        widget=forms.Select(attrs=_SELECT),
    )
    stage_name = forms.ChoiceField(
        label='Công đoạn',
        required=False,
        choices=[('', '— Chọn tổ trước —')],
        widget=forms.Select(attrs=_SELECT),
        error_messages={'invalid_choice': 'Công đoạn không thuộc tổ đã chọn.'},
    )
    checked_on = forms.DateField(
        label='Ngày kiểm',
        input_formats=['%Y-%m-%d', '%d/%m/%Y'],
        widget=forms.DateInput(format='%Y-%m-%d', attrs={**_INPUT, 'type': 'date'}),
    )
    qty_lot = forms.DecimalField(
        label='Cỡ lô',
        required=False,
        min_value=0,
        decimal_places=2,
        widget=forms.NumberInput(attrs={**_INPUT, 'step': '1', 'min': '0'}),
    )
    qty_checked = forms.DecimalField(
        label='SL kiểm',
        required=False,
        min_value=0,
        decimal_places=2,
        widget=forms.NumberInput(attrs={**_INPUT, 'step': '1', 'min': '0'}),
    )
    qty_pass = forms.DecimalField(
        label='SL đạt',
        required=False,
        min_value=0,
        decimal_places=2,
        widget=forms.NumberInput(attrs={**_INPUT, 'step': '1', 'min': '0'}),
    )
    qty_repair = forms.DecimalField(
        label='SL sửa',
        required=False,
        min_value=0,
        decimal_places=2,
        widget=forms.NumberInput(attrs={**_INPUT, 'step': '1', 'min': '0'}),
    )
    qty_fail = forms.DecimalField(
        label='SL lỗi',
        required=False,
        min_value=0,
        decimal_places=2,
        widget=forms.NumberInput(attrs={**_INPUT, 'step': '1', 'min': '0'}),
    )
    aql_level = forms.ChoiceField(
        label='AQL (%)',
        required=False,
        choices=AQL_CHOICES,
        widget=forms.Select(attrs=_SELECT),
    )
    inspection_level = forms.ChoiceField(
        label='Mức kiểm',
        required=False,
        choices=LEVEL_CHOICES,
        widget=forms.Select(attrs=_SELECT),
    )
    notes = forms.CharField(
        label='Ghi chú',
        required=False,
        widget=forms.Textarea(attrs={**_INPUT, 'rows': 2}),
    )

    def __init__(self, *args, flow: str, mo: SxProductionOrder | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.flow = flow
        open_status = [
            SxProductionOrder.STATUS_RELEASED,
            SxProductionOrder.STATUS_IN_PROGRESS,
            SxProductionOrder.STATUS_DONE,
        ]
        base = SxProductionOrder.objects.filter(is_demo=False, status__in=open_status).order_by('-order_date', '-pk')
        ids = list(base.values_list('pk', flat=True)[:300])
        if mo is not None and mo.pk and mo.pk not in ids:
            ids.append(mo.pk)
        self.fields['production_order'].queryset = (
            SxProductionOrder.objects.filter(pk__in=ids).order_by('-order_date', '-pk')
        )
        self.fields['production_order'].label_from_instance = (
            lambda item: f'{item.code} · {item.product_name or item.product_code}'
        )
        if not self.is_bound and 'checked_on' not in self.initial:
            self.initial['checked_on'] = timezone.localdate()
        if flow == SxQcFlowCheck.FLOW_INLINE:
            self.fields['team_slug'].required = True
            self.fields['stage_name'].required = True
            team = ''
            extra = ''
            if self.is_bound:
                team = (self.data.get('team_slug') or '').strip().lower()
                extra = (self.data.get('stage_name') or '').strip()
            else:
                team = (self.initial.get('team_slug') or '').strip().lower()
                extra = (self.initial.get('stage_name') or '').strip()
            labels = inline_stages_for_team(team)
            placeholder = '— Chọn công đoạn —' if labels else '— Chọn tổ trước —'
            choices = [('', placeholder)] + [(label, label) for label in labels]
            if extra and extra.casefold() not in {label.casefold() for label in labels}:
                choices.append((extra, f'{extra} (không thuộc tổ)'))
            self.fields['stage_name'].choices = choices
            for name in ('qty_lot', 'qty_checked', 'qty_pass', 'qty_repair', 'qty_fail', 'aql_level', 'inspection_level'):
                self.fields.pop(name, None)
        elif flow == SxQcFlowCheck.FLOW_ENDLINE:
            self.fields['team_slug'].required = True
            for name in ('stage_name', 'qty_lot', 'qty_checked', 'qty_pass', 'qty_repair', 'qty_fail', 'aql_level', 'inspection_level'):
                self.fields.pop(name, None)
        else:
            self.fields['qty_lot'].required = True
            for name in (
                'team_slug', 'stage_name', 'qty_checked', 'qty_pass', 'qty_repair', 'qty_fail',
                'aql_level', 'inspection_level',
            ):
                self.fields.pop(name, None)

    def clean(self):
        cleaned = super().clean()
        if self.flow != SxQcFlowCheck.FLOW_INLINE:
            return cleaned
        team = (cleaned.get('team_slug') or '').strip().lower()
        stage = (cleaned.get('stage_name') or '').strip()
        if team and stage and not stage_belongs_to_team(stage, team):
            self.add_error('stage_name', 'Công đoạn không thuộc tổ đã chọn.')
        return cleaned
