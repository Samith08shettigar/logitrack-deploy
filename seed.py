import sys
import io
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from datetime import datetime, timedelta
import random
from app import create_app
from app.models import db, Role, User, Branch, Vehicle, Customer, Driver, Address, Shipment, ShipmentHistory, TrackingLog, Payment, Invoice, Feedback, Notification, ActivityLog, Setting

def seed_database():
    app = create_app('default')
    with app.app_context():
        print("Initializing database...")
        db.create_all()
        print("Database tables created successfully!")

        # 1. Seed Roles
        roles_data = {
            'Administrator': 'System Administrator with full access',
            'Customer': 'End user booking and tracking shipments',
            'Driver': 'Delivery personnel handling shipping routes',
            'Branch Manager': 'Branch administrator managing operations and employees'
        }

        roles = {}
        for role_name, desc in roles_data.items():
            role = Role.query.filter_by(name=role_name).first()
            if not role:
                role = Role(name=role_name, description=desc)
                db.session.add(role)
                print(f"Added Role: {role_name}")
            roles[role_name] = role
        db.session.commit()

        # Reload roles from DB
        for role_name in roles_data:
            roles[role_name] = Role.query.filter_by(name=role_name).first()

        # 2. Seed System Settings
        settings_data = {
            'company_name': ('LogiTrack Logistics', 'string', 'Name of the logistics company'),
            'contact_email': ('support@logitrack.com', 'string', 'Contact email address'),
            'contact_phone': ('+1 (800) 555-0199', 'string', 'Contact phone number'),
            'currency_symbol': ('₹', 'string', 'Currency symbol used across system'),
            
            # Packaging rates per Category (INR/kg)
            'rate_packaging_clothes_garments': ('5.0', 'float', 'Packaging Rate: Clothes / Garments (INR/kg)'),
            'rate_packaging_books': ('8.0', 'float', 'Packaging Rate: Books (INR/kg)'),
            'rate_packaging_documents': ('10.0', 'float', 'Packaging Rate: Documents (INR/kg)'),
            'rate_packaging_electronics': ('15.0', 'float', 'Packaging Rate: Electronics (INR/kg)'),
            'rate_packaging_mobile_laptop': ('20.0', 'float', 'Packaging Rate: Mobile / Laptop (INR/kg)'),
            'rate_packaging_glass_items': ('20.0', 'float', 'Packaging Rate: Glass items (INR/kg)'),
            'rate_packaging_kitchen_items': ('10.0', 'float', 'Packaging Rate: Kitchen items (INR/kg)'),
            'rate_packaging_household_items': ('8.0', 'float', 'Packaging Rate: Household items (INR/kg)'),
            'rate_packaging_machinery_parts': ('20.0', 'float', 'Packaging Rate: Machinery parts (INR/kg)'),
            'rate_packaging_auto_spare_parts': ('15.0', 'float', 'Packaging Rate: Auto spare parts (INR/kg)'),
            'rate_packaging_furniture': ('20.0', 'float', 'Packaging Rate: Furniture (INR/kg)'),
            'rate_packaging_fruits_vegetables': ('8.0', 'float', 'Packaging Rate: Fruits / Vegetables (INR/kg)'),
            'rate_packaging_food_items': ('10.0', 'float', 'Packaging Rate: Food items (INR/kg)'),
            'rate_packaging_clothing_bundles': ('5.0', 'float', 'Packaging Rate: Clothing bundles (INR/kg)'),
            'rate_packaging_industrial_goods': ('25.0', 'float', 'Packaging Rate: Industrial goods (INR/kg)'),
            'rate_packaging_other': ('10.0', 'float', 'Packaging Rate: Other/Custom items (INR/kg)')
        }

        for key, val_info in settings_data.items():
            setting = Setting.query.filter_by(setting_key=key).first()
            if not setting:
                setting = Setting(
                    setting_key=key,
                    setting_value=val_info[0],
                    setting_type=val_info[1],
                    description=val_info[2]
                )
                db.session.add(setting)
                print(f"Added Setting: {key} = {val_info[0]}")
        db.session.commit()

        # 3. Seed Branches
        branches_data = [
            Branch(name="Mumbai Main Hub", code="BOM01", address="Andheri East, Off Western Express Highway", city="Mumbai", state="Maharashtra", zip_code="400069", phone="+91 22 5550 1122", email="mumbai@logitrack.com"),
            Branch(name="Delhi Central Office", code="DEL01", address="Connaught Place, Block E", city="New Delhi", state="Delhi", zip_code="110001", phone="+91 11 5550 3344", email="delhi@logitrack.com"),
            Branch(name="Bangalore Tech Branch", code="BLR01", address="Outer Ring Road, Kadubeesanahalli", city="Bangalore", state="Karnataka", zip_code="560103", phone="+91 80 5550 5566", email="bangalore@logitrack.com")
        ]

        branches = []
        for b_data in branches_data:
            existing = Branch.query.filter_by(code=b_data.code).first()
            if not existing:
                db.session.add(b_data)
                print(f"Added Branch: {b_data.name}")
                branches.append(b_data)
            else:
                branches.append(existing)
        db.session.commit()

        # 4. Seed Vehicles
        vehicles_data = [
            Vehicle(vehicle_number="MH-02-CP-8822", vehicle_type="Truck", capacity=5000.0, fuel_type="Diesel", insurance_expiry=datetime.now().date() + timedelta(days=200), maintenance_status="Good", availability="Available", branch_id=branches[0].id),
            Vehicle(vehicle_number="DL-03-CB-1199", vehicle_type="Van", capacity=1500.0, fuel_type="Petrol", insurance_expiry=datetime.now().date() + timedelta(days=80), maintenance_status="Good", availability="Available", branch_id=branches[1].id),
            Vehicle(vehicle_number="KA-03-MJ-7744", vehicle_type="Electric Van", capacity=1200.0, fuel_type="Electric", insurance_expiry=datetime.now().date() + timedelta(days=320), maintenance_status="Good", availability="Available", branch_id=branches[2].id),
            Vehicle(vehicle_number="MH-02-AX-3344", vehicle_type="Two-Wheeler", capacity=80.0, fuel_type="Electric", insurance_expiry=datetime.now().date() + timedelta(days=150), maintenance_status="Good", availability="Available", branch_id=branches[0].id)
        ]

        vehicles = []
        for v_data in vehicles_data:
            existing = Vehicle.query.filter_by(vehicle_number=v_data.vehicle_number).first()
            if not existing:
                db.session.add(v_data)
                print(f"Added Vehicle: {v_data.vehicle_number}")
                vehicles.append(v_data)
            else:
                vehicles.append(existing)
        db.session.commit()

        # 5. Seed Core Admin User
        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            admin_user = User(
                username='admin',
                email='admin@logitrack.com',
                role_id=roles['Administrator'].id,
                is_active=True
            )
            admin_user.set_password('admin123')
            db.session.add(admin_user)
            print("Added User: admin (admin@logitrack.com / admin123)")
        db.session.commit()

        # 6. Seed Branch Manager User
        manager_user = User.query.filter_by(username='manager_bom').first()
        if not manager_user:
            manager_user = User(
                username='manager_bom',
                email='manager@logitrack.com',
                role_id=roles['Branch Manager'].id,
                branch_id=branches[0].id,
                is_active=True
            )
            manager_user.set_password('manager123')
            db.session.add(manager_user)
            print("Added User: manager_bom (manager@logitrack.com / manager123)")
        else:
            # Update existing to have branch_id if not set
            if not manager_user.branch_id:
                manager_user.branch_id = branches[0].id
                print("Updated existing manager_bom user with Mumbai branch.")
        db.session.commit()

        # 7. Seed Driver User & Profile
        driver_user = User.query.filter_by(username='driver_rajesh').first()
        driver_profile = None
        if not driver_user:
            driver_user = User(
                username='driver_rajesh',
                email='driver@logitrack.com',
                role_id=roles['Driver'].id,
                is_active=True
            )
            driver_user.set_password('driver123')
            db.session.add(driver_user)
            db.session.commit()

            driver_profile = Driver(
                user_id=driver_user.id,
                phone="+91 98765 43210",
                license_number="DL-MH-20230008899",
                vehicle_id=vehicles[0].id,
                branch_id=branches[0].id,
                status="Available",
                rating=4.8
            )
            db.session.add(driver_profile)
            
            # Update vehicle status
            vehicles[0].availability = 'In Use'
            
            print("Added User: driver_rajesh (driver@logitrack.com / driver123) with Profile")
        else:
            driver_profile = Driver.query.filter_by(user_id=driver_user.id).first()
        db.session.commit()

        # Additional driver for another branch
        driver_user2 = User.query.filter_by(username='driver_amit').first()
        driver_profile2 = None
        if not driver_user2:
            driver_user2 = User(
                username='driver_amit',
                email='driver2@logitrack.com',
                role_id=roles['Driver'].id,
                is_active=True
            )
            driver_user2.set_password('driver123')
            db.session.add(driver_user2)
            db.session.commit()

            driver_profile2 = Driver(
                user_id=driver_user2.id,
                phone="+91 99887 76655",
                license_number="DL-DL-20240007711",
                vehicle_id=vehicles[1].id,
                branch_id=branches[1].id,
                status="Available",
                rating=4.5
            )
            db.session.add(driver_profile2)
            vehicles[1].availability = 'In Use'
            print("Added User: driver_amit (driver2@logitrack.com / driver123)")
        else:
            driver_profile2 = Driver.query.filter_by(user_id=driver_user2.id).first()
        db.session.commit()

        # 8. Seed Customer User & Profile
        customer_user = User.query.filter_by(username='customer_rahul').first()
        customer_profile = None
        if not customer_user:
            customer_user = User(
                username='customer_rahul',
                email='customer@logitrack.com',
                role_id=roles['Customer'].id,
                is_active=True
            )
            customer_user.set_password('customer123')
            db.session.add(customer_user)
            db.session.commit()

            customer_profile = Customer(
                user_id=customer_user.id,
                phone="+91 91234 56789",
                status="Active",
                loyalty_points=120
            )
            db.session.add(customer_profile)
            print("Added User: customer_rahul (customer@logitrack.com / customer123) with Profile")
            
            # Seed Saved Addresses for this customer
            addresses = [
                Address(user_id=customer_user.id, label="Home (Mumbai)", address_line="Apt 402, Sea Breeze, Bandra West", city="Mumbai", state="Maharashtra", zip_code="400050", phone="+91 91234 56789", is_pickup=True, is_delivery=True),
                Address(user_id=customer_user.id, label="Office (Bangalore)", address_line="Building 3B, RMZ Ecospace, Bellandur", city="Bangalore", state="Karnataka", zip_code="560103", phone="+91 91234 56789", is_pickup=True, is_delivery=True),
                Address(user_id=customer_user.id, label="Branch Ware (Delhi)", address_line="Gali No. 4, Industrial Area, Okhla", city="Delhi", state="Delhi", zip_code="110020", phone="+91 91234 56789", is_pickup=True, is_delivery=True)
            ]
            for addr in addresses:
                db.session.add(addr)
        else:
            customer_profile = Customer.query.filter_by(user_id=customer_user.id).first()
        db.session.commit()

        # 9. Seed Sample Shipments to populate charts/analytics
        # Let's generate a list of historical shipments for past 4 months
        shipment_statuses = ['Booked', 'Confirmed', 'In Transit', 'Out For Delivery', 'Delivered', 'Completed', 'Cancelled']
        categories = ['Electronics', 'Documents', 'Apparel', 'Fragile Goods', 'Hardware']
        
        # We need historical dates
        now = datetime.now()
        
        # Only seed shipments if none exist
        if Shipment.query.count() == 0 and customer_profile:
            print("Generating historical shipment data for dashboards...")
            
            # Completed & Delivered Shipments (Past months for revenue metrics)
            for i in range(25):
                months_ago = random.randint(0, 3)
                days_ago = random.randint(1, 28)
                booking_date = now - timedelta(days=(months_ago * 30 + days_ago))
                
                track_num = f"LT-{booking_date.strftime('%y%m%d')}-{random.randint(1000, 9999)}"
                weight = round(random.uniform(0.5, 30.0), 2)
                cost = round(20.0 + weight * 5.5 + (15.0 if random.choice([True, False]) else 0.0), 2)
                
                # Alternate standard/express
                dtype = random.choice(['Standard', 'Express'])
                if dtype == 'Express':
                    cost *= 1.5
                cost = round(cost, 2)
                
                sh_status = 'Completed' if months_ago > 0 else random.choice(['Delivered', 'Completed'])
                
                # Pick driver and branch
                assigned_drv = driver_profile if random.choice([True, False]) else driver_profile2
                assigned_br = branches[0] if assigned_drv == driver_profile else branches[1]

                shipment = Shipment(
                    tracking_number=track_num,
                    sender_name="Rahul Sharma",
                    sender_phone="+91 91234 56789",
                    sender_email="customer@logitrack.com",
                    pickup_address_line="Apt 402, Sea Breeze, Bandra West",
                    pickup_city="Mumbai",
                    pickup_state="Maharashtra",
                    pickup_zip_code="400050",
                    receiver_name=f"Receiver Client {i}",
                    receiver_phone=f"+91 98111 {random.randint(10000, 99999)}",
                    receiver_address_line=f"{random.randint(1, 100)}, Market Street",
                    receiver_city="Delhi" if assigned_br.code == "DEL01" else "Bangalore",
                    receiver_state="Delhi" if assigned_br.code == "DEL01" else "Karnataka",
                    receiver_zip_code="110001" if assigned_br.code == "DEL01" else "560001",
                    package_category=random.choice(categories),
                    package_description="Sample package containing documents/items",
                    package_weight=weight,
                    package_dimensions="20x15x10 cm",
                    fragile=random.choice([True, False]),
                    insurance=random.choice([True, False]),
                    delivery_type=dtype,
                    pickup_date=booking_date.date(),
                    delivery_date=(booking_date + timedelta(days=random.randint(2, 5))).date(),
                    shipping_cost=cost,
                    status=sh_status,
                    driver_id=assigned_drv.id,
                    branch_id=assigned_br.id,
                    customer_id=customer_profile.id,
                    created_at=booking_date,
                    updated_at=booking_date + timedelta(days=3)
                )
                db.session.add(shipment)
                db.session.commit() # commit to get shipment.id

                # Invoice
                subtotal = round(cost / 1.18, 2)
                tax = round(cost - subtotal, 2)
                inv = Invoice(
                    shipment_id=shipment.id,
                    invoice_number=f"INV-{booking_date.strftime('%Y%m')}-{shipment.id:04d}",
                    subtotal=subtotal,
                    tax_amount=tax,
                    total_amount=cost,
                    created_at=booking_date
                )
                db.session.add(inv)

                # Payment
                pay = Payment(
                    shipment_id=shipment.id,
                    amount=cost,
                    payment_method=random.choice(['Cash on Delivery', 'Simulated Online']),
                    payment_status='Completed',
                    transaction_id=f"TXN-{random.randint(10000000, 99999999)}",
                    created_at=booking_date
                )
                db.session.add(pay)

                # Shipment History & Tracking checkpoints
                hist1 = ShipmentHistory(shipment_id=shipment.id, status='Booked', notes='Shipment booked online', updated_at=booking_date)
                hist2 = ShipmentHistory(shipment_id=shipment.id, status='Confirmed', notes='Payment confirmed and approved', updated_at=booking_date + timedelta(hours=2))
                hist3 = ShipmentHistory(shipment_id=shipment.id, status='Driver Assigned', notes=f'Driver {assigned_drv.user.username} assigned', updated_at=booking_date + timedelta(days=1))
                hist4 = ShipmentHistory(shipment_id=shipment.id, status=sh_status, notes='Package successfully delivered to receiver', updated_at=booking_date + timedelta(days=3))
                db.session.add_all([hist1, hist2, hist3, hist4])

                track1 = TrackingLog(shipment_id=shipment.id, current_location="Mumbai Hub", status='Booked', description="Shipment booked", update_time=booking_date)
                track2 = TrackingLog(shipment_id=shipment.id, current_location="Mumbai Hub", status='Driver Assigned', description="Package handed over to driver", update_time=booking_date + timedelta(days=1))
                track3 = TrackingLog(shipment_id=shipment.id, current_location=shipment.receiver_city, status=sh_status, description="Delivered and signature captured", update_time=booking_date + timedelta(days=3))
                db.session.add_all([track1, track2, track3])

                # Feedbacks for some completed shipments
                if sh_status == 'Completed' and random.choice([True, False]):
                    feed = Feedback(
                        shipment_id=shipment.id,
                        customer_id=customer_profile.id,
                        rating=random.choice([4, 5]),
                        comment="Fast delivery, package was in perfect condition!",
                        submitted_at=booking_date + timedelta(days=4)
                    )
                    db.session.add(feed)
            
            # Active/Pending Deliveries
            active_statuses = ['Booked', 'Confirmed', 'In Transit', 'Out For Delivery']
            for i, st in enumerate(active_statuses):
                booking_date = now - timedelta(days=i)
                track_num = f"LT-{booking_date.strftime('%y%m%d')}-{random.randint(1000, 9999)}"
                weight = round(random.uniform(1.0, 10.0), 2)
                cost = round(20.0 + weight * 5.5, 2)
                
                shipment = Shipment(
                    tracking_number=track_num,
                    sender_name="Rahul Sharma",
                    sender_phone="+91 91234 56789",
                    sender_email="customer@logitrack.com",
                    pickup_address_line="Apt 402, Sea Breeze, Bandra West",
                    pickup_city="Mumbai",
                    pickup_state="Maharashtra",
                    pickup_zip_code="400050",
                    receiver_name=f"Receiver Active {i}",
                    receiver_phone="+91 98888 12345",
                    receiver_address_line="Flat 102, Green Meadows",
                    receiver_city="Bangalore",
                    receiver_state="Karnataka",
                    receiver_zip_code="560103",
                    package_category="Electronics",
                    package_weight=weight,
                    delivery_type="Standard",
                    shipping_cost=cost,
                    status=st,
                    customer_id=customer_profile.id,
                    created_at=booking_date
                )
                if st != 'Booked':
                    shipment.branch_id = branches[0].id
                if st == 'In Transit':
                    shipment.next_branch_id = branches[2].id
                if st in ['In Transit', 'Out For Delivery']:
                    shipment.driver_id = driver_profile.id
                    driver_profile.status = 'Busy'
                
                db.session.add(shipment)
                db.session.commit()

                # Add history
                hist = ShipmentHistory(shipment_id=shipment.id, status=st, notes=f'Shipment marked as {st}', updated_at=booking_date)
                db.session.add(hist)
                
                # Payment
                pay = Payment(
                    shipment_id=shipment.id,
                    amount=cost,
                    payment_method='Simulated Online',
                    payment_status='Completed' if st != 'Booked' else 'Pending',
                    created_at=booking_date
                )
                db.session.add(pay)

            # Notifications
            notifs = [
                Notification(user_id=customer_user.id, title="Welcome to LogiTrack!", message="Thank you for registering with LogiTrack. Use the customer panel to book and track packages.", type="info"),
                Notification(user_id=admin_user.id, title="System Initialized", message="The database seeding process has populated sample drivers, branches, and active shipments.", type="success")
            ]
            db.session.add_all(notifs)
            
            # Activity logs
            logs = [
                ActivityLog(user_id=admin_user.id, action="DB Seed", details="Database initialized and populated with seed records", ip_address="127.0.0.1"),
                ActivityLog(user_id=customer_user.id, action="Register", details="Registered customer account", ip_address="127.0.0.1")
            ]
            db.session.add_all(logs)
            
            db.session.commit()
            print("Successfully generated all historical and mock data!")
        
        print("Database Seeding Completed Successfully!")

if __name__ == '__main__':
    seed_database()
