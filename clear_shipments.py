import os
import glob
from app import create_app
from app.models import (
    db, Shipment, Payment, Feedback, Invoice, 
    ShipmentHistory, TrackingLog, ContainerTransfer, 
    container_shipments, Driver, Vehicle, Notification, Customer
)

def clear_shipping_data():
    app = create_app('default')
    with app.app_context():
        print("Starting cleanup of shipments, payments, and feedback...")

        # 1. Clear Feedback
        num_feedback = Feedback.query.delete()
        print(f"Deleted {num_feedback} Feedback records.")

        # 2. Clear Invoices
        num_invoices = Invoice.query.delete()
        print(f"Deleted {num_invoices} Invoice records.")

        # 3. Clear Payments
        num_payments = Payment.query.delete()
        print(f"Deleted {num_payments} Payment records.")

        # 4. Clear Tracking Logs
        num_tracking = TrackingLog.query.delete()
        print(f"Deleted {num_tracking} TrackingLog records.")

        # 5. Clear Shipment Histories
        num_history = ShipmentHistory.query.delete()
        print(f"Deleted {num_history} ShipmentHistory records.")

        # 6. Clear Container Shipments association & Container Transfers
        db.session.execute(container_shipments.delete())
        num_containers = ContainerTransfer.query.delete()
        print(f"Deleted {num_containers} ContainerTransfer records.")

        # 7. Clear Shipments
        num_shipments = Shipment.query.delete()
        print(f"Deleted {num_shipments} Shipment records.")

        # 8. Clear Notifications (associated with shipments/payments)
        num_notifications = Notification.query.delete()
        print(f"Deleted {num_notifications} Notification records.")

        # 9. Reset Customer loyalty points
        for customer in Customer.query.all():
            customer.loyalty_points = 0

        # 10. Reset Driver statuses to 'Available'
        for driver in Driver.query.all():
            driver.status = 'Available'
        print("Reset all Drivers to 'Available'.")

        # 11. Reset Vehicle availability to 'Available' (if not under repair/service)
        for vehicle in Vehicle.query.all():
            if vehicle.maintenance_status == 'Good':
                vehicle.availability = 'Available'
        print("Reset all Vehicle availability.")

        db.session.commit()
        print("Database changes committed successfully.")

        # 12. Clean up uploaded shipment files (barcodes, qrcodes, invoices, proofs, signatures, products)
        upload_dirs = [
            'barcodes',
            'invoices',
            'products',
            'proofs',
            'qrcodes',
            'signatures'
        ]
        upload_base = app.config.get('UPLOAD_FOLDER', os.path.join(os.path.dirname(__file__), 'app', 'static', 'uploads'))
        deleted_files_count = 0
        for udir in upload_dirs:
            folder_path = os.path.join(upload_base, udir)
            if os.path.exists(folder_path):
                for f in glob.glob(os.path.join(folder_path, '*')):
                    if os.path.isfile(f):
                        try:
                            os.remove(f)
                            deleted_files_count += 1
                        except Exception as e:
                            print(f"Could not remove file {f}: {e}")
        print(f"Cleaned up {deleted_files_count} uploaded static asset files.")

        print("\nAll shipments, payments, feedback, and associated records cleared successfully!")

if __name__ == '__main__':
    clear_shipping_data()
