import os
import base64
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, g, current_app
from werkzeug.utils import secure_filename
from app.models import (
    db, Driver, Shipment, ShipmentHistory, TrackingLog, Vehicle,
    ContainerTransfer, User, Branch, Payment, Invoice
)
from app.utils import login_required, role_required, log_activity, create_notification
from . import driver_bp

@driver_bp.route('/dashboard')
@login_required
@role_required('Driver')
def dashboard():
    driver = Driver.query.filter_by(user_id=g.user.id).first()
    if not driver:
        flash("Driver profile not found.", "danger")
        return redirect(url_for('auth.logout'))
        
    # Active Container Runs (Linehaul batch transfers)
    container_runs = ContainerTransfer.query.filter(
        ContainerTransfer.driver_id == driver.id,
        ContainerTransfer.status.notin_(['Completed', 'Cancelled'])
    ).all()
    
    # Active Individual Shipments (e.g. Local pickup or last-mile deliveries)
    # Exclude shipments that are part of an active container run
    active_container_shipment_ids = set()
    for c in container_runs:
        for s in c.shipments:
            active_container_shipment_ids.add(s.id)

    assigned_shipments = Shipment.query.filter(
        Shipment.driver_id == driver.id,
        Shipment.status.notin_(['Completed', 'Delivered', 'Cancelled', 'Returned', 'Failed Delivery'])
    ).all()
    assigned_individual_shipments = [s for s in assigned_shipments if s.id not in active_container_shipment_ids]
    
    completed_today = Shipment.query.filter(
        Shipment.driver_id == driver.id,
        Shipment.status.in_(['Completed', 'Delivered']),
        db.func.date(Shipment.updated_at) == datetime.utcnow().date()
    ).count()
    
    total_completed = Shipment.query.filter(
        Shipment.driver_id == driver.id,
        Shipment.status.in_(['Completed', 'Delivered'])
    ).count()

    # Cash In-Hand with Driver (Persists across statuses until manager deposits it)
    from app.models import Payment
    driver_cash_payments = Payment.query.join(Shipment).filter(
        (Payment.collected_by_driver_id == driver.id) | 
        ((Payment.collected_by_driver_id == None) & (Shipment.driver_id == driver.id)),
        Payment.cash_status.in_(['In Hand with Driver', 'Submitted to Manager'])
    ).order_by(Payment.created_at.desc()).all()
    total_cash_in_hand = sum(p.cash_collected_amount for p in driver_cash_payments if p.cash_status == 'In Hand with Driver')

    return render_template(
        'driver/dashboard.html',
        driver=driver,
        container_runs=container_runs,
        assigned_shipments=assigned_individual_shipments,
        completed_today=completed_today,
        total_completed=total_completed,
        driver_cash_payments=driver_cash_payments,
        total_cash_in_hand=total_cash_in_hand
    )

# ---------------------------------------------------------
# DRIVER CONTAINER MANAGEMENT
# ---------------------------------------------------------

@driver_bp.route('/container/<int:container_id>')
@login_required
@role_required('Driver')
def container_detail(container_id):
    driver = Driver.query.filter_by(user_id=g.user.id).first()
    container = db.session.get(ContainerTransfer, container_id)
    if not container or container.driver_id != driver.id:
        flash("Container assignment not found or unauthorized.", "danger")
        return redirect(url_for('driver.dashboard'))
        
    return render_template(
        'driver/container_detail.html',
        driver=driver,
        container=container
    )

