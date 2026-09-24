import unittest
from datetime import datetime, timezone
from app import create_app
from app.models import (
    db, User, Role, Branch, Driver, Vehicle, Customer, Shipment,
    ShipmentHistory, TrackingLog, ContainerTransfer
)

class TestMultiShipmentContainerWorkflow(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        
        # 1. Setup Roles
        self.role_admin = Role(name='Administrator')
        self.role_cust = Role(name='Customer')
        self.role_driver = Role(name='Driver')
        self.role_mgr = Role(name='Branch Manager')
        db.session.add_all([self.role_admin, self.role_cust, self.role_driver, self.role_mgr])
        db.session.commit()
        
        # 2. Setup 4 Branches along route: Mumbai -> Mangalore -> Bangalore -> Delhi
        self.branch_mum = Branch(name="Mumbai Main Terminal", code="BOM01", address="Port Yard 1", city="Mumbai", state="Maharashtra", zip_code="400001", phone="022-11111111", email="mum@logitrack.com")
        self.branch_man = Branch(name="Mangalore Hub Terminal", code="MNG01", address="Port Yard 2", city="Mangalore", state="Karnataka", zip_code="575001", phone="0824-2222222", email="man@logitrack.com")
        self.branch_ban = Branch(name="Bangalore Central Terminal", code="BLR01", address="Industrial Zone", city="Bangalore", state="Karnataka", zip_code="560001", phone="080-33333333", email="ban@logitrack.com")
        self.branch_del = Branch(name="Delhi Super Terminal", code="DEL01", address="Okhla Terminal", city="Delhi", state="Delhi", zip_code="110001", phone="011-44444444", email="del@logitrack.com")
        db.session.add_all([self.branch_mum, self.branch_man, self.branch_ban, self.branch_del])
        db.session.commit()
        
        # 3. Setup Branch Managers
        self.mgr_mum_u = User(username="mgr_bom", email="mgr_bom@logitrack.com", role_id=self.role_mgr.id, branch_id=self.branch_mum.id)
        self.mgr_mum_u.set_password("pass123")
        self.mgr_man_u = User(username="mgr_mng", email="mgr_mng@logitrack.com", role_id=self.role_mgr.id, branch_id=self.branch_man.id)
        self.mgr_man_u.set_password("pass123")
        self.mgr_ban_u = User(username="mgr_blr", email="mgr_blr@logitrack.com", role_id=self.role_mgr.id, branch_id=self.branch_ban.id)
        self.mgr_ban_u.set_password("pass123")
        self.mgr_del_u = User(username="mgr_del", email="mgr_del@logitrack.com", role_id=self.role_mgr.id, branch_id=self.branch_del.id)
        self.mgr_del_u.set_password("pass123")
        db.session.add_all([self.mgr_mum_u, self.mgr_man_u, self.mgr_ban_u, self.mgr_del_u])
        
        # 4. Setup Vehicles
        today = datetime.now().date()
        self.v_mum_truck = Vehicle(vehicle_number="MH-01-TR-9001", vehicle_type="Truck", capacity=10000.0, fuel_type="Diesel", insurance_expiry=today, branch_id=self.branch_mum.id)
        self.v_man_truck = Vehicle(vehicle_number="KA-19-TR-9002", vehicle_type="Truck", capacity=10000.0, fuel_type="Diesel", insurance_expiry=today, branch_id=self.branch_man.id)
        self.v_ban_truck = Vehicle(vehicle_number="KA-01-TR-9003", vehicle_type="Truck", capacity=10000.0, fuel_type="Diesel", insurance_expiry=today, branch_id=self.branch_ban.id)
        self.v_del_van = Vehicle(vehicle_number="DL-01-VN-5001", vehicle_type="Van", capacity=1500.0, fuel_type="Electric", insurance_expiry=today, branch_id=self.branch_del.id)
        db.session.add_all([self.v_mum_truck, self.v_man_truck, self.v_ban_truck, self.v_del_van])
        db.session.commit()
        
        # 5. Setup Drivers
        self.u_mum_driver = User(username="Mum_TruckDriver", email="mum_d@logitrack.com", role_id=self.role_driver.id, branch_id=self.branch_mum.id)
        self.u_mum_driver.set_password("driver123")
        self.u_man_driver = User(username="Man_TruckDriver", email="man_d@logitrack.com", role_id=self.role_driver.id, branch_id=self.branch_man.id)
        self.u_man_driver.set_password("driver123")
        self.u_ban_driver = User(username="Ban_TruckDriver", email="ban_d@logitrack.com", role_id=self.role_driver.id, branch_id=self.branch_ban.id)
        self.u_ban_driver.set_password("driver123")
        self.u_del_driver = User(username="Del_VanDriver", email="del_d@logitrack.com", role_id=self.role_driver.id, branch_id=self.branch_del.id)
        self.u_del_driver.set_password("driver123")
        db.session.add_all([self.u_mum_driver, self.u_man_driver, self.u_ban_driver, self.u_del_driver])
        db.session.commit()
        
        self.d_mum = Driver(user_id=self.u_mum_driver.id, branch_id=self.branch_mum.id, vehicle_id=self.v_mum_truck.id, license_number="MH01-DL-1", phone="9820011111", status="Available")
        self.d_man = Driver(user_id=self.u_man_driver.id, branch_id=self.branch_man.id, vehicle_id=self.v_man_truck.id, license_number="KA19-DL-2", phone="9820022222", status="Available")
        self.d_ban = Driver(user_id=self.u_ban_driver.id, branch_id=self.branch_ban.id, vehicle_id=self.v_ban_truck.id, license_number="KA01-DL-3", phone="9820033333", status="Available")
        self.d_del = Driver(user_id=self.u_del_driver.id, branch_id=self.branch_del.id, vehicle_id=self.v_del_van.id, license_number="DL01-DL-4", phone="9820044444", status="Available")
        db.session.add_all([self.d_mum, self.d_man, self.d_ban, self.d_del])
        
        # 6. Setup Customer
        self.u_cust = User(username="CustomerOne", email="cust1@logitrack.com", role_id=self.role_cust.id)
        self.u_cust.set_password("cust123")
        db.session.add(self.u_cust)
        db.session.commit()
        self.cust = Customer(user_id=self.u_cust.id, phone="9988776655")
        db.session.add(self.cust)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_multi_shipment_container_complete_workflow(self):
        """
        Tests:
        1. 5 separate orders created at Mumbai for Delhi.
        2. Mumbai Manager batches all 5 orders into 1 single container 'CONT-BOM-MAN-001'.
        3. Manager assigns Mumbai Truck Driver.
        4. Driver accepts -> Container is locked.
        5. Driver completes transit -> Arrives at Mangalore.
        6. Mangalore Manager receives entire container in one action -> all 5 orders become 'Warehouse' at Mangalore.
        7. Mangalore Manager creates next container 'CONT-MAN-BAN-001' with all 5 orders.
        8. Bangalore receives entire container -> creates next container 'CONT-BAN-DEL-001' to Delhi.
        9. Delhi Manager receives container -> final destination reached.
        10. Delhi Manager assigns local van driver for final delivery.
        11. Digital signature uploaded -> status 'Completed'.
        """
        # Create 5 orders
        orders = []
        for i in range(1, 6):
            sh = Shipment(
                tracking_number=f"LT-ORDER-{i:03d}",
                sender_name=f"Mumbai Vendor {i}", sender_phone=f"982000000{i}", sender_email=f"vendor{i}@mumbai.com",
                pickup_address_line="Andheri Industrial Estate", pickup_city="Mumbai", pickup_state="Maharashtra", pickup_zip_code="400069",
                receiver_name=f"Delhi Client {i}", receiver_phone=f"981100000{i}",
                receiver_address_line=f"Okhla Phase {i}", receiver_city="Delhi", receiver_state="Delhi", receiver_zip_code="110020",
                package_category="Industrial Electronics", package_weight=50.0 + (i * 10),
                delivery_type="Standard", shipping_cost=1200.0, status="Warehouse",
                customer_id=self.cust.id, branch_id=self.branch_mum.id
            )
            db.session.add(sh)
            orders.append(sh)
        db.session.commit()
        
        self.assertEqual(len(orders), 5)
        for sh in orders:
            self.assertEqual(sh.branch_id, self.branch_mum.id)
            self.assertEqual(sh.status, 'Warehouse')
            self.assertIsNone(sh.active_container)
            self.assertFalse(sh.is_container_locked)

        # -------------------------------------------------------------
        # LEG 1: Mumbai -> Mangalore
        # -------------------------------------------------------------
        # Mumbai Manager creates Container 1
        container_1 = ContainerTransfer(
            transfer_code="CONT-BOM-MAN-001",
            from_branch_id=self.branch_mum.id,
            to_branch_id=self.branch_man.id,
            status='Preparing',
            is_locked=False,
            max_orders_capacity=20,
            max_weight_capacity=5000.0
        )
        db.session.add(container_1)
        db.session.flush()

        # Batch add all 5 orders
        for sh in orders:
            container_1.shipments.append(sh)
            sh.next_branch_id = self.branch_man.id
        db.session.commit()

        # Check Container Stats
        self.assertEqual(container_1.total_orders, 5)
        self.assertEqual(container_1.total_weight, 400.0) # (60+70+80+90+100) = 400
        self.assertFalse(container_1.is_full)
        self.assertEqual(container_1.available_capacity, 15)
        for sh in orders:
            self.assertEqual(sh.current_container_id, "CONT-BOM-MAN-001")
            self.assertIsNotNone(sh.active_container)

        # Mumbai Manager assigns Mumbai Truck Driver
        container_1.driver_id = self.d_mum.id
        container_1.vehicle_id = self.v_mum_truck.id
        container_1.status = 'Driver Assigned'
        self.d_mum.status = 'Busy'
        for sh in orders:
            sh.driver_id = self.d_mum.id
            sh.status = 'Container Driver Assigned'
        db.session.commit()

        # Container Driver Accepts -> Lock Container
        container_1.status = 'Accepted'
        container_1.is_locked = True
        self.d_mum.status = 'Accepted'
        for sh in orders:
            sh.status = 'Transfer Accepted'
        db.session.commit()

        # Verify Lock
        self.assertTrue(container_1.is_locked)
        for sh in orders:
            self.assertTrue(sh.is_container_locked)

        # Driver confirms cargo loaded in truck
        container_1.status = 'Received Shipment'
        for sh in orders:
            sh.status = 'Shipment Received by Container Driver'
        db.session.commit()

        # Driver starts highway transit
        container_1.status = 'In Transit'
        self.d_mum.status = 'In Transit'
        for sh in orders:
            sh.status = 'In Transit'
        db.session.commit()

        # Driver arrives at Mangalore Hub
        container_1.status = 'Arrived at Branch'
        self.d_mum.status = 'Available'
        for sh in orders:
            sh.status = 'Arrived at Branch'
        db.session.commit()

        # Mangalore Manager receives entire container
        container_1.status = 'Completed'
        container_1.is_locked = False
        for sh in orders:
            sh.branch_id = self.branch_man.id
            sh.driver_id = None
            sh.status = 'Warehouse'
        db.session.commit()

        # Check handover
        for sh in orders:
            self.assertEqual(sh.branch_id, self.branch_man.id)
            self.assertFalse(sh.is_container_locked)
            self.assertEqual(sh.status, 'Warehouse')

        # -------------------------------------------------------------
        # LEG 2: Mangalore -> Bangalore
        # -------------------------------------------------------------
        container_2 = ContainerTransfer(
            transfer_code="CONT-MAN-BAN-001",
            from_branch_id=self.branch_man.id,
            to_branch_id=self.branch_ban.id,
            status='Preparing',
            is_locked=False,
            max_orders_capacity=20,
            max_weight_capacity=5000.0
        )
        db.session.add(container_2)
        for sh in orders:
            container_2.shipments.append(sh)
            sh.next_branch_id = self.branch_ban.id
        db.session.commit()

        # Assign Mangalore Driver
        container_2.driver_id = self.d_man.id
        container_2.vehicle_id = self.v_man_truck.id
        container_2.status = 'Driver Assigned'
        # Driver accepts
        container_2.status = 'Accepted'
        container_2.is_locked = True
        # In transit & arrive
        container_2.status = 'In Transit'
        container_2.status = 'Arrived at Branch'
        db.session.commit()

        # Bangalore Manager receives entire container
        container_2.status = 'Completed'
        container_2.is_locked = False
        for sh in orders:
            sh.branch_id = self.branch_ban.id
            sh.driver_id = None
            sh.status = 'Warehouse'
        db.session.commit()

        for sh in orders:
            self.assertEqual(sh.branch_id, self.branch_ban.id)

        # -------------------------------------------------------------
        # LEG 3: Bangalore -> Delhi (Final Hub)
        # -------------------------------------------------------------
        container_3 = ContainerTransfer(
            transfer_code="CONT-BAN-DEL-001",
            from_branch_id=self.branch_ban.id,
            to_branch_id=self.branch_del.id,
            status='Preparing',
            is_locked=False,
            max_orders_capacity=20,
            max_weight_capacity=5000.0
        )
        db.session.add(container_3)
        for sh in orders:
            container_3.shipments.append(sh)
            sh.next_branch_id = self.branch_del.id
        db.session.commit()

        # Bangalore Driver accepts & arrives Delhi
        container_3.driver_id = self.d_ban.id
        container_3.status = 'Accepted'
        container_3.is_locked = True
        container_3.status = 'In Transit'
        container_3.status = 'Arrived at Branch'
        db.session.commit()

        # Delhi Manager receives entire container
        container_3.status = 'Completed'
        container_3.is_locked = False
        for sh in orders:
            sh.branch_id = self.branch_del.id
            sh.driver_id = None
            sh.status = 'Warehouse'
            # Final destination reached!
            sh.next_branch_id = None
        db.session.commit()

        for sh in orders:
            self.assertEqual(sh.branch_id, self.branch_del.id)
            self.assertIsNone(sh.next_branch_id)
            self.assertIsNone(sh.active_container)

        # -------------------------------------------------------------
        # FINAL LEG: Last-Mile Delivery at Delhi
        # -------------------------------------------------------------
        # Delhi Manager assigns local Van Driver to Order 1
        order_1 = orders[0]
        order_1.driver_id = self.d_del.id
        order_1.status = 'Driver Assigned'
        db.session.commit()

        # Van driver delivers and collects e-signature
        order_1.status = 'Completed'
        order_1.signature_path = 'uploads/signatures/sig_test.png'
        self.d_del.status = 'Available'
        db.session.commit()

        self.assertEqual(order_1.status, 'Completed')
        self.assertEqual(order_1.signature_path, 'uploads/signatures/sig_test.png')

    def test_http_multi_shipment_endpoints(self):
        """Test HTTP routes for creating, adding shipments, assigning driver, driver accept, and receiving container."""
        client = self.app.test_client()

        # Create 3 shipments at Mumbai
        sh1 = Shipment(
            tracking_number="LT-HTTP-001",
            sender_name="Sender 1", sender_phone="9820000001", sender_email="sender1@mumbai.com",
            pickup_address_line="Street 1", pickup_city="Mumbai", pickup_state="Maharashtra", pickup_zip_code="400001",
            receiver_name="Receiver 1", receiver_phone="9811000001",
            receiver_address_line="Road 1", receiver_city="Delhi", receiver_state="Delhi", receiver_zip_code="110001",
            package_category="Electronics", package_weight=25.0,
            delivery_type="Standard", shipping_cost=600.0, status="Warehouse",
            customer_id=self.cust.id, branch_id=self.branch_mum.id
        )
        sh2 = Shipment(
            tracking_number="LT-HTTP-002",
            sender_name="Sender 2", sender_phone="9820000002", sender_email="sender2@mumbai.com",
            pickup_address_line="Street 2", pickup_city="Mumbai", pickup_state="Maharashtra", pickup_zip_code="400001",
            receiver_name="Receiver 2", receiver_phone="9811000002",
            receiver_address_line="Road 2", receiver_city="Delhi", receiver_state="Delhi", receiver_zip_code="110001",
            package_category="Electronics", package_weight=35.0,
            delivery_type="Standard", shipping_cost=750.0, status="Warehouse",
            customer_id=self.cust.id, branch_id=self.branch_mum.id
        )
        db.session.add_all([sh1, sh2])
        db.session.commit()

        # 1. Login as Mumbai Branch Manager
        with client.session_transaction() as sess:
            sess['user_id'] = self.mgr_mum_u.id
            sess['role'] = 'Branch Manager'

        # GET create container page
        res = client.get('/branch/containers/create')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Prepare Multi-Shipment Container", res.data)
        self.assertIn(b"LT-HTTP-001", res.data)
        self.assertIn(b"LT-HTTP-002", res.data)

        # POST create container with both shipments to Mangalore
        res_create = client.post('/branch/containers/create', data={
            'to_branch_id': self.branch_man.id,
            'shipment_ids': [sh1.id, sh2.id]
        }, follow_redirects=True)
        self.assertEqual(res_create.status_code, 200)
        self.assertIn(b"prepared successfully", res_create.data)

        container = ContainerTransfer.query.first()
        self.assertIsNotNone(container)
        self.assertEqual(container.total_orders, 2)
        self.assertEqual(container.status, 'Preparing')

        # Mumbai Manager assigns Driver
        res_assign = client.post(f'/branch/containers/{container.id}/assign-driver', data={
            'driver_id': self.d_mum.id
        }, follow_redirects=True)
        self.assertEqual(res_assign.status_code, 200)

        db.session.expire_all()
        container = db.session.get(ContainerTransfer, container.id)
        self.assertEqual(container.status, 'Driver Assigned')
        self.assertEqual(container.driver_id, self.d_mum.id)

        # 2. Login as Mumbai Container Driver
        with client.session_transaction() as sess:
            sess['user_id'] = self.u_mum_driver.id
            sess['role'] = 'Driver'

        # Driver accepts container
        res_accept = client.get(f'/driver/container/{container.id}/accept', follow_redirects=True)
        self.assertEqual(res_accept.status_code, 200)
        self.assertIn(b"locked for transfer", res_accept.data)

        db.session.expire_all()
        container = db.session.get(ContainerTransfer, container.id)
        self.assertTrue(container.is_locked)
        self.assertEqual(container.status, 'Accepted')

        # Driver confirms cargo loaded
        client.get(f'/driver/container/{container.id}/receive_cargo', follow_redirects=True)
        # Driver starts transit
        client.get(f'/driver/container/{container.id}/start_transfer', follow_redirects=True)
        # Driver arrives at Mangalore
        client.get(f'/driver/container/{container.id}/arrive_at_branch', follow_redirects=True)

        db.session.expire_all()
        container = db.session.get(ContainerTransfer, container.id)
        self.assertEqual(container.status, 'Arrived at Branch')

        # 3. Login as Mangalore Manager to receive entire container
        with client.session_transaction() as sess:
            sess['user_id'] = self.mgr_man_u.id
            sess['role'] = 'Branch Manager'

        res_recv = client.get(f'/branch/containers/{container.id}/receive', follow_redirects=True)
        self.assertEqual(res_recv.status_code, 200)

        db.session.expire_all()
        container = db.session.get(ContainerTransfer, container.id)
        self.assertEqual(container.status, 'Completed')

        sh1_updated = db.session.get(Shipment, sh1.id)
        sh2_updated = db.session.get(Shipment, sh2.id)
        self.assertEqual(sh1_updated.branch_id, self.branch_man.id)
        self.assertEqual(sh2_updated.branch_id, self.branch_man.id)
        self.assertEqual(sh1_updated.status, 'Warehouse')
        self.assertEqual(sh2_updated.status, 'Warehouse')

    def test_delete_container_endpoint(self):
        """Test deleting a container before lock releases orders back to warehouse."""
        client = self.app.test_client()

        # Create shipment at Mumbai
        sh = Shipment(
            tracking_number="LT-DEL-001",
            sender_name="Sender", sender_phone="9820000001", sender_email="deltest@mumbai.com",
            pickup_address_line="Street 1", pickup_city="Mumbai", pickup_state="Maharashtra", pickup_zip_code="400001",
            receiver_name="Receiver", receiver_phone="9811000001",
            receiver_address_line="Road 1", receiver_city="Delhi", receiver_state="Delhi", receiver_zip_code="110001",
            package_category="Electronics", package_weight=20.0,
            delivery_type="Standard", shipping_cost=500.0, status="Warehouse",
            customer_id=self.cust.id, branch_id=self.branch_mum.id
        )
        db.session.add(sh)
        db.session.commit()

        # Create container
        container = ContainerTransfer(
            transfer_code="CONT-BOM-MNG-999",
            from_branch_id=self.branch_mum.id,
            to_branch_id=self.branch_man.id,
            status='Preparing',
            is_locked=False
        )
        container.shipments.append(sh)
        db.session.add(container)
        db.session.commit()

        self.assertEqual(container.total_orders, 1)

        # Login as Mumbai Manager
        with client.session_transaction() as sess:
            sess['user_id'] = self.mgr_mum_u.id
            sess['role'] = 'Branch Manager'

        # Delete container
        res = client.post(f'/branch/containers/{container.id}/delete', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"deleted successfully", res.data)

        # Verify container is removed from DB
        db.session.expire_all()
        deleted_ct = db.session.get(ContainerTransfer, container.id)
        self.assertIsNone(deleted_ct)

        # Verify shipment is restored to warehouse
        sh_restored = db.session.get(Shipment, sh.id)
        self.assertEqual(sh_restored.status, 'Warehouse')
        self.assertIsNone(sh_restored.active_container)

    def test_driver_and_vehicle_relocate_to_arrival_branch_for_return_trip(self):
        """
        Real-world fleet movement test:
        1. Mangalore driver + truck carries container to Bangalore.
        2. Bangalore manager receives container.
        3. Mangalore driver and truck are now stationed at Bangalore (branch_id = Bangalore.id, status = Available).
        4. Bangalore manager can now assign this driver to a return container (Bangalore -> Mangalore).
        """
        client = self.app.test_client()

        # 1. Create order at Mangalore
        sh1 = Shipment(
            tracking_number="LT-MNG-BLR-001",
            sender_name="MNG Sender", sender_phone="9820000001", sender_email="mng@test.com",
            pickup_address_line="MNG Port", pickup_city="Mangalore", pickup_state="Karnataka", pickup_zip_code="575001",
            receiver_name="BLR Receiver", receiver_phone="9811000001",
            receiver_address_line="BLR Tech Park", receiver_city="Bangalore", receiver_state="Karnataka", receiver_zip_code="560001",
            package_category="Electronics", package_weight=50.0,
            delivery_type="Standard", shipping_cost=800.0, status="Warehouse",
            customer_id=self.cust.id, branch_id=self.branch_man.id
        )
        db.session.add(sh1)
        db.session.commit()

        # 2. Mangalore Manager prepares Container to Bangalore with Mangalore Driver
        ct1 = ContainerTransfer(
            transfer_code="CONT-MNG-BLR-888",
            from_branch_id=self.branch_man.id,
            to_branch_id=self.branch_ban.id,
            status='In Transit',
            is_locked=True,
            driver_id=self.d_man.id,
            vehicle_id=self.v_man_truck.id
        )
        ct1.shipments.append(sh1)
        db.session.add(ct1)
        db.session.commit()

        # Driver is currently stationed at Mangalore and Busy
        self.assertEqual(self.d_man.branch_id, self.branch_man.id)

        # 3. Container arrives at Bangalore Hub & Bangalore Manager receives it
        with client.session_transaction() as sess:
            sess['user_id'] = self.mgr_ban_u.id
            sess['role'] = 'Branch Manager'

        res_recv = client.post(f'/branch/containers/{ct1.id}/receive', follow_redirects=True)
        self.assertEqual(res_recv.status_code, 200)
        self.assertIn(b"received successfully", res_recv.data)

        # 4. Verify driver & truck are now stationed AT BANGALORE and Available
        db.session.expire_all()
        d_arrived = db.session.get(Driver, self.d_man.id)
        v_arrived = db.session.get(Vehicle, self.v_man_truck.id)
        self.assertEqual(d_arrived.branch_id, self.branch_ban.id)
        self.assertEqual(d_arrived.status, 'Available')
        self.assertEqual(v_arrived.branch_id, self.branch_ban.id)
        self.assertEqual(v_arrived.availability, 'Available')

        # 5. Bangalore Manager creates a RETURN container (Bangalore -> Mangalore)
        sh_return = Shipment(
            tracking_number="LT-BLR-MNG-RETURN",
            sender_name="BLR Factory", sender_phone="9820000002", sender_email="blr@test.com",
            pickup_address_line="BLR Industrial Area", pickup_city="Bangalore", pickup_state="Karnataka", pickup_zip_code="560002",
            receiver_name="MNG Port", receiver_phone="9811000002",
            receiver_address_line="MNG Port Gate 2", receiver_city="Mangalore", receiver_state="Karnataka", receiver_zip_code="575002",
            package_category="Machine Parts", package_weight=40.0,
            delivery_type="Standard", shipping_cost=700.0, status="Warehouse",
            customer_id=self.cust.id, branch_id=self.branch_ban.id
        )
        db.session.add(sh_return)
        db.session.commit()

        ct_return = ContainerTransfer(
            transfer_code="CONT-BLR-MNG-RETURN",
            from_branch_id=self.branch_ban.id,
            to_branch_id=self.branch_man.id,
            status='Preparing',
            is_locked=False
        )
        ct_return.shipments.append(sh_return)
        db.session.add(ct_return)
        db.session.commit()

        # 6. Bangalore Manager assigns this newly arrived driver to the return container!
        res_assign = client.post(f'/branch/containers/{ct_return.id}/assign-driver', data={
            'driver_id': self.d_man.id
        }, follow_redirects=True)
        self.assertEqual(res_assign.status_code, 200)
        self.assertIn(b"assigned to Container", res_assign.data)

        # Verify Return Container Driver Assignment
        db.session.expire_all()
        ct_ret_assigned = db.session.get(ContainerTransfer, ct_return.id)
        self.assertEqual(ct_ret_assigned.driver_id, self.d_man.id)
        self.assertEqual(ct_ret_assigned.status, 'Driver Assigned')

if __name__ == '__main__':
    unittest.main()
