{
    'name': 'JustPlay Brand',
    'version': '18.0.1.0.0',
    'category': 'Hidden',
    'summary': 'Giao diện Odoo ERP đồng bộ JustPlay Portal (đỏ/đen, Inter)',
    'depends': ['web'],
    'data': [
        'views/res_company.xml',
        'views/login_templates.xml',
        'views/webclient_templates.xml',
    ],
    'assets': {
        'web._assets_primary_variables': [
            'portal_justplay_brand/static/src/scss/primary_variables.scss',
        ],
        'web.assets_backend': [
            'portal_justplay_brand/static/src/scss/backend.scss',
        ],
        'web.assets_frontend': [
            'portal_justplay_brand/static/src/scss/frontend.scss',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}
