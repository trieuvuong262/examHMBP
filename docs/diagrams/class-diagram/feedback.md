# Class diagram — `feedback`

1 model. Class có tiền tố `app_` là model thuộc app khác.

```mermaid
classDiagram
    direction LR
    class Feedback {
    +BigAutoField PK id
    +ForeignKey FK submitter
    +CharField title
    +TextField body
    +BooleanField is_anonymous
    +ForeignKey FK? viewed_by
    +DateTimeField? viewed_at
    +DateTimeField created_at
    }

    class auth_User {
    +external
    }

    Feedback "*" --> "1" auth_User : submitter
    Feedback "*" --> "1" auth_User : viewed_by
```
