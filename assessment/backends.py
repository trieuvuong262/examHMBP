# assessment/backends.py
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

UserModel = get_user_model()

class EmailOrUsernameModelBackend(ModelBackend):
    """
    Bộ kiểm duyệt tự tạo: Cho phép đăng nhập bằng cả Email hoặc Username.
    Hệ thống sẽ quét xem chuỗi người dùng nhập vào khớp với cái nào thì lấy cái đó.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
            
        try:
            # Tìm user có username HOẶC email khớp với chữ nhập vào (không phân biệt hoa thường)
            user = UserModel.objects.get(
                Q(username__iexact=username) | Q(email__iexact=username)
            )
        except UserModel.DoesNotExist:
            # Bảo mật: Dù không tìm thấy user, vẫn chạy giả lập hàm kiểm tra pass 
            # để hacker không thể đo thời gian server phản hồi để đoán email có tồn tại hay không
            UserModel().set_password(password)
            return None
        except UserModel.MultipleObjectsReturned:
            # Đề phòng trường hợp trùng email, lấy cái đầu tiên
            user = UserModel.objects.filter(
                Q(username__iexact=username) | Q(email__iexact=username)
            ).order_by('id').first()

        # Kiểm tra mật khẩu
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
            
        return None