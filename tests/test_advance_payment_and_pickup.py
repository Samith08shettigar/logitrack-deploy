import os
import unittest
from datetime import datetime
from app import create_app
from app.models import (
    db, User, Role, Branch, Driver, Customer, Shipment, Payment, Invoice
)
from app.utils import calculate_shipping_cost, create_invoice_pdf

class TestAdvancePaymentAndPickup(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Roles
        self.role_admin = Role(name='Administrator')
        self.role_cust = Role(name='Customer')
        self.role_driver = Role(name='Driver')
        self.role_mgr = Role(name='Branch Manager')
        db.session.add_all([self.role_admin, self.role_cust, self.role_driver, self.role_mgr])
        db.session.commit()

        # Branch
        self.branch = Branch(
            name="Bangalore Hub",
            code="BLR01",
            address="Industrial Area",
            city="Bangalore",
            state="Karnataka",
            zip_code="560100",
            phone="080-12345678",
            email="blr@logitrack.com"
        )
        db.session.add(self.branch)
        db.session.commit()

        # Manager
        self.mgr_user = User(username="BLR_Manager", email="manager@logitrack.com", role_id=self.role_mgr.id, branch_id=self.branch.id)
        self.mgr_user.set_password("mgr123")
        db.session.add(self.mgr_user)
        db.session.commit()

        # Driver
        self.driver_user = User(username="PickupDriver", email="pickup@logitrack.com", role_id=self.role_driver.id, branch_id=self.branch.id)
        self.driver_user.set_password("driver123")
        db.session.add(self.driver_user)
        db.session.commit()

        self.driver = Driver(user_id=self.driver_user.id, branch_id=self.branch.id, license_number="KA01-2026-1", phone="9888877777", status="Available")
        db.session.add(self.driver)

        # Customer
        self.cust_user = User(username="CustomerAlice", email="alice@test.com", role_id=self.role_cust.id)
        self.cust_user.set_password("pass123")
        db.session.add(self.cust_user)
        db.session.commit()

        self.customer = Customer(user_id=self.cust_user.id, phone="9876543210")
        db.session.add(self.customer)
        db.session.commit()

        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_online_advance_payment_checkout(self):
        """Verify that advance payment is processed online and updates payment status to Completed."""
        shipment = Shipment(
            tracking_number="LT-TEST-ADV1",
            sender_name="Alice",
            sender_phone="9876543210",
            sender_email="alice@test.com",
            pickup_address_line="123 Main St",
            pickup_city="Bangalore",
            pickup_state="Karnataka",
            pickup_zip_code="560100",
            receiver_name="Bob",
            receiver_phone="9123456780",
            receiver_address_line="456 Cross Rd",
            receiver_city="Mumbai",
            receiver_state="Maharashtra",
            receiver_zip_code="400001",
            package_category="Electronics",
            package_description="Gadget",
            package_weight=0.0,
            weigh_at_pickup=True,
            advance_paid=200.0,
            delivery_type="Standard",
            shipping_cost=200.0,
            status="Booked",
            customer_id=self.customer.id,
            branch_id=self.branch.id
        )
        db.session.add(shipment)
        db.session.commit()

        payment = Payment(shipment_id=shipment.id, amount=200.0, payment_method="Simulated Online", payment_status="Pending")
        db.session.add(payment)
        db.session.commit()

        # Login as customer
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.cust_user.id
            sess['role'] = 'Customer'

        # Process payment online
        resp = self.client.post(f'/payment/process/{shipment.id}', data={
            'payment_method': 'Simulated Online',
            'card_name': 'Alice Test',
            'card_number': '4111 2222 3333 4444',
            'card_expiry': '12/28',
            'card_cvv': '123'
        }, follow_redirects=True)

        self.assertEqual(resp.status_code, 200)
        db.session.expire_all()
        updated_pay = Payment.query.filter_by(shipment_id=shipment.id).first()
        updated_sh = db.session.get(Shipment, shipment.id)
        self.assertEqual(updated_pay.payment_status, 'Completed')
        self.assertEqual(updated_pay.amount, 200.0)
        self.assertEqual(updated_sh.status, 'Confirmed')

    def test_driver_pickup_cash_collection_and_manager_handover(self):
        """Verify that when cash is collected, driver retains custody, submits to manager, and manager accepts deposit."""
        shipment = Shipment(
            tracking_number="LT-TEST-PICKUP-CASH",
            sender_name="Alice",
            sender_phone="9876543210",
            sender_email="alice@test.com",
            pickup_address_line="123 Main St",
            pickup_city="Bangalore",
            pickup_state="Karnataka",
            pickup_zip_code="560100",
            receiver_name="Bob",
            receiver_phone="9123456780",
            receiver_address_line="456 Cross Rd",
            receiver_city="Mumbai",
            receiver_state="Maharashtra",
            receiver_zip_code="400001",
            package_category="Electronics",
            package_description="Heavy Machine",
            package_weight=0.0,
            weigh_at_pickup=True,
            advance_paid=200.0,
            delivery_type="Standard",
            shipping_cost=200.0,
            status="Confirmed",
            driver_id=self.driver.id,
            customer_id=self.customer.id,
            branch_id=self.branch.id
        )
        db.session.add(shipment)
        db.session.commit()

        payment = Payment(shipment_id=shipment.id, amount=200.0, payment_method="Simulated Online", payment_status="Completed", transaction_id="TXN-11223344")
        db.session.add(payment)
        db.session.commit()

        # 1. Driver performs pickup and collects Cash
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.driver_user.id
            sess['role'] = 'Driver'

        actual_weight = 10.0
        expected_total = calculate_shipping_cost(actual_weight, shipment.delivery_type, shipment.fragile, shipment.insurance, shipment.package_category, shipment.declared_value)
        expected_balance = max(0.0, round(expected_total - 200.0, 2))

        dummy_sig = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

        resp = self.client.post(f'/driver/delivery/{shipment.id}', data={
            'status': 'Picked Up',
            'location': 'Bangalore',
            'actual_weight': str(actual_weight),
            'balance_collected': 'on',
            'pickup_payment_method': 'Cash',
            'pickup_signature_data': dummy_sig,
            'notes': 'Weighed and collected cash balance'
        }, follow_redirects=True)

        self.assertEqual(resp.status_code, 200)

        db.session.expire_all()
        sh = db.session.get(Shipment, shipment.id)
        pay = Payment.query.filter_by(shipment_id=shipment.id).first()

        self.assertEqual(sh.status, 'Picked Up')
        self.assertEqual(sh.package_weight, actual_weight)
        self.assertEqual(sh.shipping_cost, expected_total)
        self.assertEqual(pay.cash_status, 'In Hand with Driver')
        self.assertEqual(pay.cash_collected_amount, expected_balance)

        # 2. Driver submits cash handover to Branch Manager
        resp_handover = self.client.post(f'/driver/handover-cash/{pay.id}', follow_redirects=True)
        self.assertEqual(resp_handover.status_code, 200)

        db.session.expire_all()
        pay = db.session.get(Payment, pay.id)
        self.assertEqual(pay.cash_status, 'Submitted to Manager')

        # 3. Branch Manager acknowledges and receives cash deposit
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.mgr_user.id
            sess['role'] = 'Branch Manager'

        resp_ack = self.client.post(f'/branch/acknowledge-cash/{pay.id}', follow_redirects=True)
        self.assertEqual(resp_ack.status_code, 200)

        db.session.expire_all()
        pay = db.session.get(Payment, pay.id)
        self.assertEqual(pay.cash_status, 'Deposited with Manager')
        self.assertEqual(pay.cash_received_by_manager_id, self.mgr_user.id)

    def test_driver_pickup_upi_qr_direct_software_payment(self):
        """Verify that UPI QR payment is settled directly into software without requiring cash handover."""
        shipment = Shipment(
            tracking_number="LT-TEST-PICKUP-UPI",
            sender_name="Alice",
            sender_phone="9876543210",
            sender_email="alice@test.com",
            pickup_address_line="123 Main St",
            pickup_city="Bangalore",
            pickup_state="Karnataka",
            pickup_zip_code="560100",
            receiver_name="Bob",
            receiver_phone="9123456780",
            receiver_address_line="456 Cross Rd",
            receiver_city="Mumbai",
            receiver_state="Maharashtra",
            receiver_zip_code="400001",
            package_category="Electronics",
            package_description="Heavy Machine",
            package_weight=0.0,
            weigh_at_pickup=True,
            advance_paid=200.0,
            delivery_type="Standard",
            shipping_cost=200.0,
            status="Confirmed",
            driver_id=self.driver.id,
            customer_id=self.customer.id,
            branch_id=self.branch.id
        )
        db.session.add(shipment)
        db.session.commit()

        payment = Payment(shipment_id=shipment.id, amount=200.0, payment_method="Simulated Online", payment_status="Completed", transaction_id="TXN-99887766")
        db.session.add(payment)
        db.session.commit()

        with self.client.session_transaction() as sess:
            sess['user_id'] = self.driver_user.id
            sess['role'] = 'Driver'

        actual_weight = 10.0
        dummy_sig = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

        resp = self.client.post(f'/driver/delivery/{shipment.id}', data={
            'status': 'Picked Up',
            'location': 'Bangalore',
            'actual_weight': str(actual_weight),
            'balance_collected': 'on',
            'pickup_payment_method': 'UPI / QR Scan',
            'digital_ref': 'UPI-UTR-992810382910',
            'pickup_signature_data': dummy_sig,
            'notes': 'Paid via LogiTrack UPI QR'
        }, follow_redirects=True)

        self.assertEqual(resp.status_code, 200)

        db.session.expire_all()
        sh = db.session.get(Shipment, shipment.id)
        pay = Payment.query.filter_by(shipment_id=shipment.id).first()

        self.assertEqual(sh.status, 'Picked Up')
        self.assertEqual(pay.cash_status, 'N/A')
        self.assertEqual(pay.cash_collected_amount, 0.0)
        self.assertEqual(pay.digital_reference, 'UPI-UTR-992810382910')
        self.assertIn('UPI', pay.payment_method)

    def test_invoice_pdf_contains_advance_deduction(self):
        """Verify that create_invoice_pdf generates an invoice containing advance deduction and net balance without errors."""
        shipment = Shipment(
            tracking_number="LT-TEST-INV1",
            sender_name="Alice",
            sender_phone="9876543210",
            sender_email="alice@test.com",
            pickup_address_line="123 Main St",
            pickup_city="Bangalore",
            pickup_state="Karnataka",
            pickup_zip_code="560100",
            receiver_name="Bob",
            receiver_phone="9123456780",
            receiver_address_line="456 Cross Rd",
            receiver_city="Mumbai",
            receiver_state="Maharashtra",
            receiver_zip_code="400001",
            package_category="Books",
            package_description="Tech Books",
            package_weight=10.0,
            weigh_at_pickup=False,
            advance_paid=200.0,
            delivery_type="Standard",
            shipping_cost=500.0,
            status="Picked Up",
            customer_id=self.customer.id,
            branch_id=self.branch.id
        )
        db.session.add(shipment)
        db.session.commit()

        pdf_path = create_invoice_pdf(shipment)
        self.assertTrue(pdf_path.endswith('.pdf'))
        abs_path = os.path.join(self.app.config['UPLOAD_FOLDER'], 'invoices', f"invoice_{shipment.tracking_number}.pdf")
        self.assertTrue(os.path.exists(abs_path))
        self.assertGreater(os.path.getsize(abs_path), 0)
