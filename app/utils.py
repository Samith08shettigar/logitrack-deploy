import os
from functools import wraps
from flask import session, redirect, url_for, flash, g, abort, current_app
import qrcode
import barcode
from barcode.writer import ImageWriter
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from app.models import db, Notification, ActivityLog, Setting

# 1. Authentication and Authorization Decorators
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is None:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if g.user is None:
                flash("Please log in to access this page.", "warning")
                return redirect(url_for('auth.login'))
            if g.user.role.name not in roles:
                flash(f"Unauthorized. This area requires one of the following roles: {', '.join(roles)}", "danger")
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# 2. Shipping Cost Calculator
def category_to_setting_key(category):
    mapping = {
        'Clothes / Garments': 'rate_packaging_clothes_garments',
        'Books': 'rate_packaging_books',
        'Documents': 'rate_packaging_documents',
        'Electronics': 'rate_packaging_electronics',
        'Mobile / Laptop': 'rate_packaging_mobile_laptop',
        'Glass items': 'rate_packaging_glass_items',
        'Kitchen items': 'rate_packaging_kitchen_items',
        'Household items': 'rate_packaging_household_items',
        'Machinery parts': 'rate_packaging_machinery_parts',
        'Auto spare parts': 'rate_packaging_auto_spare_parts',
        'Furniture': 'rate_packaging_furniture',
        'Fruits / Vegetables': 'rate_packaging_fruits_vegetables',
        'Food items': 'rate_packaging_food_items',
        'Clothing bundles': 'rate_packaging_clothing_bundles',
        'Industrial goods': 'rate_packaging_industrial_goods',
        'Other': 'rate_packaging_other'
    }
    cleaned = str(category).strip()
    if cleaned in mapping:
        return mapping[cleaned]
    for key, val in mapping.items():
        if key.lower() == cleaned.lower():
            return val
    return 'rate_packaging_other'

def get_packaging_rate(category):
    DEFAULT_RATES = {
        'Clothes / Garments': 5.0,
        'Books': 8.0,
        'Documents': 10.0,
        'Electronics': 15.0,
        'Mobile / Laptop': 20.0,
        'Glass items': 20.0,
        'Kitchen items': 10.0,
        'Household items': 8.0,
        'Machinery parts': 20.0,
        'Auto spare parts': 15.0,
        'Furniture': 20.0,
        'Fruits / Vegetables': 8.0,
        'Food items': 10.0,
        'Clothing bundles': 5.0,
        'Industrial goods': 25.0,
        'Other': 10.0
    }
    if not category:
        return 10.0
    key = category_to_setting_key(category)
    try:
        setting = Setting.query.filter_by(setting_key=key).first()
        if setting and setting.setting_value is not None:
            return float(setting.setting_value)
    except Exception as e:
        pass
    cleaned_category = str(category).strip()
    if cleaned_category in DEFAULT_RATES:
        return DEFAULT_RATES[cleaned_category]
    for key, value in DEFAULT_RATES.items():
        if key.lower() == cleaned_category.lower():
            return value
    return 10.0

def get_gst_rate_by_category(category):
    DEFAULT_GST = {
        'Clothes / Garments': 5.0,
        'Books': 5.0,
        'Documents': 0.0,
        'Electronics': 18.0,
        'Mobile / Laptop': 18.0,
        'Glass items': 18.0,
        'Kitchen items': 5.0,
        'Household items': 5.0,
        'Machinery parts': 18.0,
        'Auto spare parts': 18.0,
        'Furniture': 18.0,
        'Fruits / Vegetables': 5.0,
        'Food items': 5.0,
        'Clothing bundles': 5.0,
        'Industrial goods': 18.0,
        'Other': 18.0
    }
    if not category:
        return 18.0
    key = category_to_setting_key(category)
    # Extract suffix to check for matching gst setting key
    if key.startswith('rate_packaging_'):
        suffix = key[15:]
    else:
        suffix = key
    gst_key = f'gst_packaging_{suffix}'
    try:
        setting = Setting.query.filter_by(setting_key=gst_key).first()
        if setting and setting.setting_value is not None:
            return float(setting.setting_value)
    except Exception as e:
        pass
    cleaned_category = str(category).strip()
    if cleaned_category in DEFAULT_GST:
        return DEFAULT_GST[cleaned_category]
    for key, value in DEFAULT_GST.items():
        if key.lower() == cleaned_category.lower():
            return value
    return 18.0

