from django import template

from accounts.formatting import format_money

register = template.Library()


@register.filter
def inr(value, decimals=2):
    """{{ 119900|inr }} -> ₹1,19,900.00 ; {{ x|inr:0 }} -> without paise."""
    return format_money(value, decimals)


@register.filter
def pct_of(value, total):
    """Percentage of `value` over `total`, as a float (0 when total is 0)."""
    try:
        return round(float(value) / float(total) * 100, 1) if float(total) else 0
    except (TypeError, ValueError):
        return 0
