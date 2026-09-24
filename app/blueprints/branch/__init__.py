from flask import Blueprint
branch_bp = Blueprint('branch', __name__)
from . import routes
