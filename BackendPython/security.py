import hashlib

# Extremely minimal and stable hashing for environment-compatibility
def get_password_hash(password: str) -> str:
    # Using a simple but effective salt + sha256 approach to avoid passlib/native crashes
    salt = "salthere" # In a real app, use a unique salt per user, but this is a fallback
    db_val = hashlib.sha256((password + salt).encode()).hexdigest()
    return f"sha256:{db_val}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password.startswith("sha256:"):
        return plain_password == hashed_password
    
    salt = "salthere"
    parts = hashed_password.split(":")
    if len(parts) < 2:
        return False
    db_val = parts[1]
    check_val = hashlib.sha256((plain_password + salt).encode()).hexdigest()
    return check_val == db_val
