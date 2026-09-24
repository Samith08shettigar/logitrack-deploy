import os
from app import create_app
from app.models import db
from app.db_loader import load_initial_database_if_empty

# Determine configuration from environment
config_mode = os.environ.get('FLASK_CONFIG', os.environ.get('FLASK_ENV', 'production'))
if config_mode not in ['production', 'development', 'testing']:
    config_mode = 'production'

app = create_app(config_mode)

# Ensure database tables exist and full database records (25 users, 4 branches, shipments, drivers) are loaded
with app.app_context():
    try:
        db.create_all()
        # Automatically load all original database entries if not already present
        load_initial_database_if_empty()
    except Exception as e:
        print(f"[LogiTrack] Database initialization note: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
