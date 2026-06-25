#!/usr/bin/env bash
docker exec odoo-db psql -U odoo -d justplay_pilot -tAc "SELECT id, login, active FROM res_users WHERE active ORDER BY id LIMIT 10;"
