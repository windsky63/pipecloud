from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pipecloud', '0004_fold_anti_corrosion_rows_into_master_schedule'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='masterschedulerow',
            name='pipecloud_master_anti_plan',
        ),
        migrations.RemoveIndex(
            model_name='masterschedulerow',
            name='pipecloud_master_cut_plan',
        ),
        migrations.RemoveIndex(
            model_name='masterschedulerow',
            name='pipecloud_master_weld_plan',
        ),
        migrations.RemoveField(
            model_name='masterschedulerow',
            name='process_sequence',
        ),
        migrations.RemoveField(
            model_name='masterschedulerow',
            name='anti_corrosion_plan_folder',
        ),
        migrations.RemoveField(
            model_name='masterschedulerow',
            name='cut_plan_folder',
        ),
        migrations.RemoveField(
            model_name='masterschedulerow',
            name='weld_plan_folder',
        ),
    ]
