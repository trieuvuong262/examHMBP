# Class diagram — `san_xuat`

89 model. Class có tiền tố `app_` là model thuộc app khác.

```mermaid
classDiagram
    direction LR
    class BomLine {
    +BigAutoField PK id
    +ForeignKey FK bom
    +ForeignKey FK material
    +ForeignKey FK? substitute_material
    +DecimalField qty
    +DecimalField scrap_pct
    +CharField size_code
    +CharField notes
    +PositiveSmallIntegerField sort_order
    }
    class BomVersion {
    +BigAutoField PK id
    +ForeignKey FK tech_doc
    +CharField version_label
    +CharField status
    +DecimalField overhead_pct
    +DecimalField overhead_amount
    +TextField notes
    +ForeignKey FK? routing
    +DateTimeField? activated_at
    +ForeignKey FK? created_by
    +DateTimeField created_at
    +DateTimeField updated_at
    }
    class CostingSnapshot {
    +BigAutoField PK id
    +ForeignKey FK bom
    +DecimalField material_cost
    +DecimalField labor_cost
    +DecimalField overhead_cost
    +DecimalField total_cost
    +DecimalField sell_price
    +DecimalField margin
    +TextField notes
    +ForeignKey FK? created_by
    +DateTimeField created_at
    }
    class ProcessStep {
    +BigAutoField PK id
    +ForeignKey FK bom
    +PositiveSmallIntegerField sequence
    +CharField process_name
    +ForeignKey FK? operation
    +CharField op_code
    +ForeignKey FK? routing_line
    +DecimalField norm_per_hour
    +DecimalField cost_per_hour
    +DecimalField piece_rate
    +DecimalField std_time_minutes
    +ForeignKey FK? work_center
    +CharField notes
    }
    class ProductTechDoc {
    +BigAutoField PK id
    +CharField UQ product_code
    +CharField product_name
    +CharField product_image_url
    +BigIntegerField? kv_product_id
    +TextField notes
    +TextField description
    +CharField season
    +CharField main_material
    +BooleanField is_active
    +ForeignKey FK? created_by
    +DateTimeField created_at
    +DateTimeField updated_at
    }
    class SxActualCostSheet {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +ForeignKey FK production_order
    +DateField? period_from
    +DateField? period_to
    +DecimalField material_cost
    +DecimalField labor_cost
    +DecimalField subcontract_cost
    +DecimalField total_cost
    +DecimalField qty_basis
    +DecimalField unit_cost
    +CharField status
    +TextField notes
    +DateTimeField created_at
    +DateTimeField? closed_at
    }
    class SxBomAuditLog {
    +BigAutoField PK id
    +ForeignKey FK bom
    +CharField action
    +CharField summary
    +JSONField changes
    +ForeignKey FK? user
    +CharField username
    +DateTimeField created_at
    }
    class SxColor {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +CharField name
    +PositiveSmallIntegerField sort_order
    +BooleanField is_active
    }
    class SxCostType {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +CharField name
    +BooleanField is_active
    +PositiveIntegerField sort_order
    +TextField notes
    +DateTimeField created_at
    }
    class SxDetailPlan {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +CharField name
    +ForeignKey FK? overall_plan
    +DateField date_from
    +DateField date_to
    +CharField status
    +TextField notes
    +DateTimeField created_at
    }
    class SxDetailPlanLine {
    +BigAutoField PK id
    +ForeignKey FK plan
    +DateField plan_date
    +CharField product_code
    +CharField product_name
    +DecimalField qty
    +CharField team_label
    +ForeignKey FK? work_center
    }
    class SxDisassemblyOrder {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +ForeignKey FK? production_order
    +CharField product_code
    +CharField product_name
    +DecimalField qty
    +DateField order_date
    +CharField status
    +TextField notes
    +DateTimeField created_at
    }
    class SxDisassemblyOrderLine {
    +BigAutoField PK id
    +ForeignKey FK order
    +CharField material_code
    +CharField material_name
    +DecimalField qty
    +CharField notes
    }
    class SxDowntimeEvent {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +ForeignKey FK? production_order
    +ForeignKey FK? work_center
    +CharField team_label
    +DateField event_date
    +CharField reason
    +PositiveIntegerField minutes
    +TextField notes
    +DateTimeField created_at
    }
    class SxFgReceiptLine {
    +BigAutoField PK id
    +ForeignKey FK receipt
    +ForeignKey FK? sku
    +CharField sku_code
    +CharField size_label
    +CharField color_label
    +CharField color_code
    +DecimalField qty
    }
    class SxFgReceiptRequest {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +ForeignKey FK production_order
    +ForeignKey FK? production_stat
    +DateField request_date
    +DecimalField qty
    +CharField status
    +BigIntegerField? kv_purchase_kiotviet_id
    +CharField kv_purchase_code
    +ForeignKey FK? received_by
    +CharField warehouse_code
    +CharField warehouse_name
    +TextField notes
    +DateTimeField created_at
    }
    class SxGeneralSettings {
    +BigAutoField PK id
    +CharField gate_release_before_issue
    +CharField gate_issue_before_stat
    +CharField gate_stat_before_fg
    +CharField gate_qc_pass_before_fg
    +CharField gate_open_qc_alert_before_fg
    +CharField gate_packing_before_done
    +CharField gate_sku_on_stat
    +CharField gate_sku_on_packing
    +BooleanField auto_create_qc_from_stat
    +BooleanField auto_create_defect_alert
    +DecimalField default_defect_tolerance_pct
    +PositiveIntegerField default_sample_qty
    +PositiveSmallIntegerField trace_min_timeline_events
    +PositiveSmallIntegerField capacity_load_warn_pct
    +PositiveSmallIntegerField capacity_load_danger_pct
    +PositiveSmallIntegerField list_default_date_range_days
    +CharField plan_capacity_mode
    +BooleanField plan_block_over_capacity
    +CharField plan_workdays
    +PositiveSmallIntegerField npl_prep_days
    +PositiveSmallIntegerField mo_late_alert_days
    +BooleanField ycx_auto_reserve_stock
    +BooleanField require_kv_link_for_fg_done
    +BooleanField shopfloor_auto_confirm_stat
    +DecimalField shopfloor_default_qty_good
    +PositiveSmallIntegerField oee_shift_hours
    +BooleanField show_pending_ycx_banner
    +CharField prefix_mo
    +CharField prefix_ycx
    +CharField prefix_stat
    +CharField prefix_fg
    +CharField prefix_qc_req
    +CharField prefix_qc_sheet
    +CharField prefix_qc_alert
    +CharField prefix_wip_ho
    +CharField prefix_wip_ret
    +CharField prefix_disassembly
    +CharField prefix_npl_surplus
    +CharField prefix_packing
    +CharField prefix_subcontract
    +CharField prefix_work_assign
    +CharField prefix_plan_overall
    +CharField prefix_plan_npl
    +CharField prefix_plan_detail
    +CharField prefix_npl_pr
    +CharField prefix_po
    +CharField prefix_cost_std
    +CharField prefix_cost_order
    +CharField prefix_actual_cost
    +CharField prefix_ncr
    +CharField prefix_downtime
    +DateTimeField updated_at
    +ForeignKey FK? updated_by
    }
    class SxHoliday {
    +BigAutoField PK id
    +DateField UQ holiday_date
    +CharField name
    +DateTimeField created_at
    }
    class SxIeAuditLog {
    +BigAutoField PK id
    +CharField action
    +CharField object_type
    +CharField object_id
    +CharField object_repr
    +CharField summary
    +JSONField changes
    +ForeignKey FK? user
    +CharField username
    +DateTimeField created_at
    }
    class SxMachine {
    +BigAutoField PK id
    +CharField UQ code
    +CharField name
    +PositiveSmallIntegerField sort_order
    +BooleanField is_active
    +CharField notes
    +DateTimeField created_at
    }
    class SxMaterialIssueRequest {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +ForeignKey FK production_order
    +ForeignKey FK? stock_issue
    +CharField status
    +DateField request_date
    +TextField notes
    +DateTimeField created_at
    }
    class SxMaterialIssueRequestLine {
    +BigAutoField PK id
    +ForeignKey FK request
    +CharField material_code
    +CharField material_name
    +DecimalField qty_requested
    +DecimalField qty_issued
    +ForeignKey FK? preferred_location
    }
    class SxMaterialPlan {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +CharField name
    +ForeignKey FK? overall_plan
    +CharField status
    +TextField notes
    +DateTimeField created_at
    }
    class SxMaterialPlanLine {
    +BigAutoField PK id
    +ForeignKey FK plan
    +CharField material_code
    +CharField material_name
    +DecimalField qty_required
    +DecimalField qty_on_hand
    +DecimalField qty_shortfall
    +DecimalField qty_expected_inbound
    +DecimalField qty_reserved
    +DateField? need_date
    }
    class SxMoProcessAssignee {
    +BigAutoField PK id
    +ForeignKey FK mo_process_step
    +ForeignKey FK user
    +ForeignKey FK? assigned_by
    +DateTimeField assigned_at
    }
    class SxMoProcessStep {
    +BigAutoField PK id
    +ForeignKey FK production_order
    +PositiveSmallIntegerField sequence
    +CharField process_name
    +ForeignKey FK? work_center
    +DateField? planned_date
    +CharField status
    +ForeignKey FK? manager
    +PositiveIntegerField? bom_process_step_id
    }
    class SxNcrCase {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +ForeignKey FK production_order
    +ForeignKey FK? alert
    +CharField disposition
    +DecimalField qty
    +CharField process_name
    +ForeignKey FK? remake_order
    +ForeignKey FK? rework_stat
    +CharField status
    +TextField notes
    +DateTimeField created_at
    +DateTimeField? confirmed_at
    }
    class SxNplPurchaseRequest {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +ForeignKey FK? material_plan
    +DateField? request_date
    +DateField? due_date
    +CharField status
    +TextField notes
    +DateTimeField created_at
    }
    class SxNplPurchaseRequestLine {
    +BigAutoField PK id
    +ForeignKey FK request
    +CharField material_code
    +CharField material_name
    +DecimalField qty
    +DateField? need_date
    }
    class SxNplSurplus {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +ForeignKey FK? production_order
    +ForeignKey FK? disassembly_order
    +CharField material_code
    +CharField material_name
    +DecimalField qty
    +DateField recorded_at
    +CharField status
    +ForeignKey FK? stock_adjustment
    +TextField notes
    +DateTimeField created_at
    }
    class SxOperation {
    +BigAutoField PK id
    +ForeignKey FK group
    +CharField op_code
    +CharField op_rev
    +CharField name_vi
    +CharField name_en
    +CharField process_stage_label
    +CharField product_part
    +TextField method_variant
    +CharField input_state
    +CharField output_state
    +ForeignKey FK? machine
    +CharField machine_code
    +ForeignKey FK? stitch_class
    +CharField thread_needle
    +CharField attachment_code
    +CharField smv_basis
    +ForeignKey FK? skill_level
    +CharField skill_level_label
    +TextField qc_criteria
    +DecimalField base_smv_min
    +ForeignKey FK? smv_source
    +CharField status
    +DateField? effective_from
    +DateField? effective_to
    +CharField ie_owner
    +CharField approved_by
    +ForeignKey FK? approved_user
    +DateTimeField? approved_at
    +CharField revision_reason
    +CharField work_instruction_url
    +CharField video_url
    +CharField notes
    +DateTimeField created_at
    +DateTimeField updated_at
    }
    class SxOperationGroup {
    +BigAutoField PK id
    +CharField UQ code
    +CharField name
    +ForeignKey FK? process_stage
    +CharField process_stage_label
    +CharField product_part
    +TextField description
    +ForeignKey FK? default_work_center
    +CharField default_work_center_code
    +CharField data_owner
    +DateField? effective_from
    +PositiveSmallIntegerField sort_order
    +BooleanField is_active
    +CharField notes
    +DateTimeField created_at
    +DateTimeField updated_at
    }
    class SxOrderPlanCost {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +CharField name
    +CharField kv_order_code
    +BigIntegerField? kv_order_kiotviet_id
    +DateField date_from
    +DateField date_to
    +DecimalField total_cost
    +CharField status
    +TextField notes
    +DateTimeField created_at
    }
    class SxOrderPlanCostLine {
    +BigAutoField PK id
    +ForeignKey FK sheet
    +CharField product_code
    +CharField product_name
    +DecimalField qty
    +DecimalField unit_cost
    +DecimalField extra_cost
    +DecimalField line_cost
    }
    class SxOrderPlanCostLineExtra {
    +BigAutoField PK id
    +ForeignKey FK line
    +ForeignKey FK cost_type
    +DecimalField amount
    }
    class SxOverallPlan {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +CharField name
    +DateField date_from
    +DateField date_to
    +CharField source
    +CharField plan_method
    +CharField mps_bucket
    +DateField? frozen_until
    +BooleanField apply_netting
    +CharField status
    +TextField notes
    +DateTimeField created_at
    }
    class SxOverallPlanLine {
    +BigAutoField PK id
    +ForeignKey FK plan
    +CharField product_code
    +CharField product_name
    +DecimalField qty_required
    +DecimalField qty_planned
    +DecimalField capacity_per_day
    +BigIntegerField? kv_order_kiotviet_id
    +CharField kv_order_code
    +ForeignKey FK? sales_order
    +DecimalField qty_gross
    +DecimalField qty_on_hand
    +DecimalField qty_wip
    +DateField? due_date
    +DateField? bucket_start
    }
    class SxPackingLine {
    +BigAutoField PK id
    +ForeignKey FK packing
    +ForeignKey FK? sku
    +CharField sku_code
    +CharField size_label
    +CharField color_label
    +CharField color_code
    +DecimalField qty
    +PositiveIntegerField carton_count
    }
    class SxPackingRecord {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +ForeignKey FK production_order
    +ForeignKey FK? fg_receipt
    +DateField pack_date
    +DecimalField qty
    +PositiveIntegerField carton_count
    +CharField lot_code
    +CharField status
    +TextField notes
    +DateTimeField? confirmed_at
    +DateTimeField created_at
    }
    class SxPlanAuditLog {
    +BigAutoField PK id
    +CharField action
    +CharField object_type
    +CharField object_id
    +CharField object_code
    +CharField summary
    +JSONField changes
    +ForeignKey FK? user
    +CharField username
    +DateTimeField created_at
    }
    class SxProcessName {
    +BigAutoField PK id
    +CharField UQ name
    +PositiveSmallIntegerField sort_order
    +BooleanField is_active
    +DateTimeField created_at
    }
    class SxProcessStage {
    +BigAutoField PK id
    +CharField UQ code
    +CharField name
    +PositiveSmallIntegerField sort_order
    +BooleanField is_active
    +CharField notes
    +DateTimeField created_at
    }
    class SxProductGroup {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +CharField name
    +BooleanField is_active
    +CharField notes
    }
    class SxProductPart {
    +BigAutoField PK id
    +CharField UQ code
    +CharField name
    +PositiveSmallIntegerField sort_order
    +BooleanField is_active
    +CharField notes
    +DateTimeField created_at
    }
    class SxProductStockPolicy {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ product_code
    +CharField product_name
    +DecimalField min_stock
    +DecimalField max_stock
    +PositiveSmallIntegerField lead_time_days
    +BooleanField is_active
    +TextField notes
    +DateTimeField created_at
    +DateTimeField updated_at
    }
    class SxProductionOrder {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +CharField product_code
    +CharField product_name
    +ForeignKey FK? detail_plan
    +ForeignKey FK? bom_version
    +ForeignKey FK? routing
    +DecimalField qty
    +DecimalField qty_done
    +DateField order_date
    +DateField? due_date
    +DateField? planned_start
    +DateField? planned_end
    +CharField team_label
    +CharField process_name
    +CharField status
    +ForeignKey FK? sales_order
    +BooleanField is_sample
    +TextField notes
    +DateTimeField created_at
    }
    class SxProductionOrderLine {
    +BigAutoField PK id
    +ForeignKey FK production_order
    +ForeignKey FK? sku
    +CharField sku_code
    +CharField size_label
    +CharField color_label
    +CharField color_code
    +DecimalField qty
    }
    class SxProductionStat {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +ForeignKey FK production_order
    +DateField stat_date
    +CharField process_name
    +DecimalField qty_good
    +DecimalField qty_defect
    +CharField team_label
    +ForeignKey FK? sku
    +CharField sku_code
    +CharField size_label
    +CharField color_label
    +CharField color_code
    +CharField status
    +TextField notes
    +DateTimeField created_at
    }
    class SxPurchaseOrder {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +CharField supplier_name
    +ForeignKey FK? supplier
    +DateField? expected_date
    +ForeignKey FK? purchase_request
    +ForeignKey FK? stock_receipt
    +CharField status
    +BigIntegerField? kv_purchase_kiotviet_id
    +CharField kv_purchase_code
    +TextField notes
    +DateTimeField created_at
    }
    class SxPurchaseOrderLine {
    +BigAutoField PK id
    +ForeignKey FK order
    +CharField material_code
    +CharField material_name
    +DecimalField qty_ordered
    +DecimalField qty_received
    +DecimalField unit_price
    +DateField? need_date
    }
    class SxQcAlert {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +CharField alert_type
    +ForeignKey FK production_order
    +ForeignKey FK? production_stat
    +ForeignKey FK? qc_request
    +ForeignKey FK? qc_inspection
    +CharField process_name
    +DecimalField defect_rate
    +DecimalField tolerance_limit
    +DecimalField qty_good
    +DecimalField qty_defect
    +TextField message
    +CharField status
    +DateTimeField created_at
    }
    class SxQcCriteria {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +CharField name
    +ForeignKey FK group
    +CharField kind
    +BooleanField is_active
    }
    class SxQcCriteriaGroup {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +CharField name
    +BooleanField is_active
    }
    class SxQcDefect {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +CharField name
    +ForeignKey FK group
    +CharField severity
    +BooleanField is_active
    }
    class SxQcDefectGroup {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +CharField name
    +BooleanField is_active
    }
    class SxQcInspection {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +ForeignKey FK? qc_request
    +ForeignKey FK? standard_set
    +DateField inspected_at
    +DecimalField qty_sample
    +DecimalField qty_pass
    +DecimalField qty_fail
    +CharField result
    +CharField status
    +TextField notes
    +DateTimeField created_at
    }
    class SxQcInspectionCriteriaLine {
    +BigAutoField PK id
    +ForeignKey FK inspection
    +ForeignKey FK criteria
    +CharField value_text
    +DecimalField? value_number
    +BooleanField? is_pass
    +CharField notes
    }
    class SxQcInspectionDefectLine {
    +BigAutoField PK id
    +ForeignKey FK inspection
    +ForeignKey FK defect
    +DecimalField qty
    +CharField notes
    }
    class SxQcRequest {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +ForeignKey FK? production_order
    +ForeignKey FK? production_stat
    +CharField product_code
    +CharField product_name
    +CharField stage_name
    +ForeignKey FK? sku
    +CharField sku_code
    +CharField size_label
    +CharField color_label
    +CharField color_code
    +DecimalField qty
    +DateField request_date
    +DateField? due_date
    +CharField status
    +TextField notes
    +DateTimeField created_at
    }
    class SxQcSamplingMethod {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +CharField name
    +CharField method_type
    +DecimalField sample_value
    +DecimalField aql_level
    +CharField inspection_level
    +BooleanField is_active
    }
    class SxQcStandardCriteria {
    +BigAutoField PK id
    +ForeignKey FK standard_set
    +ForeignKey FK criteria
    +PositiveSmallIntegerField sort_order
    +DecimalField? min_value
    +DecimalField? max_value
    }
    class SxQcStandardSet {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +CharField name
    +CharField product_code
    +CharField stage_name
    +DecimalField defect_tolerance_pct
    +ForeignKey FK sampling_method
    +BooleanField is_active
    }
    class SxRouting {
    +BigAutoField PK id
    +CharField UQ routing_id
    +CharField style_code
    +CharField style_name
    +CharField product_family
    +CharField routing_rev
    +ForeignKey FK? tech_doc
    +DateField? effective_from
    +BooleanField is_active
    +CharField approval_status
    +CharField ie_owner
    +CharField approved_by
    +DateTimeField? approved_at
    +CharField notes
    +ForeignKey FK? created_by
    +DateTimeField created_at
    +DateTimeField updated_at
    }
    class SxRoutingLine {
    +BigAutoField PK id
    +ForeignKey FK routing
    +PositiveIntegerField seq_no
    +ForeignKey FK? operation
    +CharField op_code
    +CharField op_rev
    +CharField op_name_vi
    +CharField group_code
    +DecimalField qty_per_garment
    +DecimalField library_unit_smv
    +DecimalField applied_unit_smv
    +DecimalField total_operation_smv
    +DecimalField smv_variance_pct
    +DecimalField price_factor
    +DecimalField total_unit_price
    +ForeignKey FK? machine
    +CharField machine_code
    +ForeignKey FK? work_center
    +CharField work_center_code
    +PositiveIntegerField? predecessor_seq
    +CharField parallel_group
    +PositiveIntegerField? bundle_size
    +CharField skill_level_label
    +BooleanField critical_qc
    +DecimalField target_efficiency
    +CharField notes
    +CharField variance_explanation
    }
    class SxSalesOrder {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +CharField customer_name
    +DateField request_date
    +DateField? due_date
    +CharField order_type
    +CharField confirm_status
    +ForeignKey FK? confirmed_by
    +DateTimeField? confirmed_at
    +CharField reject_reason
    +CharField source
    +BigIntegerField UQ? kv_order_kiotviet_id
    +CharField kv_order_code
    +TextField notes
    +FileField attachment
    +CharField plan_status
    +CharField plan_priority
    +PositiveIntegerField? plan_rank
    +DecimalField? plan_score
    +DateTimeField? plan_queued_at
    +CharField plan_hold_reason
    +DateTimeField created_at
    +DateTimeField updated_at
    }
    class SxSalesOrderLine {
    +BigAutoField PK id
    +ForeignKey FK order
    +CharField product_code
    +CharField product_name
    +DecimalField qty
    +JSONField size_qtys
    +ForeignKey FK? bom_version
    +ForeignKey FK? routing
    +JSONField bom_line_overrides
    +DecimalField qty_scrap_rate
    +CharField uom
    +DateField? due_date
    +PositiveSmallIntegerField sort_order
    }
    class SxSalesOrderPlanStep {
    +BigAutoField PK id
    +ForeignKey FK sales_order
    +PositiveSmallIntegerField sequence
    +CharField process_name
    +ForeignKey FK? work_center
    +DateField? planned_date
    +DecimalField minutes_per_unit
    }
    class SxSalesOrderRoutingLine {
    +BigAutoField PK id
    +ForeignKey FK sales_order_line
    +ForeignKey FK? source_routing_line
    +PositiveIntegerField seq_no
    +ForeignKey FK? operation
    +CharField op_code
    +CharField op_rev
    +CharField op_name_vi
    +CharField group_code
    +DecimalField qty_per_garment
    +DecimalField library_unit_smv
    +DecimalField applied_unit_smv
    +DecimalField total_operation_smv
    +DecimalField smv_variance_pct
    +DecimalField price_factor
    +DecimalField total_unit_price
    +ForeignKey FK? machine
    +CharField machine_code
    +ForeignKey FK? work_center
    +CharField work_center_code
    +CharField skill_level_label
    +BooleanField critical_qc
    +CharField notes
    +CharField variance_explanation
    }
    class SxSize {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +CharField name
    +PositiveSmallIntegerField sort_order
    +BooleanField is_active
    }
    class SxSkillLevel {
    +BigAutoField PK id
    +CharField UQ code
    +CharField name
    +PositiveSmallIntegerField sort_order
    +BooleanField is_active
    +CharField notes
    +DateTimeField created_at
    }
    class SxSku {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField style_code
    +CharField style_name
    +CharField color_code
    +CharField color_label
    +CharField size_label
    +CharField UQ sku_code
    +BooleanField is_active
    +CharField notes
    +DateTimeField created_at
    }
    class SxSmvBasis {
    +BigAutoField PK id
    +CharField UQ code
    +CharField name
    +PositiveSmallIntegerField sort_order
    +BooleanField is_active
    +CharField notes
    +DateTimeField created_at
    }
    class SxSmvSource {
    +BigAutoField PK id
    +CharField UQ code
    +CharField name
    +PositiveSmallIntegerField sort_order
    +BooleanField is_active
    +CharField notes
    +DateTimeField created_at
    }
    class SxStandardCostLine {
    +BigAutoField PK id
    +ForeignKey FK sheet
    +CharField product_code
    +CharField product_name
    +DecimalField unit_cost
    +DecimalField material_cost
    +DecimalField labor_cost
    +DecimalField overhead_cost
    }
    class SxStandardCostSheet {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +CharField name
    +DateField date_from
    +DateField date_to
    +CharField status
    +TextField notes
    +DateTimeField created_at
    }
    class SxStitchClass {
    +BigAutoField PK id
    +CharField UQ code
    +CharField name
    +PositiveSmallIntegerField sort_order
    +BooleanField is_active
    +CharField notes
    +DateTimeField created_at
    }
    class SxSubcontractMaterialLine {
    +BigAutoField PK id
    +ForeignKey FK order
    +CharField direction
    +CharField material_code
    +CharField material_name
    +DecimalField qty
    +CharField uom_label
    +CharField lot_code
    +CharField notes
    +DateTimeField created_at
    }
    class SxSubcontractOrder {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +ForeignKey FK? production_order
    +CharField vendor_name
    +CharField product_code
    +CharField product_name
    +CharField process_name
    +DecimalField qty
    +DecimalField qty_received
    +DecimalField service_fee
    +DateField order_date
    +DateField? due_date
    +CharField status
    +ForeignKey FK? stock_issue
    +ForeignKey FK? stock_adjustment
    +TextField notes
    +DateTimeField? sent_at
    +DateTimeField? received_at
    +DateTimeField created_at
    }
    class SxTeamDivisionMap {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField team_slug
    +ForeignKey FK division
    +CharField notes
    +BooleanField is_active
    +DateTimeField created_at
    }
    class SxTeamHrMap {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ team_label
    +CharField employee_code
    +CharField employee_name
    +CharField notes
    +BooleanField is_active
    +DateTimeField created_at
    }
    class SxTeamPersonnelSkill {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +ForeignKey FK user
    +CharField team_slug
    +JSONField process_keys
    +JSONField process_avg_qty
    +CharField skill_level
    +CharField machines
    +BooleanField is_multiskill
    +TextField notes
    +DateTimeField updated_at
    +ForeignKey FK? updated_by
    }
    class SxTeamWorkClose {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +ForeignKey FK production_order
    +CharField team_slug
    +DateTimeField closed_at
    +CharField notes
    }
    class SxTimeStudy {
    +BigAutoField PK id
    +CharField UQ study_id
    +DateField? study_date
    +CharField factory_code
    +CharField line_code
    +CharField shift
    +CharField style_code
    +CharField routing_rev
    +ForeignKey FK? operation
    +CharField op_code
    +CharField op_rev
    +CharField op_name_vi
    +CharField operator_id
    +CharField skill_level_label
    +ForeignKey FK? machine
    +CharField machine_code
    +CharField method_rev
    +PositiveIntegerField obs_no
    +DecimalField observed_cycle_sec
    +DecimalField abnormal_sec
    +DecimalField performance_rating
    +DecimalField allowance_pct
    +DecimalField current_routing_smv
    +DecimalField net_observed_sec
    +DecimalField normal_time_sec
    +DecimalField standard_time_sec
    +DecimalField calculated_smv
    +DecimalField variance_pct
    +CharField ie_observer
    +CharField conditions
    +CharField approval_status
    +CharField variance_explanation
    +CharField notes
    +DateTimeField created_at
    }
    class SxWipBalance {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +ForeignKey FK production_order
    +CharField process_name
    +DecimalField qty
    +DateTimeField updated_at
    }
    class SxWipHandover {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +ForeignKey FK production_order
    +CharField from_process
    +CharField to_process
    +DecimalField qty
    +DateField handover_date
    +CharField status
    +TextField notes
    +DateTimeField created_at
    }
    class SxWipReturn {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +ForeignKey FK? handover
    +ForeignKey FK production_order
    +CharField from_process
    +CharField to_process
    +DecimalField qty
    +DateField return_date
    +CharField reason
    +CharField status
    +TextField notes
    +DateTimeField? confirmed_at
    +DateTimeField created_at
    }
    class SxWorkAssignment {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +ForeignKey FK production_order
    +ForeignKey FK? work_center
    +CharField process_name
    +CharField title
    +ForeignKey FK? assignee
    +CharField assignee_label
    +ForeignKey FK? work_task
    +DateField? due_date
    +CharField status
    +TextField notes
    +DateTimeField? completed_at
    +DateTimeField created_at
    }
    class SxWorkCenter {
    +BigAutoField PK id
    +BooleanField is_demo
    +ForeignKey FK? created_by
    +CharField UQ code
    +CharField name
    +DecimalField capacity_per_day
    +CharField uom_label
    +PositiveSmallIntegerField headcount
    +PositiveSmallIntegerField shift_minutes_per_head
    +DecimalField efficiency_pct
    +CharField team_label
    +BooleanField is_active
    +TextField notes
    +DateTimeField created_at
    }
    class TechDocDesignFile {
    +BigAutoField PK id
    +ForeignKey FK tech_doc
    +FileField file
    +CharField title
    +CharField notes
    +CharField purpose
    +PositiveIntegerField sort_order
    +ForeignKey FK? uploaded_by
    +DateTimeField uploaded_at
    }

    class auth_User {
    +external
    }
    class hrm_Division {
    +external
    }
    class kho_npl_Material {
    +external
    }
    class kho_npl_StockAdjustment {
    +external
    }
    class kho_npl_StockIssue {
    +external
    }
    class kho_npl_StockReceipt {
    +external
    }
    class kho_npl_Supplier {
    +external
    }
    class kho_npl_WarehouseLocation {
    +external
    }
    class tasks_WorkTask {
    +external
    }

    BomLine "*" --> "1" BomVersion : bom
    BomLine "*" --> "1" kho_npl_Material : material
    BomLine "*" --> "1" kho_npl_Material : substitute_material
    BomVersion "*" --> "1" ProductTechDoc : tech_doc
    BomVersion "*" --> "1" SxRouting : routing
    BomVersion "*" --> "1" auth_User : created_by
    CostingSnapshot "*" --> "1" BomVersion : bom
    CostingSnapshot "*" --> "1" auth_User : created_by
    ProcessStep "*" --> "1" BomVersion : bom
    ProcessStep "*" --> "1" SxOperation : operation
    ProcessStep "*" --> "1" SxRoutingLine : routing_line
    ProcessStep "*" --> "1" SxWorkCenter : work_center
    ProductTechDoc "*" --> "1" auth_User : created_by
    SxActualCostSheet "*" --> "1" auth_User : created_by
    SxActualCostSheet "*" --> "1" SxProductionOrder : production_order
    SxBomAuditLog "*" --> "1" BomVersion : bom
    SxBomAuditLog "*" --> "1" auth_User : user
    SxColor "*" --> "1" auth_User : created_by
    SxCostType "*" --> "1" auth_User : created_by
    SxDetailPlan "*" --> "1" auth_User : created_by
    SxDetailPlan "*" --> "1" SxOverallPlan : overall_plan
    SxDetailPlanLine "*" --> "1" SxDetailPlan : plan
    SxDetailPlanLine "*" --> "1" SxWorkCenter : work_center
    SxDisassemblyOrder "*" --> "1" auth_User : created_by
    SxDisassemblyOrder "*" --> "1" SxProductionOrder : production_order
    SxDisassemblyOrderLine "*" --> "1" SxDisassemblyOrder : order
    SxDowntimeEvent "*" --> "1" auth_User : created_by
    SxDowntimeEvent "*" --> "1" SxProductionOrder : production_order
    SxDowntimeEvent "*" --> "1" SxWorkCenter : work_center
    SxFgReceiptLine "*" --> "1" SxFgReceiptRequest : receipt
    SxFgReceiptLine "*" --> "1" SxSku : sku
    SxFgReceiptRequest "*" --> "1" auth_User : created_by
    SxFgReceiptRequest "*" --> "1" SxProductionOrder : production_order
    SxFgReceiptRequest "*" --> "1" SxProductionStat : production_stat
    SxFgReceiptRequest "*" --> "1" auth_User : received_by
    SxGeneralSettings "*" --> "1" auth_User : updated_by
    SxIeAuditLog "*" --> "1" auth_User : user
    SxMaterialIssueRequest "*" --> "1" auth_User : created_by
    SxMaterialIssueRequest "*" --> "1" SxProductionOrder : production_order
    SxMaterialIssueRequest "*" --> "1" kho_npl_StockIssue : stock_issue
    SxMaterialIssueRequestLine "*" --> "1" SxMaterialIssueRequest : request
    SxMaterialIssueRequestLine "*" --> "1" kho_npl_WarehouseLocation : preferred_location
    SxMaterialPlan "*" --> "1" auth_User : created_by
    SxMaterialPlan "*" --> "1" SxOverallPlan : overall_plan
    SxMaterialPlanLine "*" --> "1" SxMaterialPlan : plan
    SxMoProcessAssignee "*" --> "1" SxMoProcessStep : mo_process_step
    SxMoProcessAssignee "*" --> "1" auth_User : user
    SxMoProcessAssignee "*" --> "1" auth_User : assigned_by
    SxMoProcessStep "*" --> "1" SxProductionOrder : production_order
    SxMoProcessStep "*" --> "1" SxWorkCenter : work_center
    SxMoProcessStep "*" --> "1" auth_User : manager
    SxNcrCase "*" --> "1" auth_User : created_by
    SxNcrCase "*" --> "1" SxProductionOrder : production_order
    SxNcrCase "*" --> "1" SxQcAlert : alert
    SxNcrCase "*" --> "1" SxProductionOrder : remake_order
    SxNcrCase "*" --> "1" SxProductionStat : rework_stat
    SxNplPurchaseRequest "*" --> "1" auth_User : created_by
    SxNplPurchaseRequest "*" --> "1" SxMaterialPlan : material_plan
    SxNplPurchaseRequestLine "*" --> "1" SxNplPurchaseRequest : request
    SxNplSurplus "*" --> "1" auth_User : created_by
    SxNplSurplus "*" --> "1" SxProductionOrder : production_order
    SxNplSurplus "*" --> "1" SxDisassemblyOrder : disassembly_order
    SxNplSurplus "*" --> "1" kho_npl_StockAdjustment : stock_adjustment
    SxOperation "*" --> "1" SxOperationGroup : group
    SxOperation "*" --> "1" SxMachine : machine
    SxOperation "*" --> "1" SxStitchClass : stitch_class
    SxOperation "*" --> "1" SxSkillLevel : skill_level
    SxOperation "*" --> "1" SxSmvSource : smv_source
    SxOperation "*" --> "1" auth_User : approved_user
    SxOperationGroup "*" --> "1" SxProcessStage : process_stage
    SxOperationGroup "*" --> "1" SxWorkCenter : default_work_center
    SxOrderPlanCost "*" --> "1" auth_User : created_by
    SxOrderPlanCostLine "*" --> "1" SxOrderPlanCost : sheet
    SxOrderPlanCostLineExtra "*" --> "1" SxOrderPlanCostLine : line
    SxOrderPlanCostLineExtra "*" --> "1" SxCostType : cost_type
    SxOverallPlan "*" --> "1" auth_User : created_by
    SxOverallPlanLine "*" --> "1" SxOverallPlan : plan
    SxOverallPlanLine "*" --> "1" SxSalesOrder : sales_order
    SxPackingLine "*" --> "1" SxPackingRecord : packing
    SxPackingLine "*" --> "1" SxSku : sku
    SxPackingRecord "*" --> "1" auth_User : created_by
    SxPackingRecord "*" --> "1" SxProductionOrder : production_order
    SxPackingRecord "*" --> "1" SxFgReceiptRequest : fg_receipt
    SxPlanAuditLog "*" --> "1" auth_User : user
    SxProductGroup "*" --> "1" auth_User : created_by
    SxProductStockPolicy "*" --> "1" auth_User : created_by
    SxProductionOrder "*" --> "1" auth_User : created_by
    SxProductionOrder "*" --> "1" SxDetailPlan : detail_plan
    SxProductionOrder "*" --> "1" BomVersion : bom_version
    SxProductionOrder "*" --> "1" SxRouting : routing
    SxProductionOrder "*" --> "1" SxSalesOrder : sales_order
    SxProductionOrderLine "*" --> "1" SxProductionOrder : production_order
    SxProductionOrderLine "*" --> "1" SxSku : sku
    SxProductionStat "*" --> "1" auth_User : created_by
    SxProductionStat "*" --> "1" SxProductionOrder : production_order
    SxProductionStat "*" --> "1" SxSku : sku
    SxPurchaseOrder "*" --> "1" auth_User : created_by
    SxPurchaseOrder "*" --> "1" kho_npl_Supplier : supplier
    SxPurchaseOrder "*" --> "1" SxNplPurchaseRequest : purchase_request
    SxPurchaseOrder "*" --> "1" kho_npl_StockReceipt : stock_receipt
    SxPurchaseOrderLine "*" --> "1" SxPurchaseOrder : order
    SxQcAlert "*" --> "1" auth_User : created_by
    SxQcAlert "*" --> "1" SxProductionOrder : production_order
    SxQcAlert "*" --> "1" SxProductionStat : production_stat
    SxQcAlert "*" --> "1" SxQcRequest : qc_request
    SxQcAlert "*" --> "1" SxQcInspection : qc_inspection
    SxQcCriteria "*" --> "1" auth_User : created_by
    SxQcCriteria "*" --> "1" SxQcCriteriaGroup : group
    SxQcCriteriaGroup "*" --> "1" auth_User : created_by
    SxQcDefect "*" --> "1" auth_User : created_by
    SxQcDefect "*" --> "1" SxQcDefectGroup : group
    SxQcDefectGroup "*" --> "1" auth_User : created_by
    SxQcInspection "*" --> "1" auth_User : created_by
    SxQcInspection "*" --> "1" SxQcRequest : qc_request
    SxQcInspection "*" --> "1" SxQcStandardSet : standard_set
    SxQcInspectionCriteriaLine "*" --> "1" SxQcInspection : inspection
    SxQcInspectionCriteriaLine "*" --> "1" SxQcCriteria : criteria
    SxQcInspectionDefectLine "*" --> "1" SxQcInspection : inspection
    SxQcInspectionDefectLine "*" --> "1" SxQcDefect : defect
    SxQcRequest "*" --> "1" auth_User : created_by
    SxQcRequest "*" --> "1" SxProductionOrder : production_order
    SxQcRequest "*" --> "1" SxProductionStat : production_stat
    SxQcRequest "*" --> "1" SxSku : sku
    SxQcSamplingMethod "*" --> "1" auth_User : created_by
    SxQcStandardCriteria "*" --> "1" SxQcStandardSet : standard_set
    SxQcStandardCriteria "*" --> "1" SxQcCriteria : criteria
    SxQcStandardSet "*" --> "1" auth_User : created_by
    SxQcStandardSet "*" --> "1" SxQcSamplingMethod : sampling_method
    SxRouting "*" --> "1" ProductTechDoc : tech_doc
    SxRouting "*" --> "1" auth_User : created_by
    SxRoutingLine "*" --> "1" SxRouting : routing
    SxRoutingLine "*" --> "1" SxOperation : operation
    SxRoutingLine "*" --> "1" SxMachine : machine
    SxRoutingLine "*" --> "1" SxWorkCenter : work_center
    SxSalesOrder "*" --> "1" auth_User : created_by
    SxSalesOrder "*" --> "1" auth_User : confirmed_by
    SxSalesOrderLine "*" --> "1" SxSalesOrder : order
    SxSalesOrderLine "*" --> "1" BomVersion : bom_version
    SxSalesOrderLine "*" --> "1" SxRouting : routing
    SxSalesOrderPlanStep "*" --> "1" SxSalesOrder : sales_order
    SxSalesOrderPlanStep "*" --> "1" SxWorkCenter : work_center
    SxSalesOrderRoutingLine "*" --> "1" SxSalesOrderLine : sales_order_line
    SxSalesOrderRoutingLine "*" --> "1" SxRoutingLine : source_routing_line
    SxSalesOrderRoutingLine "*" --> "1" SxOperation : operation
    SxSalesOrderRoutingLine "*" --> "1" SxMachine : machine
    SxSalesOrderRoutingLine "*" --> "1" SxWorkCenter : work_center
    SxSize "*" --> "1" auth_User : created_by
    SxSku "*" --> "1" auth_User : created_by
    SxStandardCostLine "*" --> "1" SxStandardCostSheet : sheet
    SxStandardCostSheet "*" --> "1" auth_User : created_by
    SxSubcontractMaterialLine "*" --> "1" SxSubcontractOrder : order
    SxSubcontractOrder "*" --> "1" auth_User : created_by
    SxSubcontractOrder "*" --> "1" SxProductionOrder : production_order
    SxSubcontractOrder "*" --> "1" kho_npl_StockIssue : stock_issue
    SxSubcontractOrder "*" --> "1" kho_npl_StockAdjustment : stock_adjustment
    SxTeamDivisionMap "*" --> "1" auth_User : created_by
    SxTeamDivisionMap "*" --> "1" hrm_Division : division
    SxTeamHrMap "*" --> "1" auth_User : created_by
    SxTeamPersonnelSkill "*" --> "1" auth_User : created_by
    SxTeamPersonnelSkill "*" --> "1" auth_User : user
    SxTeamPersonnelSkill "*" --> "1" auth_User : updated_by
    SxTeamWorkClose "*" --> "1" auth_User : created_by
    SxTeamWorkClose "*" --> "1" SxProductionOrder : production_order
    SxTimeStudy "*" --> "1" SxOperation : operation
    SxTimeStudy "*" --> "1" SxMachine : machine
    SxWipBalance "*" --> "1" auth_User : created_by
    SxWipBalance "*" --> "1" SxProductionOrder : production_order
    SxWipHandover "*" --> "1" auth_User : created_by
    SxWipHandover "*" --> "1" SxProductionOrder : production_order
    SxWipReturn "*" --> "1" auth_User : created_by
    SxWipReturn "*" --> "1" SxWipHandover : handover
    SxWipReturn "*" --> "1" SxProductionOrder : production_order
    SxWorkAssignment "*" --> "1" auth_User : created_by
    SxWorkAssignment "*" --> "1" SxProductionOrder : production_order
    SxWorkAssignment "*" --> "1" SxWorkCenter : work_center
    SxWorkAssignment "*" --> "1" auth_User : assignee
    SxWorkAssignment "*" --> "1" tasks_WorkTask : work_task
    SxWorkCenter "*" --> "1" auth_User : created_by
    TechDocDesignFile "*" --> "1" ProductTechDoc : tech_doc
    TechDocDesignFile "*" --> "1" auth_User : uploaded_by
```
