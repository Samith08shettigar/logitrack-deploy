from datetime import datetime, timedelta
import random
import os
from flask import render_template, request, redirect, url_for, flash, g, send_from_directory, current_app
from sqlalchemy import func
from app.models import db, User, Customer, Shipment, ShipmentHistory, TrackingLog, Address, Payment, Invoice, Feedback, Notification, Branch
from app.utils import login_required, role_required, log_activity, create_notification, calculate_shipping_cost, generate_qr_code, generate_barcode_img, create_invoice_pdf
from . import customer_bp

@customer_bp.route('/dashboard')
@login_required
@role_required('Customer')
def dashboard():
    customer = Customer.query.filter_by(user_id=g.user.id).first()
    if not customer:
        customer = Customer(user_id=g.user.id, phone="N/A", status='Active')
        db.session.add(customer)
        db.session.commit()
        
    # Get stats
    total_booked = Shipment.query.filter_by(customer_id=customer.id).count()
    active_shipments = Shipment.query.filter(
        Shipment.customer_id == customer.id,
        Shipment.status.notin_(['Completed', 'Delivered', 'Cancelled'])
    ).all()
    
    completed_shipments = Shipment.query.filter(
        Shipment.customer_id == customer.id,
        Shipment.status.in_(['Completed', 'Delivered'])
    ).all()
    
    recent_shipments = Shipment.query.filter_by(customer_id=customer.id).order_by(Shipment.created_at.desc()).limit(5).all()
    
    # Read notifications
    notifications = Notification.query.filter_by(user_id=g.user.id).order_by(Notification.created_at.desc()).limit(5).all()

    return render_template(
        'customer/dashboard.html',
        customer=customer,
        total_booked=total_booked,
        active_count=len(active_shipments),
        completed_count=len(completed_shipments),
        recent_shipments=recent_shipments,
        notifications=notifications
    )

# --- ADDRESS BOOK ---
@customer_bp.route('/addresses')
@login_required
@role_required('Customer')
def list_addresses():
    addresses = Address.query.filter_by(user_id=g.user.id).all()
    return render_template('customer/addresses.html', addresses=addresses)

@customer_bp.route('/addresses/add', methods=['GET', 'POST'])
@login_required
@role_required('Customer')
def add_address():
    if request.method == 'POST':
        label = request.form.get('label')
        addr_line = request.form.get('address_line')
        city = request.form.get('city')
        state = request.form.get('state')
        zip_code = request.form.get('zip_code')
        phone = request.form.get('phone')
        is_pickup = request.form.get('is_pickup') == 'on'
        is_delivery = request.form.get('is_delivery') == 'on'
        
        if not label or not addr_line or not city or not state or not zip_code or not phone:
            flash("All fields are required.", "warning")
            return redirect(url_for('customer.add_address'))
            
        try:
            addr = Address(
                user_id=g.user.id, label=label, address_line=addr_line,
                city=city, state=state, zip_code=zip_code, phone=phone,
                is_pickup=is_pickup, is_delivery=is_delivery
            )
            db.session.add(addr)
            db.session.commit()
            log_activity(g.user.id, "Add Address", f"Added saved address: {label}", request.remote_addr)
            flash("Address saved successfully!", "success")
            return redirect(url_for('customer.list_addresses'))
        except Exception as e:
            db.session.rollback()
            flash("Failed to save address.", "danger")
            
    return render_template('customer/address_form.html', action="Add")

@customer_bp.route('/addresses/delete/<int:id>')
@login_required
@role_required('Customer')
def delete_address(id):
    addr = Address.query.filter_by(id=id, user_id=g.user.id).first()
    if not addr:
        flash("Address not found.", "danger")
        return redirect(url_for('customer.list_addresses'))
    try:
        db.session.delete(addr)
        db.session.commit()
        log_activity(g.user.id, "Delete Address", f"Deleted saved address ID {id}", request.remote_addr)
        flash("Address removed successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Failed to remove address.", "danger")
    return redirect(url_for('customer.list_addresses'))


