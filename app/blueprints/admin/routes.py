import os
from datetime import datetime, date
import csv
import io
from flask import render_template, request, redirect, url_for, flash, g, make_response, current_app
from sqlalchemy import func
import pandas as pd
from app.models import db, User, Role, Customer, Driver, Branch, Vehicle, Shipment, ShipmentHistory, TrackingLog, Payment, Invoice, Feedback, Setting, ActivityLog
from app.utils import login_required, role_required, log_activity, create_notification, calculate_shipping_cost, generate_qr_code, generate_barcode_img, create_invoice_pdf
from . import admin_bp

@admin_bp.route('/dashboard')
@login_required
@role_required('Administrator')
def dashboard():
    # 1. KPI Metrics
    total_customers = Customer.query.count()
    total_drivers = Driver.query.count()
    total_shipments = Shipment.query.count()
    total_vehicles = Vehicle.query.count()
    total_branches = Branch.query.count()
    
    active_deliveries = Shipment.query.filter(Shipment.status.in_(['Driver Assigned', 'Picked Up', 'Warehouse', 'In Transit', 'Out For Delivery'])).count()
    pending_deliveries = Shipment.query.filter(Shipment.status.in_(['Booked', 'Payment Pending', 'Confirmed', 'Branch Assigned'])).count()
    delivered_shipments = Shipment.query.filter(Shipment.status.in_(['Delivered', 'Completed'])).count()
    cancelled_shipments = Shipment.query.filter(Shipment.status == 'Cancelled').count()
    
    # Revenue Calculation
    revenue_sum = db.session.query(func.sum(Payment.amount)).filter(Payment.payment_status == 'Completed').scalar() or 0.0
    
    # 2. Charts Data
    # Monthly Revenue (Last 6 Months) - Dialect-safe for PostgreSQL & SQLite
    try:
        is_postgres = (db.engine.dialect.name == 'postgresql')
        if is_postgres:
            month_expr = func.to_char(Payment.created_at, 'YYYY-MM').label('month')
            date_expr = func.cast(Shipment.created_at, db.Date).label('date')
        else:
            month_expr = func.strftime('%Y-%m', Payment.created_at).label('month')
            date_expr = func.date(Shipment.created_at).label('date')

        revenue_data = db.session.query(
            month_expr,
            func.sum(Payment.amount).label('total')
        ).filter(Payment.payment_status == 'Completed').group_by(month_expr).order_by(month_expr).all()
        
        # Shipments by Status
        status_data = db.session.query(
            Shipment.status,
            func.count(Shipment.id)
        ).group_by(Shipment.status).all()
        
        # Daily Bookings (Last 7 Days)
        bookings_data = db.session.query(
            date_expr,
            func.count(Shipment.id).label('count')
        ).group_by(date_expr).order_by(date_expr).limit(7).all()
    except Exception as chart_err:
        print(f"[Admin Dashboard Charts Error] {chart_err}")
        revenue_data = []
        status_data = []
        bookings_data = []
    
    # Recent Activities
    recent_activities = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(8).all()
    
    # Notifications
    notifications = g.user.notifications[-5:] if g.user.notifications else []

    return render_template(
        'admin/dashboard.html',
        total_customers=total_customers,
        total_drivers=total_drivers,
        total_shipments=total_shipments,
        total_vehicles=total_vehicles,
        total_branches=total_branches,
        active_deliveries=active_deliveries,
        pending_deliveries=pending_deliveries,
        delivered_shipments=delivered_shipments,
        cancelled_shipments=cancelled_shipments,
        monthly_revenue=round(revenue_sum, 2),
        revenue_data=revenue_data,
        status_data=status_data,
        bookings_data=bookings_data,
        recent_activities=recent_activities,
        notifications=notifications
    )

# --- CUSTOMER CRUD ---
@admin_bp.route('/customers')
@login_required
@role_required('Administrator')
def list_customers():
    customers = Customer.query.all()
    return render_template('admin/customers.html', customers=customers)

@admin_bp.route('/customers/add', methods=['GET', 'POST'])
@login_required
@role_required('Administrator')
def add_customer():
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        phone = (request.form.get('phone') or '').strip()
        status = request.form.get('status', 'Active')
        
        if not username or not email or not password or not phone:
            flash("All fields are required.", "warning")
            return redirect(url_for('admin.add_customer'))
            
        existing = User.query.filter(
            (db.func.lower(User.username) == db.func.lower(username)) | 
            (db.func.lower(User.email) == db.func.lower(email))
        ).first()
        if existing:
            flash("Username or email already exists.", "warning")
            return redirect(url_for('admin.add_customer'))
            
        role = Role.query.filter_by(name='Customer').first()
        if not role:
            role = Role(name='Customer', description='End customer booking shipments')
            db.session.add(role)
            db.session.commit()
            
        try:
            user = User(username=username, email=email, role_id=role.id, is_active=True)
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            
            customer = Customer(user_id=user.id, phone=phone, status=status)
            db.session.add(customer)
            db.session.commit()
            
            try:
                log_activity(g.user.id, "Create Customer", f"Created customer profile for {username}", request.remote_addr)
            except Exception:
                pass
                
            flash("Customer added successfully!", "success")
            return redirect(url_for('admin.list_customers'))
        except Exception as e:
            db.session.rollback()
            print(f"[Admin Add Customer Error] {e}")
            flash(f"Failed to add customer: {e}", "danger")
            
    return render_template('admin/customer_form.html', action="Add")

