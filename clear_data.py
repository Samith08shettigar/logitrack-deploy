import os
from app import create_app
from app.models import db, Role, User, Setting

def clear_all_data():
    app = create_app('default')
    with app.app_context():
        print("Cleaning up database tables...")
        try:
            db.session.remove()
            db.drop_all()
            print("Successfully dropped all database tables.")
        except Exception as e:
            print(f"Error dropping tables: {e}")
            
        db.create_all()
        print("Successfully created empty tables from schemas.")

        # 1. Seed Roles (required for system permissions and login roles)
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

        # 2. Seed System Settings (required for shipment cost calculations)
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
        print("System cost settings initialized.")

        # 3. Seed single Administrator Account (required to login and add new data)
        admin_user = User(
            username='admin',
            email='admin@logitrack.com',
            role_id=roles['Administrator'].id,
            is_active=True
        )
        admin_user.set_password('admin123')
        db.session.add(admin_user)
        db.session.commit()
        print("Default admin user created: admin / admin123")
        
        print("\nSuccess: Database cleared and ready for your data input!")

if __name__ == '__main__':
    clear_all_data()
