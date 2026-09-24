import os

class Config:
    # Basic Flask Settings
    SECRET_KEY = os.environ.get('SECRET_KEY', 'logitrack_super_secret_key_129847320')
    DEBUG = False
    TESTING = False

    # Database Configuration
    # Supports SQLite (default), PostgreSQL (Render/Railway), and MySQL
    # Render and Railway PostgreSQL URLs often start with 'postgres://' which SQLAlchemy 2.0+ requires as 'postgresql://'
    _raw_db_url = os.environ.get('DATABASE_URL')
    if _raw_db_url and _raw_db_url.startswith('postgres://'):
        _raw_db_url = _raw_db_url.replace('postgres://', 'postgresql://', 1)

    SQLALCHEMY_DATABASE_URI = _raw_db_url or (
        'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'logitrack.db')
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Session Management
    SESSION_TYPE = 'filesystem'
    SESSION_PERMANENT = False
    SESSION_USE_SIGNER = True

    # Security Settings
    SESSION_COOKIE_SECURE = False  # Controlled via environment or ProductionConfig
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # File Upload Configuration
    UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static', 'uploads')
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB Max upload limit
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}

    # SMTP Configuration for Email
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', 'notifications@logitrack-logistics.com')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', 'your-smtp-password')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'LogiTrack Notifications <notifications@logitrack-logistics.com>')

class DevelopmentConfig(Config):
    DEBUG = True

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

class ProductionConfig(Config):
    # Enable secure session cookies when running behind HTTPS in production
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() in ['true', '1']

config_by_name = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
