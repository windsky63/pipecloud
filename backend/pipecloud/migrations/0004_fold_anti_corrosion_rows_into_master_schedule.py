from django.db import migrations


ANTI_COLUMNS = [
    ('commission_no', '防腐委托单号'),
    ('commission_date', '委托日期'),
    ('pre_schedule_seq', '预排产序号'),
    ('anti_corrosion_area', '防腐面积'),
    ('library_seq', '库序号'),
    ('unit', '单元号'),
    ('unit_name', '单元名称'),
    ('pipeline', '管线号'),
    ('segment_no', '管段号'),
    ('joint_type', '接头类型'),
    ('wall_thickness', '壁厚'),
    ('wall_thickness_no', '壁厚号'),
    ('diameter', '寸径'),
    ('outer_diameter', '外径'),
    ('weld_area', '焊接区域'),
    ('material', '材质'),
    ('material_code_name', '材质代号'),
    ('weld_no_start', '初始焊口号'),
    ('weld_no_final', '最终焊口号'),
    ('material_mark_1', '材料代号1'),
    ('material_mark_2', '材料代号2'),
    ('material_unique_1', '材料唯一码1'),
    ('material_unique_2', '材料唯一码2'),
    ('material_code_1', '材料代码1'),
    ('material_code_2', '材料代码2'),
    ('material_paint_1', '材料油漆1'),
    ('material_paint_2', '材料油漆2'),
    ('quantity_1', '数量1'),
    ('quantity_2', '数量2'),
    ('description_1', '描述1'),
    ('description_2', '描述2'),
    ('welding_mode', '焊接方式'),
    ('material_arrival_status', '材料到货状态'),
    ('material_anti_corrosion_status', '材料防腐状态'),
    ('material_cutting_status', '材料下料状态'),
    ('completed_flag', '材料焊接状态'),
    ('priority', '优先级'),
    ('pre_schedule_status', '预排产状态'),
    ('pre_schedule_reason', '不可预排产原因'),
]


def fold_anti_rows(apps, schema_editor):
    AntiRow = apps.get_model('pipecloud', 'AntiCorrosionCommissionRow')
    DataSourceFile = apps.get_model('pipecloud', 'DataSourceFile')
    MasterScheduleRow = apps.get_model('pipecloud', 'MasterScheduleRow')
    for row in AntiRow.objects.filter(source_file__source_type='plan').select_related('source_file', 'project'):
        library_seq = str(row.library_seq or '').strip()
        if not library_seq:
            continue
        payload = {}
        for field_name, column in ANTI_COLUMNS:
            value = getattr(row, field_name, '')
            payload[column] = str(value if value is not None else '')
        plan_folder = ''
        source_key = str(row.source_file.source_key or '')
        parts = source_key.split(':', 2)
        if len(parts) >= 2:
            plan_folder = parts[1]
        master, _ = MasterScheduleRow.objects.get_or_create(
            project=row.project,
            library_seq=library_seq,
            defaults={
                'anti_corrosion_order_no': row.commission_no or '',
                'anti_corrosion_date': str(row.commission_date or '')[:8],
                'anti_corrosion_plan_folder': plan_folder or str(row.commission_date or '')[:8],
                'unit': row.unit or '',
                'pipeline': row.pipeline or '',
                'segment_no': row.segment_no or '',
                'weld_no_start': row.weld_no_start or '',
                'weld_no_final': row.weld_no_final or '',
                'diameter': row.diameter or '',
                'wall_thickness': row.wall_thickness or '',
                'material': row.material or '',
                'completed_flag': str(row.completed_flag),
            },
        )
        stage_payload = dict(master.stage_payload or {})
        stage_payload['anti-corrosion'] = payload
        master.stage_payload = stage_payload
        master.anti_corrosion_order_no = master.anti_corrosion_order_no or row.commission_no or ''
        master.anti_corrosion_date = master.anti_corrosion_date or str(row.commission_date or '')[:8]
        master.anti_corrosion_plan_folder = master.anti_corrosion_plan_folder or plan_folder or str(row.commission_date or '')[:8]
        master.unit = master.unit or row.unit or ''
        master.pipeline = master.pipeline or row.pipeline or ''
        master.segment_no = master.segment_no or row.segment_no or ''
        master.weld_no_start = master.weld_no_start or row.weld_no_start or ''
        master.weld_no_final = master.weld_no_final or row.weld_no_final or ''
        master.diameter = master.diameter or row.diameter or ''
        master.wall_thickness = master.wall_thickness or row.wall_thickness or ''
        master.material = master.material or row.material or ''
        master.save()
    DataSourceFile.objects.filter(
        source_type='plan',
        source_key__startswith='anti-corrosion:',
        display_name__startswith='防腐委托单-',
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('pipecloud', '0003_remove_legacy_anti_corrosion_commission_library'),
    ]

    operations = [
        migrations.RunPython(fold_anti_rows, migrations.RunPython.noop),
        migrations.DeleteModel(
            name='AntiCorrosionCommissionRow',
        ),
    ]
