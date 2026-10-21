# StockMS: update notes

## Apply the update (Windows / VS Code terminal)

```powershell
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_data --reset
python manage.py runserver
```

`seed_data --reset` replaces products, suppliers, invoices, purchase orders, alerts, e-mail and audit logs with
the new electronics demo data. **User accounts are kept** (existing passwords unchanged). New demo accounts
(`arun`, `meera`, `joseph`) use password `Stock@12345`.

Optional sanity check that models and migrations agree (should print "No changes detected"):

```powershell
python manage.py makemigrations --check --dry-run
```

## Real SMTP e-mail (otherwise e-mails print in the terminal)

```powershell
$env:STOCKMS_EMAIL_USER = "yourname@gmail.com"
$env:STOCKMS_EMAIL_PASSWORD = "your-app-password"
python manage.py runserver
```

## Table changes (4 new migrations)

| App | Change |
|---|---|
| accounts.User | + `phone`, `department` (account status = Django `is_active`) |
| inventory.Category | + `code` |
| inventory.Product | + `brand`, `cost_price` |
| billing.Invoice | + `payment_method`, `tax_percent`, `discount_amount` |
| billing.InvoiceItem | + `unit_cost` (cost snapshot, so profit stays correct) |
| alerts.StockAlert | + `alert_type` (LOW_STOCK / OUT_OF_STOCK) |
| alerts.EmailLog | **new table**: every e-mail sent, with status and body |

## Interfaces

- **Dashboard**: role-aware KPI cards, stock-level chart, demand-forecast chart, revenue/profit chart,
  stock value by category, alerts, recent invoices, top sellers.
- **Forecasting**: monthly history (6 completed months) + 3-month forecast using scikit-learn Linear Regression and
  a Moving Average; trend, R-squared, recommended restock, "Create PO" shortcut, e-mail report.
- **Reports**: tabs for Inventory, Sales, Purchases, Future Demand, E-mail Log.
- **Products**: search/filters, brand, cost and margin, edit page, auto barcode, printable CODE-128 label (JsBarcode).
- **Categories**, **Staff Management** (Admin), **Email Log**, PDF invoices (ReportLab) with e-mail and cancel-with-restock.

## Behaviour changes worth knowing

- Forecasts are now **monthly, from invoices**, not daily from stock movements.
- `Product.quantity_on_order` now counts partially-received POs and only the units still outstanding.
- Invoice creation validates stock **before** writing anything (the old code could leave stock deducted after an error).
- Resolving an alert uses the same rule as the Low Stock badge (`<=` reorder level).
- `barcode_lookup` now requires login.
- `STATICFILES_DIRS` added so `static/css/custom.css` is actually served.
