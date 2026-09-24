import os
import unittest
import base64
from io import BytesIO
from datetime import datetime
from unittest.mock import patch
from app import create_app
from app.models import (
    db, User, Role, Branch, Driver, Vehicle, Customer, Shipment,
    ShipmentHistory, TrackingLog, Notification
)
from app.utils import send_delivery_email

class TestProofOfDeliveryWorkflow(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # 1. Roles
        self.role_admin = Role(name='Administrator')
        self.role_cust = Role(name='Customer')
        self.role_driver = Role(name='Driver')
        self.role_mgr = Role(name='Branch Manager')
        db.session.add_all([self.role_admin, self.role_cust, self.role_driver, self.role_mgr])
        db.session.commit()

        # 2. Branch
        self.branch = Branch(
            name="Delhi Final Terminal",
            code="DEL01",
            address="Okhla Phase 3",
            city="Delhi",
            state="Delhi",
            zip_code="110020",
            phone="011-22222222",
            email="delhi@logitrack.com"
        )
        db.session.add(self.branch)
        db.session.commit()

        # 3. Manager
        self.mgr_user = User(username="Delhi_Manager", email="del_mgr@logitrack.com", role_id=self.role_mgr.id, branch_id=self.branch.id)
        self.mgr_user.set_password("pass123")
        db.session.add(self.mgr_user)

        # 4. Vehicle
        today = datetime.now().date()
        self.van = Vehicle(vehicle_number="DL-01-VN-9999", vehicle_type="Van", capacity=1500.0, fuel_type="Electric", insurance_expiry=today, branch_id=self.branch.id)
        db.session.add(self.van)
        db.session.commit()

        # 5. Driver
        self.driver_user = User(username="Delhi_VanDriver", email="van_driver@logitrack.com", role_id=self.role_driver.id, branch_id=self.branch.id)
        self.driver_user.set_password("driver123")
        db.session.add(self.driver_user)
        db.session.commit()

        self.driver = Driver(user_id=self.driver_user.id, branch_id=self.branch.id, vehicle_id=self.van.id, license_number="DL01-2026-9", phone="9811009999", status="Available")
        db.session.add(self.driver)

        # 6. Customer / Sender
        self.cust_user = User(username="SenderClient", email="sender@business.com", role_id=self.role_cust.id)
        self.cust_user.set_password("cust123")
        db.session.add(self.cust_user)
        db.session.commit()

        self.customer = Customer(user_id=self.cust_user.id, phone="9820055555")
        db.session.add(self.customer)
        db.session.commit()

        # 7. Create Test Shipment at Final Branch for Delivery
        self.shipment = Shipment(
            tracking_number="LT-POD-1001",
            sender_name="Sender Corp",
            sender_phone="9820055555",
            sender_email="sender@business.com",
            pickup_address_line="Andheri Yard",
            pickup_city="Mumbai",
            pickup_state="Maharashtra",
            pickup_zip_code="400069",
            receiver_name="Dr. Rajesh Sharma",
            receiver_phone="9811001111",
            receiver_address_line="Block B, Hauz Khas",
            receiver_city="Delhi",
            receiver_state="Delhi",
            receiver_zip_code="110016",
            package_category="Electronics",
            package_weight=15.0,
            delivery_type="Standard",
            shipping_cost=450.0,
            status="Out For Delivery",
            customer_id=self.customer.id,
            branch_id=self.branch.id,
            driver_id=self.driver.id
        )
        db.session.add(self.shipment)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_gated_delivery_confirmation_requires_proof_and_signature(self):
        """Driver cannot complete delivery without photo proof and signature."""
        client = self.app.test_client()

        with client.session_transaction() as sess:
            sess['user_id'] = self.driver_user.id
            sess['role'] = 'Driver'

        # Attempt to mark Delivered with NO photo and NO signature
        res = client.post(f'/driver/delivery/{self.shipment.id}', data={
            'status': 'Delivered',
            'location': 'Delhi',
            'notes': 'Delivered at door'
        }, follow_redirects=True)

        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Proof of Delivery photo is required", res.data)

        # Status must remain Out For Delivery
        db.session.expire_all()
        sh = db.session.get(Shipment, self.shipment.id)
        self.assertEqual(sh.status, 'Out For Delivery')

    def test_successful_proof_of_delivery_execution(self):
        """Complete POD with photo, receiver signature, manager alert, and sender email."""
        client = self.app.test_client()

        with client.session_transaction() as sess:
            sess['user_id'] = self.driver_user.id
            sess['role'] = 'Driver'

        # Mock image file and base64 signature
        mock_image = (BytesIO(b"fake product image binary"), "product_delivered.jpg")
        sample_sig_base64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

        res = client.post(f'/driver/delivery/{self.shipment.id}', data={
            'status': 'Delivered',
            'location': 'Hauz Khas, Delhi',
            'notes': 'Package received in good condition',
            'proof_image': mock_image,
            'signature_data': sample_sig_base64
        }, follow_redirects=True)

        self.assertEqual(res.status_code, 200)
        self.assertIn(b"marked as Delivered", res.data)

        # 1. Verify Shipment Record
        db.session.expire_all()
        sh = db.session.get(Shipment, self.shipment.id)
        self.assertEqual(sh.status, 'Delivered')
        self.assertIsNotNone(sh.delivered_at)
        self.assertIsNotNone(sh.proof_image_path)
        self.assertIsNotNone(sh.delivery_signature_path)

        # 2. Verify Driver Status is Released to Available
        drv = db.session.get(Driver, self.driver.id)
        self.assertEqual(drv.status, 'Available')

        # 3. Verify Timeline Milestones
        history_statuses = [h.status for h in sh.history]
        self.assertIn('Delivery Proof Captured', history_statuses)
        self.assertIn('Receiver Signature Captured', history_statuses)
        self.assertIn('Delivered', history_statuses)
        self.assertIn('Sender Notified', history_statuses)

        # 4. Verify Manager Alert Notification
        mgr_notif = Notification.query.filter_by(user_id=self.mgr_user.id).first()
        self.assertIsNotNone(mgr_notif)
        self.assertIn("Delivery Completed", mgr_notif.title)
        self.assertIn("LT-POD-1001", mgr_notif.message)
        self.assertIn("Dr. Rajesh Sharma", mgr_notif.message)

        # 5. Verify Customer In-System Notification
        cust_notif = Notification.query.filter_by(user_id=self.cust_user.id).first()
        self.assertIsNotNone(cust_notif)
        self.assertIn("Shipment Delivered", cust_notif.title)

    def test_email_failure_does_not_cancel_delivery(self):
        """Email dispatch failure must keep shipment Delivered and record email status as Failed."""
        sh = self.shipment
        sh.status = 'Delivered'
        sh.delivered_at = datetime.utcnow()

        # Mock exception in mail sending
        with patch('app.utils.current_app.config.get', return_value='mail.dummy-server.com'):
            with patch('smtplib.SMTP', side_effect=Exception("SMTP Connection refused")):
                success = send_delivery_email(sh)
                self.assertFalse(success)
                self.assertEqual(sh.delivery_email_status, 'Failed')
                # Status remains Delivered
                self.assertEqual(sh.status, 'Delivered')

if __name__ == '__main__':
    unittest.main()
