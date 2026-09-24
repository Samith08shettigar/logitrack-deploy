from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, g
from app.models import (
    db, Branch, Driver, Vehicle, Shipment, ShipmentHistory, TrackingLog,
    User, Role, ContainerTransfer
)
from app.utils import login_required, role_required, log_activity, create_notification, sync_branch_driver_availability
from . import branch_bp

# Helper to resolve manager's branch
def get_manager_branch():
    if g.user.branch_id:
        return g.user.branch
    if g.user.username.endswith('_bom'):
        return Branch.query.filter_by(code='BOM01').first()
    elif g.user.username.endswith('_del'):
        return Branch.query.filter_by(code='DEL01').first()
    elif g.user.username.endswith('_blr'):
        return Branch.query.filter_by(code='BLR01').first()
    elif g.user.username.endswith('_mng'):
        return Branch.query.filter_by(code='MNG01').first()
    else:
        # Check by branch code match in username
        for b in Branch.query.all():
            if b.code.lower() in g.user.username.lower() or b.city.lower() in g.user.username.lower():
                return b
        # Fallback to first branch
        return Branch.query.first()

def generate_container_id(from_branch, to_branch):
    from_code = from_branch.code[:3].upper() if from_branch else "HUB"
    to_code = to_branch.code[:3].upper() if to_branch else "DST"
    count = ContainerTransfer.query.count() + 1
    return f"CONT-{from_code}-{to_code}-{count:03d}"

def resolve_next_route_branch(from_branch, dest_city_or_branch=None):
    """
    Resolves next default hub along linehaul route:
    Mumbai (BOM01) -> Mangalore (MNG01) -> Bangalore (BLR01) -> Delhi (DEL01)
    """
    if not from_branch:
        return Branch.query.first()
    
    code = from_branch.code.upper()
    if 'BOM' in code or 'MUMBAI' in from_branch.city.upper():
        return Branch.query.filter(Branch.code.ilike('%MNG%')).first() or Branch.query.filter(Branch.city.ilike('%Mangalore%')).first()
    elif 'MNG' in code or 'MANGALORE' in from_branch.city.upper():
        return Branch.query.filter(Branch.code.ilike('%BLR%')).first() or Branch.query.filter(Branch.city.ilike('%Bangalore%')).first()
    elif 'BLR' in code or 'BANGALORE' in from_branch.city.upper():
        return Branch.query.filter(Branch.code.ilike('%DEL%')).first() or Branch.query.filter(Branch.city.ilike('%Delhi%')).first()
    else:
        # Default to another branch
        return Branch.query.filter(Branch.id != from_branch.id).first()

@branch_bp.route('/dashboard')
@login_required
@role_required('Branch Manager')
def dashboard():
    branch = get_manager_branch()
    if not branch:
        flash("Branch configuration not found. Please seed the database.", "danger")
        return redirect(url_for('auth.logout'))
        
    # KPIs for this branch
    total_local_shipments = Shipment.query.filter_by(branch_id=branch.id).count()
    active_local_shipments = Shipment.query.filter(
        Shipment.branch_id == branch.id,
        Shipment.status.in_(['Branch Assigned', 'Confirmed', 'Driver Assigned', 'Picked Up', 'Warehouse', 'In Transit', 'Out For Delivery', 'Container Driver Assigned'])
    ).all()
    
    pending_assignment = Shipment.query.filter(
        Shipment.branch_id == branch.id,
        Shipment.driver_id == None,
        Shipment.status.in_(['Booked', 'Payment Pending', 'Confirmed', 'Branch Assigned', 'Warehouse'])
    ).count()
    
    # Containers Queues
    preparing_containers = ContainerTransfer.query.filter(
        ContainerTransfer.from_branch_id == branch.id,
        ContainerTransfer.status.in_(['Preparing', 'Driver Assigned'])
    ).order_by(ContainerTransfer.created_at.desc()).all()

    in_transit_containers = ContainerTransfer.query.filter(
        ContainerTransfer.from_branch_id == branch.id,
        ContainerTransfer.status.in_(['Accepted', 'Received Shipment', 'In Transit'])
    ).order_by(ContainerTransfer.created_at.desc()).all()

    incoming_containers = ContainerTransfer.query.filter(
        ContainerTransfer.to_branch_id == branch.id,
        ContainerTransfer.status.in_(['In Transit', 'Arrived at Branch'])
    ).order_by(ContainerTransfer.created_at.desc()).all()
    
    local_drivers = Driver.query.filter_by(branch_id=branch.id).all()
    available_drivers = Driver.query.filter_by(branch_id=branch.id, status='Available').all()
    local_vehicles = Vehicle.query.filter_by(branch_id=branch.id).all()

    # Recent Delivered Shipments (Proof of Delivery)
    recent_delivered = Shipment.query.filter(
        (Shipment.branch_id == branch.id) | (Shipment.receiver_city.ilike(f"%{branch.city}%")),
        Shipment.status.in_(['Delivered', 'Completed'])
    ).order_by(Shipment.delivered_at.desc(), Shipment.updated_at.desc()).limit(10).all()

    # Cash in Hand / Pending Driver Handovers
    from app.models import Payment
    pending_cash_handovers = Payment.query.join(Shipment).filter(
        (Shipment.branch_id == branch.id) | (Shipment.pickup_city.ilike(f"%{branch.city}%")),
        Payment.cash_status.in_(['In Hand with Driver', 'Submitted to Manager'])
    ).order_by(Payment.created_at.desc()).all()
    
    return render_template(
        'branch/dashboard.html',
        branch=branch,
        total_shipments=total_local_shipments,
        active_shipments=active_local_shipments,
        pending_assignment=pending_assignment,
        preparing_containers=preparing_containers,
        in_transit_containers=in_transit_containers,
        incoming_containers=incoming_containers,
        local_drivers=local_drivers,
        available_drivers=available_drivers,
        driver_count=len(local_drivers),
        vehicle_count=len(local_vehicles),
        recent_delivered=recent_delivered,
        pending_cash_handovers=pending_cash_handovers
    )

