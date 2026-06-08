import hashlib
from passlib.context import CryptContext
 
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
 
def preprocess(password: str) -> str:
    """SHA-256 pre-hash before bcrypt (handles passwords >72 bytes safely)."""
    return hashlib.sha256(password.encode()).hexdigest()
 
def hash_password(password: str) -> str:
    return pwd_context.hash(preprocess(password))
 
def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(preprocess(plain), hashed)