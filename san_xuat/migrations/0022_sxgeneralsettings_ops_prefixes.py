# Generated manually — OEE, banner YCX, prefix mã chứng từ

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0021_sxgeneralsettings_expand'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='oee_shift_hours',
            field=models.PositiveSmallIntegerField(
                default=8,
                help_text='Dùng tính sẵn sàng trên màn Dừng chuyền / OEE.',
                verbose_name='Số giờ / ca (OEE)',
            ),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='show_pending_ycx_banner',
            field=models.BooleanField(
                default=True,
                help_text='Banner trên hub Điều phối khi còn YCX chờ duyệt.',
                verbose_name='Hiện banner hàng đợi duyệt xuất vật tư',
            ),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='prefix_mo',
            field=models.CharField(default='LSX', max_length=16, verbose_name='Prefix lệnh SX'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='prefix_ycx',
            field=models.CharField(default='YCX', max_length=16, verbose_name='Prefix yêu cầu xuất'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='prefix_stat',
            field=models.CharField(default='TKSX', max_length=16, verbose_name='Prefix thống kê SX'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='prefix_fg',
            field=models.CharField(default='YCNTP', max_length=16, verbose_name='Prefix yêu cầu nhập TP'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='prefix_qc_req',
            field=models.CharField(default='YCKT', max_length=16, verbose_name='Prefix yêu cầu kiểm tra'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='prefix_qc_sheet',
            field=models.CharField(default='PKT', max_length=16, verbose_name='Prefix phiếu kiểm tra'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='prefix_qc_alert',
            field=models.CharField(default='CBQC', max_length=16, verbose_name='Prefix cảnh báo QC'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='prefix_wip_ho',
            field=models.CharField(default='BG', max_length=16, verbose_name='Prefix bàn giao BTP'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='prefix_wip_ret',
            field=models.CharField(default='TRABTP', max_length=16, verbose_name='Prefix trả lại BTP'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='prefix_disassembly',
            field=models.CharField(default='LTD', max_length=16, verbose_name='Prefix lệnh tháo dỡ'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='prefix_npl_surplus',
            field=models.CharField(default='NPLT', max_length=16, verbose_name='Prefix NPL thừa'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='prefix_packing',
            field=models.CharField(default='DG', max_length=16, verbose_name='Prefix đóng gói'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='prefix_subcontract',
            field=models.CharField(default='GC', max_length=16, verbose_name='Prefix thuê gia công'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='prefix_work_assign',
            field=models.CharField(default='GV', max_length=16, verbose_name='Prefix giao việc'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='prefix_plan_overall',
            field=models.CharField(default='KHTT', max_length=16, verbose_name='Prefix KH tổng thể'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='prefix_plan_npl',
            field=models.CharField(default='KHNVL', max_length=16, verbose_name='Prefix KH NPL'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='prefix_plan_detail',
            field=models.CharField(default='KHCT', max_length=16, verbose_name='Prefix KH chi tiết'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='prefix_npl_pr',
            field=models.CharField(default='YCM', max_length=16, verbose_name='Prefix YC mua NPL'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='prefix_po',
            field=models.CharField(default='DMH', max_length=16, verbose_name='Prefix đơn mua hàng'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='prefix_cost_std',
            field=models.CharField(default='GTDM', max_length=16, verbose_name='Prefix GT định mức'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='prefix_cost_order',
            field=models.CharField(default='GTDH', max_length=16, verbose_name='Prefix GT theo ĐH'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='prefix_actual_cost',
            field=models.CharField(default='GTT', max_length=16, verbose_name='Prefix GT thực tế'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='prefix_ncr',
            field=models.CharField(default='NCR', max_length=16, verbose_name='Prefix NCR'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='prefix_downtime',
            field=models.CharField(default='DT', max_length=16, verbose_name='Prefix dừng chuyền'),
        ),
    ]
