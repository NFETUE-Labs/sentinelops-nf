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
import math
import sentry_sdk

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN_BACKEND", ""),
    send_default_pii=True,
    traces_sample_rate=0.1,
)

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
def get_ch_client():
    return ClickHouseClient('clickhouse', user='admin', password='sentinel123', database='sentinelops')


def ensure_clickhouse_schema():
    client = get_ch_client()
    try:
        client.execute("""
            ALTER TABLE sentinelops.anomalies
            ADD COLUMN IF NOT EXISTS api_key String DEFAULT ''
        """)
    except Exception as exc:
        # Keep API startup resilient even if ClickHouse is not ready yet.
        print(f"[SentinelOps] ClickHouse schema check skipped: {exc}")


def anomalies_has_api_key() -> bool:
    try:
        rows = get_ch_client().execute("""
            SELECT count()
            FROM system.columns
            WHERE database = 'sentinelops'
            AND table = 'anomalies'
            AND name = 'api_key'
        """)
        return rows[0][0] > 0
    except Exception:
        return False

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

app = FastAPI(title="SentinelOps API", version="0.1.0")

ensure_clickhouse_schema()

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


def seed_demo_user():
    demo_email = os.getenv("DEMO_USER_EMAIL")
    demo_password = os.getenv("DEMO_USER_PASSWORD")
    demo_api_key = os.getenv("DEMO_USER_API_KEY")

    if not demo_email or not demo_password or not demo_api_key:
        return

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == demo_email).first()
        if user:
            if user.api_key != demo_api_key:
                user.api_key = demo_api_key
                db.commit()
            return

        user = User(
            email=demo_email,
            hashed_password=hash_password(demo_password),
            api_key=demo_api_key,
        )
        db.add(user)
        db.commit()
    finally:
        db.close()

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


class ContainerMetric(BaseModel):
    timestamp: str
    service_name: str
    container_id: str
    container_name: str
    container_image: str
    container_status: str
    cpu_percent: float
    memory_percent: float
    memory_usage_mb: float
    memory_limit_mb: float
    network_rx_mb: float
    network_tx_mb: float

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


seed_demo_user()

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
    if anomalies_has_api_key():
        rows = get_ch_client().execute("""
            SELECT timestamp, service_name, anomaly_type, metric_name,
                   expected_value, actual_value, severity
            FROM sentinelops.anomalies
            WHERE api_key = %(api_key)s
            ORDER BY timestamp DESC
            LIMIT %(limit)s
        """, {'limit': limit, 'api_key': current_user.api_key})
    else:
        rows = get_ch_client().execute("""
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
    rows = get_ch_client().execute("""
        SELECT Timestamp, ServiceName, SpanName, Duration
        FROM sentinelops.traces
        WHERE ResourceAttributes['sentinelops.api_key'] = %(api_key)s
        ORDER BY Timestamp DESC
        LIMIT %(limit)s
    """, {'limit': limit, 'api_key': current_user.api_key})
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
    api_key = current_user.api_key
    total_traces = get_ch_client().execute("""
        SELECT count() FROM sentinelops.traces
        WHERE ResourceAttributes['sentinelops.api_key'] = %(api_key)s
    """, {'api_key': api_key})[0][0]
    if anomalies_has_api_key():
        total_anomalies = get_ch_client().execute("""
            SELECT count() FROM sentinelops.anomalies
            WHERE api_key = %(api_key)s
        """, {'api_key': api_key})[0][0]
    else:
        total_anomalies = get_ch_client().execute("""
            SELECT count() FROM sentinelops.anomalies
        """)[0][0]
    avg_latency = get_ch_client().execute("""
        SELECT avg(Duration) / 1e6
        FROM sentinelops.traces
        WHERE ResourceAttributes['sentinelops.api_key'] = %(api_key)s
        AND Timestamp > now() - INTERVAL 1 HOUR
    """, {'api_key': api_key})[0][0]

    avg_latency_clean = 0.0 if (avg_latency is None or math.isnan(avg_latency) or math.isinf(avg_latency)) else round(avg_latency, 2)

    return {
        "total_traces": total_traces,
        "total_anomalies": total_anomalies,
        "avg_latency_ms": avg_latency_clean
    }

@app.get("/infra")
def get_infra(current_user: User = Depends(get_current_user)):
    rows = get_ch_client().execute("""
        SELECT
            Timestamp,
            ServiceName,
            SpanAttributes['metric.cpu_percent'] as cpu,
            SpanAttributes['metric.memory_percent'] as memory,
            SpanAttributes['metric.disk_percent'] as disk
        FROM sentinelops.traces
        WHERE ResourceAttributes['sentinelops.api_key'] = %(api_key)s
        AND SpanName = 'sentinelops.infra.metrics'
        ORDER BY Timestamp DESC
        LIMIT 20
    """, {'api_key': current_user.api_key})
    return [
        {
            "timestamp": str(row[0]),
            "service_name": row[1],
            "cpu_percent": float(row[2]) if row[2] else 0,
            "memory_percent": float(row[3]) if row[3] else 0,
            "disk_percent": float(row[4]) if row[4] else 0
        }
        for row in rows
    ]


@app.get("/containers", response_model=list[ContainerMetric])
def get_containers(limit: int = 50, current_user: User = Depends(get_current_user)):
    rows = get_ch_client().execute("""
        SELECT
            Timestamp,
            ServiceName,
            SpanAttributes['container.id'] as container_id,
            SpanAttributes['container.name'] as container_name,
            SpanAttributes['container.image'] as container_image,
            SpanAttributes['container.status'] as container_status,
            SpanAttributes['metric.cpu_percent'] as cpu,
            SpanAttributes['metric.memory_percent'] as memory_percent,
            SpanAttributes['metric.memory_usage_mb'] as memory_usage_mb,
            SpanAttributes['metric.memory_limit_mb'] as memory_limit_mb,
            SpanAttributes['metric.network_rx_mb'] as network_rx_mb,
            SpanAttributes['metric.network_tx_mb'] as network_tx_mb
        FROM sentinelops.traces
        WHERE ResourceAttributes['sentinelops.api_key'] = %(api_key)s
        AND SpanName = 'sentinelops.container.metrics'
        ORDER BY Timestamp DESC
        LIMIT %(limit)s
    """, {'api_key': current_user.api_key, 'limit': limit})
    return [
        {
            "timestamp": str(row[0]),
            "service_name": row[1],
            "container_id": row[2] or "",
            "container_name": row[3] or "",
            "container_image": row[4] or "",
            "container_status": row[5] or "",
            "cpu_percent": float(row[6]) if row[6] else 0,
            "memory_percent": float(row[7]) if row[7] else 0,
            "memory_usage_mb": float(row[8]) if row[8] else 0,
            "memory_limit_mb": float(row[9]) if row[9] else 0,
            "network_rx_mb": float(row[10]) if row[10] else 0,
            "network_tx_mb": float(row[11]) if row[11] else 0,
        }
        for row in rows
    ]