"""PDF invoice generation with ReportLab."""
from io import BytesIO

from django.conf import settings
from reportlab.graphics.barcode import code128
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from accounts.formatting import format_money

# The built-in PDF fonts have no rupee glyph, so amounts print as "Rs."
RS = 'Rs. '


def _money(value):
    return format_money(value, 2, symbol=RS)


def build_invoice_pdf(invoice):
    """Return the invoice as PDF bytes."""
    company = getattr(settings, 'COMPANY_NAME', 'StockMS Electronics')
    address = getattr(settings, 'COMPANY_ADDRESS', '')
    gstin = getattr(settings, 'COMPANY_GSTIN', '')

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, title=f"Invoice {invoice.invoice_number}",
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
    )

    base = getSampleStyleSheet()
    title = ParagraphStyle('t', parent=base['Title'], fontSize=20, alignment=0, textColor=colors.HexColor('#0f172a'))
    normal = ParagraphStyle('n', parent=base['Normal'], fontSize=9.5, leading=13)
    small = ParagraphStyle('s', parent=normal, fontSize=8.5, textColor=colors.HexColor('#64748b'))
    right = ParagraphStyle('r', parent=normal, alignment=2)

    story = []

    # --- header: company on the left, invoice meta on the right
    left_block = [Paragraph(company, title)]
    if address:
        left_block.append(Paragraph(address, small))
    if gstin:
        left_block.append(Paragraph(f"GSTIN: {gstin}", small))

    customer = invoice.customer
    meta_block = [
        Paragraph(f"<b>INVOICE</b> {invoice.invoice_number}", right),
        Paragraph(f"Date: {invoice.created_at:%d %b %Y}", right),
        Paragraph(f"Status: {invoice.get_status_display()}", right),
        Paragraph(f"Payment: {invoice.get_payment_method_display()}", right),
    ]
    header = Table([[left_block, meta_block]], colWidths=[100 * mm, 74 * mm])
    header.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    story += [header, Spacer(1, 6 * mm)]

    # --- bill to
    story.append(Paragraph("<b>Billed to</b>", normal))
    if customer:
        story.append(Paragraph(customer.name, normal))
        for line in (customer.phone, customer.email, customer.address):
            if line:
                story.append(Paragraph(str(line), small))
    else:
        story.append(Paragraph("Walk-in customer", normal))
    story.append(Spacer(1, 6 * mm))

    # --- items
    rows = [['#', 'Item', 'Qty', 'Unit price', 'Amount']]
    for index, item in enumerate(invoice.items.all(), start=1):
        product = item.product
        label = f"<b>{product.name}</b><br/><font size=8 color='#64748b'>SKU {product.sku}</font>"
        rows.append([
            str(index), Paragraph(label, normal), str(item.quantity),
            _money(item.unit_price), _money(item.subtotal),
        ])

    table = Table(rows, colWidths=[9 * mm, 80 * mm, 15 * mm, 33 * mm, 37 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story += [table, Spacer(1, 4 * mm)]

    # --- totals
    totals = [['Subtotal', _money(invoice.subtotal)]]
    if invoice.tax_percent:
        totals.append([f"Tax ({invoice.tax_percent}%)", _money(invoice.tax_amount)])
    if invoice.discount_amount:
        totals.append(['Discount', '-' + _money(invoice.discount_amount)])
    totals.append(['Grand total', _money(invoice.total_amount)])

    totals_table = Table(totals, colWidths=[40 * mm, 40 * mm], hAlign='RIGHT')
    totals_table.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTSIZE', (0, 0), (-1, -1), 9.5),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('LINEABOVE', (0, -1), (-1, -1), 0.8, colors.HexColor('#0f172a')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
    ]))
    story += [totals_table, Spacer(1, 10 * mm)]

    # --- barcode + footer
    barcode = code128.Code128(invoice.invoice_number, barHeight=12 * mm, barWidth=0.4 * mm)
    story += [
        barcode,
        Spacer(1, 3 * mm),
        Paragraph("Thank you for your purchase. Goods once sold can be returned only as per the store policy.", small),
    ]

    doc.build(story)
    return buffer.getvalue()
