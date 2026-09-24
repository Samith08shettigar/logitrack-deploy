import io
import csv
from datetime import datetime, timedelta
from flask import render_template, request, redirect, url_for, flash, g, make_response, current_app
from sqlalchemy import func
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from app.models import db, Shipment, Payment, Driver, Customer, Branch, Vehicle
from app.utils import login_required, role_required
from . import reports_bp

@reports_bp.route('/')
@login_required
@role_required('Administrator', 'Branch Manager')
def index():
    return render_template('reports/index.html')

@reports_bp.route('/view', methods=['GET'])
@login_required
@role_required('Administrator', 'Branch Manager')
def view_report():
    report_type = request.args.get('type', 'shipments')
    timeframe = request.args.get('timeframe', 'monthly')
    
    # Filter by date range
    now = datetime.now()
    if timeframe == 'daily':
        start_date = now - timedelta(days=1)
    elif timeframe == 'weekly':
        start_date = now - timedelta(weeks=1)
    else: # monthly default
        start_date = now - timedelta(days=30)
        
    data = []
    headers = []
    title = ""
    
    if report_type == 'shipments':
        title = f"{timeframe.capitalize()} Shipments Report"
        query_data = Shipment.query.filter(Shipment.created_at >= start_date).order_by(Shipment.created_at.desc()).all()
        headers = ['Tracking Number', 'Sender', 'Receiver', 'Delivery Type', 'Weight (kg)', 'Cost', 'Status', 'Booking Date']
        data = [[s.tracking_number, s.sender_name, s.receiver_name, s.delivery_type, s.package_weight, f"Rs. {s.shipping_cost:.2f}", s.status, s.created_at.strftime('%Y-%m-%d')] for s in query_data]
        
    elif report_type == 'revenue':
        title = f"{timeframe.capitalize()} Revenue Report"
        query_data = Payment.query.filter(Payment.created_at >= start_date, Payment.payment_status == 'Completed').order_by(Payment.created_at.desc()).all()
        headers = ['Transaction ID', 'Tracking Number', 'Payment Method', 'Amount', 'Payment Date']
        data = [[p.transaction_id or 'COD', p.shipment.tracking_number if p.shipment else 'N/A', p.payment_method, f"Rs. {p.amount:.2f}", p.created_at.strftime('%Y-%m-%d')] for p in query_data]
        
    elif report_type == 'drivers':
        title = "Driver Performance & Ratings Report"
        query_data = Driver.query.order_by(Driver.rating.desc()).all()
        headers = ['Driver Username', 'Phone', 'License', 'Status', 'Rating', 'Jobs Handle']
        data = [[d.user.username if d.user else 'Unknown', d.phone, d.license_number, d.status, f"{d.rating:.1f}/5.0", len(d.shipments)] for d in query_data]
        
    elif report_type == 'customers':
        title = "Customer Activity Report"
        query_data = Customer.query.order_by(Customer.loyalty_points.desc()).all()
        headers = ['Customer Name', 'Phone', 'Status', 'Loyalty Points', 'Total Shipments Booked']
        data = [[c.user.username if c.user else 'Unknown', c.phone, c.status, c.loyalty_points, len(c.shipments)] for c in query_data]
        
    elif report_type == 'branches':
        title = "Branch Performance Summary"
        query_data = Branch.query.all()
        headers = ['Branch Code', 'Branch Name', 'City', 'Phone', 'Employees/Drivers', 'Shipments Processed']
        data = [[b.code, b.name, b.city, b.phone, len(b.drivers), len(b.shipments)] for b in query_data]
        
    elif report_type == 'vehicles':
        title = "Vehicle Usage & Fleet Fleet Report"
        query_data = Vehicle.query.all()
        headers = ['Plate Number', 'Type', 'Capacity (kg)', 'Availability', 'Maintenance Status', 'Branch Hub']
        data = [[v.vehicle_number, v.vehicle_type, v.capacity, v.availability, v.maintenance_status, v.branch.name if v.branch else 'Unassigned'] for v in query_data]
        
    elif report_type == 'success_rate':
        title = "Delivery Success Rate Analysis"
        headers = ['Metric', 'Count', 'Percentage']
        total = Shipment.query.count()
        completed = Shipment.query.filter(Shipment.status.in_(['Completed', 'Delivered'])).count()
        cancelled = Shipment.query.filter_by(status='Cancelled').count()
        active = total - completed - cancelled
        
        success_pct = (completed / total * 100) if total > 0 else 100.0
        cancel_pct = (cancelled / total * 100) if total > 0 else 0.0
        active_pct = (active / total * 100) if total > 0 else 0.0
        
        data = [
            ['Total Shipments Booked', total, '100.0%'],
            ['Completed Deliveries', completed, f"{success_pct:.1f}%"],
            ['Active Deliveries (In Transit)', active, f"{active_pct:.1f}%"],
            ['Cancelled Shipments', cancelled, f"{cancel_pct:.1f}%"]
        ]
        
    return render_template(
        'reports/view_report.html',
        title=title,
        headers=headers,
        data=data,
        report_type=report_type,
        timeframe=timeframe
    )

