# Class diagram — `auth`

3 model. Class có tiền tố `app_` là model thuộc app khác.

```mermaid
classDiagram
    direction LR
    class Group {
    +AutoField PK id
    +CharField UQ name
    +M2M permissions
    }
    class Permission {
    +AutoField PK id
    +CharField name
    +ForeignKey FK content_type
    +CharField codename
    }
    class User {
    +AutoField PK id
    +CharField password
    +DateTimeField? last_login
    +BooleanField is_superuser
    +CharField UQ username
    +CharField first_name
    +CharField last_name
    +CharField email
    +BooleanField is_staff
    +BooleanField is_active
    +DateTimeField date_joined
    +M2M groups
    +M2M user_permissions
    }

    class contenttypes_ContentType {
    +external
    }

    Group "*" <--> "*" Permission : permissions
    Permission "*" --> "1" contenttypes_ContentType : content_type
    User "*" <--> "*" Group : groups
    User "*" <--> "*" Permission : user_permissions
```
