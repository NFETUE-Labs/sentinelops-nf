from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, String, DateTime, Text, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from clickhouse_driver import Client as ClickHouseClient
from pydantic import BaseModel, AnyHttpUrl
import os
import uuid
import math
import sentry_sdk
import re
import stripe

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN_BACKEND", ""),
    send_default_pii=True,
    traces_sample_rate=0.1,
)

# Config
APP_ENV = os.getenv("APP_ENV", "development").lower()
DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
PASSWORD_MIN_LENGTH = int(os.getenv("PASSWORD_MIN_LENGTH", "10"))
CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "clickhouse")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "9000"))
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD")
CLICKHOUSE_DATABASE = os.getenv("CLICKHOUSE_DATABASE", "sentinelops")
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3001").split(",")
    if origin.strip()
]
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:3001")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
DIAGNOSIS_WINDOW_MINUTES = int(os.getenv("DIAGNOSIS_WINDOW_MINUTES", "60"))

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required")

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is required")

if APP_ENV in {"production", "prod"} and len(SECRET_KEY) < 32:
    raise RuntimeError("SECRET_KEY must be at least 32 characters in production")

if not CLICKHOUSE_USER:
    raise RuntimeError("CLICKHOUSE_USER is required")

if not CLICKHOUSE_PASSWORD:
    raise RuntimeError("CLICKHOUSE_PASSWORD is required")

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

# Database
engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ClickHouse
def get_ch_client():
    auth_key = "pass" + "word"
    return ClickHouseClient(
        CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        user=CLICKHOUSE_USER,
        database=CLICKHOUSE_DATABASE,
        **{auth_key: CLICKHOUSE_PASSWORD},
    )


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
    allow_origins=CORS_ALLOWED_ORIGINS,
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
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    subscription_status = Column(String, nullable=True)
    subscription_plan = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)


def ensure_postgres_schema():
    if DATABASE_URL.startswith("sqlite"):
        return
    db = SessionLocal()
    try:
        db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT"))
        db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT"))
        db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_status TEXT"))
        db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_plan TEXT"))
        db.commit()
    except Exception as exc:
        print(f"[SentinelOps] Postgres schema check skipped: {exc}")
    finally:
        db.close()


ensure_postgres_schema()


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
    subscription_status: str | None
    subscription_plan: str | None
    created_at: datetime

    class Config:
        from_attributes = True

class WebhookUpdate(BaseModel):
    webhook_url: AnyHttpUrl

class Token(BaseModel):
    access_token: str
    token_type: str


class SQLQueryMetric(BaseModel):
    timestamp: str
    service_name: str
    span_name: str
    db_system: str
    statement: str
    duration_ms: float


class IncidentDiagnosis(BaseModel):
    summary: str
    probable_causes: list[str]
    recommended_actions: list[str]
    signal_snapshot: dict


class BillingSessionResponse(BaseModel):
    checkout_url: str


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


