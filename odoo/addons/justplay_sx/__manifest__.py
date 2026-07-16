{
    'name': 'Sản xuất JustPlay',
    'version': '18.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Hub SX JustPlay: SO → kế hoạch → LSX; placeholder 9 menu',
    'description': """
Hub sản xuất JustPlay trên Odoo.
Portal kho_npl = SoT NPL (bridge); thành phẩm sync KiotViet (sau).
""",
    'author': 'JustPlay',
    'license': 'LGPL-3',
    'depends': ['stock', 'mrp'],
    'data': [
        'security/justplay_sx_security.xml',
        'security/ir.model.access.csv',
        'views/hub_views.xml',
        'views/stock_actions.xml',
        'views/menus.xml',
        'data/demo_stub.xml',
    ],
    'application': True,
    'installable': True,
}
