# Requirements Document

## Introduction

Tính năng "Tiến độ" cho phép bộ phận IT ghi lại tiến độ các chức năng mới được release trên Portal nội bộ hoặc trên website sỉ/lẻ, đồng thời cho người dùng test ghi phản hồi (feedback) và ghi chú. Tính năng gồm 2 menu con: "Tiến độ Portal" và "Tiến độ Website sỉ/lẻ". Mỗi menu con hiển thị một bảng dạng Excel chỉnh sửa trực tiếp (inline) gồm 5 cột: Tính năng, Mô tả, User flow, Feedback, Ghi chú.

Phân quyền theo cột dựa trên nhóm quyền sẵn có của module (create/update):
- Người thuộc nhóm có quyền tạo/sửa (IT) được thêm dòng, xóa dòng và sửa 3 cột đầu (Tính năng, Mô tả, User flow).
- Người dùng test chỉ được sửa 2 cột Feedback và Ghi chú.
- Cả hai nhóm cùng thao tác trên một bảng, nhưng quyền chỉnh sửa phân tách theo cột.

Tính năng tích hợp với hệ thống phân quyền menu theo phòng ban và nhóm quyền hiện có của PortalJustPlay (module key `tien_do`, URL `/tien-do/`), dùng registry submenu giống nhóm Khảo sát và decorator `module_perm_required` giống app announcements.

Portal và Website sỉ/lẻ dùng chung model, phân biệt bằng trường nền tảng (`platform`). Mỗi dòng ghi lại người tạo, thời gian tạo/cập nhật và cờ đánh dấu đã test hay chưa.

## Glossary

- **Tien_Do_Module**: Chức năng "Tiến độ" trong PortalJustPlay, có module key `tien_do`, URL gốc `/tien-do/`, nhãn menu "Tiến độ".
- **Tien_Do_Item**: Một dòng tiến độ trong bảng, gồm các trường: Tính năng, Mô tả, User flow, Feedback, Ghi chú, nền tảng, người tạo, thời gian tạo, thời gian cập nhật, cờ đã test.
- **Platform**: Trường phân biệt nền tảng của một Tien_Do_Item; nhận một trong hai giá trị `portal` (Portal nội bộ) hoặc `wholesale_retail` (Website sỉ/lẻ).
- **Submenu_Portal**: Menu con "Tiến độ Portal", key `portal`, hiển thị các Tien_Do_Item có Platform = `portal`.
- **Submenu_Wholesale_Retail**: Menu con "Tiến độ Website sỉ/lẻ", key `wholesale_retail`, hiển thị các Tien_Do_Item có Platform = `wholesale_retail`.
- **IT_User**: Người dùng thuộc nhóm quyền có quyền `create` và/hoặc `update` trên Tien_Do_Module; được thêm/xóa dòng và sửa các cột do IT nhập.
- **Tester_User**: Người dùng có quyền `view` nhưng không có quyền `create`/`update` của IT; chỉ được sửa các cột Feedback và Ghi chú. (Lưu ý: trong module này, quyền sửa cột Feedback/Ghi chú được cấp cho người có quyền `view`.)
- **IT_Columns**: Tập cột do IT nhập, gồm Tính năng, Mô tả, User flow.
- **Tester_Columns**: Tập cột do người test nhập, gồm Feedback, Ghi chú.
- **Inline_Table**: Bảng dạng Excel cho phép click vào ô để sửa trực tiếp và lưu qua AJAX.
- **Permission_System**: Hệ thống phân quyền menu theo phòng ban (`hrm/module_permissions.py`) kết hợp nhóm quyền hành động (`hrm/group_permissions.py`), registry submenu (`hrm/submenu_registry.py`).
- **PERM_VIEW / PERM_CREATE / PERM_UPDATE / PERM_DELETE**: Các hành động quyền của nhóm quyền áp cho module `tien_do`.
- **Admin_User**: Tài khoản quản trị hệ thống — người dùng có `is_superuser = True` hoặc username `admin`. Tương ứng hàm `bypass_department_modules` trong Permission_System; được bỏ qua mọi giới hạn phòng ban và nhóm quyền.

