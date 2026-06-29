from django.db import migrations, models


OLD_FIELDS = [
    'material_side',
    'material_unique',
    'material_code',
    'material_mark',
    'design_cut_length',
    'unit_name',
    'material_paint',
    'description',
]


def split_joined_values(value):
    text = str(value or '').strip()
    if not text or text.lower() == 'nan':
        return []
    return [item.strip() for item in text.replace(',', '、').split('、') if item.strip()]


def migrate_split_material_fields(apps, schema_editor):
    WeldingPlanRow = apps.get_model('pipecloud', 'WeldingPlanRow')
    rows = []
    for row in WeldingPlanRow.objects.all():
        uniques = split_joined_values(getattr(row, 'material_unique', ''))
        codes = split_joined_values(getattr(row, 'material_code', ''))
        marks = split_joined_values(getattr(row, 'material_mark', ''))
        quantities = split_joined_values(getattr(row, 'design_cut_length', ''))
        units = split_joined_values(getattr(row, 'unit_name', ''))
        paints = split_joined_values(getattr(row, 'material_paint', ''))
        descriptions = split_joined_values(getattr(row, 'description', ''))
        for side_index in range(2):
            side = side_index + 1
            setattr(row, f'material_unique_{side}', uniques[side_index] if side_index < len(uniques) else '')
            setattr(row, f'material_code_{side}', codes[side_index] if side_index < len(codes) else '')
            setattr(row, f'material_mark_{side}', marks[side_index] if side_index < len(marks) else '')
            setattr(row, f'quantity_{side}', quantities[side_index] if side_index < len(quantities) else '')
            setattr(row, f'unit_name_{side}', units[side_index] if side_index < len(units) else '')
            setattr(row, f'material_paint_{side}', paints[side_index] if side_index < len(paints) else '')
            setattr(row, f'description_{side}', descriptions[side_index] if side_index < len(descriptions) else '')
        rows.append(row)
    if rows:
        WeldingPlanRow.objects.bulk_update(rows, [
            'material_unique_1',
            'material_unique_2',
            'material_code_1',
            'material_code_2',
            'material_mark_1',
            'material_mark_2',
            'quantity_1',
            'quantity_2',
            'unit_name_1',
            'unit_name_2',
            'material_paint_1',
            'material_paint_2',
            'description_1',
            'description_2',
        ])


class Migration(migrations.Migration):

    dependencies = [
        ('pipecloud', '0004_remove_derived_schedule_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='weldingplanrow',
            name='description_1',
            field=models.TextField(blank=True, verbose_name='描述1'),
        ),
        migrations.AddField(
            model_name='weldingplanrow',
            name='description_2',
            field=models.TextField(blank=True, verbose_name='描述2'),
        ),
        migrations.AddField(
            model_name='weldingplanrow',
            name='material_code_1',
            field=models.CharField(blank=True, max_length=120, verbose_name='材料代码1'),
        ),
        migrations.AddField(
            model_name='weldingplanrow',
            name='material_code_2',
            field=models.CharField(blank=True, max_length=120, verbose_name='材料代码2'),
        ),
        migrations.AddField(
            model_name='weldingplanrow',
            name='material_mark_1',
            field=models.CharField(blank=True, max_length=120, verbose_name='材料代号1'),
        ),
        migrations.AddField(
            model_name='weldingplanrow',
            name='material_mark_2',
            field=models.CharField(blank=True, max_length=120, verbose_name='材料代号2'),
        ),
        migrations.AddField(
            model_name='weldingplanrow',
            name='material_paint_1',
            field=models.CharField(blank=True, max_length=120, verbose_name='材料油漆1'),
        ),
        migrations.AddField(
            model_name='weldingplanrow',
            name='material_paint_2',
            field=models.CharField(blank=True, max_length=120, verbose_name='材料油漆2'),
        ),
        migrations.AddField(
            model_name='weldingplanrow',
            name='material_unique_1',
            field=models.TextField(blank=True, verbose_name='材料唯一码1'),
        ),
        migrations.AddField(
            model_name='weldingplanrow',
            name='material_unique_2',
            field=models.TextField(blank=True, verbose_name='材料唯一码2'),
        ),
        migrations.AddField(
            model_name='weldingplanrow',
            name='quantity_1',
            field=models.CharField(blank=True, max_length=80, verbose_name='数量1'),
        ),
        migrations.AddField(
            model_name='weldingplanrow',
            name='quantity_2',
            field=models.CharField(blank=True, max_length=80, verbose_name='数量2'),
        ),
        migrations.AddField(
            model_name='weldingplanrow',
            name='unit_name_1',
            field=models.CharField(blank=True, max_length=40, verbose_name='单位1'),
        ),
        migrations.AddField(
            model_name='weldingplanrow',
            name='unit_name_2',
            field=models.CharField(blank=True, max_length=40, verbose_name='单位2'),
        ),
        migrations.RunPython(migrate_split_material_fields, migrations.RunPython.noop),
        *[
            migrations.RemoveField(
                model_name='weldingplanrow',
                name=field_name,
            )
            for field_name in OLD_FIELDS
        ],
    ]
