#!/usr/bin/env python3
# flake8: noqa — odoo shell injects `env`
installed = env['ir.module.module'].search([('state', '=', 'installed')])
apps = installed.filtered(lambda m: m.application)
print('=== APPLICATIONS (%d) ===' % len(apps))
for name in sorted(apps.mapped('name')):
    print(name)
print('=== ALL INSTALLED (%d) ===' % len(installed))
for name in sorted(installed.mapped('name')):
    print(name)
