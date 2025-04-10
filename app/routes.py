from flask import Blueprint

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def home():
    return "Hello from Flask app!"

@main_bp.route('/api/test')
def test():
    return {"status": "success", "message": "API is working!"}