# --- SHIPMENT BOOKING ---
@customer_bp.route('/book', methods=['GET', 'POST'])
@login_required
@role_required('Customer')
def book_shipment():
    customer = Customer.query.filter_by(user_id=g.user.id).first()
    saved_addresses = Address.query.filter_by(user_id=g.user.id).all()
    branches = Branch.query.order_by(Branch.name).all()
    
    if request.method == 'POST':
        # Receiver Info
        r_name = request.form.get('receiver_name')
        r_phone = request.form.get('receiver_phone')
        r_addr = request.form.get('receiver_address')
        r_city = request.form.get('receiver_city')
        r_state = request.form.get('receiver_state')
        r_zip = request.form.get('receiver_zip_code')
        
        # Package Info
        category = request.form.get('package_category')
        if category == 'Other':
            category = request.form.get('custom_category')
        desc = request.form.get('package_description')
        fragile = request.form.get('fragile') == 'on'
        insurance = request.form.get('insurance') == 'on'
        delivery_type = request.form.get('delivery_type', 'Standard')
        
        weigh_at_pickup = request.form.get('weigh_at_pickup') == 'on'
        if weigh_at_pickup:
            weight = 0.0
            cost = 200.0
            advance_paid = 200.0
        else:
            weight = float(request.form.get('package_weight', 1.0))
        
        # Product Image Upload handling (Compulsory)
        import uuid
        image_file = request.files.get('package_image')
        if not image_file or not image_file.filename or image_file.filename.strip() == '':
            flash("Product image is compulsory required. Please upload a clear photo of your package.", "warning")
            return redirect(url_for('customer.book_shipment'))

        ext = os.path.splitext(image_file.filename)[1].lower()
        allowed_exts = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'}
        if ext not in allowed_exts:
            flash("Invalid image format. Please upload a valid image file (JPG, PNG, WEBP, etc.).", "warning")
            return redirect(url_for('customer.book_shipment'))

        filename = f"prod_{uuid.uuid4().hex}{ext}"
        save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'products', filename)
        image_file.save(save_path)
        image_path = f"uploads/products/{filename}"
        
        # Pickup address (could be a selected saved address or custom typed)
        pickup_choice = request.form.get('pickup_address_id')
        if pickup_choice and pickup_choice != 'custom':
            p_addr_obj = db.session.get(Address, int(pickup_choice))
            p_addr = p_addr_obj.address_line
            p_city = p_addr_obj.city
            p_state = p_addr_obj.state
            p_zip = p_addr_obj.zip_code
        else:
            p_addr = request.form.get('pickup_address')
            p_city = request.form.get('pickup_city')
            p_state = request.form.get('pickup_state')
            p_zip = request.form.get('pickup_zip_code')

        # Nearest Branch selection
        branch_id = request.form.get('branch_id')
        branch_id = int(branch_id) if branch_id else None
            
        # Date Info
        p_date_str = request.form.get('pickup_date')
        p_date = datetime.strptime(p_date_str, '%Y-%m-%d').date() if p_date_str else datetime.now().date()
        
        # Cost calculation
        declared_value = float(request.form.get('declared_value', 0.0)) if insurance else 0.0
        if not weigh_at_pickup:
            cost = calculate_shipping_cost(weight, delivery_type, fragile, insurance, category, declared_value)
            advance_paid = round(cost / 2, 2)
        
        # Generate dynamic values
        tracking_num = f"LT-{datetime.now().strftime('%y%m%d')}-{random.randint(1000, 9999)}"
        
        # Resolve next branch based on receiver city
        dest_branch = Branch.query.filter(Branch.city.ilike(r_city.strip())).first()
        next_branch_id = dest_branch.id if dest_branch else None

        try:
            # Create Shipment
            shipment = Shipment(
                tracking_number=tracking_num,
                sender_name=g.user.username,
                sender_phone=customer.phone,
                sender_email=g.user.email,
                pickup_address_line=p_addr, pickup_city=p_city, pickup_state=p_state, pickup_zip_code=p_zip,
                receiver_name=r_name, receiver_phone=r_phone,
                receiver_address_line=r_addr, receiver_city=r_city, receiver_state=r_state, receiver_zip_code=r_zip,
                package_category=category, package_description=desc, package_weight=weight,
                package_dimensions=None, package_image_path=image_path, weigh_at_pickup=weigh_at_pickup,
                advance_paid=advance_paid, fragile=fragile, insurance=insurance,
                declared_value=declared_value,
                delivery_type=delivery_type, pickup_date=p_date,
                shipping_cost=cost, status='Booked', customer_id=customer.id,
                branch_id=branch_id, next_branch_id=next_branch_id
            )
            db.session.add(shipment)
            db.session.commit()
            
            # Generate QR and Barcode paths
            shipment.qr_code_path = generate_qr_code(tracking_num)
            shipment.barcode_path = generate_barcode_img(tracking_num)
            
            # History
            hist = ShipmentHistory(shipment_id=shipment.id, status='Booked', notes='Shipment booked by customer')
            db.session.add(hist)
            
            # Tracking Log
            t_log = TrackingLog(shipment_id=shipment.id, current_location=p_city, status='Booked', description="Shipment booked online")
            db.session.add(t_log)
            
            # Payment
            payment = Payment(shipment_id=shipment.id, amount=advance_paid, payment_method='Simulated Online', payment_status='Pending')
            db.session.add(payment)
            
            # Sender / Client Signature (if drawn upon booking)
            signature_data = request.form.get('signature_data')
            if signature_data:
                if ',' in signature_data:
                    signature_data = signature_data.split(',')[1]
                img_bytes = base64.b64decode(signature_data)
                sig_filename = f"sig_{tracking_num}.png"
                sig_filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], 'signatures', sig_filename)
                with open(sig_filepath, 'wb') as f:
                    f.write(img_bytes)
                shipment.signature_path = f"uploads/signatures/{sig_filename}"

            # PDF Invoice
            create_invoice_pdf(shipment)
            
            db.session.commit()
            
            log_activity(g.user.id, "Book Shipment", f"Booked shipment tracking #: {tracking_num}", request.remote_addr)
            create_notification(g.user.id, "Shipment Booked", f"Your shipment {tracking_num} has been booked. Click to pay.", "info")
            
            # Redirect to payment page
            return redirect(url_for('payment.checkout', shipment_id=shipment.id))
        except Exception as e:
            db.session.rollback()
            flash("An error occurred during booking. Please try again.", "danger")
            
    return render_template('customer/book_shipment.html', customer=customer, saved_addresses=saved_addresses, branches=branches)


