"""Seed thiết lập chung cơ bản — chạy qua manage.py shell."""
from san_xuat.hub_models import SxGeneralSettings

cfg = SxGeneralSettings.load()

# Cổng
cfg.gate_release_before_issue = "block"
cfg.gate_issue_before_stat = "block"
cfg.gate_stat_before_fg = "block"
cfg.gate_qc_pass_before_fg = "block"
cfg.gate_open_qc_alert_before_fg = "block"
cfg.gate_packing_before_done = "off"

# QC
cfg.auto_create_qc_from_stat = True
cfg.auto_create_defect_alert = True
cfg.default_defect_tolerance_pct = 5
cfg.default_sample_qty = 5
cfg.trace_min_timeline_events = 4

# Năng lực / OEE
cfg.capacity_load_warn_pct = 80
cfg.capacity_load_danger_pct = 100
cfg.list_default_date_range_days = 3
cfg.oee_shift_hours = 8

# Kho / UI
cfg.ycx_auto_reserve_stock = True
cfg.require_kv_link_for_fg_done = True
cfg.show_pending_ycx_banner = True

# Shop floor
cfg.shopfloor_auto_confirm_stat = True
cfg.shopfloor_default_qty_good = 1

cfg.save()
print("ok settings pk=", cfg.pk)
print("oee", cfg.oee_shift_hours, "banner", cfg.show_pending_ycx_banner)
print("prefix mo/ycx", cfg.prefix_mo, cfg.prefix_ycx)
