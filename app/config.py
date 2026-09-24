import os

def format_database_url(url: str) -> str:
    """
    Ensures the database connection URL is formatted properly for SQLAlchemy 2.0+ and psycopg2.
    Render and other cloud providers often provide URLs starting with 'postgres://',
    which must be normalized to 'postgresql://'.
    """
    if not url:
        return url
    url = url.strip()
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
    return url

def mask_database_url(url: str) -> str:
    """
    Safely masks database credentials for logging without exposing passwords.
    """
    if not url:
        return "None"
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.password:
            netloc = parsed.netloc.replace(f":{parsed.password}@", ":****@")
            return f"{parsed.scheme}://{netloc}{parsed.path}"
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    except Exception:
        return "[MASKED_DATABASE_URL]"

class Config:
    # Basic Flask Settings
    SECRET_KEY = os.environ.get('SECRET_KEY', 'logitrack_super_secret_key_129847320')
    DEBUG = False
    TESTING = False

    # Database Configuration Base
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }

    # Session Management
    SESSION_TYPE = 'filesystem'
    SESSION_PERMANENT = False
    SESSION_USE_SIGNER = True

    # Security Settings
    SESSION_COOKIE_SECURE = False
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

def get_database_url() -> str:
    """
    Auto-detects the PostgreSQL database URL from all possible Render and cloud environment variables.
    Supports: DATABASE_URL, INTERNAL_DATABASE_URL, EXTERNAL_DATABASE_URL,
    POSTGRES_URL, POSTGRESQL_URL, LOGISTIC_DB_URL, DB_URL.
    """
    candidate_keys = [
        'DATABASE_URL',
        'INTERNAL_DATABASE_URL',
        'EXTERNAL_DATABASE_URL',
        'POSTGRES_URL',
        'POSTGRESQL_URL',
        'LOGISTIC_DB_URL',
        'LOGISTICS_DB_URL',
        'DB_URL'
    ]
    for key in candidate_keys:
        val = os.environ.get(key)
        if val and val.strip():
            return format_database_url(val.strip())
    return None

class DevelopmentConfig(Config):
    DEBUG = True
    db_uri = get_database_url()
    if db_uri:
        SQLALCHEMY_DATABASE_URI = db_uri
    else:
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'logitrack.db')

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

class ProductionConfig(Config):
    # Enable secure session cookies when running behind HTTPS in production
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() in ['true', '1']
    
    db_uri = get_database_url()
    if db_uri:
        SQLALCHEMY_DATABASE_URI = db_uri
    else:
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'logitrack.db')

config_by_name = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
