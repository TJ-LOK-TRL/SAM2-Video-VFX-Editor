from flask import Blueprint, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()
auth_bp = Blueprint('auth', __name__)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({'error': 'Email e password são obrigatórios.'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email já está registado.'}), 400

    new_user = User(email=email, password=generate_password_hash(password))
    db.session.add(new_user)
    db.session.commit()

    access_token = create_access_token(identity=email)
    return jsonify({'access_token': access_token, 'email': email}), 201


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password, password):
        return jsonify({'error': 'Credenciais inválidas.'}), 401

    access_token = create_access_token(identity=email)
    return jsonify({'access_token': access_token, 'email': email}), 200


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def me():
    return jsonify({'email': get_jwt_identity()}), 200
