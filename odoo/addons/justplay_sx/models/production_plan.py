from odoo import fields, models
from odoo.exceptions import UserError


class JustplaySxPlan(models.Model):
    _name = 'justplay.sx.plan'
    _description = 'Kế hoạch sản xuất'
    _order = 'date_start desc, id desc'

    name = fields.Char(string='Mã KH', required=True, default='New')
    sale_order_id = fields.Many2one('justplay.sx.sale.order', string='Đơn đặt hàng', ondelete='set null')
    date_start = fields.Date(string='Bắt đầu', default=fields.Date.context_today)
    date_end = fields.Date(string='Kết thúc dự kiến')
    state = fields.Selection(
        [
            ('draft', 'Nháp'),
            ('ready', 'Sẵn sàng'),
            ('released', 'Đã phát LSX'),
            ('done', 'Xong'),
            ('cancel', 'Hủy'),
        ],
        default='draft',
        required=True,
    )
    note = fields.Text(
        default=(
            'Kế hoạch SX scaffold. Nút «Tạo LSX» tạo mrp.production (demo) nếu có MRP.\n'
            'SoT nghiệp vụ đầy đủ sẽ bổ sung sau.'
        ),
    )
    line_ids = fields.One2many('justplay.sx.plan.line', 'plan_id', string='Dòng KH')
    mo_count = fields.Integer(compute='_compute_mo_count', string='Số LSX')

    def _compute_mo_count(self):
        Production = self.env['mrp.production'].sudo()
        for plan in self:
            plan.mo_count = Production.search_count([
                ('origin', '=', plan.name),
            ])

    def action_set_ready(self):
        self.write({'state': 'ready'})

    def action_create_mo(self):
        """Tạo LSX (mrp.production) demo từ dòng kế hoạch."""
        if 'mrp.production' not in self.env:
            raise UserError('Module Manufacturing (mrp) chưa cài.')

        Production = self.env['mrp.production']
        Product = self.env['product.product']
        created = self.env['mrp.production']

        for plan in self:
            if not plan.line_ids:
                raise UserError('Kế hoạch chưa có dòng sản phẩm.')
            for line in plan.line_ids:
                product = False
                code = (line.product_code or '').strip()
                if code:
                    product = Product.search([('default_code', '=', code)], limit=1)
                if not product:
                    # Tạo product tiêu thụ tạm cho demo LSX
                    tmpl = self.env['product.template'].create({
                        'name': line.product_name or code or f'Demo {plan.name}',
                        'default_code': code or False,
                        'type': 'consu',
                        'is_storable': True,
                        'sale_ok': True,
                        'purchase_ok': False,
                    })
                    product = tmpl.product_variant_id
                mo = Production.create({
                    'product_id': product.id,
                    'product_qty': line.qty or 1.0,
                    'product_uom_id': product.uom_id.id,
                    'origin': plan.name,
                })
                line.mo_id = mo.id
                created |= mo
            plan.write({'state': 'released'})

        if len(created) == 1:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'mrp.production',
                'res_id': created.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return {
            'type': 'ir.actions.act_window',
            'name': 'LSX đã tạo',
            'res_model': 'mrp.production',
            'domain': [('id', 'in', created.ids)],
            'view_mode': 'list,form',
            'target': 'current',
        }

    def action_open_mos(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'LSX',
            'res_model': 'mrp.production',
            'domain': [('origin', '=', self.name)],
            'view_mode': 'list,form',
            'target': 'current',
        }


class JustplaySxPlanLine(models.Model):
    _name = 'justplay.sx.plan.line'
    _description = 'Dòng kế hoạch SX'

    plan_id = fields.Many2one('justplay.sx.plan', required=True, ondelete='cascade')
    product_code = fields.Char(string='Mã SP')
    product_name = fields.Char(string='Tên SP', required=True)
    qty = fields.Float(string='SL kế hoạch', default=1.0, required=True)
    mo_id = fields.Many2one('mrp.production', string='LSX', ondelete='set null', copy=False)
