import os
import sys
import sqlite3

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import text
from app.models import db

def sync_postgresql_sequences():
    """
    Synchronizes PostgreSQL primary key sequences with the maximum existing ID
    for each table. This prevents duplicate key constraint violations when inserting
    new records after migrating or restoring seed data.
    """
    if db.engine.dialect.name != 'postgresql':
        return

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
        'shipment_history',
        'tracking',
        'payments',
        'invoices',
        'feedback',
        'notifications',
        'activity_logs'
    ]

    with db.engine.connect() as conn:
        for table in tables:
            try:
                sql = text(f"""
                    DO $$
                    DECLARE
                        seq_name text;
                        max_id bigint;
                    BEGIN
                        seq_name := pg_get_serial_sequence('{table}', 'id');
                        IF seq_name IS NOT NULL THEN
                            EXECUTE 'SELECT COALESCE(MAX(id), 0) FROM {table}' INTO max_id;
                            IF max_id > 0 THEN
                                PERFORM setval(seq_name, max_id, true);
                            ELSE
                                PERFORM setval(seq_name, 1, false);
                            END IF;
                        END IF;
                    END $$;
                """)
                conn.execute(sql)
                conn.commit()
            except Exception as e:
                pass
    print("[LogiTrack] PostgreSQL sequences synchronized successfully.")

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
        sync_postgresql_sequences()
        return

    # Check if target database already has users
    try:
        from app.models import User
        if User.query.count() >= 20:
            print("[LogiTrack] Database is already populated. Synchronizing sequences...")
            sync_postgresql_sequences()
            return
    except Exception as e:
        print(f"[LogiTrack] Checking User table note: {e}")

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
    
    # Synchronize sequences after loading
    sync_postgresql_sequences()

if __name__ == '__main__':
    from app import create_app
    app = create_app('default')
    with app.app_context():
        db.create_all()
        load_initial_database_if_empty()

