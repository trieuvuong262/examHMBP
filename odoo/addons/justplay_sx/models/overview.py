from odoo import fields, models


class JustplaySxOverview(models.Model):
    _name = 'justplay.sx.overview'
    _description = 'Tổng quan SX (placeholder)'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    kpi_value = fields.Char(string='Giá trị')
    note = fields.Text(
        default=(
            'Dashboard KPI sẽ tổng hợp SO / kế hoạch / LSX / tồn NPL+TP.\n'
            'Hiện tại chỉ là placeholder scaffold.'
        ),
    )
    active = fields.Boolean(default=True)
