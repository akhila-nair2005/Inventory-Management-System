import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('alerts', '0001_initial'),
        ('inventory', '0002_category_code_product_brand_cost_price'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='stockalert',
            name='alert_type',
            field=models.CharField(
                choices=[('LOW_STOCK', 'Low Stock'), ('OUT_OF_STOCK', 'Out of Stock')],
                default='LOW_STOCK',
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name='EmailLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('recipient_email', models.CharField(max_length=254)),
                ('subject', models.CharField(max_length=255)),
                ('body', models.TextField(blank=True)),
                ('alert_type', models.CharField(
                    choices=[
                        ('LOW_STOCK', 'Low Stock'),
                        ('OUT_OF_STOCK', 'Out of Stock'),
                        ('PURCHASE_CONFIRMATION', 'Purchase Order'),
                        ('DELIVERY_DISCREPANCY', 'Delivery Discrepancy'),
                        ('FORECAST_REPORT', 'Forecast Report'),
                        ('INVOICE', 'Invoice'),
                    ],
                    max_length=30,
                )),
                ('status', models.CharField(
                    choices=[('SENT', 'Sent'), ('FAILED', 'Failed')],
                    default='SENT',
                    max_length=10,
                )),
                ('error_message', models.CharField(blank=True, default='', max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('product', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='email_logs',
                    to='inventory.product',
                )),
                ('triggered_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
