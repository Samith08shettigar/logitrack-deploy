from flask import render_template, request, redirect, url_for, flash, session, g
from app.models import db, User, Role, Customer, Driver, Branch, Address
from app.utils import login_required, log_activity, create_notification
from . import auth_bp

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if g.user:
        # Already logged in, redirect to correct dashboard
        return redirect_dashboard(g.user.role.name)
        
    if request.method == 'POST':
        username_or_email = request.form.get('username')
        password = request.form.get('password')
        
        # Support login by username or email (case-insensitive)
        user = User.query.filter(
            (db.func.lower(User.username) == db.func.lower(username_or_email)) | 
            (db.func.lower(User.email) == db.func.lower(username_or_email))
        ).first()
        
        if user and user.check_password(password):
            if not user.is_active:
                flash("Your account has been deactivated. Please contact support.", "danger")
                return render_template('auth/login.html')
                
            session.clear()
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role.name
            
            # Log activity
            log_activity(user.id, "Login", "User logged in successfully", request.remote_addr)
            
            # Redirect to specific dashboard
            return redirect_dashboard(user.role.name)
        else:
            flash("Invalid username/email or password.", "danger")
            
    return render_template('auth/login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if g.user:
        return redirect_dashboard(g.user.role.name)
        
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        phone = request.form.get('phone')
        
        # Validation checks
        if not username or not email or not password or not phone:
            flash("All fields are required.", "warning")
            return render_template('auth/register.html')
            
        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            flash("Username or email already exists.", "warning")
            return render_template('auth/register.html')
            
        # Get Customer Role
        cust_role = Role.query.filter_by(name='Customer').first()
        if not cust_role:
            flash("Customer role not found in system. Please run DB seed.", "danger")
            return render_template('auth/register.html')
            
        try:
            # Create user
            new_user = User(username=username, email=email, role_id=cust_role.id)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit() # commit to get new_user.id
            
            # Create customer profile
            cust_profile = Customer(user_id=new_user.id, phone=phone, status='Active')
            db.session.add(cust_profile)
            
            # Log action
            log_activity(new_user.id, "Register", "Customer registered account", request.remote_addr)
            create_notification(new_user.id, "Welcome!", "Account created successfully. Welcome to LogiTrack!", "success")
            
            db.session.commit()
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            flash("An error occurred during registration. Please try again.", "danger")
            
    return render_template('auth/register.html')

@auth_bp.route('/logout')
def logout():
    if g.user:
        log_activity(g.user.id, "Logout", "User logged out", request.remote_addr)
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('auth.login'))

@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    customer = Customer.query.filter_by(user_id=g.user.id).first()
    driver = Driver.query.filter_by(user_id=g.user.id).first()
    
    if request.method == 'POST':
        email = request.form.get('email')
        phone = request.form.get('phone')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # Validations
        if not email:
            flash("Email is required.", "warning")
            return render_template('auth/profile.html', customer=customer, driver=driver)
            
        existing_user = User.query.filter(User.email == email, User.id != g.user.id).first()
        if existing_user:
            flash("Email is already in use by another account.", "warning")
            return render_template('auth/profile.html', customer=customer, driver=driver)
            
        try:
            g.user.email = email
            
            if phone:
                if customer:
                    customer.phone = phone
                elif driver:
                    driver.phone = phone
                    
            if new_password:
                if new_password != confirm_password:
                    flash("Passwords do not match.", "warning")
                    return render_template('auth/profile.html', customer=customer, driver=driver)
                g.user.set_password(new_password)
                
            db.session.commit()
            log_activity(g.user.id, "Update Profile", "User updated profile information", request.remote_addr)
            flash("Profile updated successfully!", "success")
            return redirect(url_for('auth.profile'))
        except Exception as e:
            db.session.rollback()
            flash("Failed to update profile. Please try again.", "danger")
            
    return render_template('auth/profile.html', customer=customer, driver=driver)

@auth_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        email = request.form.get('email')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        user = User.query.filter_by(email=email).first()
        if not user:
            flash("No account associated with that email address.", "danger")
            return render_template('auth/reset_password.html')
            
        if new_password != confirm_password:
            flash("Passwords do not match.", "warning")
            return render_template('auth/reset_password.html')
            
        try:
            user.set_password(new_password)
            db.session.commit()
            
            log_activity(user.id, "Reset Password", "User reset password via form", request.remote_addr)
            create_notification(user.id, "Password Reset", "Your password has been successfully reset.", "warning")
            
            flash("Password reset successfully! Please log in.", "success")
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            flash("An error occurred. Please try again.", "danger")
            
    return render_template('auth/reset_password.html')

@auth_bp.route('/verify-email')
@login_required
def verify_email():
    create_notification(g.user.id, "Email Verified", "Your email address has been successfully verified.", "success")
    flash("Email verified successfully (simulated)!", "success")
    return redirect_dashboard(g.user.role.name)

# Helper to redirect to role-specific dashboard
def redirect_dashboard(role_name):
    if role_name == 'Administrator':
        return redirect(url_for('admin.dashboard'))
    elif role_name == 'Customer':
        return redirect(url_for('customer.dashboard'))
    elif role_name == 'Driver':
        return redirect(url_for('driver.dashboard'))
    elif role_name == 'Branch Manager':
        return redirect(url_for('branch.dashboard'))
    else:
        return redirect(url_for('index'))
