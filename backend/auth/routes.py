from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt, verify_jwt_in_request
from functools import wraps
from datetime import datetime, timedelta
import random

from ..users.models import User
from ..database.db import db
from .utils import hash_password, verify_password, generate_password
from .smtp import send_email

auth_bp = Blueprint("auth", __name__)

# In-memory storage for OTPs: { email: { 'otp': '123456', 'expiry': datetime_obj } }
otp_storage = {}

# =====================================================
# DECORATOR: LOGIN REQUIRED (Now JWT based)
# =====================================================
def login_required(admin_only=False):
    def wrapper(fn):
        @wraps(fn)
        def decorator(*args, **kwargs):
            try:
                verify_jwt_in_request()
            except Exception as e:
                print(f"JWT Verification Failed: {e}")
                raise e
            claims = get_jwt()
            if admin_only and claims.get('role') != 'admin':
                return jsonify(msg="Admins only!"), 403
            return fn(*args, **kwargs)
        return decorator
    return wrapper


# =====================================================
# REQUEST ACCESS (USER)
# =====================================================
@auth_bp.route("/register", methods=["POST"])
def request_access():
    data = request.json or {}
    fullname = data.get("fullname")
    email = data.get("email")
    organization = data.get("organization")

    if not fullname or not email or not organization:
        return jsonify({"error": "Missing fields"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "User already exists or pending approval"}), 409

    user = User(
        fullname=fullname, email=email, organization=organization,
        role="user", is_approved=False, password_hash=None
    )
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": "Access request submitted. Await admin approval."}), 201


# =====================================================
# LOGIN (USER + ADMIN)
# =====================================================
@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.json or {}
    identifier = data.get("identifier")
    password = data.get("password")

    if not identifier or not password:
        return jsonify({"error": "Missing credentials"}), 400

    user = User.query.filter_by(email=identifier).first()

    if not user or not user.password_hash or not verify_password(user.password_hash, password):
        return jsonify({"error": "Invalid credentials"}), 401

    if user.role != 'admin' and not user.is_approved:
        return jsonify({"error": "Admin approval pending"}), 403

    # Create and return JWT access token
    access_token = create_access_token(identity=str(user.id), additional_claims={'role': user.role})

    return jsonify({
        "message": "Login successful",
        "access_token": access_token,
        "user": { "id": user.id, "fullname": user.fullname, "email": user.email, "role": user.role }
    })

# =====================================================
# LOGOUT
# =====================================================
@auth_bp.route("/logout", methods=["POST"])
def logout():
    # For JWT, logout is handled client-side by deleting the token.
    # This endpoint can be kept for semantics or future blocklisting.
    return jsonify({"message": "Logout successful. Client should delete token."}), 200


# =====================================================
# GET USER PROFILE (PROTECTED)
# =====================================================
@auth_bp.route("/profile", methods=["GET"])
@login_required()
def user_profile():
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)

    if not user:
        return jsonify({"error": "User not found."}), 404

    return jsonify({
        "id": user.id,
        "fullname": user.fullname,
        "email": user.email,
        "role": user.role,
        "is_approved": user.is_approved
    })


# =====================================================
# ADMIN — VIEW PENDING REQUESTS
# =====================================================
@auth_bp.route("/admin/pending", methods=["GET"])
@login_required(admin_only=True)
def admin_pending_requests():
    users = User.query.filter_by(role="user", is_approved=False).all()
    return jsonify([
        {
            "id": u.id, "fullname": u.fullname, "email": u.email,
            "organization": u.organization, "created_at": u.created_at.strftime("%Y-%m-%d %H:%M")
        } for u in users
    ])


# =====================================================
# ADMIN — APPROVE USER
# =====================================================
@auth_bp.route("/admin/approve", methods=["POST"])
@login_required(admin_only=True)
def admin_approve_user():
    data = request.json or {}
    user_id = data.get("user_id")

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    if user.is_approved:
        return jsonify({"error": "User already approved"}), 400

    password = generate_password()
    user.password_hash = hash_password(password)
    user.is_approved = True
    db.session.commit()

    try:
        send_email(
            user.email, "PREACT VISION – Access Approved",
            f"Hello {user.fullname},\n\nYour access request has been approved.\n\n"
            f"Login Credentials:\nEmail: {user.email}\nPassword: {password}\n\n"
            f"Please change your password after first login.\n\n— PREACT VISION Team"
        )
        return jsonify({"message": "User approved and credentials sent"})
    except Exception as e:
        print(f"SMTP Error: {e}")
        return jsonify({"message": "User approved, but failed to send email. Check SMTP settings."}), 207


# =====================================================
# ADMIN — REJECT USER
# =====================================================
@auth_bp.route("/admin/reject", methods=["POST"])
@login_required(admin_only=True)
def admin_reject_user():
    data = request.json or {}
    user_id = data.get("user_id")

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "User rejected"})


# =====================================================
# FORGOT PASSWORD (OTP BASED)
# =====================================================
@auth_bp.route("/forgot-password/request-otp", methods=["POST"])
def request_forgot_password_otp():
    email = request.json.get("email")
    if not email:
        return jsonify({"error": "Email is required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        # Return a generic success to avoid email enumeration
        return jsonify({"message": "If the email is registered, an OTP has been sent."}), 200

    otp = str(random.randint(100000, 999999))
    expiry_time = datetime.now() + timedelta(minutes=10) # OTP valid for 10 minutes

    otp_storage[email] = {'otp': otp, 'expiry': expiry_time}

    try:
        send_email(
            user.email,
            "PREACT VISION – Password Reset OTP",
            f"Hello {user.fullname},\n\nYour One-Time Password (OTP) for password reset is: {otp}\n\nThis OTP is valid for 10 minutes.\n\n— PREACT VISION Team"
        )
        return jsonify({"message": "OTP has been sent to your email."}), 200
    except Exception as e:
        print(f"SMTP Error: {e}")
        return jsonify({"error": "Failed to send OTP email. Please check SMTP settings."}), 500

@auth_bp.route("/forgot-password/reset", methods=["POST"])
def reset_password_with_otp():
    email = request.json.get("email")
    otp = request.json.get("otp")
    new_password = request.json.get("new_password")

    if not all([email, otp, new_password]):
        return jsonify({"error": "Email, OTP, and new password are required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    stored_otp_data = otp_storage.get(email)

    if not stored_otp_data or stored_otp_data['otp'] != otp:
        return jsonify({"error": "Invalid OTP"}), 400

    if datetime.now() > stored_otp_data['expiry']:
        del otp_storage[email] # Remove expired OTP
        return jsonify({"error": "OTP has expired"}), 400

    user.password_hash = hash_password(new_password)
    db.session.commit()

    del otp_storage[email] # OTP used, remove it
    return jsonify({"message": "Password has been reset successfully."}), 200