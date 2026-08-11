{
    'name': 'JustPlay Brand',
    'version': '18.0.1.0.11',
    'category': 'Hidden',
    'summary': 'Giao diện Odoo ERP đồng bộ JustPlay Portal (đỏ/đen, Gotham)',
    'depends': ['web'],
    'data': [
        'views/res_company.xml',
        'views/login_templates.xml',
        'views/webclient_templates.xml',
    ],
    'assets': {
        'web._assets_primary_variables': [
            ('prepend', 'portal_justplay_brand/static/src/scss/primary_variables.scss'),
        ],
        'web._assets_backend_helpers': [
            'portal_justplay_brand/static/src/scss/bootstrap_overridden.scss',
        ],
        'web.assets_backend': [
            'portal_justplay_brand/static/src/scss/fonts.scss',
            'portal_justplay_brand/static/src/scss/backend.scss',
            'portal_justplay_brand/static/src/scss/sidebar.scss',
            'portal_justplay_brand/static/src/xml/justplay_sidebar.xml',
            'portal_justplay_brand/static/src/js/justplay_profile.js',
            'portal_justplay_brand/static/src/js/justplay_sidebar.js',
            'portal_justplay_brand/static/src/js/navbar_sidebar.js',
        ],
        'web.assets_web': [
            'portal_justplay_brand/static/src/scss/fonts.scss',
            'portal_justplay_brand/static/src/scss/backend.scss',
            'portal_justplay_brand/static/src/scss/sidebar.scss',
            'portal_justplay_brand/static/src/xml/justplay_sidebar.xml',
            'portal_justplay_brand/static/src/js/justplay_profile.js',
            'portal_justplay_brand/static/src/js/justplay_sidebar.js',
            'portal_justplay_brand/static/src/js/navbar_sidebar.js',
        ],
        'web.assets_frontend': [
            'portal_justplay_brand/static/src/scss/fonts.scss',
            'portal_justplay_brand/static/src/scss/frontend.scss',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}
