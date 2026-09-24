import os
from app import create_app
from app.models import db, Role, Branch
from seed import seed_database

# Determine configuration from environment
config_mode = os.environ.get('FLASK_CONFIG', os.environ.get('FLASK_ENV', 'production'))
if config_mode not in ['production', 'development', 'testing']:
    config_mode = 'production'

app = create_app(config_mode)

# Ensure database tables, all 4 branches, and basic seed records exist on startup
with app.app_context():
    try:
        db.create_all()
        # If no roles exist in database, run initial full seed
        if not Role.query.first():
            print("[LogiTrack] New database detected - initializing schema and seed records...")
            seed_database()
            print("[LogiTrack] Initial database setup completed successfully!")
        else:
            # Ensure all 4 core branches exist in active database
            core_branches = [
                {"name": "Mumbai Main Hub", "code": "BOM01", "address": "Andheri East, Off Western Express Highway", "city": "Mumbai", "state": "Maharashtra", "zip_code": "400069", "phone": "+91 22 5550 1122", "email": "mumbai@logitrack.com"},
                {"name": "Delhi Central Office", "code": "DEL01", "address": "Connaught Place, Block E", "city": "New Delhi", "state": "Delhi", "zip_code": "110001", "phone": "+91 11 5550 3344", "email": "delhi@logitrack.com"},
                {"name": "Bangalore Tech Branch", "code": "BLR01", "address": "Outer Ring Road, Kadubeesanahalli", "city": "Bangalore", "state": "Karnataka", "zip_code": "560103", "phone": "+91 80 5550 5566", "email": "bangalore@logitrack.com"},
                {"name": "Mangalore Coast Hub", "code": "MAN01", "address": "Hampankatta, Near Old Port", "city": "Mangalore", "state": "Karnataka", "zip_code": "575001", "phone": "+91 824 5550 7788", "email": "mangalore@logitrack.com"}
            ]
            added_branches = 0
            for b_info in core_branches:
                existing = Branch.query.filter((Branch.code == b_info["code"]) | (Branch.city == b_info["city"])).first()
                if not existing:
                    db.session.add(Branch(**b_info))
                    added_branches += 1
            if added_branches > 0:
                db.session.commit()
                print(f"[LogiTrack] Auto-synced {added_branches} missing branch(es) into active database.")
    except Exception as e:
        print(f"[LogiTrack] Note during database bootstrap: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
