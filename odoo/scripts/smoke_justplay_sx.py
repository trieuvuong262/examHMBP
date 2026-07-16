# Smoke test justplay_sx on VPS (odoo shell stdin)
errors = []


def ok(label, cond, detail=''):
    status = 'OK' if cond else 'FAIL'
    print(f'{status}  {label}' + (f'  ({detail})' if detail else ''))
    if not cond:
        errors.append(label)


mod = env['ir.module.module'].search([('name', '=', 'justplay_sx')], limit=1)
ok('module installed', mod.state == 'installed', mod.state)

root = env['ir.ui.menu'].search([('name', '=', 'Sản xuất JustPlay')], limit=1)
children = root.child_id.sorted('sequence') if root else env['ir.ui.menu']
ok('root menu', bool(root))
ok('9 submenus', len(children) == 9, str(children.mapped('name')))

ok('overview', env['justplay.sx.overview'].search_count([]) >= 1)
ok('SO stubs', env['justplay.sx.sale.order'].search_count([]) >= 2)
ok('plans', env['justplay.sx.plan'].search_count([]) >= 1)
ok('dispatch', env['justplay.sx.dispatch'].search_count([]) >= 1)
ok('qc', env['justplay.sx.qc.check'].search_count([]) >= 1)
ok('planned cost', env['justplay.sx.planned.cost'].search_count([]) >= 1)
ok('process', env['justplay.sx.process.route'].search_count([]) >= 1)

cat = env['product.category'].search([('name', '=', 'Kho NPL')], limit=1)
npl_count = env['product.product'].search_count([('categ_id', 'child_of', cat.id)]) if cat else 0
ok('NPL category', bool(cat))
ok('NPL products', npl_count >= 100, str(npl_count))
wh = env['stock.warehouse'].search([('code', '=', 'NPL')], limit=1)
ok('WH NPL', bool(wh), wh.code if wh else '')
quant_npl = (
    env['stock.quant'].search_count([('location_id', 'child_of', wh.view_location_id.id)])
    if wh else 0
)
ok('NPL quants', quant_npl > 0, str(quant_npl))

for xmlid in (
    'justplay_sx.action_wh_npl_products_server',
    'justplay_sx.action_wh_npl_quants',
    'justplay_sx.action_wh_fg_products_server',
):
    act = env.ref(xmlid, raise_if_not_found=False)
    ok('action ' + xmlid.split('.')[-1], bool(act))

npl_act = env.ref('justplay_sx.action_wh_npl_products_server')
result = npl_act.run()
ok('NPL action runs', isinstance(result, dict) and result.get('res_model') == 'product.product')

fg_act = env.ref('justplay_sx.action_wh_fg_products_server')
fg_result = fg_act.run()
ok('FG action runs', isinstance(fg_result, dict) and fg_result.get('res_model') == 'product.product')

so = env['justplay.sx.sale.order'].create({
    'name': 'SO-SMOKE-TEST',
    'partner_name': 'Smoke Partner',
    'product_code': 'SMOKE-FG-001',
    'product_name': 'Smoke FG',
    'qty': 3,
    'state': 'confirmed',
})
plan_action = so.action_create_plan()
plan = env['justplay.sx.plan'].browse(plan_action['res_id'])
ok('SO create plan', so.state == 'planned' and plan.exists(), plan.name)
mo_action = plan.action_create_mo()
ok(
    'plan create MO',
    plan.state == 'released' and plan.mo_count >= 1,
    'mo=%s model=%s' % (plan.mo_count, mo_action.get('res_model')),
)

for xmlid in (
    'justplay_sx.action_overview',
    'justplay_sx.action_sale_order',
    'justplay_sx.action_plan',
    'justplay_sx.action_dispatch',
    'justplay_sx.action_qc',
    'justplay_sx.action_planned_cost',
    'justplay_sx.action_process',
):
    act = env.ref(xmlid, raise_if_not_found=False)
    ok('window ' + xmlid.split('.')[-1], bool(act) and act.type == 'ir.actions.act_window')

print('---')
print('FAILS', len(errors))
if errors:
    print('FAILED:', errors)
else:
    print('ALL SMOKE PASSED')
env.cr.commit()
