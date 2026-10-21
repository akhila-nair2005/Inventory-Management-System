from django.conf import settings
from django.db import models

from inventory.models import Product


class StockAlert(models.Model):
    class AlertType(models.TextChoices):
        LOW_STOCK = 'LOW_STOCK', 'Low Stock'
        OUT_OF_STOCK = 'OUT_OF_STOCK', 'Out of Stock'

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='alerts')
    alert_type = models.CharField(
        max_length=20, choices=AlertType.choices, default=AlertType.LOW_STOCK
    )
    quantity_at_alert = models.PositiveIntegerField()
    reorder_level_at_alert = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        status = "Resolved" if self.resolved else "Active"
        return f"{self.product.name} - {status} ({self.created_at.date()})"

    class Meta:
        ordering = ['-created_at']


class EmailLog(models.Model):
    """Every e-mail the system sends through SMTP is recorded here (the "email console")."""

    class AlertType(models.TextChoices):
        LOW_STOCK = 'LOW_STOCK', 'Low Stock'
        OUT_OF_STOCK = 'OUT_OF_STOCK', 'Out of Stock'
        PURCHASE_CONFIRMATION = 'PURCHASE_CONFIRMATION', 'Purchase Order'
        DELIVERY_DISCREPANCY = 'DELIVERY_DISCREPANCY', 'Delivery Discrepancy'
        FORECAST_REPORT = 'FORECAST_REPORT', 'Forecast Report'
        INVOICE = 'INVOICE', 'Invoice'

    class Status(models.TextChoices):
        SENT = 'SENT', 'Sent'
        FAILED = 'FAILED', 'Failed'

    recipient_email = models.CharField(max_length=254)
    subject = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    alert_type = models.CharField(max_length=30, choices=AlertType.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SENT)
    error_message = models.CharField(max_length=255, blank=True, default='')
    product = models.ForeignKey(
        Product, on_delete=models.SET_NULL, null=True, blank=True, related_name='email_logs'
    )
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.alert_type}] {self.subject} -> {self.recipient_email}"