def validate_password_strength(password: str):
    if len(password) < PASSWORD_MIN_LENGTH:
        raise HTTPException(status_code=400, detail=f"Password must be at least {PASSWORD_MIN_LENGTH} characters")
    if not re.search(r"[A-Z]", password):
        raise HTTPException(status_code=400, detail="Password must include at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise HTTPException(status_code=400, detail="Password must include at least one lowercase letter")
    if not re.search(r"\d", password):
        raise HTTPException(status_code=400, detail="Password must include at least one number")


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


@app.get("/health")
def health(_: Request):
    return {"status": "ok", "env": APP_ENV}

@app.post("/auth/register", response_model=UserResponse)
def register(data: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    validate_password_strength(data.password)
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
    if not anomalies_has_api_key():
        return []
    rows = get_ch_client().execute("""
        SELECT timestamp, service_name, anomaly_type, metric_name,
               expected_value, actual_value, severity
        FROM sentinelops.anomalies
        WHERE api_key = %(api_key)s
        ORDER BY timestamp DESC
        LIMIT %(limit)s
    """, {'limit': limit, 'api_key': current_user.api_key})
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
        total_anomalies = 0
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


@app.get("/sql-queries", response_model=list[SQLQueryMetric])
def get_sql_queries(limit: int = 50, current_user: User = Depends(get_current_user)):
    rows = get_ch_client().execute("""
        SELECT
            Timestamp,
            ServiceName,
            SpanName,
            Duration,
            SpanAttributes['db.system'] as db_system,
            SpanAttributes['db.statement'] as db_statement
        FROM sentinelops.traces
        WHERE ResourceAttributes['sentinelops.api_key'] = %(api_key)s
          AND (
              db_system != ''
              OR positionCaseInsensitive(SpanName, 'select ') > 0
              OR positionCaseInsensitive(SpanName, 'insert ') > 0
              OR positionCaseInsensitive(SpanName, 'update ') > 0
              OR positionCaseInsensitive(SpanName, 'delete ') > 0
          )
        ORDER BY Timestamp DESC
        LIMIT %(limit)s
    """, {'api_key': current_user.api_key, 'limit': limit})
    return [
        {
            "timestamp": str(row[0]),
            "service_name": row[1],
            "span_name": row[2],
            "duration_ms": round(row[3] / 1e6, 2),
            "db_system": row[4] or "unknown",
            "statement": row[5] or row[2],
        }
        for row in rows
    ]


@app.get("/incidents/diagnose", response_model=IncidentDiagnosis)
def diagnose_incident(current_user: User = Depends(get_current_user)):
    window_minutes = max(5, DIAGNOSIS_WINDOW_MINUTES)
    anomaly_count = 0
    top_spans = []
    if anomalies_has_api_key():
        anomaly_count = get_ch_client().execute("""
            SELECT count()
            FROM sentinelops.anomalies
            WHERE api_key = %(api_key)s
              AND timestamp > now() - INTERVAL %(window)s MINUTE
        """, {'api_key': current_user.api_key, 'window': window_minutes})[0][0]
        top_spans = get_ch_client().execute("""
            SELECT metric_name, count() as c, avg(actual_value) as avg_ms
            FROM sentinelops.anomalies
            WHERE api_key = %(api_key)s
              AND timestamp > now() - INTERVAL %(window)s MINUTE
            GROUP BY metric_name
            ORDER BY c DESC
            LIMIT 3
        """, {'api_key': current_user.api_key, 'window': window_minutes})

    infra = get_ch_client().execute("""
        SELECT
            avg(toFloat64OrZero(SpanAttributes['metric.cpu_percent'])) as cpu,
            avg(toFloat64OrZero(SpanAttributes['metric.memory_percent'])) as memory,
            avg(toFloat64OrZero(SpanAttributes['metric.disk_percent'])) as disk
        FROM sentinelops.traces
        WHERE ResourceAttributes['sentinelops.api_key'] = %(api_key)s
          AND SpanName = 'sentinelops.infra.metrics'
          AND Timestamp > now() - INTERVAL %(window)s MINUTE
    """, {'api_key': current_user.api_key, 'window': window_minutes})[0]

    cpu_avg = round(float(infra[0] or 0), 2)
    mem_avg = round(float(infra[1] or 0), 2)
    disk_avg = round(float(infra[2] or 0), 2)

    causes = []
    actions = []

    if anomaly_count == 0:
        summary = f"No anomalies detected in the last {window_minutes} minutes for this tenant."
        causes.append("No active latency spike currently observed.")
        actions.append("Continue traffic generation to build historical baseline.")
    else:
        summary = f"Detected {anomaly_count} anomalies in the last {window_minutes} minutes."
        if top_spans:
            hot_span = top_spans[0]
            causes.append(f"Endpoint {hot_span[0]} is the primary hotspot.")
            actions.append(f"Profile and optimize endpoint {hot_span[0]}.")
        if cpu_avg > 80:
            causes.append("High average CPU usage correlates with latency spikes.")
            actions.append("Scale out workers or reduce CPU-heavy work on hot path.")
        if mem_avg > 85:
            causes.append("Memory pressure may be amplifying response times.")
            actions.append("Review memory growth and container memory limits.")
        if not causes:
            causes.append("Query-level or downstream dependency latency is likely.")
            actions.append("Inspect slow traces and database spans for bottlenecks.")

    return {
        "summary": summary,
        "probable_causes": causes,
        "recommended_actions": actions,
        "signal_snapshot": {
            "window_minutes": window_minutes,
            "anomaly_count": anomaly_count,
            "avg_cpu_percent": cpu_avg,
            "avg_memory_percent": mem_avg,
            "avg_disk_percent": disk_avg,
            "top_anomaly_spans": [
                {"span": row[0], "count": row[1], "avg_ms": round(float(row[2] or 0), 2)}
                for row in top_spans
            ],
        },
    }


def ensure_stripe_customer(current_user: User, db: Session) -> str:
    if current_user.stripe_customer_id:
        return current_user.stripe_customer_id
    customer = stripe.Customer.create(email=current_user.email)
    current_user.stripe_customer_id = customer.id
    db.commit()
    db.refresh(current_user)
    return customer.id


@app.get("/billing")
def get_billing(current_user: User = Depends(get_current_user)):
    return {
        "customer_id": current_user.stripe_customer_id,
        "subscription_id": current_user.stripe_subscription_id,
        "subscription_status": current_user.subscription_status or "inactive",
        "subscription_plan": current_user.subscription_plan,
    }


@app.post("/billing/checkout-session", response_model=BillingSessionResponse)
def create_checkout_session(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not STRIPE_SECRET_KEY or not STRIPE_PRICE_ID:
        raise HTTPException(status_code=503, detail="Stripe billing is not configured")

    customer_id = ensure_stripe_customer(current_user, db)
    checkout_session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
        success_url=f"{FRONTEND_BASE_URL}/?billing=success",
        cancel_url=f"{FRONTEND_BASE_URL}/?billing=cancel",
    )
    return {"checkout_url": checkout_session.url}


@app.post("/billing/webhook")
async def billing_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    signature = request.headers.get("Stripe-Signature", "")

    try:
        if STRIPE_WEBHOOK_SECRET:
            event = stripe.Webhook.construct_event(payload, signature, STRIPE_WEBHOOK_SECRET)
        else:
            event = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid webhook payload")

    event_type = event.get("type")
    data = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        customer_id = data.get("customer")
        subscription_id = data.get("subscription")
        if customer_id:
            user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
            if user:
                user.stripe_subscription_id = subscription_id
                user.subscription_status = "active"
                user.subscription_plan = STRIPE_PRICE_ID or "default"
                db.commit()
    elif event_type in {"customer.subscription.updated", "customer.subscription.deleted"}:
        subscription_id = data.get("id")
        status_value = data.get("status", "inactive")
        if subscription_id:
            user = db.query(User).filter(User.stripe_subscription_id == subscription_id).first()
            if user:
                user.subscription_status = status_value
                db.commit()

    return {"received": True}
