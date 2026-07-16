from odoo import fields, models


class JustplaySxSaleOrder(models.Model):
    _name = 'justplay.sx.sale.order'
    _description = 'Đơn đặt hàng SX (stub — chưa dùng sale.order)'
    _order = 'date_order desc, id desc'
    _rec_name = 'name'

    name = fields.Char(string='Số đơn', required=True, copy=False, default='New')
    partner_name = fields.Char(string='Khách hàng', required=True)
    date_order = fields.Date(string='Ngày đơn', default=fields.Date.context_today, required=True)
    product_code = fields.Char(string='Mã SP (KV)', help='Mã thành phẩm KiotViet / Odoo default_code')
    product_name = fields.Char(string='Tên SP')
    qty = fields.Float(string='Số lượng', default=1.0, required=True)
    state = fields.Selection(
        [
            ('draft', 'Nháp'),
            ('confirmed', 'Xác nhận'),
            ('planned', 'Đã lập KH'),
            ('done', 'Xong'),
            ('cancel', 'Hủy'),
        ],
        default='draft',
        required=True,
    )
    note = fields.Text(
        string='Ghi chú scaffold',
        default=(
            'Stub SO JustPlay. Sau này: bridge đơn KiotViet hoặc map sang sale.order.\n'
            'Luồng: Xác nhận SO → Tạo kế hoạch SX → Tạo LSX (MO).'
        ),
    )
    plan_ids = fields.One2many('justplay.sx.plan', 'sale_order_id', string='Kế hoạch')

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_create_plan(self):
        Plan = self.env['justplay.sx.plan']
        for order in self:
            if order.state == 'cancel':
                continue
            plan = Plan.create({
                'name': f'KH/{order.name}',
                'sale_order_id': order.id,
                'date_start': fields.Date.context_today(order),
                'line_ids': [(0, 0, {
                    'product_code': order.product_code or '',
                    'product_name': order.product_name or order.partner_name,
                    'qty': order.qty,
                })],
            })
            order.write({'state': 'planned'})
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'justplay.sx.plan',
                'res_id': plan.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return True
