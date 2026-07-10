from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pipecloud', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='MasterScheduleRow',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('library_seq', models.CharField(max_length=120, verbose_name='库序号')),
                ('process_sequence', models.CharField(blank=True, max_length=40, verbose_name='工序顺序')),
                ('production_start_stage', models.CharField(blank=True, choices=[('anti-corrosion', '防腐'), ('cutting', '下料'), ('welding', '焊接')], max_length=32, verbose_name='生产开始阶段')),
                ('production_start_date', models.CharField(blank=True, max_length=8, verbose_name='生产开始日期')),
                ('anti_corrosion_order_no', models.CharField(blank=True, max_length=120, verbose_name='防腐委托单号')),
                ('anti_corrosion_date', models.CharField(blank=True, max_length=8, verbose_name='防腐日期')),
                ('anti_corrosion_plan_folder', models.CharField(blank=True, max_length=120, verbose_name='防腐计划文件夹')),
                ('cut_order_no', models.CharField(blank=True, max_length=120, verbose_name='下料排产单号')),
                ('cut_date', models.CharField(blank=True, max_length=8, verbose_name='下料日期')),
                ('cut_plan_folder', models.CharField(blank=True, max_length=120, verbose_name='下料计划文件夹')),
                ('weld_order_no', models.CharField(blank=True, max_length=120, verbose_name='焊接排产单号')),
                ('weld_date', models.CharField(blank=True, max_length=8, verbose_name='焊接日期')),
                ('weld_plan_folder', models.CharField(blank=True, max_length=120, verbose_name='焊接计划文件夹')),
                ('source_sheet', models.CharField(blank=True, max_length=120, verbose_name='来源工作表')),
                ('unit', models.CharField(blank=True, max_length=120, verbose_name='单元号')),
                ('pipeline', models.CharField(blank=True, max_length=255, verbose_name='管线号')),
                ('segment_no', models.CharField(blank=True, max_length=120, verbose_name='管段号')),
                ('weld_no_start', models.CharField(blank=True, max_length=120, verbose_name='初始焊口号')),
                ('weld_no_final', models.CharField(blank=True, max_length=120, verbose_name='最终焊口号')),
                ('diameter', models.CharField(blank=True, max_length=80, verbose_name='寸径')),
                ('wall_thickness', models.CharField(blank=True, max_length=80, verbose_name='壁厚')),
                ('material', models.CharField(blank=True, max_length=120, verbose_name='材质')),
                ('completed_flag', models.CharField(blank=True, max_length=80, verbose_name='焊接完成状态')),
                ('stage_payload', models.JSONField(blank=True, default=dict, verbose_name='阶段计划数据')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='pipecloud.project', verbose_name='项目')),
            ],
            options={
                'verbose_name': '排产计划库',
                'verbose_name_plural': '排产计划库',
                'ordering': ['project', 'library_seq'],
            },
        ),
        migrations.AddIndex(
            model_name='masterschedulerow',
            index=models.Index(fields=['project', 'anti_corrosion_plan_folder'], name='pipecloud_master_anti_plan'),
        ),
        migrations.AddIndex(
            model_name='masterschedulerow',
            index=models.Index(fields=['project', 'cut_plan_folder'], name='pipecloud_master_cut_plan'),
        ),
        migrations.AddIndex(
            model_name='masterschedulerow',
            index=models.Index(fields=['project', 'weld_plan_folder'], name='pipecloud_master_weld_plan'),
        ),
        migrations.AddConstraint(
            model_name='masterschedulerow',
            constraint=models.UniqueConstraint(fields=('project', 'library_seq'), name='pipecloud_master_schedule_unique_library_seq'),
        ),
    ]
