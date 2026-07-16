from odoo import fields, models


class JustplaySxDispatch(models.Model):
    _name = 'justplay.sx.dispatch'
    _description = 'Điều phối SX (placeholder)'
    _order = 'date_dispatch desc, id desc'

    name = fields.Char(string='Phiếu ĐP', required=True, default='New')
    date_dispatch = fields.Date(string='Ngày', default=fields.Date.context_today, required=True)
    team = fields.Char(string='Tổ / chuyền')
    plan_id = fields.Many2one('justplay.sx.plan', string='Kế hoạch', ondelete='set null')
    state = fields.Selection(
        [
            ('draft', 'Nháp'),
            ('assigned', 'Đã gán'),
            ('done', 'Xong'),
            ('cancel', 'Hủy'),
        ],
        default='draft',
        required=True,
    )
    note = fields.Text(
        default=(
            'Bảng điều phối scaffold (kanban theo tổ/ngày).\n'
            'Sau: gán LSX / ca làm việc thực tế.'
        ),
    )