def get_city_image(city_name):
    if not city_name:
        return 'images/default_city.jpg'
    city_lower = city_name.lower().strip()
    if 'mangalore' in city_lower or 'mangaluru' in city_lower or 'managalore' in city_lower:
        return 'images/mangalore_lighthouse.jpg'
    elif 'bangalore' in city_lower or 'bengaluru' in city_lower:
        return 'images/bangalore_palace.jpg'
    elif 'delhi' in city_lower:
        return 'images/delhi_red_fort.jpg'
    elif 'mumbai' in city_lower or 'bombay' in city_lower:
        return 'images/mumbai_gateway.jpg'
    else:
        return 'images/default_city.jpg'

# --- TRACKING ---
@customer_bp.route('/track', methods=['GET', 'POST'])
def public_track():
    tracking_number = request.args.get('tracking_number') or request.form.get('tracking_number')
    shipment = None
    tracking_logs = []
    pickup_img = 'images/default_city.jpg'
    receiver_img = 'images/default_city.jpg'
    current_status_idx = 0
    ns_time = {
        'booked': '--',
        'confirmed': '--',
        'assigned': '--',
        'picked': '--',
        'warehouse_origin': '--',
        'transit': '--',
        'warehouse_dest': '--',
        'out': '--',
        'delivered': '--'
    }
    
    if tracking_number:
        tracking_number = tracking_number.strip()
        shipment = Shipment.query.filter(Shipment.tracking_number.ilike(tracking_number)).first()
        if shipment:
            tracking_logs = TrackingLog.query.filter_by(shipment_id=shipment.id).order_by(TrackingLog.update_time.desc()).all()
            pickup_img = get_city_image(shipment.pickup_city)
            receiver_img = get_city_image(shipment.receiver_city)
            
            # 1. Determine current status index
            status_map = {
                'Booked': 0,
                'Confirmed': 1,
                'Driver Assigned': 2,
                'Picked Up': 3,
                'In Transit': 5,
                'Out For Delivery': 7,
                'Delivered': 8,
                'Completed': 8
            }
            if shipment.status == 'Warehouse':
                is_dest = False
                if shipment.branch and shipment.receiver_city:
                    is_dest = (shipment.branch.city.strip().lower() == shipment.receiver_city.strip().lower())
                current_status_idx = 6 if is_dest else 4
            else:
                current_status_idx = status_map.get(shipment.status, 0)
                
            # 2. Extract timestamps chronologically to distinguish multi-leg check-ins
            chronological_logs = list(reversed(tracking_logs))
            for log in chronological_logs:
                status = log.status
                time_str = log.update_time.strftime('%I:%M %p')
                if status == 'Booked':
                    ns_time['booked'] = time_str
                elif status == 'Confirmed':
                    ns_time['confirmed'] = time_str
                elif status == 'Driver Assigned':
                    ns_time['assigned'] = time_str
                elif status == 'Picked Up':
                    ns_time['picked'] = time_str
                elif status == 'In Transit':
                    ns_time['transit'] = time_str
                elif status == 'Warehouse':
                    is_dest = False
                    if log.current_location and shipment.receiver_city:
                        is_dest = (log.current_location.strip().lower() == shipment.receiver_city.strip().lower())
                    
                    if is_dest:
                        ns_time['warehouse_dest'] = time_str
                    else:
                        ns_time['warehouse_origin'] = time_str
                elif status == 'Out For Delivery':
                    ns_time['out'] = time_str
                elif status in ['Delivered', 'Completed']:
                    ns_time['delivered'] = time_str
        else:
            flash("No shipment found with that tracking number.", "warning")
            
    # If logged in as customer, default to their tracking view
    return render_template(
        'customer/track.html', 
        shipment=shipment, 
        tracking_logs=tracking_logs, 
        search_query=tracking_number, 
        pickup_img=pickup_img, 
        receiver_img=receiver_img,
        current_status_idx=current_status_idx,
        ns_time=ns_time
    )


