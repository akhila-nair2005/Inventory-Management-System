from django.db import models

# Create your models here.

from inventory.models import Product


class StockAlert(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='alerts')
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