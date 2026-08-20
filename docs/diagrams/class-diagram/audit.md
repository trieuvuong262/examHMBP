# Class diagram — `audit`

7 model. Class có tiền tố `app_` là model thuộc app khác.

```mermaid
classDiagram
    direction LR
    class EmailSmtpConfig {
    +BigAutoField PK id
    +BooleanField enabled
    +CharField host
    +PositiveIntegerField port
    +CharField username
    +CharField password
    +BooleanField use_tls
    +BooleanField use_ssl
    +BooleanField ssl_verify
    +CharField from_email
    +DateTimeField updated_at
    +ForeignKey FK? updated_by
    }
    class IpLoginBlock {
    +BigAutoField PK id
    +GenericIPAddressField UQ ip_address
    +PositiveIntegerField failed_attempts
    +PositiveIntegerField unknown_username_count
    +JSONField sample_usernames
    +DateTimeField? blocked_at
    +DateTimeField? last_failed_at
    +DateTimeField? unlocked_at
    +ForeignKey FK? unlocked_by
    }
    class LoginSecurityConfig {
    +BigAutoField PK id
    +JSONField wan_whitelist_ips
    +JSONField ip_blacklist
    +DateTimeField updated_at
    +ForeignKey FK? updated_by
    }
    class PortalBackupJob {
    +BigAutoField PK id
    +CharField trigger
    +CharField status
    +ForeignKey FK? started_by
    +CharField remote_path
    +TextField message
    +JSONField artifacts
    +DateTimeField created_at
    +DateTimeField? started_at
    +DateTimeField? finished_at
    }
    class RustDeskHost {
    +BigAutoField PK id
    +CharField name
    +CharField hostname
    +GenericIPAddressField? ip_address
    +CharField mac_address
    +CharField UQ rustdesk_id
    +CharField rustdesk_password
    +CharField department_text
    +CharField assigned_user_text
    +TextField notes
    +ForeignKey FK? device
    +BooleanField is_active
    +DateTimeField created_at
    +DateTimeField updated_at
    }
    class UserActivityLog {
    +BigAutoField PK id
    +ForeignKey FK? user
    +CharField username
    +CharField full_name
    +CharField department_name
    +CharField role
    +CharField action
    +CharField module_key
    +CharField module_label
    +CharField summary
    +CharField path
    +CharField url_name
    +CharField method
    +CharField query_string
    +PositiveSmallIntegerField? status_code
    +PositiveIntegerField? duration_ms
    +GenericIPAddressField? ip_address
    +CharField machine_name
    +TextField user_agent
    +CharField referer
    +CharField object_type
    +CharField object_id
    +CharField object_repr
    +JSONField request_data
    +JSONField changes
    +JSONField extra
    +DateTimeField created_at
    }
    class UserLoginLock {
    +BigAutoField PK id
    +OneToOneField FK user
    +CharField username_snapshot
    +PositiveSmallIntegerField failed_attempts
    +DateTimeField? locked_at
    +DateTimeField? last_failed_at
    +GenericIPAddressField? last_ip
    +DateTimeField? unlocked_at
    +ForeignKey FK? unlocked_by
    }

    class auth_User {
    +external
    }
    class equipment_Device {
    +external
    }

    EmailSmtpConfig "*" --> "1" auth_User : updated_by
    IpLoginBlock "*" --> "1" auth_User : unlocked_by
    LoginSecurityConfig "*" --> "1" auth_User : updated_by
    PortalBackupJob "*" --> "1" auth_User : started_by
    RustDeskHost "*" --> "1" equipment_Device : device
    UserActivityLog "*" --> "1" auth_User : user
    UserLoginLock "1" --> "1" auth_User : user
    UserLoginLock "*" --> "1" auth_User : unlocked_by
```