@branch_bp.route('/acknowledge-cash/<int:payment_id>', methods=['POST'])
@login_required
@role_required('Branch Manager')
def acknowledge_cash(payment_id):
    from app.models import Payment
    payment = db.session.get(Payment, payment_id)
    if not payment:
        flash("Payment record not found.", "danger")
        return redirect(url_for('branch.dashboard'))
    
    if payment.cash_status == 'Submitted to Manager':
        payment.cash_status = 'Deposited with Manager'
        payment.cash_handed_over_at = datetime.utcnow()
        payment.cash_received_by_manager_id = g.user.id
        db.session.commit()
        driver_name = payment.shipment.driver.user.username if payment.shipment.driver else "Driver"
        log_activity(g.user.id, "Cash Deposit Acknowledged", f"Branch Manager accepted ₹{payment.cash_collected_amount:.2f} cash deposit from {driver_name} for shipment {payment.shipment.tracking_number}", request.remote_addr)
        flash(f"Successfully received and acknowledged ₹{payment.cash_collected_amount:.2f} cash deposit from {driver_name}.", "success")
    elif payment.cash_status == 'In Hand with Driver':
        flash("Driver has not submitted this cash collection yet. The driver must click 'Submit to Manager' first.", "warning")
    else:
        flash("Cash deposit has already been processed or is not pending.", "info")
    
    return redirect(request.referrer or url_for('branch.dashboard'))

@branch_bp.route('/shipments')
@login_required
@role_required('Branch Manager')
def local_shipments():
    branch = get_manager_branch()
    shipments = Shipment.query.filter_by(branch_id=branch.id).order_by(Shipment.created_at.desc()).all()
    incoming_containers = ContainerTransfer.query.filter(
        ContainerTransfer.to_branch_id == branch.id,
        ContainerTransfer.status.in_(['In Transit', 'Arrived at Branch'])
    ).order_by(ContainerTransfer.created_at.desc()).all()
    
    open_containers = ContainerTransfer.query.filter(
        ContainerTransfer.from_branch_id == branch.id,
        ContainerTransfer.is_locked == False,
        ContainerTransfer.status.in_(['Preparing', 'Driver Assigned'])
    ).order_by(ContainerTransfer.created_at.desc()).all()

    return render_template(
        'branch/local_shipments.html',
        shipments=shipments,
        incoming_containers=incoming_containers,
        open_containers=open_containers,
        branch=branch
    )

@branch_bp.route('/records')
@login_required
@role_required('Branch Manager')
def branch_records():
    branch = get_manager_branch()
    search_q = request.args.get('q', '').strip()
    active_tab = request.args.get('tab', 'all')

    query = Shipment.query.filter(
        (Shipment.branch_id == branch.id) |
        (Shipment.pickup_city.ilike(f"%{branch.city}%")) |
        (Shipment.receiver_city.ilike(f"%{branch.city}%"))
    )

    if search_q:
        query = query.filter(
            (Shipment.tracking_number.ilike(f"%{search_q}%")) |
            (Shipment.sender_name.ilike(f"%{search_q}%")) |
            (Shipment.receiver_name.ilike(f"%{search_q}%")) |
            (Shipment.receiver_city.ilike(f"%{search_q}%")) |
            (Shipment.pickup_city.ilike(f"%{search_q}%"))
        )

    all_shipments = query.order_by(Shipment.updated_at.desc()).all()

    delivered_records = [
        s for s in all_shipments 
        if s.status in ['Delivered', 'Completed'] and (
            s.receiver_city.strip().lower() == branch.city.strip().lower() or 
            s.branch_id == branch.id or
            (s.delivered_at is not None and s.branch_id == branch.id)
        )
    ]

    received_records = [
        s for s in all_shipments
        if s.branch_id == branch.id or
           s.pickup_city.strip().lower() == branch.city.strip().lower() or
           any('received' in (h.notes or '').lower() or branch.name.lower() in (h.notes or '').lower() for h in s.history)
    ]

    dispatched_records = [
        s for s in all_shipments
        if s.pickup_city.strip().lower() == branch.city.strip().lower() and
           s.receiver_city.strip().lower() != branch.city.strip().lower() and
           s.status not in ['Booked', 'Payment Pending', 'Confirmed', 'Branch Assigned']
    ]

    warehouse_records = [s for s in all_shipments if s.branch_id == branch.id and s.status == 'Warehouse']

    return render_template(
        'branch/records.html',
        branch=branch,
        all_shipments=all_shipments,
        delivered_records=delivered_records,
        received_records=received_records,
        dispatched_records=dispatched_records,
        warehouse_records=warehouse_records,
        search_q=search_q,
        active_tab=active_tab
    )

