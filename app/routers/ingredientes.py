from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from ..database import get_db
from ..auth import get_current_user
from .. import models

router = APIRouter(prefix="/api/ingredientes", tags=["ingredientes"])

class IngredienteCreate(BaseModel):
    nombre: str
    unidad: str
    costo_actual: float = 0.0
    stock_actual: float = 0.0
    stock_minimo: float = 0.0
    categoria_id: Optional[int] = None
    proveedor_id: Optional[int] = None

class IngredienteUpdate(BaseModel):
    nombre: Optional[str] = None
    unidad: Optional[str] = None
    costo_actual: Optional[float] = None
    stock_actual: Optional[float] = None
    stock_minimo: Optional[float] = None
    categoria_id: Optional[int] = None
    proveedor_id: Optional[int] = None

def recalcular_recetas_con_ingrediente(db: Session, ingrediente_id: int):
    """Recalcula el costo de todas las recetas que usan este ingrediente."""
    items = db.query(models.ItemReceta).filter(models.ItemReceta.ingrediente_id == ingrediente_id).all()
    recetas_ids = set(item.receta_id for item in items)
    for receta_id in recetas_ids:
        receta = db.query(models.Receta).filter(models.Receta.id == receta_id).first()
        if receta:
            costo = sum(
                item.cantidad * item.ingrediente.costo_actual
                for item in receta.items
            )
            receta.costo_calculado = round(costo / receta.rendimiento, 4) if receta.rendimiento > 0 else costo
    db.commit()

@router.get("")
def listar(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    items = db.query(models.Ingrediente).filter(models.Ingrediente.activo == True).all()
    result = []
    for i in items:
        result.append({
            "id": i.id,
            "nombre": i.nombre,
            "unidad": i.unidad,
            "costo_actual": i.costo_actual,
            "stock_actual": i.stock_actual,
            "stock_minimo": i.stock_minimo,
            "stock_critico": i.stock_actual <= i.stock_minimo,
            "categoria_id": i.categoria_id,
            "categoria": i.categoria.nombre if i.categoria else None,
            "proveedor_id": i.proveedor_id,
            "proveedor": i.proveedor_principal.nombre if i.proveedor_principal else None,
        })
    return result

@router.get("/stock-critico")
def stock_critico(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    items = db.query(models.Ingrediente).filter(
        models.Ingrediente.activo == True,
        models.Ingrediente.stock_actual <= models.Ingrediente.stock_minimo
    ).all()
    return [{"id": i.id, "nombre": i.nombre, "stock_actual": i.stock_actual, "stock_minimo": i.stock_minimo, "unidad": i.unidad} for i in items]

@router.get("/{id}")
def obtener(id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    i = db.query(models.Ingrediente).filter(models.Ingrediente.id == id).first()
    if not i:
        raise HTTPException(404, "Ingrediente no encontrado")
    historial = [{"fecha": h.fecha, "costo_anterior": h.costo_anterior, "costo_nuevo": h.costo_nuevo, "motivo": h.motivo}
                 for h in i.historial_costos[:10]]
    return {
        "id": i.id, "nombre": i.nombre, "unidad": i.unidad,
        "costo_actual": i.costo_actual, "stock_actual": i.stock_actual,
        "stock_minimo": i.stock_minimo,
        "categoria_id": i.categoria_id, "proveedor_id": i.proveedor_id,
        "historial_costos": historial,
    }

@router.post("")
def crear(data: IngredienteCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    ingrediente = models.Ingrediente(**data.dict())
    db.add(ingrediente)
    db.commit()
    db.refresh(ingrediente)
    return {"id": ingrediente.id, "nombre": ingrediente.nombre}

@router.put("/{id}")
def actualizar(id: int, data: IngredienteUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    ingrediente = db.query(models.Ingrediente).filter(models.Ingrediente.id == id).first()
    if not ingrediente:
        raise HTTPException(404, "No encontrado")
    update_data = data.dict(exclude_unset=True)

    # Si cambió el costo, registrar en historial y recalcular recetas
    if "costo_actual" in update_data and update_data["costo_actual"] != ingrediente.costo_actual:
        historial = models.HistorialCosto(
            ingrediente_id=id,
            costo_anterior=ingrediente.costo_actual,
            costo_nuevo=update_data["costo_actual"],
            motivo="Actualización manual",
            usuario_id=current_user.id,
        )
        db.add(historial)
        for key, val in update_data.items():
            setattr(ingrediente, key, val)
        db.commit()
        recalcular_recetas_con_ingrediente(db, id)
    else:
        for key, val in update_data.items():
            setattr(ingrediente, key, val)
        db.commit()
    return {"ok": True}

@router.delete("/{id}")
def eliminar(id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    ingrediente = db.query(models.Ingrediente).filter(models.Ingrediente.id == id).first()
    if not ingrediente:
        raise HTTPException(404, "No encontrado")
    ingrediente.activo = False
    db.commit()
    return {"ok": True}
