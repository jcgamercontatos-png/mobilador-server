import os
import sys
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager

import jwt
import bcrypt
from fastapi import FastAPI, HTTPException, Depends, status, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import declarative_base, Session, sessionmaker

DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{os.path.join(DIR, 'mobilador.db')}")
SECRET_KEY = os.environ.get("SECRET_KEY", "M0b1l4d0rS3cr3tK3y!2024#SuperS3cur3")
IS_SQLITE = DATABASE_URL.startswith("sqlite")

Base = declarative_base()


class UserDB(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(255), default="")
    license_valid = Column(Boolean, default=True)
    license_type = Column(String(50), default="permanent")
    license_days = Column(Integer, default=0)
    license_start = Column(DateTime, default=None, nullable=True)
    device_id = Column(String(255), default=None, nullable=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


engine_args = {"connect_args": {"check_same_thread": False}} if IS_SQLITE else {}
engine = create_engine(DATABASE_URL, **engine_args)
SessionLocal = sessionmaker(bind=engine)


def migrate_db():
    if not IS_SQLITE:
        return
    import sqlite3
    conn = sqlite3.connect(DATABASE_URL.replace("sqlite:///", ""))
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(users)")
    cols = [row[1] for row in cursor.fetchall()]
    for col in ["device_id", "license_type", "license_days", "license_start"]:
        if col not in cols:
            if col == "license_type":
                cursor.execute("ALTER TABLE users ADD COLUMN license_type VARCHAR DEFAULT 'permanent'")
            elif col == "license_days":
                cursor.execute("ALTER TABLE users ADD COLUMN license_days INTEGER DEFAULT 0")
            elif col == "license_start":
                cursor.execute("ALTER TABLE users ADD COLUMN license_start TIMESTAMP")
            elif col == "device_id":
                cursor.execute("ALTER TABLE users ADD COLUMN device_id VARCHAR")
    cursor.execute("PRAGMA table_info(security_events)")
    sec_cols = [row[1] for row in cursor.fetchall()]
    if not sec_cols:
        cursor.execute("""
            CREATE TABLE security_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username VARCHAR DEFAULT '',
                event_type VARCHAR,
                device_id VARCHAR DEFAULT '',
                details VARCHAR DEFAULT '',
                ip VARCHAR DEFAULT '',
                created_at TIMESTAMP
            )
        """)
    conn.commit()
    conn.close()


Base.metadata.create_all(engine)
migrate_db()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_license(user: UserDB) -> tuple[bool, str | None]:
    if user.license_type == "permanent":
        return True, None
    if user.license_type == "temporary" and user.license_days and user.license_start:
        expires = user.license_start + timedelta(days=user.license_days)
        if datetime.now(timezone.utc) > expires:
            return False, expires.isoformat()
        return True, expires.isoformat()
    return True, None


def format_date(dt: datetime) -> str:
    return dt.strftime("%d/%m/%Y %H:%M")


# --- Models ---

class LoginRequest(BaseModel):
    username: str
    password: str
    device_id: str | None = None


class LoginResponse(BaseModel):
    token: str
    expires_at: str
    user_id: int
    username: str
    display_name: str
    license_valid: bool
    license_until: str | None = None
    license_type: str = "permanent"
    license_days_remaining: int | None = None
    is_admin: bool = False
    device_locked: bool = False


class ValidateResponse(BaseModel):
    valid: bool
    user_id: int
    username: str
    display_name: str
    license_valid: bool
    license_until: str | None = None
    license_type: str = "permanent"
    license_days_remaining: int | None = None
    is_admin: bool = False


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"


class SecurityVerifyRequest(BaseModel):
    token: str
    signature_hash: str
    package_name: str
    device_id: str


class SecurityVerifyResponse(BaseModel):
    allowed: bool
    integrity_ok: bool
    license_ok: bool
    device_ok: bool
    message: str = ""


class SecurityEvent(BaseModel):
    token: str
    event_type: str
    device_id: str
    details: str = ""


class SecurityEventLog(Base):
    __tablename__ = "security_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(255), default="")
    event_type = Column(String(255))
    device_id = Column(String(255), default="")
    details = Column(String(1000), default="")
    ip = Column(String(255), default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class CalculateRequest(BaseModel):
    mouse_dpi: int
    resolution_width: int
    resolution_height: int
    mobilador_dpi: int


class CalculateResponse(BaseModel):
    sensitivity_x: int
    sensitivity_y: int
    raw_x: float = 0.0
    raw_y: float = 0.0
    switch_sensitivity_x: int = 0
    switch_sensitivity_y: int = 0
    switch_raw_x: float = 0.0
    switch_raw_y: float = 0.0
    description: str = ""
    aspect_ratio: float = 0.0
    aspect_label: str = ""
    ppi: float = 0.0
    debug_dpi_factor: float = 0.0
    debug_gg_factor: float = 0.0
    debug_fps_factor: float = 0.0
    debug_pixel_factor: float = 0.0
    debug_ppi_factor: float = 0.0
    debug_base_sensitivity: float = 0.0
    balanced: bool = False


# --- Auth ---

def create_token(user: UserDB) -> str:
    payload = {
        "user_id": user.id,
        "username": user.username,
        "exp": datetime.now(timezone.utc) + timedelta(days=30),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token invalido")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


# --- FastAPI ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    migrate_db()
    db = SessionLocal()
    admin = db.query(UserDB).filter(UserDB.username == "admin").first()
    if not admin:
        db.add(UserDB(username="admin", password_hash=hash_password("admin"),
                      display_name="Administrador", is_admin=True,
                      license_type="permanent"))
        db.commit()
    db.close()
    yield


app = FastAPI(title="Mobilador Server", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates_dir = os.path.join(DIR, "templates")
os.makedirs(templates_dir, exist_ok=True)
templates = Jinja2Templates(directory=templates_dir)


# --- API Endpoints ---

@app.get("/api/health", response_model=HealthResponse)
def health():
    return HealthResponse()


@app.post("/api/auth/login", response_model=LoginResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.username == req.username).first()
    if not user or not check_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Usuario ou senha invalidos")

    lic_valid, lic_until = check_license(user)
    if not lic_valid:
        raise HTTPException(status_code=403, detail="Licenca expirada")

    if not req.device_id:
        raise HTTPException(status_code=400, detail="Identificador do dispositivo obrigatorio")

    if user.device_id and user.device_id != req.device_id:
        raise HTTPException(status_code=403, detail="Conta ja vinculada a outro dispositivo. Pec,a ao administrador desvincular.")

    if not user.device_id:
        user.device_id = req.device_id
        db.commit()

    token = create_token(user)
    days_remaining = None
    if user.license_type == "temporary" and user.license_start:
        expires = user.license_start + timedelta(days=user.license_days)
        days_remaining = max(0, (expires - datetime.now(timezone.utc)).days)
    return LoginResponse(
        token=token,
        expires_at=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        user_id=user.id,
        username=user.username,
        display_name=user.display_name or user.username,
        license_valid=lic_valid,
        license_until=lic_until,
        license_type=user.license_type,
        license_days_remaining=days_remaining,
        is_admin=user.is_admin,
        device_locked=bool(user.device_id),
    )


@app.post("/api/auth/validate", response_model=ValidateResponse)
def validate(token_data: dict = Depends(verify_token), db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.id == token_data["user_id"]).first()
    if not user:
        raise HTTPException(status_code=401, detail="Usuario nao encontrado")
    lic_valid, lic_until = check_license(user)
    days_remaining = None
    if user.license_type == "temporary" and user.license_start:
        expires = user.license_start + timedelta(days=user.license_days)
        days_remaining = max(0, (expires - datetime.now(timezone.utc)).days)
    return ValidateResponse(
        valid=True,
        user_id=user.id,
        username=user.username,
        display_name=user.display_name or user.username,
        license_valid=lic_valid,
        license_until=lic_until,
        license_type=user.license_type,
        license_days_remaining=days_remaining,
        is_admin=user.is_admin,
    )


# --- Security & Calculation ---

EXPECTED_SIGNATURE = "c33cfce2ec1104a39f3485124418b67e37d4d83b3f543738c1daf240c6e6771b"
EXPECTED_PACKAGE = "com.mobilador.sensitivity"

KNOWN_INTEGRITY_HASHES = {
    "classes.dex": "pending",
    "resources.arsc": "pending",
}

@app.post("/api/security/verify", response_model=SecurityVerifyResponse)
def security_verify(req: SecurityVerifyRequest, db: Session = Depends(get_db)):
    response = SecurityVerifyResponse(allowed=False, integrity_ok=False, license_ok=False, device_ok=False, message="")
    try:
        data = verify_token(req.token)
        user = db.query(UserDB).filter(UserDB.id == data["user_id"]).first()
        if not user:
            response.message = "Erro de seguranca. Esta versao nao e autorizada."
            return response
        response.license_ok = True
        if user.device_id and user.device_id != req.device_id:
            response.message = "Erro de seguranca. Esta versao nao e autorizada."
            db.add(SecurityEventLog(username=user.username, event_type="device_mismatch", device_id=req.device_id, details=f"Esperado: {user.device_id}"))
            db.commit()
            return response
        response.device_ok = True
        if req.package_name != EXPECTED_PACKAGE:
            response.message = "Erro de seguranca. Esta versao nao e autorizada."
            db.add(SecurityEventLog(username=user.username, event_type="package_mismatch", device_id=req.device_id, details=f"Pacote: {req.package_name}"))
            db.commit()
            return response
        if req.signature_hash != EXPECTED_SIGNATURE:
            response.message = "Erro de seguranca. Esta versao nao e autorizada."
            db.add(SecurityEventLog(username=user.username, event_type="signature_mismatch", device_id=req.device_id, details=f"Assinatura: {req.signature_hash[:40]}..."))
            db.commit()
            return response
        response.integrity_ok = True
        response.allowed = True
    except Exception:
        response.message = "Erro de seguranca. Esta versao nao e autorizada."
    return response


@app.post("/api/security/log-event")
def log_security_event(req: SecurityEvent, request: Request, db: Session = Depends(get_db)):
    try:
        data = verify_token(req.token)
        user = db.query(UserDB).filter(UserDB.id == data["user_id"]).first()
        username = user.username if user else "unknown"
    except Exception:
        username = "unknown"
    client_ip = request.client.host if request.client else ""
    db.add(SecurityEventLog(username=username, event_type=req.event_type, device_id=req.device_id, details=req.details[:1000], ip=client_ip))
    db.commit()
    return {"ok": True}


@app.get("/api/security/events")
def list_security_events(limit: int = 50, db: Session = Depends(get_db)):
    events = db.query(SecurityEventLog).order_by(SecurityEventLog.id.desc()).limit(limit).all()
    return [{"id": e.id, "username": e.username, "event_type": e.event_type, "device_id": e.device_id, "details": e.details, "ip": e.ip, "created_at": e.created_at.isoformat() if e.created_at else ""} for e in events]


@app.post("/api/calculate", response_model=CalculateResponse)
def calculate(req: CalculateRequest):
    import math

    def mdc(a, b):
        a, b = abs(round(a)), abs(round(b))
        while b != 0:
            a, b = b, a % b
        return a

    def analisar_resolucao(largura, altura):
        lado_maior = round(max(largura, altura))
        lado_menor = round(min(largura, altura))
        divisor = mdc(lado_maior, lado_menor)
        return {
            "largura": lado_maior,
            "altura": lado_menor,
            "proporcao_texto": f"{lado_maior // divisor}:{lado_menor // divisor}",
            "proporcao_decimal": lado_maior / lado_menor,
            "area": lado_maior * lado_menor
        }

    resolucao = analisar_resolucao(req.resolution_width, req.resolution_height)
    dpi_gg = max(req.mobilador_dpi, 1)
    dpi_mouse = max(req.mouse_dpi, 1)

    largura_base, altura_base = 1920.0, 1080.0
    area_base = largura_base * altura_base
    proporcao_base = largura_base / altura_base

    area_tela = resolucao["area"]
    proporcao_tela = resolucao["proporcao_decimal"]
    relacao_area = area_tela / area_base
    fator_area_tela = relacao_area ** (1.0 / 8.0)
    relacao_proporcao = proporcao_tela / proporcao_base
    fator_horizontal_tela = relacao_proporcao ** (1.0 / 24.0)
    fator_vertical_tela = (proporcao_base / proporcao_tela) ** (1.0 / 32.0)

    centro_geometrico_base = math.sqrt((largura_base / 2.0) * (altura_base / 2.0))
    ancora_dpi_gg = centro_geometrico_base * (11.0 / 18.0)
    dpi_gg_corrigido = ancora_dpi_gg * (dpi_gg / ancora_dpi_gg) ** (7.0 / 20.0)
    fator_mouse_base = dpi_gg_corrigido / dpi_mouse
    compensacao_dpi_alto = (dpi_mouse / 800.0) ** (3.0 / 10.0) if dpi_mouse > 800 else 1.0
    fator_mouse_final = fator_mouse_base * compensacao_dpi_alto
    zona_util = math.sqrt(3.0 / 4.0)

    base_sensibilidade = centro_geometrico_base * fator_mouse_final * zona_util
    compensacao_vertical = 1.0 + ((proporcao_tela - 1.0) / 32.0)

    normal_horizontal_bruto = base_sensibilidade * fator_area_tela * fator_horizontal_tela
    normal_vertical_bruto = base_sensibilidade * fator_area_tela * fator_vertical_tela * compensacao_vertical

    intensidade_dpi = math.log2(max(dpi_mouse, 100.0) / 800.0)
    intensidade_area = math.log2(max(relacao_area, 0.25))
    desvio_proporcao = proporcao_tela - proporcao_base

    fator_comutada_horizontal = max(0.82, min(0.88, 0.8513 + intensidade_dpi * 0.0025 + intensidade_area * 0.002 - desvio_proporcao * 0.008))
    fator_comutada_vertical = max(0.82, min(0.89, 0.849 + intensidade_dpi * 0.002 + intensidade_area * 0.0025 + desvio_proporcao * 0.006))

    comutada_horizontal_bruto = base_sensibilidade * fator_area_tela * fator_horizontal_tela * fator_comutada_horizontal
    comutada_vertical_bruto = base_sensibilidade * fator_area_tela * fator_vertical_tela * compensacao_vertical * fator_comutada_vertical

    def limitar(v):
        return max(1, min(1000, round(v)))

    normal_horizontal = limitar(normal_horizontal_bruto)
    normal_vertical = limitar(normal_vertical_bruto)

    comutada_horizontal = min(limitar(comutada_horizontal_bruto), max(1, normal_horizontal - 1))
    comutada_vertical = min(limitar(comutada_vertical_bruto), max(1, normal_vertical - 1))

    diagonal_px = math.sqrt(resolucao["largura"] ** 2 + resolucao["altura"] ** 2)
    ppi = diagonal_px / 6.5

    desc = f"Proporcao {resolucao['proporcao_texto']} | Area {int(area_tela)}px | GG {dpi_gg:.0f} | Mouse {dpi_mouse:.0f}"

    return CalculateResponse(
        sensitivity_x=normal_horizontal, sensitivity_y=normal_vertical,
        raw_x=normal_horizontal_bruto, raw_y=normal_vertical_bruto,
        switch_sensitivity_x=comutada_horizontal, switch_sensitivity_y=comutada_vertical,
        switch_raw_x=float(comutada_horizontal), switch_raw_y=float(comutada_vertical),
        description=desc, aspect_ratio=proporcao_tela, aspect_label=resolucao["proporcao_texto"], ppi=ppi,
        debug_dpi_factor=dpi_mouse / 1200.0, debug_gg_factor=dpi_gg / 300.0,
        debug_fps_factor=fator_area_tela, debug_pixel_factor=fator_horizontal_tela,
        debug_ppi_factor=fator_vertical_tela, debug_base_sensitivity=base_sensibilidade,
        balanced=False,
    )


# --- Admin API ---

class AdminCreateUser(BaseModel):
    username: str
    password: str
    display_name: str = ""
    license_type: str = "permanent"
    license_days: int = 0


@app.post("/api/painel/users")
def create_user(req: AdminCreateUser, db: Session = Depends(get_db)):
    existing = db.query(UserDB).filter(UserDB.username == req.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Usuario ja existe")
    now = datetime.now(timezone.utc)
    user = UserDB(
        username=req.username,
        password_hash=hash_password(req.password),
        display_name=req.display_name or req.username,
        license_type=req.license_type,
        license_days=req.license_days if req.license_type == "temporary" else 0,
        license_start=now if req.license_type == "temporary" else None,
        license_valid=True,
    )
    db.add(user)
    db.commit()
    return {"ok": True, "username": req.username}


@app.get("/api/painel/users")
def list_users(db: Session = Depends(get_db)):
    users = db.query(UserDB).all()
    result = []
    for u in users:
        lic_valid, lic_until = check_license(u)
        days_remaining = None
        if u.license_type == "temporary" and u.license_start:
            expires = u.license_start + timedelta(days=u.license_days)
            days_remaining = max(0, (expires - datetime.now(timezone.utc)).days)
        result.append({
            "id": u.id,
            "username": u.username,
            "display_name": u.display_name,
            "license_valid": lic_valid,
            "license_until": lic_until,
            "license_type": u.license_type,
            "license_days": u.license_days,
            "license_days_remaining": days_remaining,
            "license_start": u.license_start.isoformat() if u.license_start else "",
            "is_admin": u.is_admin,
            "device_id": u.device_id,
            "created_at": u.created_at.isoformat() if u.created_at else "",
        })
    return result


@app.post("/api/painel/users/{user_id}/unlink")
def unlink_device(user_id: int, db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    user.device_id = None
    db.commit()
    return {"ok": True, "username": user.username}


@app.post("/api/painel/users/{user_id}/renew")
def renew_license(user_id: int, days: int = 30, db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    now = datetime.now(timezone.utc)
    if user.license_type == "temporary" and user.license_start:
        lic_valid, _ = check_license(user)
        if lic_valid:
            user.license_days += days
        else:
            user.license_start = now
            user.license_days = days
    else:
        user.license_type = "temporary"
        user.license_start = now
        user.license_days = days
    db.commit()
    return {"ok": True, "username": user.username, "license_days": user.license_days,
            "expires": (user.license_start + timedelta(days=user.license_days)).isoformat() if user.license_start else ""}


@app.post("/api/painel/users/{user_id}/make-permanent")
def make_permanent(user_id: int, db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    user.license_type = "permanent"
    user.license_days = 0
    user.license_start = None
    db.commit()
    return {"ok": True, "username": user.username}


@app.delete("/api/painel/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    db.delete(user)
    db.commit()
    return {"ok": True}


# --- Web Admin ---

@app.get("/", response_class=HTMLResponse)
def admin_page(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})


@app.post("/painel/login")
def admin_login(request: Request, username: str = Form(...), password: str = Form(...),
                db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.username == username).first()
    if not user or not check_password(password, user.password_hash) or not user.is_admin:
        return templates.TemplateResponse("admin.html", {"request": request, "error": "Credenciais invalidas"})
    token = create_token(user)
    response = RedirectResponse(url="/painel", status_code=302)
    response.set_cookie(key="token", value=token, httponly=True, max_age=86400 * 30)
    return response


@app.get("/painel", response_class=HTMLResponse)
def admin_panel(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("token")
    if not token:
        return templates.TemplateResponse("admin.html", {"request": request, "logged": False})
    try:
        data = verify_token(token)
        user = db.query(UserDB).filter(UserDB.id == data["user_id"]).first()
        if not user or not user.is_admin:
            return templates.TemplateResponse("admin.html", {"request": request, "logged": False})
        users = db.query(UserDB).all()
        return templates.TemplateResponse("admin.html", {"request": request, "logged": True,
                                                         "admin_user": user, "users": users,
                                                         "format_date": format_date})
    except Exception:
        return templates.TemplateResponse("admin.html", {"request": request, "logged": False})


@app.post("/painel/create-user")
def admin_create_user(request: Request, username: str = Form(...), password: str = Form(...),
                      display_name: str = Form(""), license_type: str = Form("permanent"),
                      license_days: int = Form(0), db: Session = Depends(get_db)):
    token = request.cookies.get("token")
    if not token:
        return RedirectResponse(url="/", status_code=302)
    try:
        data = verify_token(token)
        admin = db.query(UserDB).filter(UserDB.id == data["user_id"]).first()
        if not admin or not admin.is_admin:
            return RedirectResponse(url="/", status_code=302)
        existing = db.query(UserDB).filter(UserDB.username == username).first()
        if existing:
            return templates.TemplateResponse("admin.html", {"request": request, "logged": True,
                                                             "admin_user": admin,
                                                             "users": db.query(UserDB).all(),
                                                             "error": "Usuario ja existe"})
        now = datetime.now(timezone.utc)
        user = UserDB(
            username=username,
            password_hash=hash_password(password),
            display_name=display_name or username,
            license_type=license_type,
            license_days=license_days if license_type == "temporary" else 0,
            license_start=now if license_type == "temporary" else None,
            license_valid=True,
        )
        db.add(user)
        db.commit()
        created = {
            "username": username,
            "password": password,
            "display_name": display_name or username,
            "license_type": "Permanente" if license_type == "permanent" else "Temporaria",
            "license_days": license_days if license_type == "temporary" else None,
        }
        return templates.TemplateResponse("admin.html", {"request": request, "logged": True,
                                                         "admin_user": admin,
                                                         "users": db.query(UserDB).all(),
                                                         "created": created})
    except Exception:
        return RedirectResponse(url="/", status_code=302)


@app.post("/painel/unlink/{user_id}")
def admin_unlink(request: Request, user_id: int, db: Session = Depends(get_db)):
    token = request.cookies.get("token")
    if not token:
        return RedirectResponse(url="/", status_code=302)
    try:
        data = verify_token(token)
        admin = db.query(UserDB).filter(UserDB.id == data["user_id"]).first()
        if not admin or not admin.is_admin:
            return RedirectResponse(url="/", status_code=302)
        user = db.query(UserDB).filter(UserDB.id == user_id).first()
        if user:
            user.device_id = None
            db.commit()
        return RedirectResponse(url="/painel", status_code=302)
    except Exception:
        return RedirectResponse(url="/", status_code=302)


@app.post("/painel/renew/{user_id}")
def admin_renew(request: Request, user_id: int, days: int = Form(30), db: Session = Depends(get_db)):
    token = request.cookies.get("token")
    if not token:
        return RedirectResponse(url="/", status_code=302)
    try:
        data = verify_token(token)
        admin = db.query(UserDB).filter(UserDB.id == data["user_id"]).first()
        if not admin or not admin.is_admin:
            return RedirectResponse(url="/", status_code=302)
        user = db.query(UserDB).filter(UserDB.id == user_id).first()
        if user:
            now = datetime.now(timezone.utc)
            if user.license_type == "temporary" and user.license_start:
                lic_valid, _ = check_license(user)
                if lic_valid:
                    user.license_days += days
                else:
                    user.license_start = now
                    user.license_days = days
            else:
                user.license_type = "temporary"
                user.license_start = now
                user.license_days = days
            db.commit()
        return RedirectResponse(url="/painel", status_code=302)
    except Exception:
        return RedirectResponse(url="/", status_code=302)


@app.post("/painel/make-permanent/{user_id}")
def admin_make_permanent(request: Request, user_id: int, db: Session = Depends(get_db)):
    token = request.cookies.get("token")
    if not token:
        return RedirectResponse(url="/", status_code=302)
    try:
        data = verify_token(token)
        admin = db.query(UserDB).filter(UserDB.id == data["user_id"]).first()
        if not admin or not admin.is_admin:
            return RedirectResponse(url="/", status_code=302)
        user = db.query(UserDB).filter(UserDB.id == user_id).first()
        if user:
            user.license_type = "permanent"
            user.license_days = 0
            user.license_start = None
            db.commit()
        return RedirectResponse(url="/painel", status_code=302)
    except Exception:
        return RedirectResponse(url="/", status_code=302)


@app.post("/painel/delete/{user_id}")
def admin_delete(request: Request, user_id: int, db: Session = Depends(get_db)):
    token = request.cookies.get("token")
    if not token:
        return RedirectResponse(url="/", status_code=302)
    try:
        data = verify_token(token)
        admin_user = db.query(UserDB).filter(UserDB.id == data["user_id"]).first()
        if not admin_user or not admin_user.is_admin:
            return RedirectResponse(url="/", status_code=302)
        user = db.query(UserDB).filter(UserDB.id == user_id).first()
        if user and not user.is_admin:
            db.delete(user)
            db.commit()
        return RedirectResponse(url="/painel", status_code=302)
    except Exception:
        return RedirectResponse(url="/", status_code=302)


@app.get("/painel/logout")
def admin_logout():
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("token")
    return response


if __name__ == "__main__":
    import uvicorn
    import socket
    port = int(os.environ.get("PORT", sys.argv[1] if len(sys.argv) > 1 else 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"\n=== MOBILADOR SERVER ===")
    print(f"Servidor rodando na porta {port}")
    url_base = os.environ.get("RENDER_EXTERNAL_URL", f"http://localhost:{port}")
    print(f"\nAcesse o painel admin no navegador:")
    print(f"  URL: {url_base}/painel")
    if not os.environ.get("RENDER_EXTERNAL_URL"):
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            print(f"  Rede:  http://{ip}:{port}")
    print(f"\nNo app, configure a URL como {url_base}/")
    print(f"========================\n")
    uvicorn.run(app, host=host, port=port)