@driver_bp.route('/container/<int:container_id>/<action>', methods=['GET', 'POST'])
@login_required
@role_required('Driver')
def container_action(container_id, action):
    driver = Driver.query.filter_by(user_id=g.user.id).first()
    container = db.session.get(ContainerTransfer, container_id)
    if not container or container.driver_id != driver.id:
        flash("Container assignment not found or unauthorized.", "danger")
        return redirect(url_for('driver.dashboard'))

    try:
        if action == 'accept':
            container.status = 'Accepted'
            container.is_locked = True
            container.accepted_at = datetime.utcnow()
            driver.status = 'Accepted'
            
            for sh in container.shipments:
                sh.status = 'Transfer Accepted'
                hist = ShipmentHistory(shipment_id=sh.id, status='Transfer Accepted', notes=f"Driver {driver.user.username} accepted Container {container.transfer_code} transfer", updated_by_id=g.user.id)
                db.session.add(hist)
                t_log = TrackingLog(shipment_id=sh.id, current_location=container.from_branch.city, status='Transfer Accepted', description=f"Container {container.transfer_code} assignment accepted by driver {driver.user.username}")
                db.session.add(t_log)
                
            db.session.commit()
            log_activity(g.user.id, "Accept Container", f"Driver accepted container {container.transfer_code}", request.remote_addr)
            flash(f"Container {container.transfer_code} accepted! Container is now locked for transfer.", "success")

        elif action == 'reject':
            container.status = 'Preparing'
            container.is_locked = False
            container.driver_id = None
            container.vehicle_id = None
            driver.status = 'Available'
            if driver.vehicle:
                driver.vehicle.availability = 'Available'
                
            for sh in container.shipments:
                sh.driver_id = None
                sh.status = 'Warehouse'
                hist = ShipmentHistory(shipment_id=sh.id, status='Warehouse', notes=f"Driver {driver.user.username} rejected container assignment", updated_by_id=g.user.id)
                db.session.add(hist)
                
            db.session.commit()
            log_activity(g.user.id, "Reject Container", f"Driver rejected container {container.transfer_code}", request.remote_addr)
            flash(f"Container {container.transfer_code} rejected.", "warning")
            return redirect(url_for('driver.dashboard'))

        elif action == 'receive_cargo':
            container.status = 'Received Shipment'
            container.received_at = datetime.utcnow()
            driver.status = 'Loading'
            
            for sh in container.shipments:
                sh.status = 'Shipment Received by Container Driver'
                hist = ShipmentHistory(shipment_id=sh.id, status='Shipment Received by Container Driver', notes=f"Cargo loaded into Container {container.transfer_code}", updated_by_id=g.user.id)
                db.session.add(hist)
                t_log = TrackingLog(shipment_id=sh.id, current_location=container.from_branch.city, status='Shipment Received by Container Driver', description=f"All items loaded into Container {container.transfer_code}")
                db.session.add(t_log)
                
            db.session.commit()
            log_activity(g.user.id, "Receive Container Cargo", f"Loaded cargo into container {container.transfer_code}", request.remote_addr)
            flash(f"Cargo confirmed loaded into Container {container.transfer_code}.", "success")

        elif action == 'start_transfer':
            container.status = 'In Transit'
            container.departed_at = datetime.utcnow()
            driver.status = 'In Transit'
            
            for sh in container.shipments:
                sh.status = 'In Transit'
                hist = ShipmentHistory(shipment_id=sh.id, status='In Transit', notes=f"Container {container.transfer_code} departed from {container.from_branch.name} towards {container.to_branch.name}", updated_by_id=g.user.id)
                db.session.add(hist)
                t_log = TrackingLog(shipment_id=sh.id, current_location=container.from_branch.city, status='In Transit', description=f"In transit inside Container {container.transfer_code} towards {container.to_branch.city}")
                db.session.add(t_log)
                
            db.session.commit()
            log_activity(g.user.id, "Start Container Transfer", f"Departed with container {container.transfer_code}", request.remote_addr)
            flash(f"Container {container.transfer_code} is now In Transit towards {container.to_branch.city}.", "success")

        elif action == 'arrive_at_branch':
            container.status = 'Arrived at Branch'
            container.arrived_at = datetime.utcnow()
            driver.status = 'Available'
            if driver.vehicle:
                driver.vehicle.availability = 'Available'
                
            for sh in container.shipments:
                sh.status = 'Arrived at Branch'
                hist = ShipmentHistory(shipment_id=sh.id, status='Arrived at Branch', notes=f"Container {container.transfer_code} reached {container.to_branch.name}", updated_by_id=g.user.id)
                db.session.add(hist)
                t_log = TrackingLog(shipment_id=sh.id, current_location=container.to_branch.city, status='Arrived at Branch', description=f"Container {container.transfer_code} arrived at {container.to_branch.name} terminal")
                db.session.add(t_log)
                
            # Notify destination branch manager users
            dest_managers = User.query.filter(User.role.has(name='Branch Manager'), User.branch_id == container.to_branch_id).all()
            for mgr in dest_managers:
                create_notification(
                    mgr.id,
                    "Incoming Container Arrived",
                    f"Container {container.transfer_code} ({container.total_orders} orders) from {container.from_branch.city} has arrived at your terminal.",
                    "warning"
                )
                
            db.session.commit()
            log_activity(g.user.id, "Container Arrived at Branch", f"Arrived at destination branch with container {container.transfer_code}", request.remote_addr)
            flash(f"Container {container.transfer_code} marked arrived at {container.to_branch.name}. Destination manager has been alerted.", "success")
            
    except Exception as e:
        db.session.rollback()
        flash("Failed to process container action.", "danger")

    return redirect(url_for('driver.container_detail', container_id=container.id))

