# type: ignore
import unittest
from datetime import datetime, date
from app import create_app
from app.models import db, User, Role, Customer, Branch, Shipment
from app.utils import calculate_shipping_cost

class LogiTrackTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        
        # Seed basic roles only if they do not exist
        self.admin_role = Role.query.filter_by(name='Administrator').first()
        if not self.admin_role:
            self.admin_role = Role(name='Administrator', description='System Admin')
            self.customer_role = Role(name='Customer', description='End Customer')
            self.driver_role = Role(name='Driver', description='Courier Driver')
            self.manager_role = Role(name='Branch Manager', description='Branch Boss')
            db.session.add_all([self.admin_role, self.customer_role, self.driver_role, self.manager_role])
            db.session.commit()
        else:
            self.customer_role = Role.query.filter_by(name='Customer').first()
            self.driver_role = Role.query.filter_by(name='Driver').first()
            self.manager_role = Role.query.filter_by(name='Branch Manager').first()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_user_password_hashing(self):
        u = User(username='test_user', email='test@example.com', role_id=self.customer_role.id)
        u.set_password('my_secure_pass')
        db.session.add(u)
        db.session.commit()
        
        self.assertTrue(u.check_password('my_secure_pass'))
        self.assertFalse(u.check_password('wrong_pass'))
        self.assertNotEqual(u.password_hash, 'my_secure_pass')

    def test_shipping_cost_calculator(self):
        # Base: $20.0, weight: 2.0kg @ $5.50/kg = $11.0, packaging ('Other' category @ $10.0/kg) = $20.0. Total = $51.0
        cost_std = calculate_shipping_cost(2.0, 'Standard', fragile=False, insurance=False)
        self.assertEqual(cost_std, 51.0)
        
        # Category specific (Clothes / Garments @ $5.0/kg). Total = 20.0 + 11.0 + 10.0 = $41.0
        cost_garments = calculate_shipping_cost(2.0, 'Standard', fragile=False, insurance=False, package_category='Clothes / Garments')
        self.assertEqual(cost_garments, 41.0)
        
        # Express multiplier: 1.5x. Base 51.0 * 1.5 = $76.5
        cost_exp = calculate_shipping_cost(2.0, 'Express', fragile=False, insurance=False)
        self.assertEqual(cost_exp, 76.5)
        
        # Fragile fee: +$10.0. Total: 51.0 + 10.0 = $61.0
        cost_fragile = calculate_shipping_cost(2.0, 'Standard', fragile=True, insurance=False)
        self.assertEqual(cost_fragile, 61.0)
        
        # Insurance fee: Min Rs. 300.0 for Other. Total: 51.0 + 300.0 = 351.0
        cost_ins = calculate_shipping_cost(2.0, 'Standard', fragile=False, insurance=True)
        self.assertEqual(cost_ins, 351.0)

    def test_shipment_creation(self):
        # Create Branch
        b = Branch(
            name="Test Branch", code="TB01", address="123 Test St",
            city="TestCity", state="TestState", zip_code="00000",
            phone="12345", email="test@branch.com"
        )
        db.session.add(b)
        db.session.commit()
        
        # Create Customer Profile
        u = User(username='cust_test', email='cust@test.com', role_id=self.customer_role.id)
        u.set_password('pass123')
        db.session.add(u)
        db.session.commit()
        
        c = Customer(user_id=u.id, phone="99999", status="Active")
        db.session.add(c)
        db.session.commit()
        
        # Create Shipment
        sh = Shipment(
            tracking_number="LT-TEST-12345",
            sender_name="Sender", sender_phone="111", sender_email="sender@test.com",
            pickup_address_line="Pickup", pickup_city="CityA", pickup_state="StateA", pickup_zip_code="11111",
            receiver_name="Receiver", receiver_phone="222",
            receiver_address_line="ReceiverAddr", receiver_city="CityB", receiver_state="StateB", receiver_zip_code="22222",
            package_category="Electronics", package_weight=1.5,
            delivery_type="Standard", shipping_cost=28.25, status="Booked",
            customer_id=c.id, branch_id=b.id
        )
        db.session.add(sh)
        db.session.commit()
        
        # Retrieve and verify
        db_sh = Shipment.query.filter_by(tracking_number="LT-TEST-12345").first()
        self.assertIsNotNone(db_sh)
        self.assertEqual(db_sh.customer_id, c.id)
        self.assertEqual(db_sh.branch_id, b.id)
        self.assertEqual(db_sh.status, "Booked")

    def test_manager_branch_assignment(self):
        # Create Branch
        b = Branch(
            name="Test Branch 2", code="TB02", address="456 Test St",
            city="TestCity2", state="TestState2", zip_code="99999",
            phone="98765", email="test2@branch.com"
        )
        db.session.add(b)
        db.session.commit()

        # Create Manager
        m = User(
            username='mgr_test', email='mgr@test.com',
            role_id=self.manager_role.id, branch_id=b.id
        )
        m.set_password('mgr123')
        db.session.add(m)
        db.session.commit()

        # Retrieve and verify
        db_m = User.query.filter_by(username='mgr_test').first()
        self.assertIsNotNone(db_m)
        self.assertEqual(db_m.branch_id, b.id)
        self.assertEqual(db_m.branch.name, "Test Branch 2")

if __name__ == '__main__':
    unittest.main()
