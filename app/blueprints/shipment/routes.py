from flask import request, jsonify
from app.utils import calculate_shipping_cost
from app.models import Shipment, TrackingLog
from . import shipment_bp

@shipment_bp.route('/calculate-cost', methods=['POST'])
def calculate_cost_api():
    data = request.get_json() or {}
    
    # Try fetching params
    try:
        weight = float(data.get('weight', 0))
        delivery_type = data.get('delivery_type', 'Standard')
        fragile = bool(data.get('fragile', False))
        insurance = bool(data.get('insurance', False))
        package_category = data.get('package_category', 'Other')
        
        declared_value = float(data.get('declared_value', 0.0))
        cost = calculate_shipping_cost(weight, delivery_type, fragile, insurance, package_category, declared_value)
        return jsonify({
            'success': True,
            'cost': cost
        })
    except (ValueError, TypeError) as e:
        return jsonify({
            'success': False,
            'message': 'Invalid inputs provided.'
        }), 400

@shipment_bp.route('/api/track/<tracking_number>')
def tracking_info_api(tracking_number):
    shipment = Shipment.query.filter_by(tracking_number=tracking_number).first()
    if not shipment:
        return jsonify({
            'success': False,
            'message': 'Shipment not found'
        }), 404
        
    logs = TrackingLog.query.filter_by(shipment_id=shipment.id).order_by(TrackingLog.update_time.asc()).all()
    logs_data = [{
        'location': log.current_location,
        'status': log.status,
        'description': log.description,
        'time': log.update_time.strftime('%Y-%m-%d %H:%M:%S')
    } for log in logs]
    
    return jsonify({
        'success': True,
        'tracking_number': shipment.tracking_number,
        'status': shipment.status,
        'pickup_city': shipment.pickup_city,
        'receiver_city': shipment.receiver_city,
        'logs': logs_data
    })
