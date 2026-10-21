from django import forms

from .models import Category, Product


class _BootstrapMixin:
    def _style_fields(self):
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.Select):
                widget.attrs['class'] = 'form-select'
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs['class'] = 'form-check-input'
            else:
                widget.attrs['class'] = 'form-control'


class ProductForm(_BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'name', 'brand', 'sku', 'barcode', 'category', 'supplier',
            'price', 'cost_price', 'quantity', 'reorder_level', 'max_stock_level',
        ]
        labels = {
            'sku': 'SKU',
            'price': 'Selling price (\u20b9)',
            'cost_price': 'Cost price (\u20b9)',
            'quantity': 'Opening quantity',
            'reorder_level': 'Reorder level',
            'max_stock_level': 'Max stock level',
            'barcode': 'Barcode (leave blank to auto-generate)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].empty_label = '-- None --'
        self.fields['supplier'].empty_label = '-- None --'
        for name in ('price', 'cost_price'):
            self.fields[name].widget.attrs['step'] = '0.01'
        # Stock changes after creation must go through Stock Movements / goods receipts
        # so the stock ledger stays accurate.
        if self.instance and self.instance.pk:
            self.fields['quantity'].disabled = True
            self.fields['quantity'].label = 'Quantity in stock (change via Record Stock)'
        self._style_fields()

    def clean(self):
        cleaned = super().clean()
        reorder, maximum = cleaned.get('reorder_level'), cleaned.get('max_stock_level')
        if reorder is not None and maximum is not None and maximum < reorder:
            self.add_error('max_stock_level', 'Max stock level must be at least the reorder level.')
        return cleaned


class CategoryForm(_BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'code', 'description']
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}
        labels = {'code': 'Short code (e.g. LAPTOPS)'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()

    def clean_code(self):
        return self.cleaned_data.get('code', '').strip().upper()
