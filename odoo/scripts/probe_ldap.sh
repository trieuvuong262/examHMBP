#!/bin/bash
docker exec odoo-web bash -lc 'ls /usr/lib/python3/dist-packages/odoo/addons/ | grep -i ldap'
docker exec odoo-web bash -lc 'python3 - <<"PY"
import socket
try:
    s = socket.create_connection(("100.93.5.42", 636), 5)
    print("ldap 636 ok")
    s.close()
except Exception as e:
    print("ldap 636 fail", e)
PY'
docker exec odoo-web bash -lc 'grep -r "ldap_tls\|ldaps\|STARTTLS" /usr/lib/python3/dist-packages/odoo/addons/auth_ldap/models/ 2>/dev/null | head -20'
