"""Endpoints para gastos variables del CP."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
from datetime import datetime
from ..database import get_db
from ..auth import get_current_user
from .. import models

router = APIRouter(tags=["gastos_variables"])

# ─── Schema ───────────────────────────────────────────────────────────────────

class GastoVariableIn(BaseModel):
    concepto: str
    monto: float
    categoria: Optional[str] = None  # packaging, limpieza, gas, mantenimiento, etc.
    proveedor_id: Optional[int] = None
    mes: Optional[int] = None
    anio: Optional[int] = None

# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/api/gastos-variables")
def listar_gastos_variables(mes: Optional[int] = None, anio: Optional[int] = None,
                            categoria: Optional[str] = None,
                            db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    q = db.query(models.GastoVariable).order_by(models.GastoVariable.fecha.desc())
    if mes:
        q = q.filter(models.GastoVariable.mes == mes)
    if anio:
        q = q.filter(models.GastoVariable.anio == anio)
    if categoria:
        q = q.filter(models.GastoVariable.categoria == categoria)

    gastos = q.all()
    total = sum(g.monto for g in gastos)

    return {
        "total": total,
        "gastos": [
            {
                "id": g.id,
                "concepto": g.concepto,
                "monto": g.monto,
                "categoria": g.categoria,
                "proveedor": g.proveedor.nombre if g.proveedor else None,
                "fecha": g.fecha,
                "mes": g.mes,
                "anio": g.anio,
            }
            for g in gastos
        ],
    }

@router.post("/api/gastos-variables")
def crear_gasto_variable(data: GastoVariableIn,
                         db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    ahora = datetime.utcnow()
    g = models.GastoVariable(
        concepto=data.concepto,
        monto=data.monto,
        categoria=data.categoria,
        proveedor_id=data.proveedor_id,
        mes=data.mes or ahora.month,
        anio=data.anio or ahora.year,
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return {"id": g.id}

@router.put("/api/gastos-variables/{id}")
def actualizar_gasto_variable(id: int, data: GastoVariableIn,
                              db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    g = db.query(models.GastoVariable).filter(models.GastoVariable.id == id).first()
    if not g:
        raise HTTPException(404, "No encontrado")
    for k, v in data.dict(exclude_unset=True).items():
        setattr(g, k, v)
    db.commit()
    return {"ok": True}

@router.delete("/api/gastos-variables/{id}")
def eliminar_gasto_variable(id: int,
                            db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    g = db.query(models.GastoVariable).filter(models.GastoVariable.id == id).first()
    if not g:
        raise HTTPException(404, "No encontrado")
    db.delete(g)
    db.commit()
    return {"ok": True}

# ─── Resumen por categoría ────────────────────────────────────────────────────

@router.get("/api/gastos-variables/resumen/categorias")
def resumen_categorias(mes: Optional[int] = None, anio: Optional[int] = None,
                       db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    ahora = datetime.utcnow()
    mes = mes or ahora.month
    anio = anio or ahora.year

    q = db.query(models.GastoVariable).filter(
        models.GastoVariable.mes == mes,
        models.GastoVariable.anio == anio,
    )
    gastos = q.all()

    categorias = {}
    for g in gastos:
        cat = g.categoria or "Sin categoría"
        categorias[cat] = categorias.get(cat, 0) + g.monto

    return {
        "mes": mes,
        "anio": anio,
        "total": sum(categorias.values()),
        "por_categoria": [
            {"categoria": k, "total": v}
            for k, v in sorted(categorias.items(), key=lambda x: x[1], reverse=True)
        ],
    }