## Requirements

### Requirement 1: Đăng ký module và điều hướng menu

**User Story:** Là quản trị viên hệ thống, tôi muốn chức năng "Tiến độ" được đăng ký vào hệ thống phân quyền và sidebar, để người dùng được cấp quyền có thể truy cập qua menu.

#### Acceptance Criteria

1. THE Tien_Do_Module SHALL đăng ký module key `tien_do` với nhãn "Tiến độ" trong danh sách module của Permission_System.
2. THE Tien_Do_Module SHALL ánh xạ tiền tố URL `/tien-do/` tới module key `tien_do` trong bảng ánh xạ đường dẫn của Permission_System.
3. THE Tien_Do_Module SHALL đăng ký hai menu con trong registry submenu: Submenu_Portal (key `portal`, nhãn "Tiến độ Portal") và Submenu_Wholesale_Retail (key `wholesale_retail`, nhãn "Tiến độ Website sỉ/lẻ").
4. THE Tien_Do_Module SHALL xuất hiện trong một nhóm sidebar của Permission_System với hai menu con tương ứng.
8. THE Tien_Do_Module SHALL xuất hiện như một mục chọn trên màn hình phân quyền menu theo phòng ban (`/dashboard/departments/<id>/permissions/`), để quản trị viên có thể bật/tắt module `tien_do` cho từng phòng ban.
9. THE Permission_System SHALL giữ nhất quán tập module giữa danh sách lựa chọn module (`MODULE_CHOICES`) và các nhóm trên màn hình phân quyền phòng ban (`DEPARTMENT_MENU_SECTIONS`), sao cho module `tien_do` có mặt ở cả hai.
10. THE Tien_Do_Module SHALL cho phép cấu hình quyền hành động (`view`, `create`, `update`, `delete`) của module `tien_do` theo từng nhóm quyền trong ma trận nhóm quyền của Permission_System.
5. WHEN một người dùng không được cấp quyền `view` trên module `tien_do` truy cập đường dẫn `/tien-do/`, THE Permission_System SHALL từ chối truy cập và chuyển hướng về trang chủ với thông báo không có quyền.
6. WHEN một người dùng được cấp quyền `view` trên module `tien_do` và được phép xem Submenu_Portal truy cập đường dẫn `/tien-do/`, THE Tien_Do_Module SHALL chuyển hướng tới Submenu_Portal.
7. IF một người dùng được cấp quyền `view` nhưng không được phép xem Submenu_Portal truy cập đường dẫn `/tien-do/`, THEN THE Tien_Do_Module SHALL chuyển hướng tới menu con khác mà người dùng được phép xem.

### Requirement 2: Quyền của quản trị viên hệ thống

**User Story:** Là Admin_User (superuser hoặc tài khoản `admin`), tôi muốn luôn thấy và truy cập được toàn bộ chức năng Tiến độ, để quản trị không bị chặn bởi cấu hình phòng ban hay nhóm quyền.

#### Acceptance Criteria

1. THE Tien_Do_Module SHALL luôn hiển thị menu "Tiến độ" cùng cả hai menu con (Submenu_Portal và Submenu_Wholesale_Retail) trên sidebar cho mọi Admin_User, bất kể cấu hình phòng ban hay nhóm quyền.
2. WHEN một Admin_User truy cập đường dẫn `/tien-do/` hoặc bất kỳ menu con nào, THE Tien_Do_Module SHALL cho phép truy cập mà không kiểm tra cấu hình module theo phòng ban hoặc nhóm quyền.
3. THE Tien_Do_Module SHALL cấp cho mọi Admin_User đầy đủ các quyền `view`, `create`, `update`, `delete` trên module `tien_do`.
4. THE Tien_Do_Module SHALL cho phép Admin_User chỉnh sửa inline mọi cột, gồm cả IT_Columns và Tester_Columns, không ở trạng thái chỉ đọc.
5. THE Tien_Do_Module SHALL hiển thị cho Admin_User toàn bộ điều khiển thêm dòng, xóa dòng và đánh dấu đã test.

