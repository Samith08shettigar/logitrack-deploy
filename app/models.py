from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class BaseModel(db.Model):
    __abstract__ = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

class Role(BaseModel):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(255))
    
    users = db.relationship('User', backref='role', lazy=True)

    def __repr__(self):
        return f"<Role {self.name}>"

class User(BaseModel):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id', ondelete='SET NULL'), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Core Relationships
    customer_profile = db.relationship('Customer', backref='user', uselist=False, cascade="all, delete-orphan")
    driver_profile = db.relationship('Driver', backref='user', uselist=False, cascade="all, delete-orphan")
    addresses = db.relationship('Address', backref='user', lazy=True, cascade="all, delete-orphan")
    notifications = db.relationship('Notification', backref='user', lazy=True, cascade="all, delete-orphan")
    activity_logs = db.relationship('ActivityLog', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.username}>"

class Branch(BaseModel):
    __tablename__ = 'branches'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    address = db.Column(db.String(255), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(100), nullable=False)
    zip_code = db.Column(db.String(20), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    vehicles = db.relationship('Vehicle', backref='branch', lazy=True)
    drivers = db.relationship('Driver', backref='branch', lazy=True)
    managers = db.relationship('User', backref='branch', lazy=True)

    @property
    def shipments(self):
        return self.local_shipments

    def __repr__(self):
        return f"<Branch {self.name} ({self.code})>"

class Vehicle(BaseModel):
    __tablename__ = 'vehicles'
    id = db.Column(db.Integer, primary_key=True)
    vehicle_number = db.Column(db.String(50), unique=True, nullable=False)
    vehicle_type = db.Column(db.String(50), nullable=False)  # Truck, Van, Bike, Container
    capacity = db.Column(db.Float, nullable=False)            # in kg
    fuel_type = db.Column(db.String(50), nullable=False)     # Diesel, Petrol, Electric
    insurance_expiry = db.Column(db.Date, nullable=False)
    maintenance_status = db.Column(db.String(50), default='Good')   # Good, Needs Service, Under Repair
    availability = db.Column(db.String(50), default='Available')   # Available, In Use, Out of Service
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id', ondelete='SET NULL'), nullable=True)

    driver = db.relationship('Driver', backref='vehicle', uselist=False)

    def __repr__(self):
        return f"<Vehicle {self.vehicle_number}>"

class Customer(BaseModel):
    __tablename__ = 'customers'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(50), default='Active')  # Active, Suspended
    loyalty_points = db.Column(db.Integer, default=0)

    shipments = db.relationship('Shipment', backref='customer', lazy=True)
    feedbacks = db.relationship('Feedback', backref='customer', lazy=True)

    def __repr__(self):
        return f"<Customer ID: {self.id}, User: {self.user.username}>"

class Driver(BaseModel):
    __tablename__ = 'drivers'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    license_number = db.Column(db.String(50), unique=True, nullable=False)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id', ondelete='SET NULL'), unique=True, nullable=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id', ondelete='SET NULL'), nullable=True)
    status = db.Column(db.String(50), default='Available')  # Available, Busy, Offline
    rating = db.Column(db.Float, default=5.0)

    shipments = db.relationship('Shipment', backref='driver', lazy=True)

    def __repr__(self):
        return f"<Driver ID: {self.id}, User: {self.user.username}>"

