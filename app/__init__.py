import os
from flask import Flask, render_template, session, g
from app.config import config_by_name
from app.models import db, User, Role

def create_app(config_name='default'):
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(config_by_name[config_name])
    
    # Initialize extensions
    db.init_app(app)
    
    # Configure custom session if needed (Flask's built-in session is secure with cookie-signer)
    # We will use Flask's default session with cookie-signing since it does not require external storage services
    
    # Create upload directories
    upload_paths = [
        os.path.join(app.config['UPLOAD_FOLDER'], 'signatures'),
        os.path.join(app.config['UPLOAD_FOLDER'], 'proofs'),
        os.path.join(app.config['UPLOAD_FOLDER'], 'qrcodes'),
        os.path.join(app.config['UPLOAD_FOLDER'], 'barcodes'),
        os.path.join(app.config['UPLOAD_FOLDER'], 'invoices'),
        os.path.join(app.config['UPLOAD_FOLDER'], 'products')
    ]
    for path in upload_paths:
        os.makedirs(path, exist_ok=True)
        
    # Hook for loading user into flask.g before every request
    @app.before_request
    def load_logged_in_user():
        user_id = session.get('user_id')
        if user_id is None:
            g.user = None
        else:
            # Look up the user in database
            g.user = db.session.get(User, user_id)
            # If user is inactive or deleted, force logout
            if g.user and not g.user.is_active:
                session.clear()
                g.user = None

    # Context processor to make globals available in templates
    @app.context_processor
    def inject_globals():
        from datetime import datetime
        from app.utils import get_packaging_categories
        return dict(current_user=g.user, datetime=datetime, get_packaging_categories=get_packaging_categories)

    # Register Error Handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        # We can log error if needed
        return render_template('errors/500.html'), 500

    # Main routing / Public Site
    @app.route('/')
    def index():
        from app.models import Shipment
        return render_template('landing.html')

    # Register Blueprints
    from app.blueprints.auth import auth_bp
    from app.blueprints.admin import admin_bp
    from app.blueprints.customer import customer_bp
    from app.blueprints.driver import driver_bp
    from app.blueprints.branch import branch_bp
    from app.blueprints.shipment import shipment_bp
    from app.blueprints.payment import payment_bp
    from app.blueprints.reports import reports_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(customer_bp, url_prefix='/customer')
    app.register_blueprint(driver_bp, url_prefix='/driver')
    app.register_blueprint(branch_bp, url_prefix='/branch')
    app.register_blueprint(shipment_bp, url_prefix='/shipment')
    app.register_blueprint(payment_bp, url_prefix='/payment')
    app.register_blueprint(reports_bp, url_prefix='/reports')

    with app.app_context():
        try:
            from sqlalchemy import inspect, text
            inspector = inspect(db.engine)
            if 'payments' in inspector.get_table_names():
                cols = [c['name'] for c in inspector.get_columns('payments')]
                if 'cash_status' not in cols:
                    db.session.execute(text("ALTER TABLE payments ADD COLUMN cash_status VARCHAR(50)"))
                if 'cash_collected_amount' not in cols:
                    db.session.execute(text("ALTER TABLE payments ADD COLUMN cash_collected_amount FLOAT DEFAULT 0.0"))
                if 'cash_handed_over_at' not in cols:
                    db.session.execute(text("ALTER TABLE payments ADD COLUMN cash_handed_over_at DATETIME"))
                if 'cash_received_by_manager_id' not in cols:
                    db.session.execute(text("ALTER TABLE payments ADD COLUMN cash_received_by_manager_id INTEGER"))
                if 'collected_by_driver_id' not in cols:
                    db.session.execute(text("ALTER TABLE payments ADD COLUMN collected_by_driver_id INTEGER"))
                if 'digital_reference' not in cols:
                    db.session.execute(text("ALTER TABLE payments ADD COLUMN digital_reference VARCHAR(100)"))
                db.session.commit()
        except Exception:
            db.session.rollback()

    return app