# Single-order driver workflow (for local pickup and last-mile delivery)
@driver_bp.route('/assignment/<int:id>/<action>')
@login_required
@role_required('Driver')
def handle_assignment(id, action):
    driver = Driver.query.filter_by(user_id=g.user.id).first()
    shipment = Shipment.query.filter_by(id=id, driver_id=driver.id).first()
    
    if not shipment:
        flash("Assigned shipment not found.", "danger")
        return redirect(url_for('driver.dashboard'))
        
    if action == 'accept':
        shipment.status = 'Confirmed'
        msg = "Driver accepted the assignment."
        flash("Assignment accepted! Prepare for pickup/delivery.", "success")
    elif action == 'reject':
        shipment.driver_id = None
        shipment.status = 'Warehouse'
        msg = f"Driver {g.user.username} rejected the assignment."
        driver.status = 'Available'
        flash("Assignment rejected.", "warning")
    else:
        flash("Invalid action.", "danger")
        return redirect(url_for('driver.dashboard'))
        
    try:
        hist = ShipmentHistory(shipment_id=shipment.id, status=shipment.status, notes=msg, updated_by_id=g.user.id)
        db.session.add(hist)
        t_log = TrackingLog(shipment_id=shipment.id, current_location="Branch Hub", status=shipment.status, description=msg)
        db.session.add(t_log)
        db.session.commit()
        log_activity(g.user.id, f"Driver {action.capitalize()}", f"Shipment {shipment.tracking_number} assignment {action}ed", request.remote_addr)
    except Exception as e:
        db.session.rollback()
        flash("Failed to update assignment.", "danger")
        
    return redirect(url_for('driver.dashboard'))

def get_allowed_driver_statuses(shipment):
    """
    Determines valid status transitions based on transit leg:
    1. Pickup Leg: Picked Up -> Warehouse (Origin Warehouse)
    2. Highway/Intermediate Leg: In Transit -> Arrived at Branch / Warehouse
    3. Last-Mile Delivery Leg: Out For Delivery -> Delivered (with POD photo + signature)
    """
    has_reached_warehouse = any(h.status in ['Warehouse', 'In Transit', 'Arrived at Branch', 'Received Shipment'] for h in shipment.history) or shipment.status in ['Warehouse', 'In Transit', 'Out For Delivery', 'Delivered', 'Completed']
    
    current_branch_city = shipment.branch.city.strip().lower() if shipment.branch else ""
    dest_city = shipment.receiver_city.strip().lower() if shipment.receiver_city else ""
    is_final_branch = (current_branch_city == dest_city) or (shipment.next_branch_id is None and has_reached_warehouse)

    # Leg 3: Final Delivery Leg (Out for Delivery or Delivered or at destination branch after reaching warehouse)
    if shipment.status in ['Out For Delivery', 'Delivered'] or (is_final_branch and has_reached_warehouse and shipment.status != 'Picked Up'):
        if shipment.status == 'Out For Delivery':
            return ['Delivered', 'Failed Delivery'], False, True
        return ['Out For Delivery', 'Delivered', 'Failed Delivery'], False, True

    # Leg 1: Pickup Leg (Has not reached warehouse yet, or currently in Picked Up / Booking status)
    elif not has_reached_warehouse or shipment.status in ['Picked Up', 'Booked', 'Confirmed', 'Branch Assigned']:
        if shipment.status == 'Picked Up':
            return ['Warehouse'], False, False
        return ['Picked Up', 'Warehouse'], False, False

    # Leg 2: Intermediate Highway Leg
    else:
        if shipment.status == 'In Transit':
            return ['Arrived at Branch', 'Warehouse'], True, False
        return ['In Transit', 'Arrived at Branch', 'Warehouse'], True, False

