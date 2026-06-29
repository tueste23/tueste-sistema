from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from ..database import get_db
from ..auth import get_current_user
from .. import models

router = APIRouter(prefix="/api/recetas", tags=["recetas"])

class ItemRecetaIn(BaseModel):
    ingrediente_id: int
    cantidad: float
    unidad: Optional[str] = None

class RecetaCreate(BaseModel):
    producto_id: int
    rendimiento: float = 1.0
    descripcion: Optional[str] = None
    items: List[ItemRecetaIn]

class RecetaUpdate(BaseModel):
    rendimiento: Optional[float] = None
    descripcion: Optional[str] = None
    items: Optional[List[ItemRecetaIn]] = None

def calcular_costo_receta(receta: models.Receta) -> float:
    costo = sum(item.cantidad * item.ingrediente.costo_actual for item in receta.items)
    return round(costo / receta.rendimiento, 4) if receta.rendimiento > 0 else round(costo, 4)

def receta_to_dict(r: models.Receta):
    producto = r.producto
    precio_venta = producto.precio_venta if producto else 0
    costo = r.costo_calculado
    margen = round((precio_venta - costo) / precio_venta * 100, 1) if precio_venta > 0 else 0
    return {
        "id": r.id,
        "producto_id": r.producto_id,
        "producto": producto.nombre if producto else None,
        "precio_venta": precio_venta,
        "rendimiento": r.rendimiento,
        "descripcion": r.descripcion,
        "costo_calculado": costo,
        "margen_pct": margen,
        "items": [
            {
                "id": it.id,
                "ingrediente_id": it.ingrediente_id,
                "ingrediente": it.ingrediente.nombre,
                "unidad": it.unidad or it.ingrediente.unidad,
                "cantidad": it.cantidad,
                "costo_unitario": it.ingrediente.costo_actual,
                "subtotal": round(it.cantidad * it.ingrediente.costo_actual, 4),
            }
            for it in r.items
        ],
    }

@router.get("")
def listar(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    recetas = db.query(models.Receta).all()
    return [receta_to_dict(r) for r in recetas]

@router.get("/{id}")
def obtener(id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    r = db.query(models.Receta).filter(models.Receta.id == id).first()
    if not r:
        raise HTTPException(404, "Receta no encontrada")
    return receta_to_dict(r)

@router.post("")
def crear(data: RecetaCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    # Verificar que el producto existe y no tiene receta
    prod = db.query(models.Producto).filter(models.Producto.id == data.producto_id).first()
    if not prod:
        raise HTTPException(404, "Producto no encontrado")
    existente = db.query(models.Receta).filter(models.Receta.producto_id == data.producto_id).first()
    if existente:
        raise HTTPException(400, "El producto ya tiene una receta. Usá PUT para editar.")

    receta = models.Receta(
        producto_id=data.producto_id,
        rendimiento=data.rendimiento,
        descripcion=data.descripcion,
    )
    db.add(receta)
    db.flush()

    for item_data in data.items:
        ing = db.query(models.Ingrediente).filter(models.Ingrediente.id == item_data.ingrediente_id).first()
        if not ing:
            raise HTTPException(404, f"Ingrediente {item_data.ingrediente_id} no encontrado")
        item = models.ItemReceta(
            receta_id=receta.id,
            ingrediente_id=item_data.ingrediente_id,
            cantidad=item_data.cantidad,
            unidad=item_data.unidad or ing.unidad,
        )
        db.add(item)

    db.flush()
    db.refresh(receta)
    receta.costo_calculado = calcular_costo_receta(receta)
    db.commit()
    return receta_to_dict(receta)

@router.put("/{id}")
def actualizar(id: int, data: RecetaUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    receta = db.query(models.Receta).filter(models.Receta.id == id).first()
    if not receta:
        raise HTTPException(404, "Receta no encontrada")

    if data.rendimiento is not None:
        receta.rendimiento = data.rendimiento
    if data.descripcion is not None:
        receta.descripcion = data.descripcion

    if data.items is not None:
        # Reemplazar todos los items
        for item in receta.items:
            db.delete(item)
        db.flush()
        for item_data in data.items:
            ing = db.query(models.Ingrediente).filter(models.Ingrediente.id == item_data.ingrediente_id).first()
            if not ing:
                raise HTTPException(404, f"Ingrediente {item_data.ingrediente_id} no encontrado")
            item = models.ItemReceta(
                receta_id=receta.id,
                ingrediente_id=item_data.ingrediente_id,
                cantidad=item_data.cantidad,
                unidad=item_data.unidad or ing.unidad,
            )
            db.add(item)
        db.flush()

    db.refresh(receta)
    receta.costo_calculado = calcular_costo_receta(receta)
    db.commit()
    return receta_to_dict(receta)

@router.delete("/{id}")
def eliminar(id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    receta = db.query(models.Receta).filter(models.Receta.id == id).first()
    if not receta:
        raise HTTPException(404, "No encontrada")
    db.delete(receta)
    db.commit()
    return {"ok": True}
