import bcrypt
import secrets
import string

def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(hash_pw, password):
    return bcrypt.checkpw(password.encode(), hash_pw.encode())

def generate_password(length=10):
    chars = string.ascii_letters + string.digits + "@#%!"
    return ''.join(secrets.choice(chars) for _ in range(length))
