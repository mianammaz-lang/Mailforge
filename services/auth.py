import jwt
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Request, HTTPException, Depends
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from database.database import get_db
from database.models import User
from config.settings import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SESSION_SECRET, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, settings.SESSION_SECRET, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid session")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid session")
        
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user

def ensure_admin_exists(db: Session):
    admin = db.query(User).filter(User.email == settings.ADMIN_EMAIL).first()
    if not admin and settings.ADMIN_PASSWORD:
        hashed = get_password_hash(settings.ADMIN_PASSWORD)
        new_admin = User(email=settings.ADMIN_EMAIL, password_hash=hashed)
        db.add(new_admin)
        db.commit()
