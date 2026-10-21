from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='payment_method',
            field=models.CharField(
                choices=[('CASH', 'Cash'), ('CARD', 'Card'), ('UPI', 'UPI'), ('CREDIT', 'Credit')],
                default='CASH',
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='invoice',
            name='tax_percent',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=5),
        ),
        migrations.AddField(
            model_name='invoice',
            name='discount_amount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name='invoiceitem',
            name='unit_cost',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
    ]