# --- DOWNLOAD INVOICE ---
@customer_bp.route('/invoice/<tracking_number>')
@login_required
@role_required('Customer', 'Administrator', 'Branch Manager')
def download_invoice(tracking_number):
    shipment = Shipment.query.filter_by(tracking_number=tracking_number).first()
    if not shipment:
        flash("Invoice not found.", "danger")
        return redirect(url_for('customer.dashboard'))
        
    if shipment.status in ['Booked', 'Payment Pending', 'Confirmed', 'Branch Assigned'] and g.user.role.name == 'Customer':
        flash("Invoice is not available yet. It will be generated after the courier agent weighs the package, collects your signature, and picks up the item.", "warning")
        return redirect(url_for('customer.dashboard'))
        
    filename = f"invoice_{shipment.tracking_number}.pdf"
    directory = os.path.join(current_app.config['UPLOAD_FOLDER'], 'invoices')
    
    # Always generate fresh up-to-date PDF with latest signatures, weight recalculations & payments
    create_invoice_pdf(shipment)
        
    return send_from_directory(directory, filename, as_attachment=True)


# --- CANCEL SHIPMENT ---
@customer_bp.route('/cancel/<int:id>')
@login_required
@role_required('Customer')
def cancel_shipment(id):
    customer = Customer.query.filter_by(user_id=g.user.id).first()
    shipment = Shipment.query.filter_by(id=id, customer_id=customer.id).first()
    
    if not shipment:
        flash("Shipment not found.", "danger")
        return redirect(url_for('customer.dashboard'))
        
    # Cancellation allowed only before Driver is assigned
    if shipment.status not in ['Booked', 'Payment Pending', 'Confirmed', 'Branch Assigned']:
        flash("Cannot cancel shipment once dispatch has started.", "danger")
        return redirect(url_for('customer.dashboard'))
        
    try:
        shipment.status = 'Cancelled'
        
        # History
        hist = ShipmentHistory(shipment_id=shipment.id, status='Cancelled', notes='Shipment cancelled by customer')
        db.session.add(hist)
        
        # Payment status
        if shipment.payment:
            shipment.payment.payment_status = 'Refunded' if shipment.payment.payment_status == 'Completed' else 'Cancelled'
            
        db.session.commit()
        log_activity(g.user.id, "Cancel Shipment", f"Cancelled shipment {shipment.tracking_number}", request.remote_addr)
        create_notification(g.user.id, "Shipment Cancelled", f"Shipment {shipment.tracking_number} was cancelled.", "warning")
        
        flash("Shipment cancelled successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Failed to cancel shipment.", "danger")
        
    return redirect(url_for('customer.dashboard'))


# --- FEEDBACK ---
@customer_bp.route('/feedback/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('Customer')
def submit_feedback(id):
    customer = Customer.query.filter_by(user_id=g.user.id).first()
    shipment = Shipment.query.filter_by(id=id, customer_id=customer.id).first()
    
    if not shipment:
        flash("Shipment not found.", "danger")
        return redirect(url_for('customer.dashboard'))
        
    if shipment.status not in ['Delivered', 'Completed']:
        flash("Feedback can only be submitted for completed deliveries.", "warning")
        return redirect(url_for('customer.dashboard'))
        
    # Check if feedback already submitted
    existing = Feedback.query.filter_by(shipment_id=shipment.id).first()
    if existing:
        flash("Feedback already submitted for this shipment.", "info")
        return redirect(url_for('customer.dashboard'))
        
    if request.method == 'POST':
        rating = int(request.form.get('rating', 5))
        comment = request.form.get('comment')
        
        try:
            feed = Feedback(shipment_id=shipment.id, customer_id=customer.id, rating=rating, comment=comment)
            db.session.add(feed)
            
            # Reward loyalty points
            customer.loyalty_points += 10
            
            # Recalculate Driver rating
            if shipment.driver:
                driver_profile = shipment.driver
                # Calculate average ratings
                avg_rating = db.session.query(func.avg(Feedback.rating)).join(Shipment).filter(Shipment.driver_id == driver_profile.id).scalar()
                if avg_rating:
                    driver_profile.rating = round(float(avg_rating), 1)
                    
            db.session.commit()
            log_activity(g.user.id, "Submit Feedback", f"Feedback submitted for shipment {shipment.tracking_number}", request.remote_addr)
            flash("Thank you for your feedback!", "success")
            return redirect(url_for('customer.dashboard'))
        except Exception as e:
            db.session.rollback()
            flash("Failed to submit feedback.", "danger")
            
    return render_template('customer/feedback_form.html', shipment=shipment)
