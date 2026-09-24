from flask import Blueprint
reports_bp = Blueprint('reports', __name__)
from . import routes
