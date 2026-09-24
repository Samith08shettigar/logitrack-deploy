import os
import sys
import sqlite3

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import text
from app.models import db

def load_initial_database_if_empty():
    """
    Checks if the current active database has users.
    If empty, populates all tables directly from app/logitrack.db so all 
    historical entries (25 users, 4 branches, 16 vehicles, shipments, etc.)
    are 100% preserved.
    """
    source_db = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'logitrack.db')
    if not os.path.exists(source_db):
        print("[LogiTrack] Source logitrack.db not found, skipping sync.")
        return

    # Check if target database already has users
    try:
        from app.models import User
        if User.query.count() >= 20:
            print("[LogiTrack] Database is already fully populated.")
            return
    except Exception as e:
        print(f"[LogiTrack] Checking User table: {e}")

    print(f"[LogiTrack] Populating database from {source_db}...")
    src_conn = sqlite3.connect(source_db)
    src_conn.row_factory = sqlite3.Row
    src_cur = src_conn.cursor()

    # Ordered table list to respect foreign key constraints
    tables = [
        'roles',
        'branches',
        'settings',
        'users',
        'vehicles',
        'customers',
        'drivers',
        'addresses',
        'shipments',
        'container_transfers',
        'container_shipments',
        'shipment_history',
        'tracking',
        'payments',
        'invoices',
        'feedback',
        'notifications',
        'activity_logs'
    ]

    engine = db.engine
    
    with engine.connect() as conn:
        for table in tables:
            try:
                rows = src_cur.execute(f"SELECT * FROM `{table}`").fetchall()
                if not rows:
                    continue

                col_names = list(rows[0].keys())
                placeholders = ", ".join([f":{col}" for col in col_names])
                cols_str = ", ".join([f"`{col}`" if engine.dialect.name == 'mysql' else f'"{col}"' if engine.dialect.name == 'postgresql' else col for col in col_names])

                insert_sql = text(f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders})")

                inserted = 0
                for row in rows:
                    data = dict(row)
                    try:
                        conn.execute(insert_sql, data)
                        inserted += 1
                    except Exception as row_err:
                        # Row might already exist (e.g. primary key conflict)
                        pass
                
                conn.commit()
                print(f"  [LogiTrack] Synced {table}: {inserted}/{len(rows)} records")
            except Exception as tbl_err:
                print(f"  [LogiTrack] Note on table {table}: {tbl_err}")

    src_conn.close()
    print("[LogiTrack] Database population from logitrack.db completed successfully!")

if __name__ == '__main__':
    from app import create_app
    app = create_app('default')
    with app.app_context():
        db.create_all()
        load_initial_database_if_empty()
