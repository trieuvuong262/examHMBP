from odoo import fields, models


class JustplaySxQcCheck(models.Model):
    _name = 'justplay.sx.qc.check'
    _description = 'Kiểm tra chất lượng (placeholder)'
    _order = 'date_check desc, id desc'

    name = fields.Char(string='Phiếu QC', required=True, default='New')
    date_check = fields.Date(string='Ngày', default=fields.Date.context_today)
    product_code = fields.Char(string='Mã SP')
    plan_id = fields.Many2one('justplay.sx.plan', string='Kế hoạch', ondelete='set null')
    result = fields.Selection(
        [
            ('pending', 'Chờ'),
            ('pass', 'Đạt'),
            ('fail', 'Không đạt'),
        ],
        default='pending',
        required=True,
    )
    note = fields.Text(
        default=(
            'QC scaffold. Sau có thể dùng Odoo Quality hoặc rule JustPlay.\n'
            'Chưa ràng buộc chứng từ kho.'
        ),
    )
