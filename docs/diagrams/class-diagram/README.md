# Class diagram — PortalJustPlay

Sinh tự động: `docker compose exec -T web python scripts/gen_class_diagram.py`

## Sơ đồ phụ thuộc giữa các module

```mermaid
flowchart LR
    announcements["announcements<br/>2 model"]
    assessment["assessment<br/>7 model"]
    audit["audit<br/>7 model"]
    auth["auth<br/>3 model"]
    documents["documents<br/>4 model"]
    equipment["equipment<br/>5 model"]
    feedback["feedback<br/>1 model"]
    hrm["hrm<br/>10 model"]
    kho_npl["kho_npl<br/>24 model"]
    kho_san_pham["kho_san_pham<br/>4 model"]
    kiotviet["kiotviet<br/>29 model"]
    kpi["kpi<br/>3 model"]
    nas_storage["nas_storage<br/>6 model"]
    recruitment["recruitment<br/>3 model"]
    reports["reports<br/>13 model"]
    san_xuat["san_xuat<br/>89 model"]
    service_requests["service_requests<br/>9 model"]
    surveys["surveys<br/>3 model"]
    tasks["tasks<br/>8 model"]
    tools["tools<br/>1 model"]
    training["training<br/>6 model"]
    utilities["utilities<br/>13 model"]
    zalo["zalo<br/>2 model"]

    announcements -->|2| auth
    assessment -->|2| auth
    audit -->|7| auth
    audit -->|1| equipment
    documents -->|3| auth
    equipment -->|2| auth
    equipment -->|2| hrm
    equipment -->|1| service_requests
    feedback -->|2| auth
    hrm -->|4| auth
    kho_npl -->|16| auth
    kho_san_pham -->|2| auth
    kho_san_pham -->|1| san_xuat
    kiotviet -->|2| auth
    kpi -->|3| auth
    nas_storage -->|6| auth
    recruitment -->|1| auth
    reports -->|10| auth
    san_xuat -->|61| auth
    san_xuat -->|1| hrm
    san_xuat -->|9| kho_npl
    san_xuat -->|1| tasks
    service_requests -->|6| auth
    service_requests -->|1| equipment
    service_requests -->|2| hrm
    surveys -->|3| auth
    surveys -->|1| training
    tasks -->|15| auth
    tasks -->|2| hrm
    tasks -->|1| san_xuat
    tools -->|1| auth
    training -->|1| assessment
    training -->|3| auth
    utilities -->|8| auth
    zalo -->|1| auth
```

## Chi tiết từng module

| Module | Model | Sơ đồ |
|---|---|---|
| `san_xuat` | 89 | [san_xuat.md](./san_xuat.md) |
| `kiotviet` | 29 | [kiotviet.md](./kiotviet.md) |
| `kho_npl` | 24 | [kho_npl.md](./kho_npl.md) |
| `reports` | 13 | [reports.md](./reports.md) |
| `utilities` | 13 | [utilities.md](./utilities.md) |
| `hrm` | 10 | [hrm.md](./hrm.md) |
| `service_requests` | 9 | [service_requests.md](./service_requests.md) |
| `tasks` | 8 | [tasks.md](./tasks.md) |
| `assessment` | 7 | [assessment.md](./assessment.md) |
| `audit` | 7 | [audit.md](./audit.md) |
| `training` | 6 | [training.md](./training.md) |
| `nas_storage` | 6 | [nas_storage.md](./nas_storage.md) |
| `equipment` | 5 | [equipment.md](./equipment.md) |
| `documents` | 4 | [documents.md](./documents.md) |
| `kho_san_pham` | 4 | [kho_san_pham.md](./kho_san_pham.md) |
| `auth` | 3 | [auth.md](./auth.md) |
| `recruitment` | 3 | [recruitment.md](./recruitment.md) |
| `kpi` | 3 | [kpi.md](./kpi.md) |
| `surveys` | 3 | [surveys.md](./surveys.md) |
| `announcements` | 2 | [announcements.md](./announcements.md) |
| `zalo` | 2 | [zalo.md](./zalo.md) |
| `feedback` | 1 | [feedback.md](./feedback.md) |
| `tools` | 1 | [tools.md](./tools.md) |

Tổng: **23 module**, **252 model**.
