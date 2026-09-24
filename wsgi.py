import os
from app import create_app
from app.config import mask_database_url
from app.models import db
from app.db_loader import load_initial_database_if_empty, sync_postgresql_sequences

# Determine configuration from environment
config_mode = os.environ.get('FLASK_CONFIG', os.environ.get('FLASK_ENV', 'production'))
if config_mode not in ['production', 'development', 'testing']:
    config_mode = 'production'

app = create_app(config_mode)

# Ensure database tables exist and full database records (25 users, 4 branches, shipments, drivers) are loaded
with app.app_context():
    try:
        db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
        dialect = db.engine.dialect.name
        print(f"[LogiTrack Production Boot] Active DB Dialect: {dialect} | Target: {mask_database_url(db_uri)}")
        
        # 1. Create all tables in PostgreSQL
        db.create_all()
        print(f"[LogiTrack Production Boot] All schema tables verified in {dialect}.")
        
        # 2. Automatically seed original data if database is fresh
        load_initial_database_if_empty()
        
        # 3. Synchronize auto-increment sequences
        sync_postgresql_sequences()
        
        print("[LogiTrack Production Boot] Application database initialization completed successfully.")
    except Exception as e:
        print(f"[LogiTrack Production Boot Error] Database initialization note: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
