import random
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, g
from app.models import db, Shipment, Payment, ShipmentHistory, TrackingLog, Invoice
from app.utils import login_required, role_required, log_activity, create_notification, create_invoice_pdf
from . import payment_bp

@payment_bp.route('/checkout/<int:shipment_id>', methods=['GET'])
@login_required
@role_required('Customer', 'Administrator')
def checkout(shipment_id):
    shipment = db.session.get(Shipment, shipment_id)
    if not shipment:
        flash("Shipment record not found.", "danger")
        return redirect(url_for('customer.dashboard'))
        
    payment = Payment.query.filter_by(shipment_id=shipment.id).first()
    expected_advance = shipment.advance_paid if shipment.advance_paid > 0 else shipment.shipping_cost
    if not payment:
        payment = Payment(shipment_id=shipment.id, amount=expected_advance, payment_method='Simulated Online', payment_status='Pending')
        db.session.add(payment)
        db.session.commit()
    else:
        if payment.payment_status == 'Pending':
            payment.amount = expected_advance
            db.session.commit()
        
    if payment.payment_status == 'Completed':
        flash("Advance payment has already been completed for this shipment.", "info")
        return redirect(url_for('payment.success', shipment_id=shipment.id))
        
    from app.utils import get_gst_rate_by_category
    gst_rate = get_gst_rate_by_category(shipment.package_category)
    subtotal = round(payment.amount / (1 + (gst_rate / 100)), 2)
    tax = round(payment.amount - subtotal, 2)
        
    return render_template('payment/checkout.html', shipment=shipment, payment=payment, subtotal=subtotal, tax=tax, gst_rate=gst_rate)

@payment_bp.route('/process/<int:shipment_id>', methods=['POST'])
@login_required
@role_required('Customer', 'Administrator')
def process_payment(shipment_id):
    shipment = db.session.get(Shipment, shipment_id)
    if not shipment:
        flash("Shipment not found.", "danger")
        return redirect(url_for('customer.dashboard'))
        
    payment = Payment.query.filter_by(shipment_id=shipment.id).first()
    if not payment:
        expected_advance = shipment.advance_paid if shipment.advance_paid > 0 else shipment.shipping_cost
        payment = Payment(shipment_id=shipment.id, amount=expected_advance, payment_method='Simulated Online', payment_status='Pending')
        db.session.add(payment)
        db.session.commit()
        
    payment_method = request.form.get('payment_method', 'Online Card')
    
    if payment_method == 'Cash on Delivery':
        flash("Advance booking payment must be paid online. Cash on Delivery is not allowed for the initial advance fee.", "warning")
        return redirect(url_for('payment.checkout', shipment_id=shipment_id))
        
    advance_amount = shipment.advance_paid if shipment.advance_paid > 0 else shipment.shipping_cost
    payment.amount = advance_amount
    payment.cash_status = 'N/A'
    payment.cash_collected_amount = 0.0

    if payment_method in ['UPI', 'UPI / QR Scan', 'Online UPI']:
        upi_ref = request.form.get('upi_ref', '').strip()
        if not upi_ref:
            upi_ref = f"UPI-UTR-{random.randint(100000000000, 999999999999)}"
        payment.payment_method = 'UPI / QR Scan'
        payment.digital_reference = upi_ref
        payment.payment_status = 'Completed'
        payment.transaction_id = f"TXN-UPI-{random.randint(10000000, 99999999)}"
        shipment.status = 'Confirmed'
        notes = f"Advance payment of ₹{advance_amount:.2f} successfully paid online via UPI / QR Scan. UTR Ref: {upi_ref}. Transaction ID: {payment.transaction_id}."
    else:
        # Simulated Online Card Checkout
        card_num = request.form.get('card_number', '').strip()
        card_name = request.form.get('card_name', '').strip()
        
        if not card_num or len(card_num.replace(" ", "")) < 12:
            flash("Please enter valid card details.", "warning")
            return redirect(url_for('payment.checkout', shipment_id=shipment_id))
            
        card_digits = card_num.replace(" ", "")
        last4 = card_digits[-4:] if len(card_digits) >= 4 else "4444"
        payment.payment_method = 'Online Card'
        payment.digital_reference = f"CARD-AUTH-{last4}-{random.randint(1000, 9999)}"
        payment.payment_status = 'Completed'
        payment.transaction_id = f"TXN-CARD-{random.randint(10000000, 99999999)}"
        shipment.status = 'Confirmed'
        notes = f"Advance payment of ₹{advance_amount:.2f} successfully paid online via Card. Card ending {last4}. Transaction ID: {payment.transaction_id}."
        
    try:
        # History
        hist = ShipmentHistory(shipment_id=shipment.id, status=shipment.status, notes=notes, updated_by_id=g.user.id)
        db.session.add(hist)
        
        # Tracking
        t_log = TrackingLog(shipment_id=shipment.id, current_location=shipment.pickup_city, status=shipment.status, description=notes)
        db.session.add(t_log)
        
        # Invoice details creation
        from app.utils import get_gst_rate_by_category
        gst_rate = get_gst_rate_by_category(shipment.package_category)
        subtotal = round(shipment.shipping_cost / (1 + (gst_rate / 100)), 2)
        tax = round(shipment.shipping_cost - subtotal, 2)
        
        # Check if invoice already exists
        inv = Invoice.query.filter_by(shipment_id=shipment.id).first()
        if not inv:
            inv = Invoice(
                shipment_id=shipment.id,
                invoice_number=f"INV-{datetime.now().strftime('%Y%m')}-{shipment.id:04d}",
                subtotal=subtotal,
                tax_amount=tax,
                total_amount=shipment.shipping_cost
            )
            db.session.add(inv)
            db.session.commit()
            
        # Re-generate invoice PDF containing receipt details
        create_invoice_pdf(shipment)
        
        # Update customer loyalty points on successful payment
        if payment.payment_status == 'Completed' and shipment.customer:
            shipment.customer.loyalty_points += int(payment.amount / 10)
            
        db.session.commit()
        log_activity(g.user.id, "Advance Payment Processed", f"Processed online advance payment ₹{advance_amount:.2f} for shipment {shipment.tracking_number} - Status: {payment.payment_status}", request.remote_addr)
        
        # Add notifications
        create_notification(g.user.id, "Payment Processed", f"Advance payment of ₹{advance_amount:.2f} for {shipment.tracking_number} confirmed online.", "success")
        
        return redirect(url_for('payment.success', shipment_id=shipment.id))
    except Exception as e:
        db.session.rollback()
        flash("Failed to process payment. Please try again.", "danger")
        return redirect(url_for('payment.checkout', shipment_id=shipment_id))

@payment_bp.route('/success/<int:shipment_id>')
@login_required
@role_required('Customer', 'Administrator')
def success(shipment_id):
    shipment = db.session.get(Shipment, shipment_id)
    if not shipment:
        flash("Shipment not found.", "danger")
        return redirect(url_for('customer.dashboard'))
        
    payment = Payment.query.filter_by(shipment_id=shipment.id).first()
    return render_template('payment/success.html', shipment=shipment, payment=payment)
