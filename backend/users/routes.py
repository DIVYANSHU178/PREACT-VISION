from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required
from .models import User
from ..database.db import db
from ..cameras.routes import admin_required

users_bp = Blueprint("users", __name__)

@users_bp.route("/pending", methods=["GET"])
@jwt_required()
@admin_required
def pending_users():
    users = User.query.filter_by(is_approved=False).all()
    # If there is an is_verified field, use it. If not, don't.
    # Looking at other routes, we'll keep it simple:
    return jsonify([
        {"id": u.id, "email": u.email, "fullname": u.fullname, "organization": u.organization}
        for u in users
    ])


@users_bp.route("/approve/<int:user_id>", methods=["POST"])
@jwt_required()
@admin_required
def approve_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"message": "User not found"}), 404
    user.is_approved = True
    db.session.commit()
    return jsonify({"message": "User approved"}), 200
