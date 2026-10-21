"""Pure helpers (no Django imports) for Indian-style money formatting."""
from decimal import Decimal, InvalidOperation


def group_indian(digits):
    """'1234567' -> '12,34,567' (lakh / crore grouping)."""
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ','.join(parts + [tail])


def format_money(value, decimals=2, symbol='\u20b9'):
    """format_money(119900) -> '₹1,19,900.00'. Use symbol='Rs. ' where the font lacks the rupee sign."""
    if value is None or value == '':
        return '-'
    try:
        amount = Decimal(str(value))
        places = int(decimals)
    except (InvalidOperation, ValueError, TypeError):
        return str(value)
    amount = amount.quantize(Decimal(1).scaleb(-places))
    sign = '-' if amount < 0 else ''
    text = f"{abs(amount):.{places}f}"
    whole, _, frac = text.partition('.')
    return f"{sign}{symbol}{group_indian(whole)}" + (f".{frac}" if frac else '')
