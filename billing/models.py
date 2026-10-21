from django.db import models

# Create your models here.
from decimal import Decimal

from django.conf import settings
from inventory.models import Product


class Customer(models.Model):
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Invoice(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        PAID = 'PAID', 'Paid'
        CANCELLED = 'CANCELLED', 'Cancelled'

    class PaymentMethod(models.TextChoices):
        CASH = 'CASH', 'Cash'
        CARD = 'CARD', 'Card'
        UPI = 'UPI', 'UPI'
        CREDIT = 'CREDIT', 'Credit'

    invoice_number = models.CharField(max_length=20, unique=True)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, related_name='invoices')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    payment_method = models.CharField(
        max_length=10, choices=PaymentMethod.choices, default=PaymentMethod.CASH
    )
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.invoice_number

    @property
    def subtotal(self):
        return sum(item.subtotal for item in self.items.all())

    @property
    def tax_amount(self):
        return round(self.subtotal * (Decimal(str(self.tax_percent)) / 100), 2)

    @property
    def total_amount(self):
        """Grand total: items + tax - discount (identical to the old value when tax/discount are 0)."""
        return round(self.subtotal + self.tax_amount - Decimal(str(self.discount_amount)), 2)

    @property
    def total_cost(self):
        return sum(item.quantity * item.unit_cost for item in self.items.all())

    @property
    def gross_profit(self):
        """Items revenue - discount - cost of goods. Tax is pass-through, so it is excluded."""
        return self.subtotal - Decimal(str(self.discount_amount)) - self.total_cost


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    # Product cost at the time of sale, so profit reports stay correct if cost changes later.
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"

    @property
    def subtotal(self):
        return self.quantity * self.unit_price