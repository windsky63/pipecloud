from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pipecloud', '0003_alter_weldlibraryrow_completed_flag'),
    ]

    operations = [
        migrations.DeleteModel(name='CuttingDetailRow'),
        migrations.DeleteModel(name='SegmentListRow'),
        migrations.DeleteModel(name='MaterialDetailRow'),
        migrations.DeleteModel(name='PipePickListRow'),
        migrations.DeleteModel(name='FittingPickListRow'),
        migrations.DeleteModel(name='MasterScheduleRow'),
    ]
