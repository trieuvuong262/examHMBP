from django import forms

from audit.models import RustDeskHost
from audit.services.wake_on_lan import normalize_mac


class RustDeskHostForm(forms.ModelForm):
    class Meta:
        model = RustDeskHost
        fields = [
            'name',
            'hostname',
            'ip_address',
            'mac_address',
            'rustdesk_id',
            'rustdesk_password',
            'department_text',
            'assigned_user_text',
            'notes',
            'device',
            'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'VD: PC Kế toán — Nguyễn A'}),
            'hostname': forms.TextInput(attrs={'class': 'form-control'}),
            'ip_address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '192.168.x.x'}),
            'mac_address': forms.TextInput(attrs={
                'class': 'form-control font-monospace',
                'placeholder': 'AA:BB:CC:DD:EE:FF',
                'autocomplete': 'off',
            }),
            'rustdesk_id': forms.TextInput(attrs={
                'class': 'form-control font-monospace',
                'placeholder': '258 599 030',
                'inputmode': 'numeric',
                'autocomplete': 'off',
            }),
            'rustdesk_password': forms.TextInput(attrs={
                'class': 'form-control font-monospace',
                'autocomplete': 'off',
            }),
            'department_text': forms.TextInput(attrs={'class': 'form-control'}),
            'assigned_user_text': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'device': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from equipment.models import Device
        from equipment.scope import filter_devices_for_scope, SCOPE_IT

        self.fields['device'].queryset = filter_devices_for_scope(
            Device.objects.order_by('device_code'),
            SCOPE_IT,
        )
        self.fields['device'].required = False
        self.fields['rustdesk_id'].label = 'RustDesk ID'
        self.fields['mac_address'].label = 'MAC (Wake-on-LAN)'
        self.fields['mac_address'].required = False
        self.fields['mac_address'].help_text = (
            'Tùy chọn — dùng để bật máy từ xa. Có thể lấy từ thiết bị IT liên kết.'
        )
        self.fields['rustdesk_password'].label = 'RustDesk mật khẩu'
        self.fields['rustdesk_password'].required = False

    def clean_rustdesk_id(self):
        raw = (self.cleaned_data.get('rustdesk_id') or '').strip()
        if not raw:
            raise forms.ValidationError('RustDesk ID là bắt buộc.')
        digits = ''.join(c for c in raw if c.isdigit())
        if not digits:
            raise forms.ValidationError('RustDesk ID chỉ gồm chữ số.')
        if len(digits) < 6:
            raise forms.ValidationError('RustDesk ID quá ngắn.')
        return digits

    def clean_mac_address(self):
        raw = (self.cleaned_data.get('mac_address') or '').strip()
        if not raw:
            return ''
        return normalize_mac(raw)

    def clean_rustdesk_password(self):
        return (self.cleaned_data.get('rustdesk_password') or '').strip()[:128]
