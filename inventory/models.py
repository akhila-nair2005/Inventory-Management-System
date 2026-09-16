from django.db import models
from django.conf import settings


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name


class Supplier(models.Model):
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    gst_number = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=50, unique=True)
    barcode = models.CharField(max_length=100, unique=True, blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='products')
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, related_name='products')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=0)
    reorder_level = models.PositiveIntegerField(default=10)
    max_stock_level = models.PositiveIntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.sku})"

    @property
    def is_low_stock(self):
        return self.quantity <= self.reorder_level

    @property
    def suggested_reorder_quantity(self):
        """How much to order to reach max_stock_level from current quantity."""
        suggestion = self.max_stock_level - self.quantity
        return max(suggestion, 0)

    @property
    def quantity_on_order(self):
        """Total quantity still pending across open (PENDING) purchase orders."""
        from django.db.models import Sum
        total = self.purchase_order_items.filter(
            purchase_order__status='PENDING'
        ).aggregate(Sum('quantity_ordered'))['quantity_ordered__sum']
        return total or 0

    @property
    def expected_stock(self):
        """Current physical stock + whatever is still on order."""
        return self.quantity + self.quantity_on_order


class StockMovement(models.Model):
    class MovementType(models.TextChoices):
        IN = 'IN', 'Stock In'
        OUT = 'OUT', 'Stock Out'

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='movements')
    movement_type = models.CharField(max_length=3, choices=MovementType.choices)
    quantity = models.PositiveIntegerField()
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    note = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.movement_type} - {self.product.name} ({self.quantity})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.movement_type == self.MovementType.IN:
            self.product.quantity += self.quantity
        else:
            self.product.quantity -= self.quantity
        self.product.save()


class PurchaseOrder(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        PARTIALLY_RECEIVED = 'PARTIALLY_RECEIVED', 'Partially Received'
        RECEIVED = 'RECEIVED', 'Received'
        CANCELLED = 'CANCELLED', 'Cancelled'

    order_number = models.CharField(max_length=20, unique=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='purchase_orders')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    order_date = models.DateTimeField(auto_now_add=True)
    expected_delivery_date = models.DateField(null=True, blank=True)
    payment_terms = models.CharField(max_length=100, blank=True, default='Due on delivery')
    delivery_address = models.CharField(max_length=255, blank=True)

    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.order_number} - {self.supplier.name} ({self.status})"

    @property
    def subtotal(self):
        return sum(item.subtotal for item in self.items.all())

    @property
    def tax_amount(self):
        return round(self.subtotal * (self.tax_percent / 100), 2)

    @property
    def grand_total(self):
        return round(self.subtotal + self.tax_amount - self.discount_amount, 2)

    @property
    def total_value_received(self):
        return sum(item.value_received_so_far for item in self.items.all())


class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='purchase_order_items')
    quantity_ordered = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.product.name} x {self.quantity_ordered}"

    @property
    def subtotal(self):
        return self.quantity_ordered * self.unit_cost

    @property
    def margin_per_unit(self):
        return self.product.price - self.unit_cost

    @property
    def quantity_received_so_far(self):
        from django.db.models import Sum
        total = self.receipt_items.aggregate(Sum('quantity_received'))['quantity_received__sum']
        return total or 0

    @property
    def is_fully_received(self):
        return self.quantity_received_so_far >= self.quantity_ordered

    @property
    def quantity_remaining(self):
        return max(self.quantity_ordered - self.quantity_received_so_far, 0)
    
    @property
    def value_received_so_far(self):
        return self.quantity_received_so_far * self.unit_cost


class GoodsReceipt(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='receipts')
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    received_date = models.DateTimeField(auto_now_add=True)
    remarks = models.TextField(blank=True)

    def __str__(self):
        return f"Receipt for {self.purchase_order.order_number} on {self.received_date.date()}"


class GoodsReceiptItem(models.Model):
    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name='items')
    po_item = models.ForeignKey(PurchaseOrderItem, on_delete=models.PROTECT, related_name='receipt_items')
    quantity_received = models.PositiveIntegerField(default=0)
    quantity_damaged = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.po_item.product.name}: {self.quantity_received} good, {self.quantity_damaged} damaged"

    @property
    def usable_quantity(self):
        """Only undamaged units actually go into sellable stock."""
        return max(self.quantity_received - self.quantity_damaged, 0)