@branch_bp.route('/shipments/approve/<int:id>')
@login_required
@role_required('Branch Manager')
def approve_shipment(id):
    branch = get_manager_branch()
    shipment = Shipment.query.filter_by(id=id, branch_id=branch.id).first()
    
    if not shipment:
        shipment = Shipment.query.filter_by(id=id, branch_id=None).first()
        if shipment:
            shipment.branch_id = branch.id
        else:
            flash("Shipment not found.", "danger")
            return redirect(url_for('branch.local_shipments'))
            
    try:
        shipment.status = 'Confirmed'
        
        hist = ShipmentHistory(shipment_id=shipment.id, status='Confirmed', notes=f"Approved by Branch Manager at {branch.name}", updated_by_id=g.user.id)
        db.session.add(hist)
        
        t_log = TrackingLog(shipment_id=shipment.id, current_location=branch.city, status='Confirmed', description=f"Shipment approved at branch hub: {branch.name}")
        db.session.add(t_log)
        
        if shipment.payment and shipment.payment.payment_method == 'Cash on Delivery':
            shipment.payment.payment_status = 'Pending'
            
        db.session.commit()
        log_activity(g.user.id, "Approve Shipment", f"Approved shipment {shipment.tracking_number} at branch {branch.code}", request.remote_addr)
        flash(f"Shipment {shipment.tracking_number} approved successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Failed to approve shipment.", "danger")
        
    return redirect(url_for('branch.local_shipments'))

# ---------------------------------------------------------
# MULTI-SHIPMENT CONTAINER WORKFLOW ROUTES
# ---------------------------------------------------------

@branch_bp.route('/containers')
@login_required
@role_required('Branch Manager')
def list_containers():
    branch = get_manager_branch()
    
    preparing_containers = ContainerTransfer.query.filter(
        ContainerTransfer.from_branch_id == branch.id,
        ContainerTransfer.status.in_(['Preparing', 'Driver Assigned'])
    ).order_by(ContainerTransfer.created_at.desc()).all()

    in_transit_containers = ContainerTransfer.query.filter(
        ContainerTransfer.from_branch_id == branch.id,
        ContainerTransfer.status.in_(['Accepted', 'Received Shipment', 'In Transit'])
    ).order_by(ContainerTransfer.created_at.desc()).all()

    incoming_containers = ContainerTransfer.query.filter(
        ContainerTransfer.to_branch_id == branch.id,
        ContainerTransfer.status.in_(['In Transit', 'Arrived at Branch'])
    ).order_by(ContainerTransfer.created_at.desc()).all()

    completed_containers = ContainerTransfer.query.filter(
        (ContainerTransfer.from_branch_id == branch.id) | (ContainerTransfer.to_branch_id == branch.id),
        ContainerTransfer.status == 'Completed'
    ).order_by(ContainerTransfer.updated_at.desc()).limit(20).all()

    return render_template(
        'branch/containers.html',
        branch=branch,
        preparing_containers=preparing_containers,
        in_transit_containers=in_transit_containers,
        incoming_containers=incoming_containers,
        completed_containers=completed_containers
    )