class Address(BaseModel):
    __tablename__ = 'addresses'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    label = db.Column(db.String(50), nullable=False)  # Home, Office, Warehouse
    address_line = db.Column(db.String(255), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(100), nullable=False)
    zip_code = db.Column(db.String(20), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    is_pickup = db.Column(db.Boolean, default=True)
    is_delivery = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Address {self.label}: {self.city}>"

class Shipment(BaseModel):
    __tablename__ = 'shipments'
    id = db.Column(db.Integer, primary_key=True)
    tracking_number = db.Column(db.String(50), unique=True, nullable=False)
    sender_name = db.Column(db.String(100), nullable=False)
    sender_phone = db.Column(db.String(20), nullable=False)
    sender_email = db.Column(db.String(100), nullable=False)
    
    pickup_address_line = db.Column(db.String(255), nullable=False)
    pickup_city = db.Column(db.String(100), nullable=False)
    pickup_state = db.Column(db.String(100), nullable=False)
    pickup_zip_code = db.Column(db.String(20), nullable=False)
    
    receiver_name = db.Column(db.String(100), nullable=False)
    receiver_phone = db.Column(db.String(20), nullable=False)
    receiver_address_line = db.Column(db.String(255), nullable=False)
    receiver_city = db.Column(db.String(100), nullable=False)
    receiver_state = db.Column(db.String(100), nullable=False)
    receiver_zip_code = db.Column(db.String(20), nullable=False)
    
    package_category = db.Column(db.String(50), nullable=False)  # Electronics, Documents, Apparel, Fragile, etc.
    package_description = db.Column(db.Text)
    package_weight = db.Column(db.Float, nullable=False)         # in kg
    package_dimensions = db.Column(db.String(50))                # e.g., 30x20x10 cm
    package_image_path = db.Column(db.String(255))               # path to uploaded product image
    weigh_at_pickup = db.Column(db.Boolean, default=False)       # whether package is weighed at pickup
    advance_paid = db.Column(db.Float, default=0.0)              # amount paid as advance (50% or flat 500)
    signature_path = db.Column(db.String(255))                   # path to pickup signature image file
    proof_image_path = db.Column(db.String(255), nullable=True)   # path to delivery proof product image
    delivery_signature_path = db.Column(db.String(255), nullable=True) # path to receiver e-signature
    delivered_at = db.Column(db.DateTime, nullable=True)          # exact delivery completion timestamp
    delivery_email_status = db.Column(db.String(50), default='Pending') # Sent, Failed, Pending
    fragile = db.Column(db.Boolean, default=False)
    insurance = db.Column(db.Boolean, default=False)
    declared_value = db.Column(db.Float, default=0.0)
    delivery_type = db.Column(db.String(50), nullable=False)     # Standard, Express
    pickup_date = db.Column(db.Date)
    delivery_date = db.Column(db.Date)
    shipping_cost = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default='Booked')          # Booked, Payment Pending, Confirmed, etc.
    
    qr_code_path = db.Column(db.String(255))
    barcode_path = db.Column(db.String(255))
    
    driver_id = db.Column(db.Integer, db.ForeignKey('drivers.id', ondelete='SET NULL'), nullable=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id', ondelete='SET NULL'), nullable=True)
    next_branch_id = db.Column(db.Integer, db.ForeignKey('branches.id', ondelete='SET NULL'), nullable=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id', ondelete='SET NULL'), nullable=True)
    
    # Explicit relationships for branch routing
    branch = db.relationship('Branch', foreign_keys=[branch_id], backref='local_shipments')
    next_branch = db.relationship('Branch', foreign_keys=[next_branch_id], backref='incoming_shipments')
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    history = db.relationship('ShipmentHistory', backref='shipment', lazy=True, cascade="all, delete-orphan")
    tracking_logs = db.relationship('TrackingLog', backref='shipment', lazy=True, cascade="all, delete-orphan")
    payment = db.relationship('Payment', backref='shipment', uselist=False, cascade="all, delete-orphan")
    invoice = db.relationship('Invoice', backref='shipment', uselist=False, cascade="all, delete-orphan")
    feedback = db.relationship('Feedback', backref='shipment', uselist=False, cascade="all, delete-orphan")

    @property
    def active_container(self):
        """Returns the active (uncompleted) ContainerTransfer this shipment is part of."""
        for ct in reversed(self.container_transfers):
            if ct.status != 'Completed' and ct.status != 'Cancelled':
                return ct
        return None

    @property
    def is_container_locked(self):
        """Returns True if the shipment is inside a locked active container."""
        active = self.active_container
        if active and active.is_locked and active.status != 'Completed':
            return True
        return self.status in [
            'Container Driver Assigned', 'Transfer Accepted', 'Received Shipment',
            'Shipment Received by Container Driver', 'In Transit', 'Arrived at Branch'
        ] and active is not None

    @property
    def current_container_id(self):
        """Returns the transfer code of the active or most recent container."""
        active = self.active_container
        if active:
            return active.transfer_code
        if self.container_transfers:
            return self.container_transfers[-1].transfer_code
        return None

    def __repr__(self):
        return f"<Shipment {self.tracking_number} - Status: {self.status}>"

# Many-to-Many Association Table for Containers and Shipments
container_shipments = db.Table('container_shipments',
    db.Column('container_id', db.Integer, db.ForeignKey('container_transfers.id', ondelete='CASCADE'), primary_key=True),
    db.Column('shipment_id', db.Integer, db.ForeignKey('shipments.id', ondelete='CASCADE'), primary_key=True),
    db.Column('added_at', db.DateTime, default=datetime.utcnow)
)

class ContainerTransfer(BaseModel):
    __tablename__ = 'container_transfers'
    id = db.Column(db.Integer, primary_key=True)
    transfer_code = db.Column(db.String(50), unique=True, nullable=False) # e.g., CONT-BOM-MAN-001
    from_branch_id = db.Column(db.Integer, db.ForeignKey('branches.id', ondelete='SET NULL'), nullable=True)
    to_branch_id = db.Column(db.Integer, db.ForeignKey('branches.id', ondelete='SET NULL'), nullable=True)
    driver_id = db.Column(db.Integer, db.ForeignKey('drivers.id', ondelete='SET NULL'), nullable=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id', ondelete='SET NULL'), nullable=True)
    
    # Lifecycle: Preparing -> Driver Assigned -> Accepted -> Received Shipment -> In Transit -> Arrived at Branch -> Completed
    status = db.Column(db.String(50), default='Preparing')
    is_locked = db.Column(db.Boolean, default=False)
    max_orders_capacity = db.Column(db.Integer, default=20)
    max_weight_capacity = db.Column(db.Float, default=5000.0) # in kg
    notes = db.Column(db.Text, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    assigned_at = db.Column(db.DateTime, nullable=True)
    accepted_at = db.Column(db.DateTime, nullable=True)
    received_at = db.Column(db.DateTime, nullable=True)        # Confirmed cargo loaded
    departed_at = db.Column(db.DateTime, nullable=True)        # Start highway transit
    arrived_at = db.Column(db.DateTime, nullable=True)         # Arrived at destination terminal
    branch_received_at = db.Column(db.DateTime, nullable=True)  # Destination manager received whole container
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    from_branch = db.relationship('Branch', foreign_keys=[from_branch_id], backref='dispatched_containers')
    to_branch = db.relationship('Branch', foreign_keys=[to_branch_id], backref='incoming_containers')
    driver = db.relationship('Driver', foreign_keys=[driver_id], backref='container_assignments')
    vehicle = db.relationship('Vehicle', foreign_keys=[vehicle_id])
    shipments = db.relationship('Shipment', secondary=container_shipments, lazy='subquery',
                                backref=db.backref('container_transfers', lazy=True))

    @property
    def total_orders(self):
        return len(self.shipments)

    @property
    def total_weight(self):
        return round(sum(s.package_weight for s in self.shipments), 2)

    @property
    def available_capacity(self):
        return max(0, self.max_orders_capacity - self.total_orders)

    @property
    def is_full(self):
        return self.total_orders >= self.max_orders_capacity

    def __repr__(self):
        return f"<ContainerTransfer {self.transfer_code} ({self.status}) - {self.total_orders} Orders>"

class ShipmentHistory(BaseModel):
    __tablename__ = 'shipment_history'
    id = db.Column(db.Integer, primary_key=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey('shipments.id', ondelete='CASCADE'), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    notes = db.Column(db.Text)
    updated_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    updated_by = db.relationship('User')

    def __repr__(self):
        return f"<ShipmentHistory {self.shipment_id} -> {self.status}>"

class TrackingLog(BaseModel):
    __tablename__ = 'tracking'
    id = db.Column(db.Integer, primary_key=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey('shipments.id', ondelete='CASCADE'), nullable=False)
    current_location = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(50), nullable=False)
    update_time = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<TrackingLog {self.shipment_id} - Location: {self.current_location}>"

class Payment(BaseModel):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey('shipments.id', ondelete='CASCADE'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)  # Cash on Delivery, Simulated Online
    payment_status = db.Column(db.String(50), nullable=False)  # Pending, Completed, Refunded
    transaction_id = db.Column(db.String(100), unique=True, nullable=True)
    cash_status = db.Column(db.String(50), default=None, nullable=True)  # 'In Hand with Driver', 'Submitted to Manager', 'Deposited with Manager', 'N/A'
    cash_collected_amount = db.Column(db.Float, default=0.0)
    cash_handed_over_at = db.Column(db.DateTime, nullable=True)
    cash_received_by_manager_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    cash_received_by_manager = db.relationship('User', foreign_keys=[cash_received_by_manager_id], lazy=True)
    collected_by_driver_id = db.Column(db.Integer, db.ForeignKey('drivers.id', ondelete='SET NULL'), nullable=True)
    collected_by_driver = db.relationship('Driver', foreign_keys=[collected_by_driver_id], lazy=True)
    digital_reference = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Payment {self.id} - Status: {self.payment_status}>"

class Invoice(BaseModel):
    __tablename__ = 'invoices'
    __table_args__ = {'extend_existing': True}
    id = db.Column(db.Integer, primary_key=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey('shipments.id', ondelete='CASCADE'), unique=True, nullable=False)
    invoice_number = db.Column(db.String(50), unique=True, nullable=False)
    subtotal = db.Column(db.Float, nullable=False)
    tax_amount = db.Column(db.Float, nullable=False)  # GST (e.g. 18%)
    total_amount = db.Column(db.Float, nullable=False)
    pdf_path = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Invoice {self.invoice_number}>"

class Feedback(BaseModel):
    __tablename__ = 'feedback'
    id = db.Column(db.Integer, primary_key=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey('shipments.id', ondelete='CASCADE'), unique=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id', ondelete='CASCADE'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Feedback Shipment: {self.shipment_id}, Rating: {self.rating}>"

class Notification(BaseModel):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    type = db.Column(db.String(50))  # info, success, warning, danger
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Notification {self.title} for User: {self.user_id}>"

class ActivityLog(BaseModel):
    __tablename__ = 'activity_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<ActivityLog {self.action} by User: {self.user_id}>"

class Setting(BaseModel):
    __tablename__ = 'settings'
    id = db.Column(db.Integer, primary_key=True)
    setting_key = db.Column(db.String(100), unique=True, nullable=False)
    setting_value = db.Column(db.Text)
    setting_type = db.Column(db.String(50), default='string')  # string, int, float, bool
    description = db.Column(db.String(255))

    def __repr__(self):
        return f"<Setting {self.setting_key}: {self.setting_value}>"