def get_insurance_fee(category, declared_value):
    DEFAULT_INS_RATES = {
        'Clothes / Garments': 1.0,
        'Books': 0.5,
        'Documents': 0.5,
        'Electronics': 2.0,
        'Mobile / Laptop': 2.5,
        'Glass items': 2.5,
        'Kitchen items': 1.0,
        'Household items': 1.0,
        'Machinery parts': 2.0,
        'Auto spare parts': 2.0,
        'Furniture': 1.5,
        'Fruits / Vegetables': 1.0,
        'Food items': 1.0,
        'Clothing bundles': 1.0,
        'Industrial goods': 2.5,
        'Other': 2.5
    }
    DEFAULT_INS_MINS = {
        'Clothes / Garments': 100.0,
        'Books': 75.0,
        'Documents': 100.0,
        'Electronics': 250.0,
        'Mobile / Laptop': 300.0,
        'Glass items': 300.0,
        'Kitchen items': 100.0,
        'Household items': 100.0,
        'Machinery parts': 250.0,
        'Auto spare parts': 250.0,
        'Furniture': 200.0,
        'Fruits / Vegetables': 100.0,
        'Food items': 100.0,
        'Clothing bundles': 100.0,
        'Industrial goods': 300.0,
        'Other': 300.0
    }
    
    rate, min_fee = None, None
    if category:
        key = category_to_setting_key(category)
        if key.startswith('rate_packaging_'):
            suffix = key[15:]
        else:
            suffix = key
            
        ins_rate_key = f'ins_rate_packaging_{suffix}'
        ins_min_key = f'ins_min_packaging_{suffix}'
        
        try:
            setting_rate = Setting.query.filter_by(setting_key=ins_rate_key).first()
            if setting_rate and setting_rate.setting_value is not None:
                rate = float(setting_rate.setting_value)
                
            setting_min = Setting.query.filter_by(setting_key=ins_min_key).first()
            if setting_min and setting_min.setting_value is not None:
                min_fee = float(setting_min.setting_value)
        except Exception as e:
            pass
            
    cleaned_category = str(category).strip()
    if rate is None:
        rate = DEFAULT_INS_RATES.get(cleaned_category, 2.5)
        for k, v in DEFAULT_INS_RATES.items():
            if k.lower() == cleaned_category.lower():
                rate = v
                break
                
    if min_fee is None:
        min_fee = DEFAULT_INS_MINS.get(cleaned_category, 300.0)
        for k, v in DEFAULT_INS_MINS.items():
            if k.lower() == cleaned_category.lower():
                min_fee = v
                break
                
    calculated_fee = (declared_value or 0.0) * (rate / 100.0)
    return max(calculated_fee, min_fee)

def calculate_shipping_cost(weight, delivery_type, fragile=False, insurance=False, package_category='Other', declared_value=0.0):
    # Minimum base charge
    cost = 20.0
    
    # Weight charge (per kg)
    cost += weight * 5.5
    
    # Packaging charge based on category
    packaging_rate = get_packaging_rate(package_category)
    cost += weight * packaging_rate
    
    # Express shipment surcharge
    if delivery_type == 'Express':
        cost *= 1.5
        
    # Extra handling fee
    if fragile:
        cost += 10.0
        
    # Cargo Insurance fee
    if insurance:
        cost += get_insurance_fee(package_category, declared_value)
        
    return round(cost, 2)

# 3. Barcode and QR Code Generators
def generate_qr_code(tracking_number):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(tracking_number)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    filename = f"{tracking_number}.png"
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], 'qrcodes', filename)
    img.save(filepath)
    return f"uploads/qrcodes/{filename}"

