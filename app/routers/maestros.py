"""Endpoints para entidades maestras: locales, categorías, proveedores, productos, gastos."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
from ..database import get_db
from ..auth import get_current_user
from .. import models

router = APIRouter(tags=["maestros"])

# ─── Locales ──────────────────────────────────────────────────────────────────

@router.get("/api/locales")
def listar_locales(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return [{"id": l.id, "nombre": l.nombre, "tipo": l.tipo} for l in db.query(models.Local).filter(models.Local.activo == True).all()]

@router.post("/api/locales")
def crear_local(nombre: str, tipo: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    l = models.Local(nombre=nombre, tipo=tipo)
    db.add(l); db.commit(); db.refresh(l)
    return {"id": l.id}

# ─── Categorías ───────────────────────────────────────────────────────────────

@router.get("/api/categorias")
def listar_categorias(tipo: Optional[str] = None, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    q = db.query(models.Categoria)
    if tipo:
        q = q.filter(models.Categoria.tipo == tipo)
    return [{"id": c.id, "nombre": c.nombre, "tipo": c.tipo, "margen_objetivo": c.margen_objetivo} for c in q.all()]

class CategoriaIn(BaseModel):
    nombre: str
    tipo: str
    margen_objetivo: float = 0.65

@router.post("/api/categorias")
def crear_categoria(data: CategoriaIn, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    c = models.Categoria(**data.dict())
    db.add(c); db.commit(); db.refresh(c)
    return {"id": c.id}

# ─── Proveedores ──────────────────────────────────────────────────────────────

@router.get("/api/proveedores")
def listar_proveedores(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return [
        {"id": p.id, "nombre": p.nombre, "contacto": p.contacto, "telefono": p.telefono,
         "email": p.email, "condicion_pago": p.condicion_pago}
        for p in db.query(models.Proveedor).filter(models.Proveedor.activo == True).all()
    ]

class ProveedorIn(BaseModel):
    nombre: str
    contacto: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    condicion_pago: Optional[str] = None

@router.post("/api/proveedores")
def crear_proveedor(data: ProveedorIn, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    p = models.Proveedor(**data.dict())
    db.add(p); db.commit(); db.refresh(p)
    return {"id": p.id}

@router.put("/api/proveedores/{id}")
def actualizar_proveedor(id: int, data: ProveedorIn, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    p = db.query(models.Proveedor).filter(models.Proveedor.id == id).first()
    if not p: raise HTTPException(404, "No encontrado")
    for k, v in data.dict(exclude_unset=True).items():
        setattr(p, k, v)
    db.commit()
    return {"ok": True}

@router.delete("/api/proveedores/{id}")
def eliminar_proveedor(id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    p = db.query(models.Proveedor).filter(models.Proveedor.id == id).first()
    if not p: raise HTTPException(404, "No encontrado")
    p.activo = False; db.commit()
    return {"ok": True}

# ─── Productos ────────────────────────────────────────────────────────────────

@router.get("/api/productos")
def listar_productos(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    prods = db.query(models.Producto).filter(models.Producto.activo == True).all()
    return [
        {
            "id": p.id, "nombre": p.nombre, "descripcion": p.descripcion,
            "precio_venta": p.precio_venta,
            "categoria": p.categoria.nombre if p.categoria else None,
            "categoria_id": p.categoria_id,
            "local_id": p.local_id,
            "tiene_receta": p.receta is not None,
            "costo": p.receta.costo_calculado if p.receta else None,
            "margen_pct": round((p.precio_venta - p.receta.costo_calculado) / p.precio_venta * 100, 1)
                          if p.receta and p.precio_venta > 0 else None,
        }
        for p in prods
    ]

class ProductoIn(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    precio_venta: float
    categoria_id: Optional[int] = None
    local_id: Optional[int] = None

@router.post("/api/productos")
def crear_producto(data: ProductoIn, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    p = models.Producto(**data.dict())
    db.add(p); db.commit(); db.refresh(p)
    return {"id": p.id}

@router.put("/api/productos/{id}")
def actualizar_producto(id: int, data: ProductoIn, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    p = db.query(models.Producto).filter(models.Producto.id == id).first()
    if not p: raise HTTPException(404, "No encontrado")
    for k, v in data.dict(exclude_unset=True).items():
        setattr(p, k, v)
    db.commit()
    return {"ok": True}

@router.delete("/api/productos/{id}")
def eliminar_producto(id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    p = db.query(models.Producto).filter(models.Producto.id == id).first()
    if not p: raise HTTPException(404, "No encontrado")
    p.activo = False; db.commit()
    return {"ok": True}

# ─── Gastos fijos ─────────────────────────────────────────────────────────────

@router.get("/api/gastos")
def listar_gastos(mes: Optional[int] = None, anio: Optional[int] = None,
                  db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    from datetime import datetime
    ahora = datetime.utcnow()
    q = db.query(models.GastoFijo)
    if mes: q = q.filter(models.GastoFijo.mes == mes)
    if anio: q = q.filter(models.GastoFijo.anio == anio)
    return [{"id": g.id, "concepto": g.concepto, "monto": g.monto, "mes": g.mes, "anio": g.anio, "categoria": g.categoria} for g in q.all()]

class GastoIn(BaseModel):
    concepto: str
    monto: float
    mes: int
    anio: int
    categoria: Optional[str] = None
    local_id: Optional[int] = None

@router.post("/api/gastos")
def crear_gasto(data: GastoIn, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    g = models.GastoFijo(**data.dict())
    db.add(g); db.commit(); db.refresh(g)
    return {"id": g.id}

@router.delete("/api/gastos/{id}")
def eliminar_gasto(id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    g = db.query(models.GastoFijo).filter(models.GastoFijo.id == id).first()
    if not g: raise HTTPException(404, "No encontrado")
    db.delete(g); db.commit()
    return {"ok": True}

# ─── Stock (movimientos) ──────────────────────────────────────────────────────

@router.get("/api/stock/movimientos")
def movimientos(ingrediente_id: Optional[int] = None, limit: int = 100,
                db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    q = db.query(models.MovimientoStock).order_by(models.MovimientoStock.fecha.desc())
    if ingrediente_id:
        q = q.filter(models.MovimientoStock.ingrediente_id == ingrediente_id)
    movs = q.limit(limit).all()
    return [
        {"id": m.id, "ingrediente": m.ingrediente.nombre, "tipo": m.tipo,
         "cantidad": m.cantidad, "stock_anterior": m.stock_anterior,
         "stock_nuevo": m.stock_nuevo, "motivo": m.motivo, "fecha": m.fecha}
        for m in movs
    ]

class AjusteStock(BaseModel):
    ingrediente_id: int
    cantidad_nueva: float
    motivo: str

@router.post("/api/stock/ajuste")
def ajustar_stock(data: AjusteStock, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    ing = db.query(models.Ingrediente).filter(models.Ingrediente.id == data.ingrediente_id).first()
    if not ing: raise HTTPException(404, "Ingrediente no encontrado")
    anterior = ing.stock_actual
    ing.stock_actual = data.cantidad_nueva
    mov = models.MovimientoStock(
        ingrediente_id=ing.id, tipo="ajuste",
        cantidad=data.cantidad_nueva - anterior,
        stock_anterior=anterior, stock_nuevo=data.cantidad_nueva,
        motivo=data.motivo, usuario_id=current_user.id,
    )
    db.add(mov); db.commit()
    return {"ok": True}