@admin_bp.route('/customers/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('Administrator')
def edit_customer(id):
    customer = db.session.get(Customer, id)
    if not customer:
        flash("Customer not found.", "danger")
        return redirect(url_for('admin.list_customers'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        phone = request.form.get('phone')
        status = request.form.get('status')
        loyalty = request.form.get('loyalty_points', 0)
        password = request.form.get('password')
        
        # Check unique email
        existing_email = User.query.filter(User.email == email, User.id != customer.user_id).first()
        if existing_email:
            flash("Email already in use.", "warning")
            return redirect(url_for('admin.edit_customer', id=id))
            
        try:
            customer.user.email = email
            customer.phone = phone
            customer.status = status
            customer.loyalty_points = int(loyalty)
            
            if password:
                customer.user.set_password(password)
                
            db.session.commit()
            log_activity(g.user.id, "Edit Customer", f"Updated customer ID {id}", request.remote_addr)
            flash("Customer updated successfully!", "success")
            return redirect(url_for('admin.list_customers'))
        except Exception as e:
            db.session.rollback()
            flash("Failed to update customer.", "danger")
            
    return render_template('admin/customer_form.html', action="Edit", customer=customer)

@admin_bp.route('/customers/delete/<int:id>')
@login_required
@role_required('Administrator')
def delete_customer(id):
    customer = db.session.get(Customer, id)
    if not customer:
        flash("Customer not found.", "danger")
        return redirect(url_for('admin.list_customers'))
    try:
        user_id = customer.user_id
        db.session.delete(customer)
        # Cascade will handle it, but User deletion triggers cleanup
        user = db.session.get(User, user_id)
        if user:
            db.session.delete(user)
        db.session.commit()
        log_activity(g.user.id, "Delete Customer", f"Deleted customer profile ID {id}", request.remote_addr)
        flash("Customer profile deleted successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Failed to delete customer.", "danger")
    return redirect(url_for('admin.list_customers'))


# --- DRIVER CRUD ---
@admin_bp.route('/drivers')
@login_required
@role_required('Administrator')
def list_drivers():
    drivers = Driver.query.all()
    return render_template('admin/drivers.html', drivers=drivers)

@admin_bp.route('/drivers/add', methods=['GET', 'POST'])
@login_required
@role_required('Administrator')
def add_driver():
    branches = Branch.query.all()
    # Exclude vehicles that are already assigned to other drivers
    assigned_vehicle_ids = [d.vehicle_id for d in Driver.query.filter(Driver.vehicle_id != None).all()]
    if assigned_vehicle_ids:
        vehicles = Vehicle.query.filter(~Vehicle.id.in_(assigned_vehicle_ids)).all()
    else:
        vehicles = Vehicle.query.all()
    
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        phone = (request.form.get('phone') or '').strip()
        license_number = (request.form.get('license_number') or '').strip()
        branch_id = request.form.get('branch_id')
        vehicle_id = request.form.get('vehicle_id')
        status = request.form.get('status', 'Available')
        
        # Validations
        if not username or not email or not password or not license_number:
            flash("Required fields missing.", "warning")
            return redirect(url_for('admin.add_driver'))
            
        existing = User.query.filter(
            (db.func.lower(User.username) == db.func.lower(username)) | 
            (db.func.lower(User.email) == db.func.lower(email))
        ).first()
        if existing:
            flash("User already exists.", "warning")
            return redirect(url_for('admin.add_driver'))
            
        role = Role.query.filter_by(name='Driver').first()
        if not role:
            role = Role(name='Driver', description='Fleet delivery driver')
            db.session.add(role)
            db.session.commit()
            
        try:
            user = User(username=username, email=email, role_id=role.id, is_active=True)
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            
            driver = Driver(
                user_id=user.id,
                phone=phone,
                license_number=license_number,
                branch_id=int(branch_id) if branch_id else None,
                vehicle_id=int(vehicle_id) if vehicle_id else None,
                status=status
            )
            db.session.add(driver)
            
            # If vehicle was assigned, update availability
            if vehicle_id:
                veh = db.session.get(Vehicle, int(vehicle_id))
                if veh:
                    veh.availability = 'In Use'
                    
            db.session.commit()
            
            try:
                log_activity(g.user.id, "Create Driver", f"Created driver profile for {username}", request.remote_addr)
            except Exception:
                pass
                
            flash("Driver added successfully!", "success")
            return redirect(url_for('admin.list_drivers'))
        except Exception as e:
            db.session.rollback()
            print(f"[Admin Add Driver Error] {e}")
            flash(f"Failed to add driver. Ensure license number and email/username are unique.", "danger")
            
    return render_template('admin/driver_form.html', action="Add", branches=branches, vehicles=vehicles)

@admin_bp.route('/drivers/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('Administrator')
def edit_driver(id):
    driver = db.session.get(Driver, id)
    if not driver:
        flash("Driver not found.", "danger")
        return redirect(url_for('admin.list_drivers'))
        
    branches = Branch.query.all()
    # Exclude vehicles assigned to other drivers, but include the one assigned to this driver
    assigned_vehicle_ids = [d.vehicle_id for d in Driver.query.filter(Driver.vehicle_id != None, Driver.id != id).all()]
    if assigned_vehicle_ids:
        vehicles = Vehicle.query.filter(~Vehicle.id.in_(assigned_vehicle_ids)).all()
    else:
        vehicles = Vehicle.query.all()
    
    if request.method == 'POST':
        email = request.form.get('email')
        phone = request.form.get('phone')
        license_number = request.form.get('license_number')
        branch_id = request.form.get('branch_id')
        vehicle_id = request.form.get('vehicle_id')
        status = request.form.get('status')
        password = request.form.get('password')
        
        try:
            driver.user.email = email
            driver.phone = phone
            driver.license_number = license_number
            driver.status = status
            driver.branch_id = int(branch_id) if branch_id else None
            
            # Vehicle swapping logic
            old_vehicle_id = driver.vehicle_id
            new_veh_id = int(vehicle_id) if vehicle_id else None
            
            if old_vehicle_id != new_veh_id:
                if old_vehicle_id:
                    old_veh = db.session.get(Vehicle, old_vehicle_id)
                    if old_veh:
                        old_veh.availability = 'Available'
                if new_veh_id:
                    new_veh = db.session.get(Vehicle, new_veh_id)
                    if new_veh:
                        new_veh.availability = 'In Use'
                driver.vehicle_id = new_veh_id
                
            if password:
                driver.user.set_password(password)
                
            db.session.commit()
            log_activity(g.user.id, "Edit Driver", f"Updated driver ID {id}", request.remote_addr)
            flash("Driver updated successfully!", "success")
            return redirect(url_for('admin.list_drivers'))
        except Exception as e:
            db.session.rollback()
            flash("Failed to update driver.", "danger")
            
    return render_template('admin/driver_form.html', action="Edit", driver=driver, branches=branches, vehicles=vehicles)

@admin_bp.route('/drivers/delete/<int:id>')
@login_required
@role_required('Administrator')
def delete_driver(id):
    driver = db.session.get(Driver, id)
    if not driver:
        flash("Driver not found.", "danger")
        return redirect(url_for('admin.list_drivers'))
        
    try:
        user_id = driver.user_id
        if driver.vehicle_id:
            veh = db.session.get(Vehicle, driver.vehicle_id)
            if veh:
                veh.availability = 'Available'
                
        db.session.delete(driver)
        user = db.session.get(User, user_id)
        if user:
            db.session.delete(user)
            
        db.session.commit()
        log_activity(g.user.id, "Delete Driver", f"Deleted driver profile ID {id}", request.remote_addr)
        flash("Driver profile deleted successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Failed to delete driver.", "danger")
        
    return redirect(url_for('admin.list_drivers'))


# --- VEHICLE CRUD ---
@admin_bp.route('/vehicles')
@login_required
@role_required('Administrator')
def list_vehicles():
    vehicles = Vehicle.query.all()
    return render_template('admin/vehicles.html', vehicles=vehicles)

@admin_bp.route('/vehicles/add', methods=['GET', 'POST'])
@login_required
@role_required('Administrator')
def add_vehicle():
    branches = Branch.query.all()
    if request.method == 'POST':
        num = request.form.get('vehicle_number')
        v_type = request.form.get('vehicle_type')
        cap = request.form.get('capacity', 0)
        fuel = request.form.get('fuel_type')
        ins = request.form.get('insurance_expiry')
        m_status = request.form.get('maintenance_status', 'Good')
        avail = request.form.get('availability', 'Available')
        branch_id = request.form.get('branch_id')
        
        if not num or not v_type or not cap or not fuel or not ins:
            flash("All fields except branch are required.", "warning")
            return redirect(url_for('admin.add_vehicle'))
            
        try:
            ins_date = datetime.strptime(ins, '%Y-%m-%d').date()
            veh = Vehicle(
                vehicle_number=num,
                vehicle_type=v_type,
                capacity=float(cap),
                fuel_type=fuel,
                insurance_expiry=ins_date,
                maintenance_status=m_status,
                availability=avail,
                branch_id=int(branch_id) if branch_id else None
            )
            db.session.add(veh)
            db.session.commit()
            log_activity(g.user.id, "Create Vehicle", f"Created vehicle {num}", request.remote_addr)
            flash("Vehicle added successfully!", "success")
            return redirect(url_for('admin.list_vehicles'))
        except Exception as e:
            db.session.rollback()
            flash("Failed to add vehicle. Ensure license plate is unique.", "danger")
            
    return render_template('admin/vehicle_form.html', action="Add", branches=branches)

@admin_bp.route('/vehicles/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('Administrator')
def edit_vehicle(id):
    veh = db.session.get(Vehicle, id)
    if not veh:
        flash("Vehicle not found.", "danger")
        return redirect(url_for('admin.list_vehicles'))
        
    branches = Branch.query.all()
    if request.method == 'POST':
        num = request.form.get('vehicle_number')
        v_type = request.form.get('vehicle_type')
        cap = request.form.get('capacity')
        fuel = request.form.get('fuel_type')
        ins = request.form.get('insurance_expiry')
        m_status = request.form.get('maintenance_status')
        avail = request.form.get('availability')
        branch_id = request.form.get('branch_id')
        
        try:
            ins_date = datetime.strptime(ins, '%Y-%m-%d').date()
            veh.vehicle_number = num
            veh.vehicle_type = v_type
            veh.capacity = float(cap)
            veh.fuel_type = fuel
            veh.insurance_expiry = ins_date
            veh.maintenance_status = m_status
            veh.availability = avail
            veh.branch_id = int(branch_id) if branch_id else None
            
            db.session.commit()
            log_activity(g.user.id, "Edit Vehicle", f"Updated vehicle ID {id}", request.remote_addr)
            flash("Vehicle updated successfully!", "success")
            return redirect(url_for('admin.list_vehicles'))
        except Exception as e:
            db.session.rollback()
            flash("Failed to update vehicle.", "danger")
            
    return render_template('admin/vehicle_form.html', action="Edit", vehicle=veh, branches=branches)

@admin_bp.route('/vehicles/delete/<int:id>')
@login_required
@role_required('Administrator')
def delete_vehicle(id):
    veh = db.session.get(Vehicle, id)
    if not veh:
        flash("Vehicle not found.", "danger")
        return redirect(url_for('admin.list_vehicles'))
    try:
        # Check driver association first
        driver = Driver.query.filter_by(vehicle_id=veh.id).first()
        if driver:
            driver.vehicle_id = None
        db.session.delete(veh)
        db.session.commit()
        log_activity(g.user.id, "Delete Vehicle", f"Deleted vehicle ID {id}", request.remote_addr)
        flash("Vehicle deleted successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Failed to delete vehicle.", "danger")
    return redirect(url_for('admin.list_vehicles'))


# --- BRANCH CRUD ---
@admin_bp.route('/branches')
@login_required
@role_required('Administrator')
def list_branches():
    branches = Branch.query.all()
    return render_template('admin/branches.html', branches=branches)

@admin_bp.route('/branches/add', methods=['GET', 'POST'])
@login_required
@role_required('Administrator')
def add_branch():
    if request.method == 'POST':
        name = request.form.get('name')
        code = request.form.get('code')
        addr = request.form.get('address')
        city = request.form.get('city')
        state = request.form.get('state')
        zip_c = request.form.get('zip_code')
        phone = request.form.get('phone')
        email = request.form.get('email')
        
        if not name or not code or not addr or not city or not state or not zip_c or not phone or not email:
            flash("All fields are required.", "warning")
            return redirect(url_for('admin.add_branch'))
            
        try:
            br = Branch(name=name, code=code, address=addr, city=city, state=state, zip_code=zip_c, phone=phone, email=email)
            db.session.add(br)
            db.session.commit()
            log_activity(g.user.id, "Create Branch", f"Created branch {code}", request.remote_addr)
            flash("Branch added successfully!", "success")
            return redirect(url_for('admin.list_branches'))
        except Exception as e:
            db.session.rollback()
            flash("Failed to add branch. Branch code must be unique.", "danger")
            
    return render_template('admin/branch_form.html', action="Add")

@admin_bp.route('/branches/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('Administrator')
def edit_branch(id):
    br = db.session.get(Branch, id)
    if not br:
        flash("Branch not found.", "danger")
        return redirect(url_for('admin.list_branches'))
        
    if request.method == 'POST':
        try:
            br.name = request.form.get('name')
            br.code = request.form.get('code')
            br.address = request.form.get('address')
            br.city = request.form.get('city')
            br.state = request.form.get('state')
            br.zip_code = request.form.get('zip_code')
            br.phone = request.form.get('phone')
            br.email = request.form.get('email')
            
            db.session.commit()
            log_activity(g.user.id, "Edit Branch", f"Updated branch ID {id}", request.remote_addr)
            flash("Branch updated successfully!", "success")
            return redirect(url_for('admin.list_branches'))
        except Exception as e:
            db.session.rollback()
            flash("Failed to update branch.", "danger")
            
    return render_template('admin/branch_form.html', action="Edit", branch=br)

@admin_bp.route('/branches/delete/<int:id>')
@login_required
@role_required('Administrator')
def delete_branch(id):
    br = db.session.get(Branch, id)
    if not br:
        flash("Branch not found.", "danger")
        return redirect(url_for('admin.list_branches'))
    try:
        db.session.delete(br)
        db.session.commit()
        log_activity(g.user.id, "Delete Branch", f"Deleted branch ID {id}", request.remote_addr)
        flash("Branch deleted successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Failed to delete branch. Ensure no shipments depend on it.", "danger")
    return redirect(url_for('admin.list_branches'))


# --- EMPLOYEES CRUD (Admins & Branch Managers) ---
@admin_bp.route('/employees')
@login_required
@role_required('Administrator')
def list_employees():
    admin_r = Role.query.filter_by(name='Administrator').first()
    bm_r = Role.query.filter_by(name='Branch Manager').first()
    employees = User.query.filter(User.role_id.in_([admin_r.id, bm_r.id])).all()
    return render_template('admin/employees.html', employees=employees)

@admin_bp.route('/employees/add', methods=['GET', 'POST'])
@login_required
@role_required('Administrator')
def add_employee():
    roles = Role.query.filter(Role.name.in_(['Administrator', 'Branch Manager'])).all()
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        role_id = request.form.get('role_id')
        branch_id = request.form.get('branch_id')
        is_active = request.form.get('is_active') == 'on'
        
        if not username or not email or not password or not role_id:
            flash("All fields are required.", "warning")
            return redirect(url_for('admin.add_employee'))
            
        selected_role = Role.query.get(int(role_id))
        if selected_role and selected_role.name != 'Branch Manager':
            branch_id = None
        else:
            branch_id = int(branch_id) if branch_id else None
            
        existing = User.query.filter(
            (db.func.lower(User.username) == db.func.lower(username)) | 
            (db.func.lower(User.email) == db.func.lower(email))
        ).first()
        if existing:
            flash("User with that username or email already exists.", "warning")
            return redirect(url_for('admin.add_employee'))
            
        try:
            user = User(username=username, email=email, role_id=int(role_id), branch_id=branch_id, is_active=is_active)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            
            try:
                log_activity(g.user.id, "Create Employee", f"Created employee {username}", request.remote_addr)
            except Exception:
                pass
                
            flash("Employee added successfully!", "success")
            return redirect(url_for('admin.list_employees'))
        except Exception as e:
            db.session.rollback()
            print(f"[Admin Add Employee Error] {e}")
            flash("Failed to add employee. Please try again.", "danger")
            
    branches = Branch.query.all()
    return render_template('admin/employee_form.html', action="Add", roles=roles, branches=branches)

@admin_bp.route('/employees/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('Administrator')
def edit_employee(id):
    emp = db.session.get(User, id)
    if not emp:
        flash("Employee not found.", "danger")
        return redirect(url_for('admin.list_employees'))
        
    roles = Role.query.filter(Role.name.in_(['Administrator', 'Branch Manager'])).all()
    
    if request.method == 'POST':
        email = request.form.get('email')
        role_id = request.form.get('role_id')
        branch_id = request.form.get('branch_id')
        is_active = request.form.get('is_active') == 'on'
        password = request.form.get('password')
        
        selected_role = Role.query.get(int(role_id))
        if selected_role and selected_role.name != 'Branch Manager':
            branch_id = None
        else:
            branch_id = int(branch_id) if branch_id else None
            
        existing_email = User.query.filter(User.email == email, User.id != emp.id).first()
        if existing_email:
            flash("Email already in use.", "warning")
            return redirect(url_for('admin.edit_employee', id=id))
            
        try:
            emp.email = email
            emp.role_id = int(role_id)
            emp.branch_id = branch_id
            emp.is_active = is_active
            if password:
                emp.set_password(password)
                
            db.session.commit()
            log_activity(g.user.id, "Edit Employee", f"Updated employee ID {id}", request.remote_addr)
            flash("Employee updated successfully!", "success")
            return redirect(url_for('admin.list_employees'))
        except Exception as e:
            db.session.rollback()
            flash("Failed to update employee.", "danger")
            
    branches = Branch.query.all()
    return render_template('admin/employee_form.html', action="Edit", employee=emp, roles=roles, branches=branches)

@admin_bp.route('/employees/delete/<int:id>')
@login_required
@role_required('Administrator')
def delete_employee(id):
    emp = db.session.get(User, id)
    if not emp:
        flash("Employee not found.", "danger")
        return redirect(url_for('admin.list_employees'))
    if emp.id == g.user.id:
        flash("You cannot delete your own admin account.", "danger")
        return redirect(url_for('admin.list_employees'))
        
    try:
        db.session.delete(emp)
        db.session.commit()
        log_activity(g.user.id, "Delete Employee", f"Deleted employee ID {id}", request.remote_addr)
        flash("Employee account deleted successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Failed to delete employee.", "danger")
    return redirect(url_for('admin.list_employees'))


# --- SHIPMENT CRUD ---
@admin_bp.route('/shipments')
@login_required
@role_required('Administrator')
def list_shipments():
    shipments = Shipment.query.order_by(Shipment.created_at.desc()).all()
    return render_template('admin/shipments.html', shipments=shipments)

@admin_bp.route('/shipments/add', methods=['GET', 'POST'])
@login_required
@role_required('Administrator')
def add_shipment():
    branches = Branch.query.all()
    drivers = Driver.query.filter_by(status='Available').all()
    
    if request.method == 'POST':
        # Gather sender & receiver details
        s_name = request.form.get('sender_name')
        s_phone = request.form.get('sender_phone')
        s_email = request.form.get('sender_email')
        
        p_addr = request.form.get('pickup_address')
        p_city = request.form.get('pickup_city')
        p_state = request.form.get('pickup_state')
        p_zip = request.form.get('pickup_zip_code')
        
        r_name = request.form.get('receiver_name')
        r_phone = request.form.get('receiver_phone')
        r_addr = request.form.get('receiver_address')
        r_city = request.form.get('receiver_city')
        r_state = request.form.get('receiver_state')
        r_zip = request.form.get('receiver_zip_code')
        
        category = request.form.get('package_category')
        if category == 'Other':
            category = request.form.get('custom_category')
        desc = request.form.get('package_description')
        weight = float(request.form.get('package_weight', 0))
        fragile = request.form.get('fragile') == 'on'
        insurance = request.form.get('insurance') == 'on'
        delivery_type = request.form.get('delivery_type', 'Standard')
        
        # Product Image Upload handling (Compulsory)
        import uuid
        image_file = request.files.get('package_image')
        if not image_file or not image_file.filename or image_file.filename.strip() == '':
            flash("Product image is compulsory required. Please upload a clear photo of the package.", "warning")
            return redirect(url_for('admin.add_shipment'))

        ext = os.path.splitext(image_file.filename)[1].lower()
        allowed_exts = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'}
        if ext not in allowed_exts:
            flash("Invalid image format. Please upload a valid image file (JPG, PNG, WEBP, etc.).", "warning")
            return redirect(url_for('admin.add_shipment'))

        filename = f"prod_{uuid.uuid4().hex}{ext}"
        save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'products', filename)
        image_file.save(save_path)
        image_path = f"uploads/products/{filename}"
        
        branch_id = request.form.get('branch_id')
        driver_id = request.form.get('driver_id')
        
        # Calculate cost
        declared_value = float(request.form.get('declared_value', 0.0)) if insurance else 0.0
        cost = calculate_shipping_cost(weight, delivery_type, fragile, insurance, category, declared_value)
        
        # Generate tracking number
        tracking_num = f"LT-{datetime.now().strftime('%y%m%d')}-{random_randint()}"
        
        try:
            shipment = Shipment(
                tracking_number=tracking_num,
                sender_name=s_name, sender_phone=s_phone, sender_email=s_email,
                pickup_address_line=p_addr, pickup_city=p_city, pickup_state=p_state, pickup_zip_code=p_zip,
                receiver_name=r_name, receiver_phone=r_phone,
                receiver_address_line=r_addr, receiver_city=r_city, receiver_state=r_state, receiver_zip_code=r_zip,
                package_category=category, package_description=desc, package_weight=weight,
                package_dimensions=None, package_image_path=image_path, fragile=fragile, insurance=insurance,
                declared_value=declared_value,
                delivery_type=delivery_type, shipping_cost=cost, status='Booked',
                branch_id=int(branch_id) if branch_id else None,
                driver_id=int(driver_id) if driver_id else None
            )
            db.session.add(shipment)
            db.session.commit()
            
            # Generate QR and Barcode
            shipment.qr_code_path = generate_qr_code(tracking_num)
            shipment.barcode_path = generate_barcode_img(tracking_num)
            
            # History log
            hist = ShipmentHistory(shipment_id=shipment.id, status='Booked', notes='Shipment booked by administrator')
            db.session.add(hist)
            
            # Tracking log
            t_log = TrackingLog(shipment_id=shipment.id, current_location="Admin Hub", status='Booked', description="Shipment recorded at local hub")
            db.session.add(t_log)
            
            # Payment record (default pending, cash on delivery or simulate)
            pm = Payment(shipment_id=shipment.id, amount=cost, payment_method='Cash on Delivery', payment_status='Pending')
            db.session.add(pm)
            
            # PDF Invoice
            create_invoice_pdf(shipment)
            
            db.session.commit()
            log_activity(g.user.id, "Create Shipment", f"Created shipment {tracking_num}", request.remote_addr)
            flash("Shipment booked successfully!", "success")
            return redirect(url_for('admin.list_shipments'))
        except Exception as e:
            db.session.rollback()
            flash("Failed to book shipment.", "danger")
            
    return render_template('admin/shipment_form.html', action="Add", branches=branches, drivers=drivers)

@admin_bp.route('/shipments/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('Administrator')
def edit_shipment(id):
    shipment = db.session.get(Shipment, id)
    if not shipment:
        flash("Shipment not found.", "danger")
        return redirect(url_for('admin.list_shipments'))
        
    branches = Branch.query.all()
    drivers = Driver.query.all()
    
    if request.method == 'POST':
        # Capture updates
        shipment.status = request.form.get('status')
        shipment.branch_id = int(request.form.get('branch_id')) if request.form.get('branch_id') else None
        
        old_driver = shipment.driver_id
        new_driver_str = request.form.get('driver_id')
        new_driver = int(new_driver_str) if new_driver_str else None
        
        if old_driver != new_driver:
            shipment.driver_id = new_driver
            # Update driver availability status
            if new_driver:
                drv = db.session.get(Driver, new_driver)
                if drv:
                    drv.status = 'Busy'
            if old_driver:
                old_drv = db.session.get(Driver, old_driver)
                if old_drv:
                    # check if he has other active shipments
                    active_count = Shipment.query.filter(Shipment.driver_id == old_driver, Shipment.status.notin_(['Delivered', 'Completed', 'Cancelled'])).count()
                    if active_count == 0:
                        old_drv.status = 'Available'
                        
        try:
            # Capture notes
            notes = request.form.get('status_notes', f"Shipment status updated to {shipment.status}")
            
            # History log
            hist = ShipmentHistory(shipment_id=shipment.id, status=shipment.status, notes=notes, updated_by_id=g.user.id)
            db.session.add(hist)
            
            # Tracking log
            loc = request.form.get('current_location', 'Warehouse Hub')
            t_log = TrackingLog(shipment_id=shipment.id, current_location=loc, status=shipment.status, description=notes)
            db.session.add(t_log)
            
            # Generate new PDF invoice
            create_invoice_pdf(shipment)
            
            # If delivered/completed, update payment if COD
            if shipment.status in ['Delivered', 'Completed'] and shipment.payment and shipment.payment.payment_method == 'Cash on Delivery':
                shipment.payment.payment_status = 'Completed'
                
            db.session.commit()
            log_activity(g.user.id, "Edit Shipment", f"Updated shipment ID {id} to {shipment.status}", request.remote_addr)
            flash("Shipment updated successfully!", "success")
            return redirect(url_for('admin.list_shipments'))
        except Exception as e:
            db.session.rollback()
            flash("Failed to update shipment.", "danger")
            
    return render_template('admin/shipment_form.html', action="Edit", shipment=shipment, branches=branches, drivers=drivers)

@admin_bp.route('/shipments/delete/<int:id>')
@login_required
@role_required('Administrator')
def delete_shipment(id):
    shipment = db.session.get(Shipment, id)
    if not shipment:
        flash("Shipment not found.", "danger")
        return redirect(url_for('admin.list_shipments'))
    try:
        db.session.delete(shipment)
        db.session.commit()
        log_activity(g.user.id, "Delete Shipment", f"Deleted shipment ID {id}", request.remote_addr)
        flash("Shipment deleted successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Failed to delete shipment.", "danger")
    return redirect(url_for('admin.list_shipments'))


# --- PAYMENTS CRUD ---
@admin_bp.route('/payments')
@login_required
@role_required('Administrator')
def list_payments():
    payments = Payment.query.order_by(Payment.created_at.desc()).all()
    return render_template('admin/payments.html', payments=payments)

@admin_bp.route('/payments/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('Administrator')
def edit_payment(id):
    payment = db.session.get(Payment, id)
    if not payment:
        flash("Payment record not found.", "danger")
        return redirect(url_for('admin.list_payments'))
        
    if request.method == 'POST':
        payment.payment_status = request.form.get('payment_status')
        payment.transaction_id = request.form.get('transaction_id')
        
        try:
            db.session.commit()
            log_activity(g.user.id, "Edit Payment", f"Updated payment status of record ID {id}", request.remote_addr)
            flash("Payment record updated successfully!", "success")
            return redirect(url_for('admin.list_payments'))
        except Exception as e:
            db.session.rollback()
            flash("Failed to update payment record.", "danger")
            
    return render_template('admin/payment_form.html', payment=payment)


# --- FEEDBACK VIEW ---
@admin_bp.route('/feedback')
@login_required
@role_required('Administrator')
def list_feedback():
    feedbacks = Feedback.query.order_by(Feedback.submitted_at.desc()).all()
    return render_template('admin/feedback.html', feedbacks=feedbacks)


@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@role_required('Administrator')
def system_settings():
    # 1. Seed missing GST & Insurance rates for any existing packaging rates in db
    DEFAULT_GST_RATES = {
        'rate_packaging_clothes_garments': '5',
        'rate_packaging_books': '5',
        'rate_packaging_documents': '0',
        'rate_packaging_electronics': '18',
        'rate_packaging_mobile_laptop': '18',
        'rate_packaging_glass_items': '18',
        'rate_packaging_kitchen_items': '5',
        'rate_packaging_household_items': '5',
        'rate_packaging_machinery_parts': '18',
        'rate_packaging_auto_spare_parts': '18',
        'rate_packaging_furniture': '18',
        'rate_packaging_fruits_vegetables': '5',
        'rate_packaging_food_items': '5',
        'rate_packaging_clothing_bundles': '5',
        'rate_packaging_industrial_goods': '18',
        'rate_packaging_other': '18'
    }
    DEFAULT_INS_RATES = {
        'rate_packaging_clothes_garments': '1.0',
        'rate_packaging_books': '0.5',
        'rate_packaging_documents': '0.5',
        'rate_packaging_electronics': '2.0',
        'rate_packaging_mobile_laptop': '2.5',
        'rate_packaging_glass_items': '2.5',
        'rate_packaging_kitchen_items': '1.0',
        'rate_packaging_household_items': '1.0',
        'rate_packaging_machinery_parts': '2.0',
        'rate_packaging_auto_spare_parts': '2.0',
        'rate_packaging_furniture': '1.5',
        'rate_packaging_fruits_vegetables': '1.0',
        'rate_packaging_food_items': '1.0',
        'rate_packaging_clothing_bundles': '1.0',
        'rate_packaging_industrial_goods': '2.5',
        'rate_packaging_other': '2.5'
    }
    DEFAULT_INS_MINS = {
        'rate_packaging_clothes_garments': '100',
        'rate_packaging_books': '75',
        'rate_packaging_documents': '100',
        'rate_packaging_electronics': '250',
        'rate_packaging_mobile_laptop': '300',
        'rate_packaging_glass_items': '300',
        'rate_packaging_kitchen_items': '100',
        'rate_packaging_household_items': '100',
        'rate_packaging_machinery_parts': '250',
        'rate_packaging_auto_spare_parts': '250',
        'rate_packaging_furniture': '200',
        'rate_packaging_fruits_vegetables': '100',
        'rate_packaging_food_items': '100',
        'rate_packaging_clothing_bundles': '100',
        'rate_packaging_industrial_goods': '300',
        'rate_packaging_other': '300'
    }
    
    try:
        current_settings = Setting.query.all()
        for s in current_settings:
            if s.setting_key.startswith('rate_packaging_'):
                suffix = s.setting_key[15:]
                
                # GST Rate
                gst_key = f'gst_packaging_{suffix}'
                existing_gst = next((x for x in current_settings if x.setting_key == gst_key), None)
                if not existing_gst:
                    default_val = DEFAULT_GST_RATES.get(s.setting_key, '18')
                    cat_name = s.description.replace('Packaging Rate: ', '').replace(' (INR/kg)', '') if s.description else suffix
                    gst_setting = Setting(
                        setting_key=gst_key,
                        setting_value=default_val,
                        setting_type='float',
                        description=f"GST Rate: {cat_name} (%)"
                    )
                    db.session.add(gst_setting)
                    
                # Insurance Rate
                ins_rate_key = f'ins_rate_packaging_{suffix}'
                existing_ins_rate = next((x for x in current_settings if x.setting_key == ins_rate_key), None)
                if not existing_ins_rate:
                    default_ins = DEFAULT_INS_RATES.get(s.setting_key, '2.5')
                    cat_name = s.description.replace('Packaging Rate: ', '').replace(' (INR/kg)', '') if s.description else suffix
                    ins_rate_setting = Setting(
                        setting_key=ins_rate_key,
                        setting_value=default_ins,
                        setting_type='float',
                        description=f"Insurance Rate: {cat_name} (%)"
                    )
                    db.session.add(ins_rate_setting)
                    
                # Minimum Insurance
                ins_min_key = f'ins_min_packaging_{suffix}'
                existing_ins_min = next((x for x in current_settings if x.setting_key == ins_min_key), None)
                if not existing_ins_min:
                    default_min = DEFAULT_INS_MINS.get(s.setting_key, '300')
                    cat_name = s.description.replace('Packaging Rate: ', '').replace(' (INR/kg)', '') if s.description else suffix
                    ins_min_setting = Setting(
                        setting_key=ins_min_key,
                        setting_value=default_min,
                        setting_type='float',
                        description=f"Minimum Insurance: {cat_name} (INR)"
                    )
                    db.session.add(ins_min_setting)
                    
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        
    settings = Setting.query.all()
    
    if request.method == 'POST':
        action = request.form.get('action')
        try:
            if action == 'add_category':
                cat_name = request.form.get('new_category_name')
                cat_rate = request.form.get('new_category_rate')
                cat_gst = request.form.get('new_category_gst', '18')
                cat_ins_rate = request.form.get('new_category_ins_rate', '2.5')
                cat_ins_min = request.form.get('new_category_ins_min', '300')
                if cat_name and cat_rate:
                    clean_name = cat_name.strip()
                    suffix = clean_name.lower().replace(' ', '_').replace('/', '_').replace('-', '_')
                    rate_key = 'rate_packaging_' + suffix
                    gst_key = 'gst_packaging_' + suffix
                    ins_rate_key = 'ins_rate_packaging_' + suffix
                    ins_min_key = 'ins_min_packaging_' + suffix
                    
                    existing_rate = Setting.query.filter_by(setting_key=rate_key).first()
                    if not existing_rate:
                        rate_setting = Setting(
                            setting_key=rate_key,
                            setting_value=cat_rate.strip(),
                            setting_type='float',
                            description=f"Packaging Rate: {clean_name} (INR/kg)"
                        )
                        db.session.add(rate_setting)
                        
                        gst_setting = Setting(
                            setting_key=gst_key,
                            setting_value=cat_gst.strip(),
                            setting_type='float',
                            description=f"GST Rate: {clean_name} (%)"
                        )
                        db.session.add(gst_setting)
                        
                        ins_rate_setting = Setting(
                            setting_key=ins_rate_key,
                            setting_value=cat_ins_rate.strip(),
                            setting_type='float',
                            description=f"Insurance Rate: {clean_name} (%)"
                        )
                        db.session.add(ins_rate_setting)
                        
                        ins_min_setting = Setting(
                            setting_key=ins_min_key,
                            setting_value=cat_ins_min.strip(),
                            setting_type='float',
                            description=f"Minimum Insurance: {clean_name} (INR)"
                        )
                        db.session.add(ins_min_setting)
                        
                        db.session.commit()
                        log_activity(g.user.id, "Add Settings Category", f"Added packaging category: {clean_name}", request.remote_addr)
                        flash(f"Category '{clean_name}' added successfully!", "success")
                    else:
                        flash("This category already exists.", "warning")
                else:
                    flash("Category name and rate are required to add.", "warning")
                return redirect(url_for('admin.system_settings'))
                
            elif action and action.startswith('delete_category:'):
                rate_key = action.split('delete_category:')[1]
                suffix = rate_key[15:]
                gst_key = f'gst_packaging_{suffix}'
                ins_rate_key = f'ins_rate_packaging_{suffix}'
                ins_min_key = f'ins_min_packaging_{suffix}'
                
                s_rate = Setting.query.filter_by(setting_key=rate_key).first()
                s_gst = Setting.query.filter_by(setting_key=gst_key).first()
                s_ins_rate = Setting.query.filter_by(setting_key=ins_rate_key).first()
                s_ins_min = Setting.query.filter_by(setting_key=ins_min_key).first()
                
                cat_name_deleted = "Category"
                if s_rate:
                    cat_name_deleted = s_rate.description.replace('Packaging Rate: ', '').replace(' (INR/kg)', '') if s_rate.description else rate_key
                    db.session.delete(s_rate)
                if s_gst:
                    db.session.delete(s_gst)
                if s_ins_rate:
                    db.session.delete(s_ins_rate)
                if s_ins_min:
                    db.session.delete(s_ins_min)
                    
                db.session.commit()
                log_activity(g.user.id, "Delete Settings Category", f"Deleted packaging category: {cat_name_deleted}", request.remote_addr)
                flash(f"Category '{cat_name_deleted}' deleted successfully!", "success")
                return redirect(url_for('admin.system_settings'))
                
            else:
                for s in settings:
                    val = request.form.get(s.setting_key)
                    if val is not None:
                        s.setting_value = val
                db.session.commit()
                log_activity(g.user.id, "Update Settings", "Updated system config settings", request.remote_addr)
                flash("System settings updated successfully!", "success")
                return redirect(url_for('admin.system_settings'))
        except Exception as e:
            db.session.rollback()
            flash("An error occurred. Failed to save setting.", "danger")
            
    # Process structured category objects to render side-by-side rates, GSTs, and Insurance
    categories_list = []
    for s in settings:
        if s.setting_key.startswith('rate_packaging_'):
            suffix = s.setting_key[15:]
            gst_key = f'gst_packaging_{suffix}'
            ins_rate_key = f'ins_rate_packaging_{suffix}'
            ins_min_key = f'ins_min_packaging_{suffix}'
            
            gst_s = next((x for x in settings if x.setting_key == gst_key), None)
            ins_rate_s = next((x for x in settings if x.setting_key == ins_rate_key), None)
            ins_min_s = next((x for x in settings if x.setting_key == ins_min_key), None)
            
            cat_name = s.description.replace('Packaging Rate: ', '').replace(' (INR/kg)', '') if s.description else suffix
            categories_list.append({
                'name': cat_name,
                'rate_setting': s,
                'gst_setting': gst_s,
                'ins_rate_setting': ins_rate_s,
                'ins_min_setting': ins_min_s,
                'rate_key': s.setting_key,
                'gst_key': gst_key,
                'ins_rate_key': ins_rate_key,
                'ins_min_key': ins_min_key
            })
            
    return render_template('admin/settings.html', settings=settings, categories_list=categories_list)


# --- REPORTS GENERATION & EXPORTS ---
@admin_bp.route('/reports')
@login_required
@role_required('Administrator')
def reports_page():
    return redirect(url_for('reports.index'))

@admin_bp.route('/reports/export')
@login_required
@role_required('Administrator')
def export_report():
    report_type = request.args.get('type', 'shipments')
    file_format = request.args.get('format', 'csv')
    
    # Query datasets
    if report_type == 'shipments':
        data = Shipment.query.order_by(Shipment.created_at.desc()).all()
        headers = ['Tracking Number', 'Sender Name', 'Receiver Name', 'Category', 'Weight (kg)', 'Cost (INR)', 'Status', 'Date']
        rows = [[s.tracking_number, s.sender_name, s.receiver_name, s.package_category, s.package_weight, s.shipping_cost, s.status, s.created_at.strftime('%Y-%m-%d')] for s in data]
    elif report_type == 'revenue':
        data = Payment.query.filter_by(payment_status='Completed').order_by(Payment.created_at.desc()).all()
        headers = ['Transaction ID', 'Tracking Number', 'Payment Method', 'Amount (INR)', 'Date']
        rows = [[p.transaction_id, p.shipment.tracking_number, p.payment_method, p.amount, p.created_at.strftime('%Y-%m-%d')] for p in data]
    elif report_type == 'drivers':
        data = Driver.query.all()
        headers = ['Driver Name', 'Phone', 'License Number', 'Assigned Vehicle', 'Status', 'Rating']
        rows = [[d.user.username, d.phone, d.license_number, d.vehicle.vehicle_number if d.vehicle else 'None', d.status, d.rating] for d in data]
    elif report_type == 'vehicles':
        data = Vehicle.query.all()
        headers = ['Vehicle Plate', 'Type', 'Capacity (kg)', 'Fuel Type', 'Availability', 'Maintenance Status']
        rows = [[v.vehicle_number, v.vehicle_type, v.capacity, v.fuel_type, v.availability, v.maintenance_status] for v in data]
    else:
        flash("Invalid report type.", "warning")
        return redirect(url_for('reports.index'))

    # Build CSV or Excel Output
    if file_format == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        
        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = f"attachment; filename={report_type}_report.csv"
        response.headers["Content-type"] = "text/csv"
        return response
        
    elif file_format == 'excel':
        # Create DataFrame
        df = pd.DataFrame(rows, columns=headers)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Sheet1')
            
        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = f"attachment; filename={report_type}_report.xlsx"
        response.headers["Content-type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return response
        
    else:
        flash("Unsupported format.", "warning")
        return redirect(url_for('reports.index'))

# Simple integer randomizer
def random_randint():
    import random
    return random.randint(1000, 9999)
