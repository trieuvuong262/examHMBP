from odoo import fields, models


class JustplaySxProcessRoute(models.Model):
    _name = 'justplay.sx.process.route'
    _description = 'Quy trình SX (placeholder)'
    _order = 'sequence, id'

    name = fields.Char(string='Tên công đoạn', required=True)
    sequence = fields.Integer(default=10)
    product_code = fields.Char(string='Mã SP áp dụng')
    workcenter = fields.Char(string='Tổ / máy')
    duration_hours = fields.Float(string='Giờ định mức', default=1.0)
    note = fields.Text(
        default=(
            'Quy trình scaffold. Sau: port ProcessStep Portal → mrp.routing.workcenter.'
        ),
    )
    active = fields.Boolean(default=True)
