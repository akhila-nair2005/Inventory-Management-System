import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from inventory.models import Category, Supplier, Product, StockMovement
from accounts.models import User


class Command(BaseCommand):
    help = 'Seeds the database with sample inventory data for testing/demo'

    def handle(self, *args, **kwargs):
        self.stdout.write('Seeding data...')

        categories = []
        for name in ['Electronics', 'Stationery', 'Groceries']:
            cat, _ = Category.objects.get_or_create(name=name)
            categories.append(cat)

        supplier, _ = Supplier.objects.get_or_create(
            name='Sample Supplier Pvt Ltd',
            defaults={'phone': '9999999999', 'email': 'supplier@example.com'}
        )

        admin_user = User.objects.filter(role='ADMIN').first()

        product_names = ['Laptop', 'Notebook', 'Pen', 'Rice Bag', 'Mouse']
        products = []
        for name in product_names:
            product, created = Product.objects.get_or_create(
                sku=f"SKU-{name[:3].upper()}",
                defaults={
                    'name': name,
                    'category': random.choice(categories),
                    'supplier': supplier,
                    'price': round(random.uniform(10, 500), 2),
                    'quantity': 300,  # higher starting stock
                    'reorder_level': 20,
                }
            )
            products.append(product)

        today = timezone.now()
        for product in products:
            for days_ago in range(30, 0, -1):
                date = today - timedelta(days=days_ago)

                # Occasional restock (every ~10 days) to keep stock realistic
                if days_ago % 10 == 0:
                    restock_qty = random.randint(30, 60)
                    movement = StockMovement.objects.create(
                        product=product,
                        movement_type='IN',
                        quantity=restock_qty,
                        performed_by=admin_user,
                        note='Scheduled restock'
                    )
                    StockMovement.objects.filter(id=movement.id).update(timestamp=date)

                # Daily sale, but only if enough stock is available
                if random.random() < 0.7:
                    product.refresh_from_db()
                    max_sellable = min(10, product.quantity)
                    if max_sellable > 0:
                        qty = random.randint(1, max_sellable)
                        movement = StockMovement.objects.create(
                            product=product,
                            movement_type='OUT',
                            quantity=qty,
                            performed_by=admin_user,
                        )
                        StockMovement.objects.filter(id=movement.id).update(timestamp=date)

        self.stdout.write(self.style.SUCCESS('Sample data seeded successfully!'))