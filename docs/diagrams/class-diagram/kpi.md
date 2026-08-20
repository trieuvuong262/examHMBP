# Class diagram — `kpi`

3 model. Class có tiền tố `app_` là model thuộc app khác.

```mermaid
classDiagram
    direction LR
    class KpiPeriod {
    +BigAutoField PK id
    +CharField title
    +IntegerField year
    +CharField period_type
    +BooleanField is_active
    }
    class YearlyKpi {
    +BigAutoField PK id
    +ForeignKey FK employee
    +IntegerField year
    +CharField eval_type
    +ForeignKey FK? direct_manager
    +ForeignKey FK? general_manager
    +CharField q1_status
    +CharField q2_status
    +CharField q3_status
    +CharField q4_status
    +CharField h1_status
    +CharField h2_status
    +CharField y_status
    +DateTimeField created_at
    }
    class YearlyKpiItem {
    +BigAutoField PK id
    +ForeignKey FK yearly_kpi
    +CharField pillar
    +TextField personal_objective
    +TextField kpi_indicator
    +FloatField weightage
    +FloatField yearly_target
    +CharField unit
    +CharField trend
    +FloatField? y_self
    +FloatField? y_mgr
    +FloatField? y_gm
    +FloatField? q1_self
    +FloatField? q2_self
    +FloatField? q3_self
    +FloatField? q4_self
    +FloatField? q1_mgr
    +FloatField? q2_mgr
    +FloatField? q3_mgr
    +FloatField? q4_mgr
    +FloatField? q1_gm
    +FloatField? q2_gm
    +FloatField? q3_gm
    +FloatField? q4_gm
    +FloatField? h1_self
    +FloatField? h2_self
    +FloatField? h1_mgr
    +FloatField? h2_mgr
    +FloatField? h1_gm
    +FloatField? h2_gm
    }

    class auth_User {
    +external
    }

    YearlyKpi "*" --> "1" auth_User : employee
    YearlyKpi "*" --> "1" auth_User : direct_manager
    YearlyKpi "*" --> "1" auth_User : general_manager
    YearlyKpiItem "*" --> "1" YearlyKpi : yearly_kpi
```
