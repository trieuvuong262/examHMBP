# Class diagram — `kho_san_pham`

4 model. Class có tiền tố `app_` là model thuộc app khác.

```mermaid
classDiagram
    direction LR
    class Product {
    +BigAutoField PK id
    +CharField product_type
    +ForeignKey FK? catalog_type
    +CharField style_code
    +CharField color_code
    +CharField color_label
    +CharField size_label
    +CharField UQ code
    +ForeignKey FK? sx_sku
    +CharField accounting_code
    +CharField kiotviet_code
    +BigIntegerField UQ? kiotviet_id
    +CharField name
    +CharField full_name
    +CharField bar_code
    +CharField unit
    +CharField category_name
    +CharField category_path
    +TextField description
    +DecimalField base_price
    +FileField image
    +CharField image_url
    +BooleanField? allows_sale
    +BooleanField is_active
    +CharField sync_source
    +DateTimeField? kv_modified_at
    +DateTimeField? synced_at
    +TextField notes
    +ForeignKey FK? created_by
    +DateTimeField created_at
    +DateTimeField updated_at
    }
    class ProductStyle {
    +BigAutoField PK id
    +CharField UQ code
    +ForeignKey FK product_type
    +CharField name
    +CharField brand
    +PositiveSmallIntegerField? year
    +PositiveIntegerField? sequence
    +CharField root_kiotviet_code
    +CharField source
    +BooleanField is_active
    +ForeignKey FK? created_by
    +DateTimeField created_at
    +DateTimeField updated_at
    }
    class ProductType {
    +BigAutoField PK id
    +CharField UQ code
    +CharField name
    +PositiveSmallIntegerField sort_order
    +BooleanField is_active
    }
    class ProductTypeKvMap {
    +BigAutoField PK id
    +CharField match_value
    +CharField match_mode
    +ForeignKey FK product_type
    +PositiveSmallIntegerField priority
    +BooleanField is_active
    +CharField notes
    }

    class auth_User {
    +external
    }
    class san_xuat_SxSku {
    +external
    }

    Product "*" --> "1" ProductType : catalog_type
    Product "*" --> "1" san_xuat_SxSku : sx_sku
    Product "*" --> "1" auth_User : created_by
    ProductStyle "*" --> "1" ProductType : product_type
    ProductStyle "*" --> "1" auth_User : created_by
    ProductTypeKvMap "*" --> "1" ProductType : product_type
```
