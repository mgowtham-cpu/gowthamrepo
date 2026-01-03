from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import SQLModel, Session, create_engine, select
from typing import Optional
from datetime import datetime, timedelta
from passlib.context import CryptContext
from pydantic import BaseModel
import jwt

from .models import User, Post

SECRET = "CHANGE_THIS_SECRET"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(title="Flavor Club")

# SQLite for MVP
engine = create_engine("sqlite:///./food_forum.db", connect_args={"check_same_thread": False})
SQLModel.metadata.create_all(engine)

class UserCreate(BaseModel):
    username: str
    email: str
    password: str

def get_session():
    with Session(engine) as session:
        yield session

def create_access_token(data: dict, expires_minutes: int = 60*24):
    to_encode = data.copy()
    to_encode.update({"exp": datetime.utcnow() + timedelta(minutes=expires_minutes)})
    return jwt.encode(to_encode, SECRET, algorithm="HS256")

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def get_password_hash(password):
    return pwd_context.hash(password)

@app.post("/auth/register")
def register(payload: UserCreate, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.email == payload.email)).first()
    if user:
        raise HTTPException(status_code=400, detail="Email already registered")
    u = User(username=payload.username, email=payload.email, password_hash=get_password_hash(payload.password))
    session.add(u); session.commit(); session.refresh(u)
    token = create_access_token({"sub": u.email})
    return {"access_token": token, "token_type": "bearer", "user": {"id": u.id, "username": u.username}}

@app.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.email == form.username)).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer", "user": {"id": user.id, "username": user.username}}

@app.post("/posts")
def create_post(title: str, body: str, session: Session = Depends(get_session), authorization: Optional[str] = None):
    # Very simple auth parsing (for MVP only). In production validate JWT and fetch user.
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    token = authorization.split("Bearer ")[-1]
    try:
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        email = payload.get("sub")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = session.exec(select(User).where(User.email == email)).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    p = Post(title=title, body=body, author_id=user.id)
    session.add(p); session.commit(); session.refresh(p)
    return p

@app.get("/posts")
def list_posts(skip: int = 0, limit: int = 20, session: Session = Depends(get_session)):
    posts = session.exec(select(Post).offset(skip).limit(limit).order_by(Post.created_at.desc())).all()
    return posts

@app.get("/posts/{post_id}")
def get_post(post_id: int, session: Session = Depends(get_session)):
    post = session.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post