import unittest
from datetime import datetime
from app import create_app
from app.models import db, User, Role, Branch, Customer, Shipment, ContainerTransfer

class TestBranchRecords(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # 1. Roles
        self.role_mgr = Role(name='Branch Manager')
        self.role_cust = Role(name='Customer')
        db.session.add_all([self.role_mgr, self.role_cust])
        db.session.commit()

        # 2. Branches
        self.branch_mum = Branch(name="Mumbai Main Hub", code="BOM01", address="Port Yard 1", city="Mumbai", state="Maharashtra", zip_code="400001", phone="022-11111111", email="mum@logitrack.com")
        self.branch_man = Branch(name="Mangalore Hub", code="MNG01", address="Port Yard 2", city="Mangalore", state="Karnataka", zip_code="575001", phone="0824-2222222", email="man@logitrack.com")
        db.session.add_all([self.branch_mum, self.branch_man])
        db.session.commit()

        # 3. Manager
        self.mgr = User(username="Mumbai_Manager01", email="mum_mgr@logitrack.com", role_id=self.role_mgr.id, branch_id=self.branch_mum.id)
        self.mgr.set_password("pass123")
        db.session.add(self.mgr)

        # 4. Customer
        self.cust_user = User(username="ClientA", email="clienta@logitrack.com", role_id=self.role_cust.id)
        self.cust_user.set_password("pass123")
        db.session.add(self.cust_user)
        db.session.commit()

        self.cust = Customer(user_id=self.cust_user.id, phone="9900112233")
        db.session.add(self.cust)
        db.session.commit()

        # 5. Create Test Shipments:
        # 1 Delivered Shipment at Mumbai
        self.sh_delivered = Shipment(
            tracking_number="LT-REC-DEL-01",
            sender_name="Sender Corp", sender_phone="9820011111", sender_email="sender@corp.com",
            pickup_address_line="Andheri", pickup_city="Mumbai", pickup_state="Maharashtra", pickup_zip_code="400069",
            receiver_name="Dr. Mehta", receiver_phone="9811022222",
            receiver_address_line="Bandra West", receiver_city="Mumbai", receiver_state="Maharashtra", receiver_zip_code="400050",
            package_category="Documents", package_weight=2.0, delivery_type="Standard", shipping_cost=150.0,
            status="Delivered", delivered_at=datetime.utcnow(),
            proof_image_path="uploads/proofs/test_doc.png",
            delivery_signature_path="uploads/signatures/test_sig.png",
            customer_id=self.cust.id, branch_id=self.branch_mum.id
        )

        # 1 Received/Inflow Shipment from Mangalore
        self.sh_inflow = Shipment(
            tracking_number="LT-REC-INFLOW-02",
            sender_name="Mangalore Coffee", sender_phone="9820033333", sender_email="mng@coffee.com",
            pickup_address_line="Hampankatta", pickup_city="Mangalore", pickup_state="Karnataka", pickup_zip_code="575001",
            receiver_name="Mumbai Cafe", receiver_phone="9811044444",
            receiver_address_line="Nariman Point", receiver_city="Mumbai", receiver_state="Maharashtra", receiver_zip_code="400021",
            package_category="Food items", package_weight=30.0, delivery_type="Standard", shipping_cost=600.0,
            status="Warehouse", customer_id=self.cust.id, branch_id=self.branch_mum.id
        )
        db.session.add_all([self.sh_delivered, self.sh_inflow])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_branch_records_view(self):
        """Test accessing branch records page and verifying delivered and inflow orders."""
        client = self.app.test_client()

        with client.session_transaction() as sess:
            sess['user_id'] = self.mgr.id
            sess['role'] = 'Branch Manager'

        res = client.get('/branch/records')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Terminal Shipment Records", res.data)
        self.assertIn(b"LT-REC-DEL-01", res.data)
        self.assertIn(b"LT-REC-INFLOW-02", res.data)
        self.assertIn(b"Delivered Orders Record", res.data)
        self.assertIn(b"Total Received at Branch", res.data)

    def test_branch_records_search(self):
        """Test searching records by tracking number."""
        client = self.app.test_client()

        with client.session_transaction() as sess:
            sess['user_id'] = self.mgr.id
            sess['role'] = 'Branch Manager'

        res = client.get('/branch/records?q=LT-REC-DEL-01')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"LT-REC-DEL-01", res.data)
        self.assertNotIn(b"LT-REC-INFLOW-02", res.data)

if __name__ == '__main__':
    unittest.main()
