from django.db import migrations


def remove_legacy_commission_library(apps, schema_editor):
    DataSourceFile = apps.get_model('pipecloud', 'DataSourceFile')
    DataSourceFile.objects.filter(
        source_type='library',
        source_key='anti-corrosion-commission-library',
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('pipecloud', '0002_master_schedule_row'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='anticorrosioncommissionrow',
            options={
                'ordering': ['project', 'row_index'],
                'verbose_name': '防腐委托单行',
                'verbose_name_plural': '防腐委托单行',
            },
        ),
        migrations.RunPython(remove_legacy_commission_library, migrations.RunPython.noop),
    ]