@driver_bp.route('/delivery/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('Driver')
def delivery_detail(id):
    driver = Driver.query.filter_by(user_id=g.user.id).first()
    shipment = Shipment.query.filter_by(id=id, driver_id=driver.id).first()
    
    if not shipment:
        flash("Shipment not found or already completed/returned to warehouse.", "info")
        return redirect(url_for('driver.dashboard'))
        
    if request.method == 'POST':
        new_status = request.form.get('status')
        notes = request.form.get('notes')
        current_loc = request.form.get('location', 'In Transit')
        
        allowed_statuses, is_container_leg, is_last_mile_leg = get_allowed_driver_statuses(shipment)
        if new_status not in allowed_statuses:
            flash("Invalid status transition for this transit leg.", "warning")
            return redirect(url_for('driver.delivery_detail', id=id))
            
        try:
            sig_path = None
            signature_data = request.form.get('signature_data') or request.form.get('pickup_signature_data')
            if signature_data:
                if ',' in signature_data:
                    signature_data = signature_data.split(',')[1]
                img_bytes = base64.b64decode(signature_data)
                sig_filename = f"sig_{shipment.tracking_number}.png"
                sig_filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], 'signatures', sig_filename)
                with open(sig_filepath, 'wb') as f:
                    f.write(img_bytes)
                sig_path = f"uploads/signatures/{sig_filename}"
                shipment.signature_path = sig_path

            if new_status == 'Picked Up':
                from app.utils import calculate_shipping_cost, get_gst_rate_by_category, create_invoice_pdf
                
                actual_weight_val = request.form.get('actual_weight')
                if actual_weight_val:
                    actual_weight = float(actual_weight_val)
                elif shipment.weigh_at_pickup:
                    actual_weight = float(request.form.get('actual_weight', 1.0))
                else:
                    actual_weight = shipment.package_weight

                if actual_weight > 0:
                    shipment.package_weight = actual_weight
                    final_cost = calculate_shipping_cost(
                        actual_weight, shipment.delivery_type, 
                        shipment.fragile, shipment.insurance, 
                        shipment.package_category,
                        shipment.declared_value
                    )
                    shipment.shipping_cost = final_cost

                advance_paid = shipment.advance_paid or 0.0
                balance_due = max(0.0, round(shipment.shipping_cost - advance_paid, 2))
                balance_collected = request.form.get('balance_collected') == 'on' or (balance_due == 0.0)
                pickup_payment_method = request.form.get('pickup_payment_method', 'Cash')
                digital_ref = request.form.get('digital_ref', '').strip()

                if balance_collected:
                    if not shipment.payment:
                        shipment.payment = Payment(
                            shipment_id=shipment.id,
                            amount=shipment.shipping_cost,
                            payment_method='Simulated Online',
                            payment_status='Completed'
                        )
                        db.session.add(shipment.payment)

                    shipment.payment.amount = shipment.shipping_cost
                    shipment.payment.payment_status = 'Completed'
                    shipment.payment.collected_by_driver_id = driver.id

                    if balance_due > 0:
                        shipment.payment.payment_method = f"Online Advance (₹{advance_paid:.0f}) + {pickup_payment_method} (₹{balance_due:.0f})"
                        if pickup_payment_method == 'Cash':
                            shipment.payment.cash_status = 'In Hand with Driver'
                            shipment.payment.cash_collected_amount = balance_due
                        else:
                            shipment.payment.cash_status = 'N/A'
                            shipment.payment.cash_collected_amount = 0.0
                            default_prefix = "POS-CARD" if pickup_payment_method == 'Online Card' else "UPI-DIRECT"
                            shipment.payment.digital_reference = digital_ref or f"{default_prefix}-{shipment.tracking_number}"
                    else:
                        shipment.payment.payment_method = 'Simulated Online'
                        shipment.payment.cash_status = 'N/A'
                        shipment.payment.cash_collected_amount = 0.0

                    notes = notes or f"Shipment successfully picked up from sender. Weighed: {shipment.package_weight} kg. Total Rate: ₹{shipment.shipping_cost:.2f}, Advance Paid Online: ₹{advance_paid:.2f}, Balance Collected: ₹{balance_due:.2f} via {pickup_payment_method}."
                else:
                    notes = notes or f"Shipment successfully picked up from sender. Weighed: {shipment.package_weight} kg. Total Rate: ₹{shipment.shipping_cost:.2f}, Advance Paid Online: ₹{advance_paid:.2f}, Balance Pending: ₹{balance_due:.2f}."

                if sig_path:
                    notes += f" | Pickup Signature captured"

                shipment.status = 'Picked Up'

                from app.models import Invoice
                gst_rate = get_gst_rate_by_category(shipment.package_category)
                subtotal = round(shipment.shipping_cost / (1 + (gst_rate / 100)), 2)
                tax = round(shipment.shipping_cost - subtotal, 2)
                inv = Invoice.query.filter_by(shipment_id=shipment.id).first()
                if inv:
                    inv.subtotal = subtotal
                    inv.tax_amount = tax
                    inv.total_amount = shipment.shipping_cost
                else:
                    inv = Invoice(
                        shipment_id=shipment.id,
                        invoice_number=f"INV-{datetime.now().strftime('%Y%m')}-{shipment.id:04d}",
                        subtotal=subtotal,
                        tax_amount=tax,
                        total_amount=shipment.shipping_cost
                    )
                    db.session.add(inv)
                db.session.commit()
                create_invoice_pdf(shipment)

            elif new_status == 'Warehouse':
                shipment.status = 'Warehouse'
                notes = notes or f"Shipment safely arrived and stored at {current_loc} warehouse inventory."
                driver.status = 'Available'
                if driver.vehicle:
                    driver.vehicle.availability = 'Available'
                shipment.driver_id = None # Releases driver so run completes and leaves driver dashboard

            elif new_status == 'Arrived at Branch':
                shipment.status = 'Arrived at Branch'
                notes = notes or f"Shipment arrived at destination terminal: {current_loc}"
                driver.status = 'Available'
                if driver.vehicle:
                    driver.vehicle.availability = 'Available'
                shipment.driver_id = None

            elif new_status == 'Delivered':
                # Proof of Delivery Validation: Both photo and signature are mandatory
                proof_file = request.files.get('proof_image')
                proof_image_data = request.form.get('proof_image_data')
                
                proof_path = None
                if proof_file and proof_file.filename != '':
                    filename = secure_filename(f"proof_{shipment.tracking_number}_{secure_filename(proof_file.filename)}")
                    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], 'proofs', filename)
                    proof_file.save(filepath)
                    proof_path = f"uploads/proofs/{filename}"
                elif proof_image_data:
                    if ',' in proof_image_data:
                        proof_image_data = proof_image_data.split(',')[1]
                    img_bytes = base64.b64decode(proof_image_data)
                    proof_filename = f"proof_{shipment.tracking_number}.png"
                    proof_filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], 'proofs', proof_filename)
                    with open(proof_filepath, 'wb') as f:
                        f.write(img_bytes)
                    proof_path = f"uploads/proofs/{proof_filename}"

                if not proof_path and shipment.proof_image_path:
                    proof_path = shipment.proof_image_path

                if not proof_path:
                    flash("Proof of Delivery photo is required to mark shipment as Delivered.", "danger")
                    return redirect(url_for('driver.delivery_detail', id=id))

                if not sig_path and not shipment.delivery_signature_path and not shipment.signature_path:
                    flash("Receiver Electronic Signature is required to mark shipment as Delivered.", "danger")
                    return redirect(url_for('driver.delivery_detail', id=id))

                shipment.proof_image_path = proof_path
                if sig_path:
                    shipment.delivery_signature_path = sig_path
                    shipment.signature_path = sig_path

                delivered_time = datetime.utcnow()
                shipment.delivered_at = delivered_time
                shipment.status = 'Delivered'
                
                if shipment.payment and shipment.payment.payment_method == 'Cash on Delivery':
                    shipment.payment.payment_status = 'Completed'
                    
                driver.status = 'Available'
                if driver.vehicle:
                    driver.vehicle.availability = 'Available'

                # Record Detailed POD Timeline Milestones
                hist_proof = ShipmentHistory(
                    shipment_id=shipment.id,
                    status='Delivery Proof Captured',
                    notes=f"Product delivery photo captured and verified at {current_loc}.",
                    updated_by_id=g.user.id
                )
                hist_sig = ShipmentHistory(
                    shipment_id=shipment.id,
                    status='Receiver Signature Captured',
                    notes=f"Electronic signature confirmed by receiver {shipment.receiver_name}.",
                    updated_by_id=g.user.id
                )
                hist_del = ShipmentHistory(
                    shipment_id=shipment.id,
                    status='Delivered',
                    notes=f"Order successfully delivered to {shipment.receiver_name} by {driver.user.username}.",
                    updated_by_id=g.user.id
                )
                db.session.add_all([hist_proof, hist_sig, hist_del])

                t_log = TrackingLog(
                    shipment_id=shipment.id,
                    current_location=current_loc,
                    status='Delivered',
                    description=f"Delivered to {shipment.receiver_name} at {shipment.receiver_address_line}. Proof of delivery recorded."
                )
                db.session.add(t_log)

                # Manager Alert
                mgr_users = User.query.filter(
                    User.role.has(name='Branch Manager'),
                    (User.branch_id == shipment.branch_id) | (User.branch_id == None)
                ).all()
                delivered_str = delivered_time.strftime('%d %b %Y, %I:%M %p')
                for mgr in mgr_users:
                    create_notification(
                        mgr.id,
                        "🔔 Delivery Completed",
                        f"Order {shipment.tracking_number} for {shipment.receiver_name} was delivered by {driver.user.username} at {delivered_str}.",
                        "success"
                    )

                # Customer Notification
                if shipment.customer_id:
                    create_notification(
                        shipment.customer.user_id,
                        "Shipment Delivered ✓",
                        f"Your package {shipment.tracking_number} was successfully delivered to {shipment.receiver_name} at {delivered_str}.",
                        "success"
                    )

                # Fail-Safe Email Dispatch
                from app.utils import send_delivery_email
                email_sent = send_delivery_email(shipment)
                
                hist_email = ShipmentHistory(
                    shipment_id=shipment.id,
                    status='Sender Notified',
                    notes=f"Delivery confirmation email {'dispatched successfully' if email_sent else 'queued/simulated'} to {shipment.sender_email or 'customer'}.",
                    updated_by_id=g.user.id
                )
                db.session.add(hist_email)

                db.session.commit()
                log_activity(g.user.id, "Confirm Delivery", f"Delivered shipment {shipment.tracking_number} with proof photo & signature", request.remote_addr)
                flash(f"Shipment {shipment.tracking_number} marked as Delivered! Proof of delivery and electronic signature recorded.", "success")
                return redirect(url_for('driver.dashboard'))

            else:
                shipment.status = new_status
                notes = notes or f"Shipment moved to {new_status}"
                
            hist = ShipmentHistory(shipment_id=shipment.id, status=shipment.status, notes=notes, updated_by_id=g.user.id)
            db.session.add(hist)
            t_log = TrackingLog(shipment_id=shipment.id, current_location=current_loc, status=shipment.status, description=notes)
            db.session.add(t_log)
            db.session.commit()
            log_activity(g.user.id, "Update Delivery Status", f"Shipment {shipment.tracking_number} status updated to {shipment.status}", request.remote_addr)
            
            if shipment.customer_id:
                cust_user_id = shipment.customer.user_id
                create_notification(cust_user_id, f"Shipment {shipment.status}", f"Your package {shipment.tracking_number} is now {shipment.status}.", "info")
                
            flash(f"Shipment status updated to: {shipment.status}", "success")
            return redirect(url_for('driver.dashboard'))
        except Exception as e:
            db.session.rollback()
            flash("Failed to update shipment status.", "danger")
            
    from app.utils import get_packaging_rate, get_insurance_fee
    packaging_rate = get_packaging_rate(shipment.package_category)
    insurance_fee = get_insurance_fee(shipment.package_category, shipment.declared_value) if shipment.insurance else 0.0
    advance_paid = shipment.advance_paid or 0.0
    balance_due = max(0.0, round(shipment.shipping_cost - advance_paid, 2))

    allowed_statuses, is_container_leg, is_last_mile_leg = get_allowed_driver_statuses(shipment)
    return render_template(
        'driver/delivery_detail.html',
        shipment=shipment,
        allowed_statuses=allowed_statuses,
        is_container_leg=is_container_leg,
        is_last_mile_leg=is_last_mile_leg,
        packaging_rate=packaging_rate,
        insurance_fee=insurance_fee,
        advance_paid=advance_paid,
        balance_due=balance_due
    )

