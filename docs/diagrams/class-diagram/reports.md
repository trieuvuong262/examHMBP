# Class diagram — `reports`

13 model. Class có tiền tố `app_` là model thuộc app khác.

```mermaid
classDiagram
    direction LR
    class DailyWorkReport {
    +BigAutoField PK id
    +ForeignKey FK employee
    +DateField report_date
    +CharField shift
    +CharField title
    +CharField report_profile
    +JSONField? spreadsheet_json
    +TextField document_html
    +TextField links
    +CharField report_period
    +CharField status
    +DateTimeField? submitted_at
    +DateTimeField? submit_clicked_at
    +DateTimeField? draft_saved_at
    +BooleanField hod_reviewed
    +DateTimeField? hod_reviewed_at
    +DateTimeField? hod_first_reviewed_at
    +BooleanField hod_rejected
    +DateTimeField? hod_rejected_at
    +CharField hod_note
    +DecimalField? declared_work_hours
    +DateTimeField? shift_started_at
    +ForeignKey FK? proxy_entered_by
    +BooleanField auto_submitted
    +DateTimeField created_at
    +DateTimeField updated_at
    }
    class DailyWorkReportAttachment {
    +BigAutoField PK id
    +ForeignKey FK report
    +CharField source_tab
    +CharField kind
    +FileField file
    +CharField original_name
    +DateTimeField created_at
    }
    class DailyWorkReportEditLog {
    +BigAutoField PK id
    +ForeignKey FK report
    +ForeignKey FK? edited_by
    +CharField actor_kind
    +CharField action
    +CharField summary
    +TextField detail
    +DateTimeField edited_at
    }
    class DailyWorkReportLine {
    +BigAutoField PK id
    +ForeignKey FK report
    +CharField area
    +CharField order_code
    +CharField product_name
    +PositiveIntegerField quantity
    +CharField unit
    +CharField note
    +PositiveSmallIntegerField sort_order
    }
    class ProductionHourlyQuantity {
    +BigAutoField PK id
    +ForeignKey FK product
    +PositiveSmallIntegerField slot_index
    +DecimalField quantity
    +PositiveIntegerField damaged_quantity
    +CharField note
    +DecimalField? partial_hours
    +CharField zero_reason
    }
    class ProductionReportImageImport {
    +BigAutoField PK id
    +ForeignKey FK? employee
    +DateField report_date
    +CharField shift
    +FileField image
    +CharField original_name
    +JSONField extracted_data
    +CharField error_message
    +CharField status
    +ForeignKey FK? created_by
    +ForeignKey FK? applied_report
    +DateTimeField? applied_at
    +DateTimeField created_at
    +DateTimeField updated_at
    }
    class ProductionReportReminderLog {
    +BigAutoField PK id
    +ForeignKey FK employee
    +DateField report_date
    +CharField shift
    +PositiveSmallIntegerField wave
    +DateTimeField sent_at
    }
    class ProductionShiftProduct {
    +BigAutoField PK id
    +ForeignKey FK report
    +CharField product_code
    +CharField process_name
    +DecimalField? norm_per_hour
    +CharField status
    +PositiveSmallIntegerField sort_order
    +PositiveSmallIntegerField first_slot_index
    +DateTimeField? started_at
    +DateTimeField? ended_at
    +DecimalField? total_quantity
    +PositiveIntegerField total_damaged_quantity
    +CharField completion_note
    +BooleanField submitted_locked
    +ForeignKey FK? updated_by
    }
    class ReportComment {
    +BigAutoField PK id
    +ForeignKey FK? daily_report
    +ForeignKey FK? weekly_report
    +ForeignKey FK author
    +TextField body
    +BooleanField is_read
    +DateTimeField created_at
    }
    class ReportCommentAttachment {
    +BigAutoField PK id
    +ForeignKey FK comment
    +CharField kind
    +FileField file
    +CharField original_name
    +DateTimeField created_at
    }
    class ReportsGeneralSettings {
    +BigAutoField PK id
    +BooleanField workers_may_edit_stage_time
    +BooleanField managers_may_edit_stage_time
    +BooleanField allow_edit_wrong_stage_time
    +PositiveSmallIntegerField max_time_efficiency_pct
    +PositiveSmallIntegerField max_quantity_efficiency_pct
    +TimeField auto_submit_time
    +BooleanField night_auto_submit_enabled
    +TimeField night_auto_submit_time
    +DecimalField night_default_declared_work_hours
    +PositiveSmallIntegerField approve_deadline_hours
    +PositiveSmallIntegerField unapprove_deadline_days
    +PositiveSmallIntegerField auto_reject_deadline_hours
    +PositiveSmallIntegerField employee_edit_deadline_hours
    +DecimalField default_declared_work_hours
    +DecimalField work_hours_min
    +DecimalField work_hours_max
    +BooleanField auto_approve_proxy_reports
    +BooleanField auto_approve_manager_edited_reports
    +DateTimeField updated_at
    +ForeignKey FK? updated_by
    }
    class WeeklyWorkReport {
    +BigAutoField PK id
    +ForeignKey FK employee
    +DateField week_start
    +CharField report_profile
    +TextField links
    +CharField status
    +DateTimeField? submitted_at
    +DateTimeField? draft_saved_at
    +BooleanField hod_reviewed
    +CharField hod_note
    +DateTimeField created_at
    +DateTimeField updated_at
    }
    class WeeklyWorkReportAttachment {
    +BigAutoField PK id
    +ForeignKey FK report
    +CharField kind
    +FileField file
    +CharField original_name
    +DateTimeField created_at
    }

    class auth_User {
    +external
    }

    DailyWorkReport "*" --> "1" auth_User : employee
    DailyWorkReport "*" --> "1" auth_User : proxy_entered_by
    DailyWorkReportAttachment "*" --> "1" DailyWorkReport : report
    DailyWorkReportEditLog "*" --> "1" DailyWorkReport : report
    DailyWorkReportEditLog "*" --> "1" auth_User : edited_by
    DailyWorkReportLine "*" --> "1" DailyWorkReport : report
    ProductionHourlyQuantity "*" --> "1" ProductionShiftProduct : product
    ProductionReportImageImport "*" --> "1" auth_User : employee
    ProductionReportImageImport "*" --> "1" auth_User : created_by
    ProductionReportImageImport "*" --> "1" DailyWorkReport : applied_report
    ProductionReportReminderLog "*" --> "1" auth_User : employee
    ProductionShiftProduct "*" --> "1" DailyWorkReport : report
    ProductionShiftProduct "*" --> "1" auth_User : updated_by
    ReportComment "*" --> "1" DailyWorkReport : daily_report
    ReportComment "*" --> "1" WeeklyWorkReport : weekly_report
    ReportComment "*" --> "1" auth_User : author
    ReportCommentAttachment "*" --> "1" ReportComment : comment
    ReportsGeneralSettings "*" --> "1" auth_User : updated_by
    WeeklyWorkReport "*" --> "1" auth_User : employee
    WeeklyWorkReportAttachment "*" --> "1" WeeklyWorkReport : report
```
