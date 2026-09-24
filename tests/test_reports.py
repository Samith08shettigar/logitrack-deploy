import unittest
from datetime import datetime, timedelta
from app import create_app
from app.models import db, User, Role, Branch, Customer, Shipment, Payment, Driver, Vehicle

class TestReports(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Roles
        self.role_admin = Role(name='Administrator')
        self.role_mgr = Role(name='Branch Manager')
        self.role_driver = Role(name='Driver')
        self.role_cust = Role(name='Customer')
        db.session.add_all([self.role_admin, self.role_mgr, self.role_driver, self.role_cust])
        db.session.commit()

        # Branch
        self.branch = Branch(
            name="Delhi North Hub", code="DEL01",
            address="Ring Road 5", city="Delhi", state="Delhi",
            zip_code="110001", phone="011-23456789", email="del@logitrack.com"
        )
        db.session.add(self.branch)
        db.session.commit()

        # Admin user
        self.admin = User(username="admin_user", email="admin@logitrack.com", role_id=self.role_admin.id)
        self.admin.set_password("pass123")
        db.session.add(self.admin)

        # Driver user & profile
        self.driver_user = User(username="speedy_driver", email="driver@logitrack.com", role_id=self.role_driver.id)
        self.driver_user.set_password("pass123")
        db.session.add(self.driver_user)
        db.session.commit()

        self.driver = Driver(user_id=self.driver_user.id, phone="9876543210", license_number="DL-12345", branch_id=self.branch.id)
        db.session.add(self.driver)

        # Customer user & profile
        self.cust_user = User(username="shopper1", email="shopper@logitrack.com", role_id=self.role_cust.id)
        self.cust_user.set_password("pass123")
        db.session.add(self.cust_user)
        db.session.commit()

        self.customer = Customer(user_id=self.cust_user.id, phone="9123456780")
        db.session.add(self.customer)

        # Vehicle
        self.vehicle = Vehicle(
            vehicle_number="DL-01-AB-1234", vehicle_type="Van",
            capacity=1000.0, fuel_type="Diesel", insurance_expiry=datetime.now().date(),
            branch_id=self.branch.id
        )
        db.session.add(self.vehicle)
        db.session.commit()

        # Shipment
        self.shipment = Shipment(
            tracking_number="LT-REP-001",
            sender_name="Sender", sender_phone="9876500000", sender_email="sender@test.com",
            pickup_address_line="Street 1", pickup_city="Delhi", pickup_state="Delhi", pickup_zip_code="110001",
            receiver_name="Receiver", receiver_phone="9876500001",
            receiver_address_line="Street 2", receiver_city="Delhi", receiver_state="Delhi", receiver_zip_code="110002",
            package_category="Electronics", package_weight=5.0,
            delivery_type="Standard", shipping_cost=250.0, status="Delivered",
            branch_id=self.branch.id, customer_id=self.customer.id, driver_id=self.driver.id
        )
        db.session.add(self.shipment)
        db.session.commit()

        # Payment
        self.payment = Payment(
            shipment_id=self.shipment.id, amount=250.0,
            payment_method="Simulated Online", payment_status="Completed",
            transaction_id="TXN-REP-001"
        )
        db.session.add(self.payment)
        db.session.commit()

        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _login_admin(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin.id
            sess['role'] = 'Administrator'
            sess['username'] = self.admin.username

    def test_branch_shipments_property(self):
        """Test branch.shipments property returns local_shipments."""
        self.assertEqual(len(self.branch.shipments), 1)
        self.assertEqual(self.branch.shipments[0].tracking_number, "LT-REP-001")

    def test_view_report_all_types(self):
        """Test viewing all report types in the reports blueprint."""
        self._login_admin()
        report_types = ['branches', 'shipments', 'revenue', 'drivers', 'customers', 'vehicles', 'success_rate']
        for rtype in report_types:
            res = self.client.get(f'/reports/view?type={rtype}&timeframe=daily')
            self.assertEqual(res.status_code, 200, f"Failed on report view for {rtype}")
            self.assertIn(b"LogiTrack", res.data)

    def test_export_report_branches_csv_excel_pdf(self):
        """Test exporting branch report as CSV, Excel, and PDF."""
        self._login_admin()
        for fmt in ['csv', 'excel', 'pdf']:
            res = self.client.get(f'/reports/export?type=branches&timeframe=daily&format={fmt}')
            self.assertEqual(res.status_code, 200, f"Failed on export format {fmt} for branches")
            self.assertGreater(len(res.data), 0)
