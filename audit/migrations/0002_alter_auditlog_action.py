from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('audit', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='auditlog',
            name='action',
            field=models.CharField(
                choices=[('CREATE', 'Create'), ('EDIT', 'Edit'), ('UPDATE', 'Update'), ('DELETE', 'Delete')],
                max_length=10,
            ),
        ),
    ]