@driver_bp.route('/history')
@login_required
@role_required('Driver')
def history():
    driver = Driver.query.filter_by(user_id=g.user.id).first()
    if not driver:
        flash("Driver profile not found.", "danger")
        return redirect(url_for('auth.logout'))
        
    # 1. All shipments the driver was assigned to, updated in history, or collected cash for
    history_shipment_ids = db.session.query(ShipmentHistory.shipment_id).filter(
        ShipmentHistory.updated_by_id == g.user.id
    ).distinct()
    
    cash_shipment_ids = db.session.query(Payment.shipment_id).filter(
        Payment.collected_by_driver_id == driver.id
    ).distinct()
    
    assigned_shipment_ids = db.session.query(Shipment.id).filter(
        Shipment.driver_id == driver.id
    )
    
    all_shipment_ids = set([s[0] for s in history_shipment_ids.all()] + 
                           [s[0] for s in cash_shipment_ids.all()] + 
                           [s[0] for s in assigned_shipment_ids.all()])
                           
    shipments = Shipment.query.filter(
        Shipment.id.in_(all_shipment_ids)
    ).order_by(Shipment.updated_at.desc()).all() if all_shipment_ids else []

    # 2. All Container Transfers driven by this driver
    container_transfers = ContainerTransfer.query.filter(
        ContainerTransfer.driver_id == driver.id
    ).order_by(ContainerTransfer.updated_at.desc()).all()

    # 3. Overall Stats
    total_shipments_count = len(shipments)
    total_containers_count = len(container_transfers)
    total_weight_carried = sum(s.package_weight for s in shipments) + sum(c.total_weight for c in container_transfers)
    total_cash_handled = sum(s.payment.cash_collected_amount for s in shipments if s.payment and s.payment.collected_by_driver_id == driver.id)

    return render_template(
        'driver/history.html', 
        driver=driver,
        shipments=shipments, 
        container_transfers=container_transfers,
        total_shipments_count=total_shipments_count,
        total_containers_count=total_containers_count,
        total_weight_carried=round(total_weight_carried, 1),
        total_cash_handled=round(total_cash_handled, 2)
    )

@driver_bp.route('/handover-cash/<int:payment_id>', methods=['POST'])
@login_required
@role_required('Driver')
def handover_cash(payment_id):
    from app.models import Payment
    payment = db.session.get(Payment, payment_id)
    if not payment:
        flash("Payment record not found.", "danger")
        return redirect(url_for('driver.dashboard'))
    
    if payment.cash_status == 'In Hand with Driver':
        payment.cash_status = 'Submitted to Manager'
        db.session.commit()
        log_activity(g.user.id, "Cash Handover Submitted", f"Driver submitted cash of ₹{payment.cash_collected_amount:.2f} to Branch Manager for shipment {payment.shipment.tracking_number}", request.remote_addr)
        flash(f"Submitted ₹{payment.cash_collected_amount:.2f} cash handover request to Branch Manager.", "success")
    
    return redirect(request.referrer or url_for('driver.dashboard'))
