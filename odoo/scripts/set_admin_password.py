#!/usr/bin/env python3
# flake8: noqa — odoo shell injects env
pwd = '123123sS@@'
admin = env['res.users'].browse(env.ref('base.user_admin').id)
admin.sudo().write({'password': pwd, 'login': 'admin'})
env.cr.commit()
print('OK: admin login=admin, password updated')