@reports_bp.route('/export')
@login_required
@role_required('Administrator', 'Branch Manager')
def export_report_file():
    report_type = request.args.get('type', 'shipments')
    timeframe = request.args.get('timeframe', 'monthly')
    file_format = request.args.get('format', 'csv')
    
    # Filter by date range
    now = datetime.now()
    if timeframe == 'daily':
        start_date = now - timedelta(days=1)
    elif timeframe == 'weekly':
        start_date = now - timedelta(weeks=1)
    else: # monthly default
        start_date = now - timedelta(days=30)
        
    data = []
    headers = []
    report_title = ""
    
    if report_type == 'shipments':
        report_title = f"{timeframe.capitalize()} Shipments Report"
        query_data = Shipment.query.filter(Shipment.created_at >= start_date).order_by(Shipment.created_at.desc()).all()
        headers = ['Tracking Number', 'Sender', 'Receiver', 'Delivery Type', 'Weight (kg)', 'Cost', 'Status', 'Date']
        data = [[s.tracking_number, s.sender_name, s.receiver_name, s.delivery_type, s.package_weight, s.shipping_cost, s.status, s.created_at.strftime('%Y-%m-%d')] for s in query_data]
        
    elif report_type == 'revenue':
        report_title = f"{timeframe.capitalize()} Revenue Report"
        query_data = Payment.query.filter(Payment.created_at >= start_date, Payment.payment_status == 'Completed').order_by(Payment.created_at.desc()).all()
        headers = ['Transaction ID', 'Tracking Number', 'Payment Method', 'Amount', 'Date']
        data = [[p.transaction_id or 'COD', p.shipment.tracking_number if p.shipment else 'N/A', p.payment_method, p.amount, p.created_at.strftime('%Y-%m-%d')] for p in query_data]
        
    elif report_type == 'drivers':
        report_title = "Driver Performance Report"
        query_data = Driver.query.order_by(Driver.rating.desc()).all()
        headers = ['Driver Username', 'Phone', 'License', 'Status', 'Rating', 'Jobs Assigned']
        data = [[d.user.username if d.user else 'Unknown', d.phone, d.license_number, d.status, d.rating, len(d.shipments)] for d in query_data]
        
    elif report_type == 'customers':
        report_title = "Customer Activity Report"
        query_data = Customer.query.order_by(Customer.loyalty_points.desc()).all()
        headers = ['Customer Name', 'Phone', 'Status', 'Loyalty Points', 'Total Bookings']
        data = [[c.user.username if c.user else 'Unknown', c.phone, c.status, c.loyalty_points, len(c.shipments)] for c in query_data]
        
    elif report_type == 'branches':
        report_title = "Branch Performance Summary"
        query_data = Branch.query.all()
        headers = ['Branch Code', 'Branch Name', 'City', 'Phone', 'Drivers count', 'Total Shipments']
        data = [[b.code, b.name, b.city, b.phone, len(b.drivers), len(b.shipments)] for b in query_data]
        
    elif report_type == 'vehicles':
        report_title = "Vehicle Fleet Report"
        query_data = Vehicle.query.all()
        headers = ['Plate Number', 'Type', 'Capacity (kg)', 'Availability', 'Maintenance Status', 'Branch']
        data = [[v.vehicle_number, v.vehicle_type, v.capacity, v.availability, v.maintenance_status, v.branch.name if v.branch else 'Unassigned'] for v in query_data]
        
    elif report_type == 'success_rate':
        report_title = "Delivery Success Rate Report"
        headers = ['Metric', 'Count', 'Percentage']
        total = Shipment.query.count()
        completed = Shipment.query.filter(Shipment.status.in_(['Completed', 'Delivered'])).count()
        cancelled = Shipment.query.filter_by(status='Cancelled').count()
        active = total - completed - cancelled
        
        success_pct = (completed / total * 100) if total > 0 else 100.0
        cancel_pct = (cancelled / total * 100) if total > 0 else 0.0
        active_pct = (active / total * 100) if total > 0 else 0.0
        
        data = [
            ['Total Shipments Booked', total, '100.0%'],
            ['Completed Deliveries', completed, f"{success_pct:.1f}%"],
            ['Active Deliveries', active, f"{active_pct:.1f}%"],
            ['Cancelled Shipments', cancelled, f"{cancel_pct:.1f}%"]
        ]

    # --- CSV EXPORT ---
    if file_format == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(data)
        
        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = f"attachment; filename={report_type}_{timeframe}_report.csv"
        response.headers["Content-type"] = "text/csv"
        return response
        
    # --- EXCEL EXPORT ---
    elif file_format == 'excel':
        df = pd.DataFrame(data, columns=headers)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Sheet1')
            
        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = f"attachment; filename={report_type}_{timeframe}_report.xlsx"
        response.headers["Content-type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return response
        
    # --- PDF EXPORT ---
    elif file_format == 'pdf':
        output = io.BytesIO()
        doc = SimpleDocTemplate(output, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=40, bottomMargin=40)
        story = []
        
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'ReportTitle',
            parent=styles['Heading1'],
            fontSize=20,
            leading=24,
            textColor=colors.HexColor('#1e3a8a'),
            spaceAfter=15
        )
        subtitle_style = ParagraphStyle(
            'ReportSub',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#475569'),
            spaceAfter=20
        )
        
        # Header
        story.append(Paragraph(f"LogiTrack - {report_title}", title_style))
        story.append(Paragraph(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Filter: {timeframe.capitalize()}", subtitle_style))
        
        # Build Table
        # We need to wrap each cell in Paragraph to prevent text overflow if columns are tight
        table_headers = [Paragraph(f"<b>{h}</b>", styles['Normal']) for h in headers]
        table_rows = [table_headers]
        
        for r in data:
            row_cells = []
            for item in r:
                row_cells.append(Paragraph(str(item), styles['Normal']))
            table_rows.append(row_cells)
            
        # Calculate column width dynamically (budgeting 540 pt width total)
        col_count = len(headers)
        col_width = 540.0 / col_count
        
        t = Table(table_rows, colWidths=[col_width]*col_count)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1e3a8a')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
            # Set header font color
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ]))
        
        # Quick fix for text colors inside paragraphs of tables
        for row_idx in range(len(table_rows)):
            for col_idx in range(len(table_headers)):
                if row_idx == 0:
                    # Header styling
                    pass # We did <b> inside Paragraph
                    
        story.append(t)
        doc.build(story)
        
        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = f"attachment; filename={report_type}_{timeframe}_report.pdf"
        response.headers["Content-type"] = "application/pdf"
        return response
        
    else:
        flash("Unsupported format.", "warning")
        return redirect(url_for('reports.index'))
