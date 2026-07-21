from decimal import Decimal

from san_xuat.hub_models import SxGeneralSettings

cfg = SxGeneralSettings.load()
# Cổng — chế độ chặt
cfg.gate_release_before_issue = "block"
cfg.gate_issue_before_stat = "block"
cfg.gate_stat_before_fg = "block"
cfg.gate_qc_pass_before_fg = "block"
cfg.gate_open_qc_alert_before_fg = "block"
cfg.gate_packing_before_done = "off"
# QC / truy xuất
cfg.auto_create_qc_from_stat = True
cfg.auto_create_defect_alert = True
cfg.default_defect_tolerance_pct = Decimal("5")
cfg.default_sample_qty = 5
cfg.trace_min_timeline_events = 4
# Năng lực / list
cfg.capacity_load_warn_pct = 80
cfg.capacity_load_danger_pct = 100
cfg.list_default_date_range_days = 7
# Kho / KV
cfg.ycx_auto_reserve_stock = True
cfg.require_kv_link_for_fg_done = True
# Shop floor
cfg.shopfloor_auto_confirm_stat = True
cfg.shopfloor_default_qty_good = Decimal("1")
cfg.save()
print("SAVED", cfg.pk)
print(
    "gates",
    cfg.gate_issue_before_stat,
    cfg.gate_qc_pass_before_fg,
    cfg.gate_open_qc_alert_before_fg,
    cfg.gate_packing_before_done,
)
print("qc", cfg.auto_create_qc_from_stat, cfg.default_defect_tolerance_pct, cfg.trace_min_timeline_events)
print("cap", cfg.capacity_load_warn_pct, cfg.capacity_load_danger_pct, cfg.list_default_date_range_days)
print("stock", cfg.ycx_auto_reserve_stock, cfg.require_kv_link_for_fg_done)
print("sf", cfg.shopfloor_auto_confirm_stat, cfg.shopfloor_default_qty_good)
