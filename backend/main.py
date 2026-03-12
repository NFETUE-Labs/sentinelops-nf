from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from clickhouse_driver import Client as ClickHouseClient
from pydantic import BaseModel
import os
import uuid

# Config
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://admin:sentinel123@postgres:5432/sentinelops')
SECRET_KEY = os.getenv('SECRET_KEY', 'sentinelops-secret-key-change-in-production')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

# Database
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ClickHouse
ch_client = ClickHouseClient(
    host='clickhouse',
    port=9000,
    user='admin',
    password='sentinel123',
    database='sentinelops'
)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

app = FastAPI(title="SentinelOps API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models
class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    api_key = Column(String, unique=True, default=lambda: str(uuid.uuid4()))
    webhook_url = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# Schemas
class UserCreate(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    api_key: str
    webhook_url: str | None
    created_at: datetime

    class Config:
        from_attributes = True

class WebhookUpdate(BaseModel):
    webhook_url: str

class Token(BaseModel):
    access_token: str
    token_type: str

# Helpers
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str):
    return pwd_context.verify(plain, hashed)

def create_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

# Routes
@app.get("/")
def root():
    return {"service": "SentinelOps API", "version": "0.1.0", "status": "running"}

@app.post("/auth/register", response_model=UserResponse)
def register(data: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=data.email,
        hashed_password=hash_password(data.password)
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@app.post("/auth/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer"}

@app.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user

@app.put("/me/webhook", response_model=UserResponse)
def update_webhook(data: WebhookUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current_user.webhook_url = data.webhook_url
    db.commit()
    db.refresh(current_user)
    return current_user

@app.get("/anomalies")
def get_anomalies(limit: int = 50, current_user: User = Depends(get_current_user)):
    rows = ch_client.execute("""
        SELECT timestamp, service_name, anomaly_type, metric_name,
               expected_value, actual_value, severity
        FROM sentinelops.anomalies
        ORDER BY timestamp DESC
        LIMIT %(limit)s
    """, {'limit': limit})
    return [
        {
            "timestamp": str(row[0]),
            "service_name": row[1],
            "anomaly_type": row[2],
            "metric_name": row[3],
            "expected_value": row[4],
            "actual_value": row[5],
            "severity": row[6]
        }
        for row in rows
    ]

@app.get("/traces")
def get_traces(limit: int = 50, current_user: User = Depends(get_current_user)):
    rows = ch_client.execute("""
        SELECT Timestamp, ServiceName, SpanName, Duration
        FROM sentinelops.traces
        ORDER BY Timestamp DESC
        LIMIT %(limit)s
    """, {'limit': limit})
    return [
        {
            "timestamp": str(row[0]),
            "service_name": row[1],
            "span_name": row[2],
            "duration_ms": round(row[3] / 1e6, 2)
        }
        for row in rows
    ]

@app.get("/stats")
def get_stats(current_user: User = Depends(get_current_user)):
    total_traces = ch_client.execute("SELECT count() FROM sentinelops.traces")[0][0]
    total_anomalies = ch_client.execute("SELECT count() FROM sentinelops.anomalies")[0][0]
    avg_latency = ch_client.execute("""
        SELECT avg(Duration) / 1e6
        FROM sentinelops.traces
        WHERE Timestamp > now() - INTERVAL 1 HOUR
    """)[0][0]
    
    import math
    avg_latency_clean = 0.0 if (avg_latency is None or math.isnan(avg_latency) or math.isinf(avg_latency)) else round(avg_latency, 2)
    
    return {
        "total_traces": total_traces,
        "total_anomalies": total_anomalies,
        "avg_latency_ms": avg_latency_clean
    }