@branch_bp.route('/containers/create', methods=['GET', 'POST'])
@login_required
@role_required('Branch Manager')
def create_container():
    branch = get_manager_branch()
    branches = Branch.query.filter(Branch.id != branch.id).all()
    default_next_branch = resolve_next_route_branch(branch)
    
    # Get available shipments in warehouse eligible for container linehaul transfer
    eligible_shipments = Shipment.query.filter(
        Shipment.branch_id == branch.id,
        Shipment.status.in_(['Warehouse', 'Confirmed', 'Branch Assigned']),
        Shipment.driver_id == None
    ).all()
    
    # Filter out shipments already in an active uncompleted container
    ready_shipments = [s for s in eligible_shipments if not s.active_container]

    if request.method == 'POST':
        to_branch_id_str = request.form.get('to_branch_id')
        selected_shipment_ids = request.form.getlist('shipment_ids')
        
        if not to_branch_id_str:
            flash("Please select a destination next branch.", "warning")
            return redirect(url_for('branch.create_container'))
            
        to_branch = db.session.get(Branch, int(to_branch_id_str))
        if not to_branch:
            flash("Invalid destination branch.", "danger")
            return redirect(url_for('branch.create_container'))
            
        transfer_code = generate_container_id(branch, to_branch)
        
        container = ContainerTransfer(
            transfer_code=transfer_code,
            from_branch_id=branch.id,
            to_branch_id=to_branch.id,
            status='Preparing',
            is_locked=False,
            max_orders_capacity=20,
            max_weight_capacity=5000.0
        )
        db.session.add(container)
        db.session.flush()
        
        # Add selected shipments
        added_count = 0
        for s_id_str in selected_shipment_ids:
            if added_count >= container.max_orders_capacity:
                break
            sh = db.session.get(Shipment, int(s_id_str))
            if sh and sh.branch_id == branch.id and not sh.active_container:
                container.shipments.append(sh)
                sh.next_branch_id = to_branch.id
                added_count += 1
                
        db.session.commit()
        log_activity(g.user.id, "Create Container", f"Created container {transfer_code} with {added_count} orders", request.remote_addr)
        flash(f"Container {transfer_code} prepared successfully with {added_count} orders. You can now assign a container driver.", "success")
        return redirect(url_for('branch.container_detail', container_id=container.id))
        
    open_containers = ContainerTransfer.query.filter(
        ContainerTransfer.from_branch_id == branch.id,
        ContainerTransfer.status.in_(['Preparing', 'Driver Assigned']),
        ContainerTransfer.is_locked == False
    ).order_by(ContainerTransfer.created_at.desc()).all()

    return render_template(
        'branch/container_create.html',
        branch=branch,
        branches=branches,
        default_next_branch=default_next_branch,
        ready_shipments=ready_shipments,
        open_containers=open_containers
    )

@branch_bp.route('/containers/<int:container_id>')
@login_required
@role_required('Branch Manager')
def container_detail(container_id):
    branch = get_manager_branch()
    container = db.session.get(ContainerTransfer, container_id)
    if not container:
        flash("Container not found.", "danger")
        return redirect(url_for('branch.list_containers'))
        
    # Check permissions
    if container.from_branch_id != branch.id and container.to_branch_id != branch.id:
        flash("Unauthorized to view this container.", "danger")
        return redirect(url_for('branch.list_containers'))

    # Available shipments in current branch eligible to be added (only if preparing/assigned & unlocked)
    available_shipments = []
    if container.status in ['Preparing', 'Driver Assigned'] and not container.is_locked and container.from_branch_id == branch.id:
        candidates = Shipment.query.filter(
            (Shipment.branch_id == branch.id) | (Shipment.pickup_city.ilike(f"%{branch.city}%")),
            Shipment.status.in_(['Warehouse', 'Confirmed', 'Branch Assigned']),
            Shipment.driver_id == None
        ).all()
        # Exclude shipments already in active containers
        available_shipments = [s for s in candidates if not s.active_container and s not in container.shipments]

    # Ensure driver availability statuses are accurately synchronized
    sync_branch_driver_availability(branch.id)

    # Available container drivers at this branch
    available_drivers = Driver.query.filter_by(branch_id=branch.id, status='Available').all()
    # Include currently assigned driver so they are selectable and marked assigned
    if container.driver and container.driver not in available_drivers:
        available_drivers.append(container.driver)

    # Sort drivers so currently assigned and Truck drivers appear first, but all branch drivers are selectable
    available_truck_drivers = sorted(
        available_drivers,
        key=lambda d: (
            0 if container.driver_id == d.id else (
                1 if d.vehicle and d.vehicle.vehicle_type in ['Truck', 'Container', 'Heavy Truck'] else 2
            ),
            d.user.username
        )
    )

    return render_template(
        'branch/container_detail.html',
        branch=branch,
        container=container,
        available_shipments=available_shipments,
        available_truck_drivers=available_truck_drivers
    )

