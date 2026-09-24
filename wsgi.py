import os
from app import create_app
from app.models import db, Role
from seed import seed_database

# Determine configuration from environment
config_mode = os.environ.get('FLASK_CONFIG', os.environ.get('FLASK_ENV', 'production'))
if config_mode not in ['production', 'development', 'testing']:
    config_mode = 'production'

app = create_app(config_mode)

# Ensure database tables and basic seed records exist on startup
with app.app_context():
    try:
        db.create_all()
        # If no roles exist in database, seed initial data (Admin, Settings, Roles, Branches)
        if not Role.query.first():
            print("[LogiTrack] New database detected - initializing schema and seed records...")
            seed_database()
            print("[LogiTrack] Initial database setup completed successfully!")
    except Exception as e:
        print(f"[LogiTrack] Note during database bootstrap: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