### Requirement 3: Hiển thị bảng tiến độ theo nền tảng

**User Story:** Là người dùng được cấp quyền, tôi muốn xem bảng tiến độ của Portal hoặc Website sỉ/lẻ, để nắm được các chức năng đã release.

#### Acceptance Criteria

1. WHEN một người dùng có quyền `view` mở Submenu_Portal, THE Tien_Do_Module SHALL hiển thị Inline_Table chỉ chứa các Tien_Do_Item có Platform = `portal`.
2. WHEN một người dùng có quyền `view` mở Submenu_Wholesale_Retail, THE Tien_Do_Module SHALL hiển thị Inline_Table chỉ chứa các Tien_Do_Item có Platform = `wholesale_retail`.
3. THE Inline_Table SHALL hiển thị năm cột theo thứ tự: Tính năng, Mô tả, User flow, Feedback, Ghi chú.
4. THE Inline_Table SHALL hiển thị cờ đã test cùng thời gian cập nhật cho mỗi Tien_Do_Item.
5. WHEN danh sách Tien_Do_Item của một nền tảng vượt quá kích thước một trang, THE Tien_Do_Module SHALL phân trang kết quả.
6. WHEN không có Tien_Do_Item nào cho nền tảng đang xem, THE Tien_Do_Module SHALL hiển thị thông báo bảng trống.

### Requirement 4: Thêm dòng tiến độ

**User Story:** Là IT_User, tôi muốn thêm một dòng tiến độ mới cho nền tảng đang xem, để ghi lại chức năng vừa release.

#### Acceptance Criteria

1. WHEN một IT_User có quyền `create` gửi yêu cầu thêm dòng trên một nền tảng, THE Tien_Do_Module SHALL tạo một Tien_Do_Item mới với Platform bằng nền tảng đang xem.
2. WHEN một Tien_Do_Item được tạo, THE Tien_Do_Module SHALL gán người tạo bằng người dùng hiện tại và ghi thời gian tạo.
3. WHEN một Tien_Do_Item được tạo, THE Tien_Do_Module SHALL đặt cờ đã test bằng giá trị chưa test.
4. IF một người dùng không có quyền `create` gửi yêu cầu thêm dòng, THEN THE Tien_Do_Module SHALL từ chối yêu cầu và trả về mã lỗi 403 kèm thông báo không có quyền.

### Requirement 5: Chỉnh sửa inline theo phân quyền cột

**User Story:** Là người dùng, tôi muốn click vào một ô để sửa trực tiếp và lưu bằng AJAX, để cập nhật nhanh nội dung giống thao tác trên Excel.

#### Acceptance Criteria

1. WHEN một IT_User có quyền `update` lưu một ô thuộc IT_Columns qua AJAX, THE Tien_Do_Module SHALL lưu giá trị mới, cập nhật thời gian cập nhật và trả về kết quả thành công.
2. WHEN một Tester_User có quyền `view` lưu một ô thuộc Tester_Columns qua AJAX, THE Tien_Do_Module SHALL lưu giá trị mới, cập nhật thời gian cập nhật và trả về kết quả thành công.
3. IF một người dùng không có quyền `update` cố lưu một ô thuộc IT_Columns, THEN THE Tien_Do_Module SHALL từ chối yêu cầu và trả về mã lỗi 403 kèm thông báo không có quyền.
4. IF một người dùng không có quyền `view` trên module cố lưu một ô thuộc Tester_Columns, THEN THE Tien_Do_Module SHALL từ chối yêu cầu và trả về mã lỗi 403 kèm thông báo không có quyền.
5. IF một yêu cầu lưu inline tham chiếu tới tên cột không thuộc năm cột hợp lệ, THEN THE Tien_Do_Module SHALL từ chối yêu cầu và trả về mã lỗi kèm thông báo cột không hợp lệ.
6. IF một yêu cầu lưu inline tham chiếu tới một Tien_Do_Item không tồn tại, THEN THE Tien_Do_Module SHALL trả về mã lỗi 404.
7. WHILE một người dùng không có quyền sửa một cột, THE Tien_Do_Module SHALL hiển thị ô của cột đó ở trạng thái chỉ đọc trong Inline_Table.