@branch_bp.route('/shipments/<int:shipment_id>/add-to-container/<int:container_id>', methods=['POST'])
@login_required
@role_required('Branch Manager')
def direct_add_shipment_to_container(shipment_id, container_id):
    branch = get_manager_branch()
    container = db.session.get(ContainerTransfer, container_id)
    if not container or container.from_branch_id != branch.id:
        flash("Container not found or unauthorized.", "danger")
        return redirect(request.referrer or url_for('branch.local_shipments'))
        
    if container.is_locked or container.status not in ['Preparing', 'Driver Assigned']:
        flash("Container is locked or in transit. Cannot modify contents.", "warning")
        return redirect(request.referrer or url_for('branch.local_shipments'))

    if container.is_full:
        flash(f"Container {container.transfer_code} is full (Max {container.max_orders_capacity} orders).", "warning")
        return redirect(request.referrer or url_for('branch.local_shipments'))

    sh = db.session.get(Shipment, shipment_id)
    if not sh or (sh.branch_id != branch.id and branch.city.lower() not in (sh.pickup_city or '').lower()):
        flash("Shipment not found or unauthorized.", "danger")
        return redirect(request.referrer or url_for('branch.local_shipments'))

    if sh.active_container:
        flash(f"Shipment {sh.tracking_number} is already in container {sh.active_container.transfer_code}.", "info")
        return redirect(request.referrer or url_for('branch.local_shipments'))

    container.shipments.append(sh)
    sh.next_branch_id = container.to_branch_id
    db.session.commit()
    log_activity(g.user.id, "Add Order to Container", f"Added order {sh.tracking_number} to container {container.transfer_code}", request.remote_addr)
    flash(f"Order {sh.tracking_number} successfully added to Container {container.transfer_code}.", "success")
    return redirect(url_for('branch.container_detail', container_id=container.id))

@branch_bp.route('/containers/<int:container_id>/add-shipments', methods=['POST'])
@login_required
@role_required('Branch Manager')
def add_shipments_to_container(container_id):
    branch = get_manager_branch()
    container = db.session.get(ContainerTransfer, container_id)
    if not container or container.from_branch_id != branch.id:
        flash("Container not found or unauthorized.", "danger")
        return redirect(url_for('branch.list_containers'))
        
    if container.is_locked or container.status not in ['Preparing', 'Driver Assigned']:
        flash("Container is locked or in transit. Cannot modify contents.", "warning")
        return redirect(url_for('branch.container_detail', container_id=container.id))

    selected_ids = request.form.getlist('shipment_ids')
    if not selected_ids:
        flash("No orders selected to add.", "warning")
        return redirect(url_for('branch.container_detail', container_id=container.id))
        
    added = 0
    for s_id_str in selected_ids:
        if container.is_full:
            flash("Container capacity limit reached (Max 20 orders).", "warning")
            break
        sh = db.session.get(Shipment, int(s_id_str))
        if sh and sh.branch_id == branch.id and not sh.active_container and sh not in container.shipments:
            container.shipments.append(sh)
            sh.next_branch_id = container.to_branch_id
            added += 1
            
    db.session.commit()
    log_activity(g.user.id, "Add Orders to Container", f"Added {added} orders to container {container.transfer_code}", request.remote_addr)
    flash(f"Added {added} order(s) to Container {container.transfer_code}.", "success")
    return redirect(url_for('branch.container_detail', container_id=container.id))

@branch_bp.route('/containers/<int:container_id>/remove-shipment/<int:shipment_id>', methods=['POST'])
@login_required
@role_required('Branch Manager')
def remove_shipment_from_container(container_id, shipment_id):
    branch = get_manager_branch()
    container = db.session.get(ContainerTransfer, container_id)
    if not container or container.from_branch_id != branch.id:
        flash("Container not found or unauthorized.", "danger")
        return redirect(url_for('branch.list_containers'))
        
    if container.is_locked or container.status not in ['Preparing', 'Driver Assigned']:
        flash("Container is locked or in transit. Cannot remove orders.", "warning")
        return redirect(url_for('branch.container_detail', container_id=container.id))

    sh = db.session.get(Shipment, shipment_id)
    if sh and sh in container.shipments:
        container.shipments.remove(sh)
        db.session.commit()
        log_activity(g.user.id, "Remove Order from Container", f"Removed order {sh.tracking_number} from container {container.transfer_code}", request.remote_addr)
        flash(f"Order {sh.tracking_number} removed from Container {container.transfer_code}.", "info")
        
    return redirect(url_for('branch.container_detail', container_id=container.id))

@branch_bp.route('/containers/<int:container_id>/delete', methods=['GET', 'POST'])
@login_required
@role_required('Branch Manager')
def delete_container(container_id):
    branch = get_manager_branch()
    container = db.session.get(ContainerTransfer, container_id)
    if not container or container.from_branch_id != branch.id:
        flash("Container not found or unauthorized.", "danger")
        return redirect(request.referrer or url_for('branch.list_containers'))
        
    if container.is_locked or container.status not in ['Preparing', 'Driver Assigned']:
        flash("Cannot delete container while locked or in active transit.", "warning")
        return redirect(url_for('branch.container_detail', container_id=container.id))

    code = container.transfer_code
    
    # 1. Release all shipments inside container back to warehouse
    for sh in list(container.shipments):
        sh.driver_id = None
        sh.status = 'Warehouse'
        sh.next_branch_id = None
    container.shipments.clear()
    
    # 2. Release driver if assigned
    if container.driver:
        container.driver.status = 'Available'
        if container.driver.vehicle:
            container.driver.vehicle.availability = 'Available'
            
    # 3. Delete container record
    db.session.delete(container)
    db.session.commit()
    
    log_activity(g.user.id, "Delete Container", f"Deleted container {code} and released orders back to warehouse", request.remote_addr)
    flash(f"Container {code} was deleted successfully. Any loaded shipments have been returned to warehouse inventory.", "success")
    return redirect(request.referrer or url_for('branch.list_containers'))

