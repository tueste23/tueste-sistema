from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
import os

from .database import engine, Base, get_db
from . import models
from .auth import hash_password, verify_password, create_access_token
from .routers import ingredientes, recetas, compras, ventas, dashboard, maestros

# Crear tablas
Base.metadata.create_all(bind=engine)

app = FastAPI(title="TUESTE Sistema", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar routers
app.include_router(ingredientes.router)
app.include_router(recetas.router)
app.include_router(compras.router)
app.include_router(ventas.router)
app.include_router(dashboard.router)
app.include_router(maestros.router)

# ─── Auth ─────────────────────────────────────────────────────────────────────

class LoginData(BaseModel):
    email: str
    password: str

class RegistroData(BaseModel):
    nombre: str
    email: str
    password: str
    rol: str = "operario"

@app.post("/api/auth/login")
def login(data: LoginData, db: Session = Depends(get_db)):
    user = db.query(models.Usuario).filter(models.Usuario.email == data.email).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Email o contraseña incorrectos")
    if not user.activo:
        raise HTTPException(403, "Usuario inactivo")
    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer", "nombre": user.nombre, "rol": user.rol}

@app.post("/api/auth/registro")
def registro(data: RegistroData, db: Session = Depends(get_db)):
    existente = db.query(models.Usuario).filter(models.Usuario.email == data.email).first()
    if existente:
        raise HTTPException(400, "El email ya está registrado")
    user = models.Usuario(
        nombre=data.nombre,
        email=data.email,
        password_hash=hash_password(data.password),
        rol=data.rol,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer", "nombre": user.nombre, "rol": user.rol}

@app.get("/api/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

# ─── Seed de datos iniciales ──────────────────────────────────────────────────

@app.on_event("startup")
def seed():
    db = next(get_db())
    try:
        # Crear usuario admin si no existe
        admin = db.query(models.Usuario).filter(models.Usuario.email == "admin@tueste.com").first()
        if not admin:
            admin = models.Usuario(
                nombre="Administrador",
                email="admin@tueste.com",
                password_hash=hash_password("tueste2024"),
                rol="dueno",
            )
            db.add(admin)
            db.flush()

        # Crear locales base
        if db.query(models.Local).count() == 0:
            for nombre, tipo in [("Cafetería", "cafeteria"), ("Restaurante", "restaurante"), ("Centro de Producción", "produccion")]:
                db.add(models.Local(nombre=nombre, tipo=tipo))

        # Crear categorías base
        if db.query(models.Categoria).count() == 0:
            cats = [
                ("Bebidas", "producto", 0.70), ("Comidas", "producto", 0.65),
                ("Postres", "producto", 0.68), ("Snacks", "producto", 0.60),
                ("Lácteos", "ingrediente", 0.0), ("Carnes", "ingrediente", 0.0),
                ("Verduras", "ingrediente", 0.0), ("Panificados", "ingrediente", 0.0),
                ("Bebidas (insumo)", "ingrediente", 0.0), ("Secos", "ingrediente", 0.0),
            ]
            for nombre, tipo, margen in cats:
                db.add(models.Categoria(nombre=nombre, tipo=tipo, margen_objetivo=margen))

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Seed error: {e}")
    finally:
        db.close()

# ─── Servir frontend ──────────────────────────────────────────────────────────

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/", response_class=HTMLResponse)
@app.get("/{full_path:path}", response_class=HTMLResponse)
def serve_frontend(full_path: str = ""):
    index = os.path.join(static_dir, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return HTMLResponse("<h1>Frontend no encontrado</h1>", status_code=404)
