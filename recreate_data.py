import os
from datetime import date
from app import create_app
from app.models import db, Role, User, Setting, Branch, Vehicle, Customer, Driver

def recreate_exact_data():
    app = create_app('default')
    with app.app_context():
        print("Resetting database...")
        db.session.remove()
        db.drop_all()
        db.create_all()
        print("Database schema created.")

        # 1. Seed Roles
        roles_data = {
            'Administrator': 'System Administrator with full access',
            'Customer': 'End user booking and tracking shipments',
            'Driver': 'Delivery personnel handling shipping routes',
            'Branch Manager': 'Branch administrator managing operations and employees'
        }
        roles = {}
        for role_name, desc in roles_data.items():
            role = Role(name=role_name, description=desc)
            db.session.add(role)
            roles[role_name] = role
        db.session.commit()
        print("Roles initialized.")

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
            setting = Setting(
                setting_key=key,
                setting_value=val_info[0],
                setting_type=val_info[1],
                description=val_info[2]
            )
            db.session.add(setting)
        db.session.commit()
        print("System settings initialized.")

        # 3. Create default admin user
        admin_user = User(
            username='admin',
            email='admin@logitrack.com',
            role_id=roles['Administrator'].id,
            is_active=True
        )
        admin_user.set_password('admin123')
        db.session.add(admin_user)
        db.session.commit()
        print("Created default admin user (admin / admin123).")

        # 4. Seed Branches
        branches_list = [
            {'name': 'Mumbai', 'code': 'BOM01', 'city': 'Mumbai', 'state': 'Maharashtra', 'zip': '400001', 'address': 'Mumbai Port Area'},
            {'name': 'Mangalore Central', 'code': 'MAN01', 'city': 'Mangalore', 'state': 'Karnataka', 'zip': '575001', 'address': 'Mangaluru Port Road'},
            {'name': 'Bangalore', 'code': 'BAN01', 'city': 'Bangalore', 'state': 'Karnataka', 'zip': '560001', 'address': 'Electronic City Phase 1'},
            {'name': 'Delhi', 'code': 'DEL01', 'city': 'Delhi', 'state': 'Delhi', 'zip': '110001', 'address': 'Okhla Industrial Area'}
        ]
        branches = {}
        for b in branches_list:
            branch = Branch(
                name=b['name'],
                code=b['code'],
                address=b['address'],
                city=b['city'],
                state=b['state'],
                zip_code=b['zip'],
                phone='+91 22 5550 9999',
                email=f"{b['city'].lower()}@logitrack.com"
            )
            db.session.add(branch)
            db.session.commit() # commit to get branch.id
            branches[b['city'].lower()] = branch
        print("Branches initialized successfully.")

        # 5. Seed Vehicles
        vehicles_list = [
            # Mumbai
            {'number': 'MH-22-EE-7852', 'type': 'Truck', 'capacity': 5000.0, 'city': 'mumbai'},
            {'number': 'MH-22-EX-1020', 'type': 'Van', 'capacity': 1500.0, 'city': 'mumbai'},
            {'number': 'MH-22-MX-3050', 'type': 'Electric Van', 'capacity': 1200.0, 'city': 'mumbai'},
            {'number': 'MH-22-JX-5484', 'type': 'Two Wheeler', 'capacity': 80.0, 'city': 'mumbai'},
            
            # Mangalore
            {'number': 'KA-19-EV-9999', 'type': 'Truck', 'capacity': 5000.0, 'city': 'mangalore'},
            {'number': 'KA-19-GG-7656', 'type': 'Van', 'capacity': 1500.0, 'city': 'mangalore'},
            {'number': 'KA-19-RE-5555', 'type': 'Electric Van', 'capacity': 1200.0, 'city': 'mangalore'},
            {'number': 'KA-19-TT-3253', 'type': 'Two Wheeler', 'capacity': 80.0, 'city': 'mangalore'},

            # Bangalore
            {'number': 'KA-53-DD-2645', 'type': 'Truck', 'capacity': 5000.0, 'city': 'bangalore'},
            {'number': 'KA-53-YY-8855', 'type': 'Van', 'capacity': 1500.0, 'city': 'bangalore'},
            {'number': 'KA-53-HH-5521', 'type': 'Electric Van', 'capacity': 1200.0, 'city': 'bangalore'},
            {'number': 'KA-53-FG-3532', 'type': 'Two Wheeler', 'capacity': 80.0, 'city': 'bangalore'},

            # Delhi
            {'number': 'DL-01-EV-5524', 'type': 'Truck', 'capacity': 5000.0, 'city': 'delhi'},
            {'number': 'DL-05-TQ-2678', 'type': 'Van', 'capacity': 1500.0, 'city': 'delhi'},
            {'number': 'DL-01-EE-3423', 'type': 'Electric Van', 'capacity': 1200.0, 'city': 'delhi'},
            {'number': 'DL-05-YY-6346', 'type': 'Two Wheeler', 'capacity': 80.0, 'city': 'delhi'}
        ]
        
        vehicles = {}
        for v in vehicles_list:
            veh = Vehicle(
                vehicle_number=v['number'],
                vehicle_type=v['type'],
                capacity=v['capacity'],
                fuel_type='Electric' if 'Electric' in v['type'] else ('Diesel' if v['type'] == 'Truck' else 'Petrol'),
                insurance_expiry=date.today(),
                maintenance_status='Good',
                availability='Available',
                branch_id=branches[v['city']].id
            )
            db.session.add(veh)
            db.session.commit()
            vehicles[v['number']] = veh
        print("Vehicles initialized successfully.")

        # 6. Seed Branch Managers
        managers_data = [
            {'username': 'Mumbai_Manager01', 'password': 'Mumbai@2022', 'city': 'mumbai'},
            {'username': 'Mangalore_Manager01', 'password': 'Mangalore@2022', 'city': 'mangalore'},
            {'username': 'Bangalore_Manager01', 'password': 'Bangalore@2022', 'city': 'bangalore'},
            {'username': 'Delhi_Manager01', 'password': 'Delhi@2022', 'city': 'delhi'}
        ]
        for m in managers_data:
            user = User(
                username=m['username'],
                email=f"{m['username'].lower()}@logitrack.com",
                role_id=roles['Branch Manager'].id,
                branch_id=branches[m['city']].id,
                is_active=True
            )
            user.set_password(m['password'])
            db.session.add(user)
        db.session.commit()
        print("Branch Managers created.")

        # 7. Seed regular Customer User
        user_samith = User(
            username='Samithbshettigar',
            email='samith@logitrack.com',
            role_id=roles['Customer'].id,
            is_active=True
        )
        user_samith.set_password('Samith@2022')
        db.session.add(user_samith)
        db.session.commit()
        
        cust_samith = Customer(
            user_id=user_samith.id,
            phone='+91 98888 77777',
            status='Active'
        )
        db.session.add(cust_samith)
        db.session.commit()
        print("User 'Samithbshettigar' created successfully.")

        # 8. Seed Drivers
        drivers_data = [
            # Mumbai
            {'username': 'Mum_driver01', 'password': 'Mumbai@2022', 'city': 'mumbai', 'lic': 'MH01-DRV-2026-001', 'phone': '+91 91111 22222', 'veh_num': 'MH-22-EE-7852'},
            {'username': 'Mum_driver02', 'password': 'Mumbai@2022', 'city': 'mumbai', 'lic': 'MH01-DRV-2026-002', 'phone': '+91 91111 33333', 'veh_num': 'MH-22-EX-1020'},
            {'username': 'Mum_driver03', 'password': 'Mumbai@2022', 'city': 'mumbai', 'lic': 'MH01-DRV-2026-003', 'phone': '+91 91111 44444', 'veh_num': 'MH-22-MX-3050'},
            {'username': 'Mum_driver04', 'password': 'Mumbai@2022', 'city': 'mumbai', 'lic': 'MH01-DRV-2026-004', 'phone': '+91 91111 55555', 'veh_num': 'MH-22-JX-5484'},
            
            # Bangalore
            {'username': 'Ban_driver01', 'password': 'Bangalore@2022', 'city': 'bangalore', 'lic': 'KA01-DRV-2026-001', 'phone': '+91 93333 11111', 'veh_num': 'KA-53-DD-2645'},
            {'username': 'Ban_driver02', 'password': 'Bangalore@2022', 'city': 'bangalore', 'lic': 'KA01-DRV-2026-002', 'phone': '+91 93333 22222', 'veh_num': 'KA-53-YY-8855'},
            {'username': 'Ban_driver03', 'password': 'Bangalore@2022', 'city': 'bangalore', 'lic': 'KA01-DRV-2026-003', 'phone': '+91 93333 33333', 'veh_num': 'KA-53-HH-5521'},
            {'username': 'Ban_driver04', 'password': 'Bangalore@2022', 'city': 'bangalore', 'lic': 'KA01-DRV-2026-004', 'phone': '+91 93333 44444', 'veh_num': 'KA-53-FG-3532'},
            
            # Delhi
            {'username': 'Del_driver01', 'password': 'Delhi@2022', 'city': 'delhi', 'lic': 'DL01-DRV-2026-001', 'phone': '+91 94444 11111', 'veh_num': 'DL-01-EV-5524'},
            {'username': 'Del_driver02', 'password': 'Delhi@2022', 'city': 'delhi', 'lic': 'DL01-DRV-2026-002', 'phone': '+91 94444 22222', 'veh_num': 'DL-05-TQ-2678'},
            {'username': 'Del_driver03', 'password': 'Delhi@2022', 'city': 'delhi', 'lic': 'DL01-DRV-2026-003', 'phone': '+91 94444 33333', 'veh_num': 'DL-01-EE-3423'},
            {'username': 'Del_driver04', 'password': 'Delhi@2022', 'city': 'delhi', 'lic': 'DL01-DRV-2026-004', 'phone': '+91 94444 44444', 'veh_num': 'DL-05-YY-6346'},
            
            # Mangalore
            {'username': 'Man_driver01', 'password': 'Mangalore@2022', 'city': 'mangalore', 'lic': 'KA19-DRV-2026-001', 'phone': '+91 92222 33333', 'veh_num': 'KA-19-EV-9999'},
            {'username': 'Man_driver02', 'password': 'Mangalore@2022', 'city': 'mangalore', 'lic': 'KA19-DRV-2026-002', 'phone': '+91 92222 44444', 'veh_num': 'KA-19-GG-7656'},
            {'username': 'Man_driver03', 'password': 'Mangalore@2022', 'city': 'mangalore', 'lic': 'KA19-DRV-2026-003', 'phone': '+91 92222 55555', 'veh_num': 'KA-19-RE-5555'},
            {'username': 'Man_driver04', 'password': 'Mangalore@2022', 'city': 'mangalore', 'lic': 'KA19-DRV-2026-004', 'phone': '+91 92222 66666', 'veh_num': 'KA-19-TT-3253'}
        ]
        for d in drivers_data:
            user = User(
                username=d['username'],
                email=f"{d['username'].lower()}@logitrack.com",
                role_id=roles['Driver'].id,
                branch_id=branches[d['city']].id,
                is_active=True
            )
            user.set_password(d['password'])
            db.session.add(user)
            db.session.commit() # commit to get user.id
            
            # Create Driver profile
            drv = Driver(
                user_id=user.id,
                phone=d['phone'],
                license_number=d['lic'],
                vehicle_id=vehicles[d['veh_num']].id,
                branch_id=branches[d['city']].id,
                status='Available',
                rating=5.0
            )
            db.session.add(drv)
            
            # Set vehicle availability to in use / occupied by the driver
            vehicles[d['veh_num']].availability = 'In Use'
            db.session.commit()
            
        print("Drivers initialized successfully.")
        print("\nAll requested data seeded exactly as defined!")

if __name__ == '__main__':
    recreate_exact_data()