def generate_barcode_img(tracking_number):
    COD = barcode.get_barcode_class('code128')
    filename = tracking_number
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], 'barcodes', filename)
    
    writer = ImageWriter()
    writer.set_options({
        'module_width': 0.2,
        'module_height': 8.0,
        'font_size': 8,
        'text_distance': 4.0
    })
    
    barcode_instance = COD(tracking_number, writer=writer)
    barcode_instance.save(filepath) # Automatically appends .png extension
    return f"uploads/barcodes/{filename}.png"

# 4. Rupees to Words Helper
def number_to_words(num):
    num = int(round(num))
    if num == 0:
        return "Rupees Zero Only"
        
    ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
            "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
    
    def helper(n):
        if n < 20:
            return ones[n]
        elif n < 100:
            return tens[n // 10] + (" " + ones[n % 10] if n % 10 != 0 else "")
        elif n < 1000:
            return ones[n // 100] + " Hundred" + (" " + helper(n % 100) if n % 100 != 0 else "")
        elif n < 100000:
            return helper(n // 1000) + " Thousand" + (" " + helper(n % 1000) if n % 1000 != 0 else "")
        elif n < 10000000:
            return helper(n // 100000) + " Lakh" + (" " + helper(n % 100000) if n % 100000 != 0 else "")
        else:
            return helper(n // 10000000) + " Crore" + (" " + helper(n % 10000000) if n % 10000000 != 0 else "")
            
    words = helper(num).strip()
    words = " ".join(words.split()) # normalize whitespace
    return f"Rupees {words} Only"

# 5. Canvas Background Curve & Footer Drawing
def draw_invoice_background(canvas, doc):
    canvas.saveState()
    width, height = letter
    
    # 1. Top dark header block extending across the full header area
    header_height = 110
    p = canvas.beginPath()
    p.moveTo(0, height)
    p.lineTo(0, height - header_height)
    p.lineTo(width, height - header_height)
    p.lineTo(width, height)
    p.close()
    
    canvas.setFillColor(colors.HexColor('#0f172a')) # Dark Slate-900
    canvas.drawPath(p, fill=1, stroke=0)
    
    # 2. Yellow accent stripe directly underneath the header block
    canvas.setStrokeColor(colors.HexColor('#fbbf24')) # Yellow/Amber Accent
    canvas.setLineWidth(3.5)
    canvas.line(0, height - header_height, width, height - header_height)
    
    # 3. Bottom dark footer block (0 to 55 pt height)
    canvas.setFillColor(colors.HexColor('#0f172a'))
    canvas.rect(0, 0, width, 55, fill=1, stroke=0)
    
    # 4. Bottom yellow line on top of footer
    canvas.setStrokeColor(colors.HexColor('#fbbf24'))
    canvas.setLineWidth(3)
    canvas.line(0, 55, width, 55)
    
    # 5. Footer text labels & values (drawn inside the dark bottom bar)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(colors.HexColor('#fbbf24'))
    canvas.drawString(36, 38, "PHONE")
    canvas.drawString(190, 38, "ADDRESS")
    canvas.drawString(410, 38, "CONTACT")
    
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor('#cbd5e1'))
    canvas.drawString(36, 26, "+91 98888 77777")
    canvas.drawString(36, 16, "+91 80 1234 5678")
    
    canvas.drawString(190, 26, "LogiTrack Logistics Pvt. Ltd.")
    canvas.drawString(190, 16, "#12, 3rd Floor, Industrial Area, Bangalore - 560100")
    
    canvas.drawString(410, 26, "info@logitrack.com")
    canvas.drawString(410, 16, "www.logitrack.com")
    
    canvas.restoreState()

# 6. ReportLab PDF Invoice Generator
def create_invoice_pdf(shipment):
    filename = f"invoice_{shipment.tracking_number}.pdf"
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], 'invoices', filename)
    
    # Page setup (letter size, margins adjusted to leave space for custom canvas footer)
    doc = SimpleDocTemplate(filepath, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=65)
    story = []
    
    styles = getSampleStyleSheet()
    
    # Define custom styles
    logo_style = ParagraphStyle(
        'InvoiceLogo',
        parent=styles['Normal'],
        fontSize=26,
        leading=30,
        textColor=colors.HexColor('#ffffff')
    )
    
    logo_sub_style = ParagraphStyle(
        'InvoiceLogoSub',
        parent=styles['Normal'],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#94a3b8')
    )
    
    header_title_style = ParagraphStyle(
        'HeaderTitle',
        parent=styles['Normal'],
        fontSize=22,
        leading=26,
        textColor=colors.HexColor('#ffffff'),
        alignment=2 # Right aligned
    )
    
    header_sub_style = ParagraphStyle(
        'HeaderSub',
        parent=styles['Normal'],
        fontSize=10,
        leading=12,
        textColor=colors.HexColor('#fbbf24'),
        alignment=2 # Right aligned
    )
    
    card_title_style = ParagraphStyle(
        'CardTitle',
        parent=styles['Normal'],
        fontSize=9,
        leading=11,
        textColor=colors.HexColor('#ffffff'),
        fontName='Helvetica-Bold'
    )
    
    normal_style = ParagraphStyle(
        'InvoiceNormal',
        parent=styles['Normal'],
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#1e293b')
    )
    
    th_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontSize=8.5,
        leading=10,
        textColor=colors.HexColor('#ffffff'),
        fontName='Helvetica-Bold'
    )
    
    meta_label_style = ParagraphStyle(
        'MetaLabel',
        parent=styles['Normal'],
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor('#64748b')
    )
    
    meta_val_style = ParagraphStyle(
        'MetaValue',
        parent=styles['Normal'],
        fontSize=9,
        leading=11,
        textColor=colors.HexColor('#0f172a'),
        fontName='Helvetica-Bold'
    )
    
    terms_text_style = ParagraphStyle(
        'TermsText',
        parent=styles['Normal'],
        fontSize=6.5,
        leading=8.5,
        textColor=colors.HexColor('#475569')
    )
    
    # 1. Header Table (LogiTrack Logo on left, Invoice Number on right) - matches transparent canvas background
    logo_paragraph = Paragraph('<b><font color="#fbbf24">Logi</font>Track</b>', logo_style)
    logo_sub_paragraph = Paragraph('Smart Delivery & Freight Management Services', logo_sub_style)
    
    left_header = [logo_paragraph, logo_sub_paragraph]
    right_header = [
        Paragraph('<b>INVOICE</b>', header_title_style),
        Spacer(1, 3),
        Paragraph(f'<b>INV-{shipment.created_at.strftime("%Y%m")}-{shipment.id:04d}</b>', header_sub_style)
    ]
    
    header_table = Table([[left_header, right_header]], colWidths=[340, 200])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 10))

    # 2. Metadata Section Table
    meta_data = [
        [
            Paragraph('Tracking Number', meta_label_style),
            Paragraph('Booking Date', meta_label_style),
            Paragraph('Invoice No.', meta_label_style),
            Paragraph('Delivery Mode', meta_label_style)
        ],
        [
            Paragraph(f'<b>{shipment.tracking_number}</b>', meta_val_style),
            Paragraph(f'<b>{shipment.created_at.strftime("%Y-%m-%d %H:%M")}</b>', meta_val_style),
            Paragraph(f'<b>INV-{shipment.created_at.strftime("%Y%m")}-{shipment.id:04d}</b>', meta_val_style),
            Paragraph(f'<b>{shipment.delivery_type}</b>', meta_val_style)
        ]
    ]
    meta_table = Table(meta_data, colWidths=[135, 135, 135, 135])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#f1f5f9')),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 12))

    # 3. Address details Cards
    sender_text = (
        f'<b>Name:</b> {shipment.sender_name}<br/>'
        f'<b>Phone:</b> {shipment.sender_phone}<br/>'
        f'<b>Pickup:</b> {shipment.pickup_address_line}<br/>'
        f'<b>City:</b> {shipment.pickup_city.capitalize()}, {shipment.pickup_state} - {shipment.pickup_zip_code}'
    )
    
    receiver_text = (
        f'<b>Name:</b> {shipment.receiver_name}<br/>'
        f'<b>Phone:</b> {shipment.receiver_phone}<br/>'
        f'<b>Dropoff:</b> {shipment.receiver_address_line}<br/>'
        f'<b>City:</b> {shipment.receiver_city.capitalize()}, {shipment.receiver_state} - {shipment.receiver_zip_code}'
    )
    
    sender_card_table = Table([
        [Paragraph('<b>SENDER DETAILS</b>', card_title_style)],
        [Paragraph(sender_text, normal_style)]
    ], colWidths=[260])
    sender_card_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,0), colors.HexColor('#0f172a')),
        ('BACKGROUND', (0,1), (0,1), colors.HexColor('#f8fafc')),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    
    receiver_card_table = Table([
        [Paragraph('<b>RECEIVER DETAILS</b>', card_title_style)],
        [Paragraph(receiver_text, normal_style)]
    ], colWidths=[260])
    receiver_card_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,0), colors.HexColor('#0f172a')),
        ('BACKGROUND', (0,1), (0,1), colors.HexColor('#f8fafc')),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    
    addr_table = Table([[sender_card_table, '', receiver_card_table]], colWidths=[260, 20, 260])
    addr_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(addr_table)
    story.append(Spacer(1, 12))

    # 4. Billing Summary
    story.append(Paragraph('<b>BILLING SUMMARY</b>', ParagraphStyle('BillTitle', parent=styles['Normal'], fontSize=11, leading=13, textColor=colors.HexColor('#0f172a'), fontName='Helvetica-Bold', spaceAfter=6)))
    
    gst_rate = get_gst_rate_by_category(shipment.package_category)
    subtotal = round(shipment.shipping_cost / (1 + (gst_rate / 100)), 2)
    tax = round(shipment.shipping_cost - subtotal, 2)
    
    fragile_fee = 10.0 if shipment.fragile else 0.0
    insurance_fee = get_insurance_fee(shipment.package_category, shipment.declared_value) if shipment.insurance else 0.0
    base_weight_charge = subtotal - fragile_fee - insurance_fee
    
    # Billing headers
    items = [
        [
            Paragraph('#', th_style),
            Paragraph('ITEM DESCRIPTION', th_style),
            Paragraph('QTY / WEIGHT', th_style),
            Paragraph('UNIT PRICE (INR)', th_style),
            Paragraph('AMOUNT (INR)', th_style)
        ]
    ]
    
    # Billing items
    items.append([
        Paragraph('1', normal_style),
        Paragraph('Standard Freight Logistics Service', normal_style),
        Paragraph(f'{shipment.package_weight} kg', normal_style),
        Paragraph('-', normal_style),
        Paragraph(f'Rs. {base_weight_charge:,.2f}', ParagraphStyle('TextRight', parent=normal_style, alignment=2))
    ])
    
    item_num = 2
    if shipment.fragile:
        items.append([
            Paragraph(str(item_num), normal_style),
            Paragraph('Fragile Care Handling Charge', normal_style),
            Paragraph('-', normal_style),
            Paragraph('-', normal_style),
            Paragraph(f'Rs. {fragile_fee:,.2f}', ParagraphStyle('TextRight', parent=normal_style, alignment=2))
        ])
        item_num += 1
        
    if shipment.insurance:
        items.append([
            Paragraph(str(item_num), normal_style),
            Paragraph('Shipment Cargo Insurance Cover', normal_style),
            Paragraph('-', normal_style),
            Paragraph('-', normal_style),
            Paragraph(f'Rs. {insurance_fee:,.2f}', ParagraphStyle('TextRight', parent=normal_style, alignment=2))
        ])
        item_num += 1
        
    advance_paid = shipment.advance_paid or 0.0
    balance_due = max(0.0, round(shipment.shipping_cost - advance_paid, 2))
    
    # Totals rows
    items.append([
        '', '', '',
        Paragraph('<b>Subtotal (Net)</b>', normal_style),
        Paragraph(f'Rs. {subtotal:,.2f}', ParagraphStyle('TextRightBold', parent=normal_style, alignment=2, fontName='Helvetica-Bold'))
    ])
    items.append([
        '', '', '',
        Paragraph(f'<b>GST Tax ({int(gst_rate)}%)</b>', normal_style),
        Paragraph(f'Rs. {tax:,.2f}', ParagraphStyle('TextRightBold', parent=normal_style, alignment=2, fontName='Helvetica-Bold'))
    ])
    items.append([
        '', '', '',
        Paragraph('<b>Gross Total (Incl. Tax)</b>', ParagraphStyle('GrossText', parent=normal_style, fontName='Helvetica-Bold', textColor=colors.HexColor('#0f172a'))),
        Paragraph(f'Rs. {shipment.shipping_cost:,.2f}', ParagraphStyle('GrossAmount', parent=normal_style, alignment=2, fontName='Helvetica-Bold', textColor=colors.HexColor('#0f172a')))
    ])
    items.append([
        '', '', '',
        Paragraph('<b>Less: Advance Paid (Online)</b>', ParagraphStyle('AdvText', parent=normal_style, fontName='Helvetica-Bold', textColor=colors.HexColor('#15803d'))),
        Paragraph(f'- Rs. {advance_paid:,.2f}', ParagraphStyle('AdvAmount', parent=normal_style, alignment=2, fontName='Helvetica-Bold', textColor=colors.HexColor('#15803d')))
    ])
    items.append([
        '', '', '',
        Paragraph('<b>NET BALANCE DUE / PAID</b>', ParagraphStyle('TotalText', parent=normal_style, fontName='Helvetica-Bold', textColor=colors.HexColor('#0f172a'))),
        Paragraph(f'<b>Rs. {balance_due:,.2f}</b>', ParagraphStyle('TotalAmount', parent=normal_style, alignment=2, fontName='Helvetica-Bold', textColor=colors.HexColor('#0f172a')))
    ])
    
    billing_table = Table(items, colWidths=[25, 235, 90, 90, 100])
    
    # Table styles
    table_styles = [
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0f172a')), # Header background
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ('INNERGRID', (0,0), (-1,-6), 0.5, colors.HexColor('#cbd5e1')), # Grid lines for items
        ('BOX', (0,0), (-1,-6), 0.5, colors.HexColor('#cbd5e1')),
        
        # Advance Paid line formatting
        ('BACKGROUND', (3,-2), (4,-2), colors.HexColor('#f0fdf4')),
        ('TOPPADDING', (3,-2), (4,-2), 4),
        ('BOTTOMPADDING', (3,-2), (4,-2), 4),

        # Grand Total / Net Balance yellow bar highlighting
        ('BACKGROUND', (3,-1), (4,-1), colors.HexColor('#fbbf24')),
        ('TOPPADDING', (3,-1), (4,-1), 6),
        ('BOTTOMPADDING', (3,-1), (4,-1), 6),
        ('BOX', (3,-1), (4,-1), 1, colors.HexColor('#fbbf24')),
        
        # Subtotal, GST & Gross spacing
        ('TOPPADDING', (3,-5), (4,-3), 3),
        ('BOTTOMPADDING', (3,-5), (4,-3), 3),
    ]
    billing_table.setStyle(TableStyle(table_styles))
    story.append(billing_table)
    story.append(Spacer(1, 10))

    # 5. Amount in Words Card & Signature Block
    words_style = ParagraphStyle(
        'WordsStyle',
        parent=normal_style,
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor('#475569')
    )
    
    pay_status_text = "Fully Settled" if balance_due == 0 else f"Balance: Rs. {balance_due:,.2f}"
    words_text = (
        '<b>TOTAL AMOUNT IN WORDS</b><br/>'
        f'<font size="7">{number_to_words(shipment.shipping_cost)}</font><br/>'
        f'<font size="6.5" color="#0f766e"><b>Advance Paid:</b> Rs. {advance_paid:,.2f} (Online) | <b>Status:</b> {pay_status_text}</font>'
    )
    
    words_card = Table([[Paragraph(words_text, words_style)]], colWidths=[260])
    words_card.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ('LEFTPADDING', (0,0), (-1,-1), 12),
        ('RIGHTPADDING', (0,0), (-1,-1), 12),
    ]))
    
    # Signature side
    sig_elements = [
        Paragraph('<b>Client Signature:</b>', ParagraphStyle('SigTitle', parent=normal_style, alignment=0)),
        Spacer(1, 4)
    ]
    sig_found = False
    for path_candidate in [shipment.signature_path, shipment.delivery_signature_path]:
        if path_candidate:
            sig_filename = path_candidate.replace('\\', '/').split('/')[-1]
            abs_sig_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'signatures', sig_filename)
            if not os.path.exists(abs_sig_path):
                abs_sig_path = os.path.join(current_app.root_path, 'static', 'uploads', 'signatures', sig_filename)
            if os.path.exists(abs_sig_path):
                sig_elements.append(Image(abs_sig_path, width=130, height=38))
                sig_elements.append(Spacer(1, 2))
                sig_found = True
                break
    if not sig_found:
        sig_elements.append(Spacer(1, 28))
    sig_elements.append(Paragraph('___________________________________', ParagraphStyle('SigLine', parent=normal_style, alignment=0)))
    
    sig_block = Table([[sig_elements]], colWidths=[260])
    sig_block.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
        ('LEFTPADDING', (0,0), (-1,-1), 20),
    ]))
    
    words_sig_table = Table([[words_card, sig_block]], colWidths=[260, 280])
    words_sig_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(words_sig_table)
    story.append(Spacer(1, 12))

    # 6. Terms & Conditions
    terms_html = (
        '<b>TERMS & CONDITIONS</b><br/>'
        '1. Goods carried at owner risk unless covered by insurance.<br/>'
        '2. Payment is due within standard schedules.<br/>'
        '3. Standard delivery takes 3-5 working days; Express takes 1-2 days.'
    )
    terms_table = Table([[Paragraph(terms_html, terms_text_style)]], colWidths=[540])
    terms_table.setStyle(TableStyle([
        ('LINEABOVE', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(terms_table)
    
    # Build Document using background canvas callback
    doc.build(story, onFirstPage=draw_invoice_background)
    return f"uploads/invoices/{filename}"

# 5. Shared Notification and Audit logging Helpers
def log_activity(user_id, action, details=None, ip_address=None):
    log = ActivityLog(user_id=user_id, action=action, details=details, ip_address=ip_address)
    db.session.add(log)
    db.session.commit()

def create_notification(user_id, title, message, notif_type="info"):
    notif = Notification(user_id=user_id, title=title, message=message, type=notif_type)
    db.session.add(notif)
    db.session.commit()

def get_packaging_categories():
    try:
        settings = Setting.query.filter(Setting.setting_key.like('rate_packaging_%')).all()
        categories = []
        for s in settings:
            key = s.setting_key
            if key == 'rate_packaging_other':
                continue
            desc = s.description or ''
            if "Packaging Rate: " in desc and " (INR/kg)" in desc:
                cat_name = desc.split("Packaging Rate: ")[1].split(" (INR/kg)")[0]
            else:
                cat_name = key.replace('rate_packaging_', '').replace('_', ' ').title()
            categories.append((cat_name, s.setting_value))
        
        categories.sort(key=lambda x: x[0])
        return categories
    except Exception as e:
        return [
            ('Clothes / Garments', '5.0'),
            ('Books', '8.0'),
            ('Documents', '10.0'),
            ('Electronics', '15.0'),
            ('Mobile / Laptop', '20.0'),
            ('Glass items', '20.0'),
            ('Kitchen items', '10.0'),
            ('Household items', '8.0'),
            ('Machinery parts', '20.0'),
            ('Auto spare parts', '15.0'),
            ('Furniture', '20.0'),
            ('Fruits / Vegetables', '8.0'),
            ('Food items', '10.0'),
            ('Clothing bundles', '5.0'),
            ('Industrial goods', '25.0')
        ]

def send_delivery_email(shipment):
    """
    Sends a delivery confirmation email to the sender/customer.
    Wraps all email operations in a fail-safe try-except block so that
    temporary email server failures will NEVER roll back or cancel the delivery.
    """
    from datetime import datetime
    if not shipment:
        return False
        
    recipient = shipment.sender_email
    if not recipient and shipment.customer and shipment.customer.user:
        recipient = shipment.customer.user.email
        
    if not recipient:
        shipment.delivery_email_status = 'Failed'
        return False

    delivered_time_str = (shipment.delivered_at or datetime.utcnow()).strftime('%d %b %Y, %I:%M %p')
    driver_name = shipment.driver.user.username if (shipment.driver and shipment.driver.user) else "Assigned Delivery Driver"
    branch_name = shipment.branch.name if shipment.branch else "Destination Branch"

    subject = f"Shipment {shipment.tracking_number} Delivered Successfully"
    body_text = f"""Dear {shipment.sender_name},

Your shipment with LogiTrack has been delivered successfully!

DELIVERY SUMMARY:
- Tracking Number: {shipment.tracking_number}
- Delivery Status: Delivered
- Receiver Name: {shipment.receiver_name}
- Delivered Date & Time: {delivered_time_str}
- Delivered By: {driver_name}
- Final Branch Hub: {branch_name}
- E-Signature & Photo Proof: Captured & Verified

You can review the full Proof of Delivery (POD), product photo, and receiver signature by logging into your LogiTrack dashboard or tracking your shipment online.

Thank you for choosing LogiTrack Logistics!
"""

    try:
        mail_server = current_app.config.get('MAIL_SERVER')
        if mail_server:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            msg = MIMEMultipart()
            msg['From'] = current_app.config.get('MAIL_DEFAULT_SENDER', 'no-reply@logitrack.com')
            msg['To'] = recipient
            msg['Subject'] = subject
            msg.attach(MIMEText(body_text, 'plain'))

            port = current_app.config.get('MAIL_PORT', 587)
            use_tls = current_app.config.get('MAIL_USE_TLS', True)
            username = current_app.config.get('MAIL_USERNAME')
            password = current_app.config.get('MAIL_PASSWORD')

            with smtplib.SMTP(mail_server, port, timeout=5) as server:
                if use_tls:
                    server.starttls()
                if username and password:
                    server.login(username, password)
                server.send_message(msg)

            shipment.delivery_email_status = 'Sent'
            return True
        else:
            # Simulated email dispatch in development/test environment
            print(f"[EMAIL SIMULATION] Sent delivery confirmation email for {shipment.tracking_number} to {recipient}")
            shipment.delivery_email_status = 'Sent'
            return True
    except Exception as e:
        print(f"[EMAIL DISPATCH FAILED] Could not send email to {recipient}: {e}")
        shipment.delivery_email_status = 'Failed'
        return False

def sync_branch_driver_availability(branch_id=None):
    """
    Self-healing driver availability synchronization.
    A driver is marked 'Busy' ONLY if:
      - They have active individual shipments (status not in Delivered/Completed/Cancelled/Returned)
      - OR they are assigned to an active uncompleted linehaul container (status not in Completed/Arrived at Destination/Cancelled)
    Otherwise, they are automatically restored to 'Available'.
    """
    from app.models import db, Driver, Shipment, ContainerTransfer
    try:
        query = Driver.query
        if branch_id:
            query = query.filter_by(branch_id=branch_id)
        drivers = query.all()
        for d in drivers:
            # Check individual active runs (excluding orders inside containers where container itself tracks the driver)
            active_shipments_count = Shipment.query.filter_by(driver_id=d.id).filter(
                Shipment.status.notin_(['Delivered', 'Completed', 'Cancelled', 'Returned', 'Container Driver Assigned'])
            ).count()
            
            # Check active container transfers
            active_containers_count = ContainerTransfer.query.filter_by(driver_id=d.id).filter(
                ContainerTransfer.status.notin_(['Completed', 'Arrived at Destination', 'Cancelled'])
            ).count()
            
            is_busy = (active_shipments_count > 0 or active_containers_count > 0)
            expected_status = 'Busy' if is_busy else 'Available'
            
            if d.status != expected_status:
                d.status = expected_status
                
            if d.vehicle:
                expected_veh = 'Busy' if is_busy else 'Available'
                if d.vehicle.availability != expected_veh:
                    d.vehicle.availability = expected_veh
                    
        db.session.commit()
    except Exception as e:
        db.session.rollback()

