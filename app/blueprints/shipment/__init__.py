from flask import Blueprint
shipment_bp = Blueprint('shipment', __name__)
from . import routes
