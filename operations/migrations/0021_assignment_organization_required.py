import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0020_assignment_assigned_by_assignment_organization'),
    ]

    operations = [
        migrations.AlterField(
            model_name='assignment',
            name='organization',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='assignments', to='operations.organization'),
        ),
    ]