@branch_bp.route('/containers/<int:container_id>/assign-driver', methods=['POST'])
@login_required
@role_required('Branch Manager')
def assign_container_driver(container_id):
    branch = get_manager_branch()
    container = db.session.get(ContainerTransfer, container_id)
    if not container or container.from_branch_id != branch.id:
        flash("Container not found or unauthorized.", "danger")
        return redirect(url_for('branch.list_containers'))

    if container.is_locked:
        flash("Container is already locked for transfer.", "warning")
        return redirect(url_for('branch.container_detail', container_id=container.id))

    if container.total_orders == 0:
        flash("Cannot assign driver to an empty container. Add at least one order.", "warning")
        return redirect(url_for('branch.container_detail', container_id=container.id))

    driver_id_str = request.form.get('driver_id')
    if not driver_id_str:
        flash("Please select a container driver.", "warning")
        return redirect(url_for('branch.container_detail', container_id=container.id))

    sync_branch_driver_availability(branch.id)

    driver = db.session.get(Driver, int(driver_id_str))
    if not driver or driver.branch_id != branch.id:
        flash("Selected driver does not belong to this branch.", "danger")
        return redirect(url_for('branch.container_detail', container_id=container.id))

    # If driver is already assigned to this container, do nothing
    if container.driver_id == driver.id and container.status == 'Driver Assigned':
        flash(f"Driver {driver.user.username} is already assigned to this container.", "info")
        return redirect(url_for('branch.container_detail', container_id=container.id))

    # If another driver was previously assigned, release them
    if container.driver and container.driver_id != driver.id:
        old_driver = container.driver
        old_driver.status = 'Available'
        if old_driver.vehicle:
            old_driver.vehicle.availability = 'Available'

    # Assign new driver to container
    container.driver_id = driver.id
    if driver.vehicle:
        container.vehicle_id = driver.vehicle.id
        driver.vehicle.availability = 'Busy'
    driver.status = 'Busy'
    
    container.status = 'Driver Assigned'
    container.assigned_at = datetime.utcnow()
    
    # Update status on all individual shipments inside container
    for sh in container.shipments:
        sh.driver_id = driver.id
        sh.status = 'Container Driver Assigned'
        sh.next_branch_id = container.to_branch_id
        
        hist = ShipmentHistory(
            shipment_id=sh.id,
            status='Container Driver Assigned',
            notes=f"Assigned to Container {container.transfer_code} with Driver {driver.user.username}",
            updated_by_id=g.user.id
        )
        db.session.add(hist)
        
        t_log = TrackingLog(
            shipment_id=sh.id,
            current_location=branch.city,
            status='Container Driver Assigned',
            description=f"Loaded into Container Unit {container.transfer_code}. Driver assigned: {driver.user.username}"
        )
        db.session.add(t_log)

    db.session.commit()
    
    # Notifications
    create_notification(
        driver.user_id,
        "New Container Assignment",
        f"You have been assigned Container {container.transfer_code} ({container.total_orders} orders) bound for {container.to_branch.city}.",
        "info"
    )
    
    log_activity(g.user.id, "Assign Container Driver", f"Assigned driver {driver.user.username} to container {container.transfer_code}", request.remote_addr)
    flash(f"Driver {driver.user.username} assigned to Container {container.transfer_code}. Waiting for driver acceptance.", "success")
    return redirect(url_for('branch.container_detail', container_id=container.id))

@branch_bp.route('/containers/<int:container_id>/unassign-driver', methods=['POST'])
@login_required
@role_required('Branch Manager')
def unassign_container_driver(container_id):
    branch = get_manager_branch()
    container = db.session.get(ContainerTransfer, container_id)
    if not container or container.from_branch_id != branch.id:
        flash("Container not found or unauthorized.", "danger")
        return redirect(url_for('branch.list_containers'))

    if container.is_locked:
        flash("Cannot unassign driver while container is locked in transit.", "warning")
        return redirect(url_for('branch.container_detail', container_id=container.id))

    if container.driver:
        old_driver = container.driver
        old_driver.status = 'Available'
        if old_driver.vehicle:
            old_driver.vehicle.availability = 'Available'

    container.driver_id = None
    container.vehicle_id = None
    container.status = 'Preparing'
    container.assigned_at = None

    for sh in container.shipments:
        sh.driver_id = None
        sh.status = 'Warehouse'

    db.session.commit()
    sync_branch_driver_availability(branch.id)

    log_activity(g.user.id, "Unassign Container Driver", f"Unassigned driver from container {container.transfer_code}", request.remote_addr)
    flash(f"Driver unassigned from Container {container.transfer_code}. Container status reset to Preparing.", "info")
    return redirect(url_for('branch.container_detail', container_id=container.id))

