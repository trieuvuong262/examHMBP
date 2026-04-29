from django.db import models

class MetabaseReport(models.Model):
    title = models.CharField(max_length=200, verbose_name="Tên Báo Cáo (VD: Thống kê Quý 1)")
    uuid = models.CharField(max_length=100, verbose_name="Mã UUID từ Metabase")
    
    # Phân biệt nó là Dashboard hay Question (Biểu đồ đơn)
    TYPE_CHOICES = [
        ('dashboard', 'Dashboard (Bảng điều khiển)'),
        ('question', 'Question (Biểu đồ đơn)'),
    ]
    report_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='dashboard', verbose_name="Loại báo cáo")
    
    is_active = models.BooleanField(default=True, verbose_name="Cho phép hiển thị")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
    
    class Meta:
        verbose_name = "Báo Cáo Metabase"
        verbose_name_plural = "Danh Sách Báo Cáo"