### Requirement 6: Đánh dấu đã test

**User Story:** Là người dùng test, tôi muốn đánh dấu một dòng là đã test, để theo dõi trạng thái kiểm thử của từng chức năng.

#### Acceptance Criteria

1. WHEN một người dùng có quyền `view` gửi yêu cầu bật cờ đã test cho một Tien_Do_Item qua AJAX, THE Tien_Do_Module SHALL đặt cờ đã test bằng giá trị đã test và cập nhật thời gian cập nhật.
2. WHEN một người dùng có quyền `view` gửi yêu cầu tắt cờ đã test cho một Tien_Do_Item qua AJAX, THE Tien_Do_Module SHALL đặt cờ đã test bằng giá trị chưa test và cập nhật thời gian cập nhật.

### Requirement 7: Xóa dòng tiến độ

**User Story:** Là IT_User, tôi muốn xóa một dòng tiến độ không còn cần thiết, để giữ bảng gọn gàng.

#### Acceptance Criteria

1. WHEN một IT_User có quyền `delete` xác nhận xóa một Tien_Do_Item, THE Tien_Do_Module SHALL xóa Tien_Do_Item khỏi hệ thống.
2. WHEN một IT_User yêu cầu xóa một Tien_Do_Item, THE Tien_Do_Module SHALL yêu cầu bước xác nhận trước khi thực hiện xóa.
3. IF một người dùng không có quyền `delete` yêu cầu xóa một Tien_Do_Item, THEN THE Tien_Do_Module SHALL từ chối yêu cầu và trả về mã lỗi 403 kèm thông báo không có quyền.
4. IF một yêu cầu xóa tham chiếu tới một Tien_Do_Item không tồn tại, THEN THE Tien_Do_Module SHALL trả về mã lỗi 404.

### Requirement 8: Tìm kiếm

**User Story:** Là người dùng, tôi muốn tìm kiếm dòng tiến độ theo Tính năng hoặc Mô tả, để nhanh chóng tìm được chức năng cần xem.

#### Acceptance Criteria

1. WHEN một người dùng nhập từ khóa tìm kiếm, THE Tien_Do_Module SHALL hiển thị các Tien_Do_Item của nền tảng đang xem có Tính năng hoặc Mô tả chứa từ khóa (không phân biệt hoa thường).
2. WHEN từ khóa tìm kiếm rỗng, THE Tien_Do_Module SHALL hiển thị toàn bộ Tien_Do_Item của nền tảng đang xem.
3. WHEN một tìm kiếm được áp dụng cùng phân trang, THE Tien_Do_Module SHALL giữ lại từ khóa tìm kiếm trên các liên kết chuyển trang.

### Requirement 9: Hiển thị điều khiển theo quyền

**User Story:** Là người dùng, tôi muốn chỉ thấy các nút thao tác mà tôi được phép dùng, để giao diện rõ ràng và tránh thao tác bị từ chối.

#### Acceptance Criteria

1. WHILE một người dùng không có quyền `create`, THE Tien_Do_Module SHALL ẩn điều khiển thêm dòng trong giao diện.
2. WHILE một người dùng không có quyền `delete`, THE Tien_Do_Module SHALL ẩn điều khiển xóa dòng trong giao diện.
3. WHILE một người dùng không có quyền `update`, THE Tien_Do_Module SHALL hiển thị các cột thuộc IT_Columns ở trạng thái chỉ đọc.