@branch_bp.route('/containers/<int:container_id>/receive', methods=['GET', 'POST'])
@login_required
@role_required('Branch Manager')
def receive_container(container_id):
    branch = get_manager_branch()
    container = db.session.get(ContainerTransfer, container_id)
    if not container:
        flash("Container not found.", "danger")
        return redirect(url_for('branch.list_containers'))

    # Security: only destination branch manager can receive the container
    if container.to_branch_id != branch.id:
        flash("Unauthorized. Only the destination branch manager can receive this incoming container.", "danger")
        return redirect(url_for('branch.list_containers'))

    if container.status != 'Arrived at Branch' and container.status != 'In Transit':
        flash(f"Container is currently in '{container.status}' state. It must arrive at branch before receipt.", "warning")
        return redirect(url_for('branch.container_detail', container_id=container.id))

    try:
        # Mark container completed & unlocked
        container.status = 'Completed'
        container.is_locked = False
        # Release driver and vehicle and relocate physical location to this arrival branch
        if container.driver:
            container.driver.status = 'Available'
            container.driver.branch_id = branch.id
            if container.driver.user:
                container.driver.user.branch_id = branch.id
            if container.driver.vehicle:
                container.driver.vehicle.availability = 'Available'
                container.driver.vehicle.branch_id = branch.id
        elif container.vehicle:
            container.vehicle.availability = 'Available'
            container.vehicle.branch_id = branch.id

        order_count = 0
        for sh in container.shipments:
            order_count += 1
            # Automatic branch handover
            sh.branch_id = branch.id
            sh.driver_id = None
            sh.status = 'Warehouse'
            
            # Check if this branch is the final destination
            is_final_dest = (sh.receiver_city.strip().lower() == branch.city.strip().lower())
            if is_final_dest:
                sh.next_branch_id = None

            # History & Tracking Log
            hist = ShipmentHistory(
                shipment_id=sh.id,
                status='Warehouse',
                notes=f"Received at hub {branch.name} via Container {container.transfer_code}. Previous manager control transferred.",
                updated_by_id=g.user.id
            )
            db.session.add(hist)

            t_log = TrackingLog(
                shipment_id=sh.id,
                current_location=branch.city,
                status='Warehouse',
                description=f"Received at {branch.name} terminal. Container transfer {container.transfer_code} completed."
            )
            db.session.add(t_log)

            if sh.customer_id:
                create_notification(
                    sh.customer.user_id,
                    "Shipment Arrived at Hub",
                    f"Your shipment {sh.tracking_number} has safely reached {branch.name} terminal.",
                    "info"
                )

        db.session.commit()
        log_activity(g.user.id, "Receive Container", f"Received container {container.transfer_code} with {order_count} orders at branch {branch.code}", request.remote_addr)
        flash(f"Container {container.transfer_code} received successfully! All {order_count} orders transferred to {branch.name} warehouse inventory.", "success")
        return redirect(url_for('branch.local_shipments'))
    except Exception as e:
        db.session.rollback()
        flash("Failed to receive container.", "danger")
        return redirect(url_for('branch.container_detail', container_id=container.id))

