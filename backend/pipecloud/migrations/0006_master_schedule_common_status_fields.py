from django.db import migrations, models


COMMON_VALUE_FIELDS = [
    ('priority', ['优先级']),
    ('material_arrival_status', ['材料到货状态', '到货状态']),
    ('material_anti_corrosion_status', ['材料防腐状态', '防腐状态']),
    ('material_cutting_status', ['材料下料状态', '下料状态']),
    ('completed_flag', ['材料焊接状态', '是否完成', '完成状态', '焊接状态']),
]
COMMON_PAYLOAD_COLUMNS = {
    '库序号',
    '来源工作表',
    '单元号',
    '管线号',
    '管段号',
    '初始焊口号',
    '最终焊口号',
    '寸径',
    '壁厚',
    '材质',
    '优先级',
    '材料到货状态',
    '到货状态',
    '材料防腐状态',
    '防腐状态',
    '材料下料状态',
    '下料状态',
    '材料焊接状态',
    '是否完成',
    '完成状态',
    '焊接状态',
}
ANTI_STAGE_COLUMNS = {'防腐面积', '材料油漆', '材料油漆1', '材料油漆2'}


def _first_payload_value(payload, column_names):
    for stage_payload in (payload or {}).values():
        if not isinstance(stage_payload, dict):
            continue
        for column_name in column_names:
            value = stage_payload.get(column_name)
            text = str(value if value is not None else '').strip()
            if text:
                return text
    return ''


def move_common_values_from_stage_payload(apps, schema_editor):
    MasterScheduleRow = apps.get_model('pipecloud', 'MasterScheduleRow')
    for row in MasterScheduleRow.objects.all():
        payload = dict(row.stage_payload or {})
        update_fields = []
        for field_name, column_names in COMMON_VALUE_FIELDS:
            if str(getattr(row, field_name, '') or '').strip():
                continue
            value = _first_payload_value(payload, column_names)
            if value:
                setattr(row, field_name, value)
                update_fields.append(field_name)

        trimmed_payload = {}
        for stage_key, stage_payload in payload.items():
            if not isinstance(stage_payload, dict):
                continue
            if stage_key == 'anti-corrosion':
                keep_columns = ANTI_STAGE_COLUMNS
                next_stage_payload = {
                    column: value
                    for column, value in stage_payload.items()
                    if column in keep_columns
                }
            else:
                next_stage_payload = {
                    column: value
                    for column, value in stage_payload.items()
                    if column not in COMMON_PAYLOAD_COLUMNS
                }
            trimmed_payload[stage_key] = next_stage_payload

        if trimmed_payload != payload:
            row.stage_payload = trimmed_payload
            update_fields.append('stage_payload')
        if update_fields:
            row.save(update_fields=[*update_fields, 'updated_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('pipecloud', '0005_trim_master_schedule_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='masterschedulerow',
            name='priority',
            field=models.CharField(blank=True, max_length=80, verbose_name='优先级'),
        ),
        migrations.AddField(
            model_name='masterschedulerow',
            name='material_arrival_status',
            field=models.CharField(blank=True, max_length=80, verbose_name='材料到货状态'),
        ),
        migrations.AddField(
            model_name='masterschedulerow',
            name='material_anti_corrosion_status',
            field=models.CharField(blank=True, max_length=80, verbose_name='材料防腐状态'),
        ),
        migrations.AddField(
            model_name='masterschedulerow',
            name='material_cutting_status',
            field=models.CharField(blank=True, max_length=80, verbose_name='材料下料状态'),
        ),
        migrations.AlterField(
            model_name='masterschedulerow',
            name='completed_flag',
            field=models.CharField(blank=True, max_length=80, verbose_name='材料焊接状态'),
        ),
        migrations.RunPython(move_common_values_from_stage_payload, migrations.RunPython.noop),
    ]
