from django.urls import path

from audit import views_odoo

app_name = 'odoo'

urlpatterns = [
    path('', views_odoo.odoo_redirect, name='redirect'),
]
