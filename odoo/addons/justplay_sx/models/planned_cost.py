from odoo import api, fields, models


class JustplaySxPlannedCost(models.Model):
    _name = 'justplay.sx.planned.cost'
    _description = 'Giá thành kế hoạch (placeholder)'
    _order = 'id desc'

    name = fields.Char(string='Bảng giá thành', required=True)
    product_code = fields.Char(string='Mã SP')
    plan_id = fields.Many2one('justplay.sx.plan', string='Kế hoạch', ondelete='set null')
    material_cost = fields.Float(string='NVL (dự kiến)')
    labor_cost = fields.Float(string='Nhân công (dự kiến)')
    overhead_cost = fields.Float(string='Chi phí chung')
    total_cost = fields.Float(string='Tổng', compute='_compute_total', store=True)
    note = fields.Text(
        default=(
            'Placeholder giá thành kế hoạch.\n'
            'Sau: port từ Portal san_xuat CostingSnapshot / BOM Odoo.'
        ),
    )

    @api.depends('material_cost', 'labor_cost', 'overhead_cost')
    def _compute_total(self):
        for rec in self:
            rec.total_cost = (rec.material_cost or 0) + (rec.labor_cost or 0) + (rec.overhead_cost or 0)