# Single-order driver assignment for local pickup / last-mile delivery
@branch_bp.route('/shipments/assign/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('Branch Manager')
def assign_driver(id):
    branch = get_manager_branch()
    shipment = Shipment.query.filter_by(id=id, branch_id=branch.id).first()
    
    if not shipment:
        flash("Shipment not found or does not belong to your branch terminal.", "danger")
        return redirect(url_for('branch.local_shipments'))
        
    if shipment.is_container_locked:
        flash("Shipment is actively locked in a container transfer. Cannot modify assignment.", "warning")
        return redirect(url_for('branch.local_shipments'))
        
    available_drivers = Driver.query.filter_by(branch_id=branch.id, status='Available').all()
    available_vehicles = Vehicle.query.filter_by(branch_id=branch.id, availability='Available').all()
    
    is_linehaul = (shipment.status == 'Warehouse' and shipment.receiver_city.strip().lower() != branch.city.strip().lower())
    
    if is_linehaul:
        # Prompt manager to use multi-shipment container workflow instead
        flash("For branch-to-branch linehaul transfers, create or add to a Multi-Shipment Container!", "info")
        return redirect(url_for('branch.create_container'))
        
    if request.method == 'POST':
        driver_id_str = request.form.get('driver_id')
        if not driver_id_str:
            flash("Please select a local driver.", "warning")
            return redirect(url_for('branch.assign_driver', id=id))
            
        try:
            driver_id = int(driver_id_str)
            driver = db.session.get(Driver, driver_id)
            if not driver or driver.branch_id != branch.id or driver.status != 'Available':
                flash("Selected driver is not available or does not belong to this branch.", "danger")
                return redirect(url_for('branch.assign_driver', id=id))
                
            shipment.driver_id = driver.id
            shipment.status = 'Driver Assigned'
            driver.status = 'Busy'
            
            hist = ShipmentHistory(shipment_id=shipment.id, status='Driver Assigned', notes=f"Local delivery driver {driver.user.username} assigned by Branch Manager", updated_by_id=g.user.id)
            db.session.add(hist)
            
            t_log = TrackingLog(shipment_id=shipment.id, current_location=branch.city, status='Driver Assigned', description=f"Local delivery driver {driver.user.username} assigned.")
            db.session.add(t_log)
            
            db.session.commit()
            log_activity(g.user.id, "Assign Driver", f"Assigned local driver {driver.user.username} to shipment {shipment.tracking_number}", request.remote_addr)
            
            create_notification(driver.user_id, "New Delivery Assigned", f"Shipment {shipment.tracking_number} has been assigned to you for delivery.", "info")
            if shipment.customer_id:
                create_notification(shipment.customer.user_id, "Driver Assigned", f"Driver {driver.user.username} ({driver.phone}) has been assigned to your shipment.", "success")
                
            flash(f"Driver {driver.user.username} assigned successfully to shipment {shipment.tracking_number}.", "success")
            return redirect(url_for('branch.local_shipments'))
        except Exception as e:
            db.session.rollback()
            flash("Failed to assign driver.", "danger")
            
    return render_template('branch/assign_form.html', shipment=shipment, drivers=available_drivers, vehicles=available_vehicles, is_linehaul=False, branch=branch)

@branch_bp.route('/shipments/receive/<int:id>')
@login_required
@role_required('Branch Manager')
def receive_shipment(id):
    branch = get_manager_branch()
    shipment = db.session.get(Shipment, id)
    if not shipment:
        flash("Shipment not found.", "danger")
        return redirect(url_for('branch.local_shipments'))

    # If part of active container, redirect to container receive
    if shipment.active_container:
        return redirect(url_for('branch.container_detail', container_id=shipment.active_container.id))

    if shipment.next_branch_id != branch.id:
        flash("Shipment is not destined for this branch.", "danger")
        return redirect(url_for('branch.local_shipments'))
        
    try:
        if shipment.driver_id:
            driver = db.session.get(Driver, shipment.driver_id)
            if driver:
                driver.status = 'Available'
                driver.branch_id = branch.id
                if driver.user:
                    driver.user.branch_id = branch.id
                if driver.vehicle:
                    driver.vehicle.availability = 'Available'
                    driver.vehicle.branch_id = branch.id
                
        shipment.branch_id = branch.id
        shipment.driver_id = None
        shipment.status = 'Warehouse'
        
        is_dest = (shipment.receiver_city.strip().lower() == branch.city.strip().lower())
        if is_dest:
            shipment.next_branch_id = None
            
        hist = ShipmentHistory(shipment_id=shipment.id, status='Warehouse', notes=f"Shipment received at hub: {branch.name} by manager", updated_by_id=g.user.id)
        db.session.add(hist)
        
        t_log = TrackingLog(shipment_id=shipment.id, current_location=branch.city, status='Warehouse', description=f"Received at warehouse: {branch.name}")
        db.session.add(t_log)
        
        db.session.commit()
        log_activity(g.user.id, "Receive Shipment", f"Received shipment {shipment.tracking_number} at branch {branch.code}", request.remote_addr)
        flash(f"Shipment {shipment.tracking_number} received successfully at warehouse.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Failed to receive shipment.", "danger")
        
    return redirect(url_for('branch.local_shipments'))

@branch_bp.route('/employees')
@login_required
@role_required('Branch Manager')
def list_employees():
    branch = get_manager_branch()
    drivers = Driver.query.filter_by(branch_id=branch.id).all()
    return render_template('branch/employees.html', drivers=drivers, branch=branch)

@branch_bp.route('/reports')
@login_required
@role_required('Branch Manager')
def reports():
    branch = get_manager_branch()
    
    shipments = Shipment.query.filter_by(branch_id=branch.id).all()
    total_count = len(shipments)
    completed_count = sum(1 for s in shipments if s.status in ['Completed', 'Delivered'])
    revenue = sum(s.shipping_cost for s in shipments if s.payment and s.payment.payment_status == 'Completed')
    
    success_rate = (completed_count / total_count * 100) if total_count > 0 else 100.0
    
    return render_template(
        'branch/reports.html',
        branch=branch,
        total_count=total_count,
        completed_count=completed_count,
        revenue=round(revenue, 2),
        success_rate=round(success_rate, 1),
        shipments=shipments
    )
