from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from ..database import get_db
from ..auth import get_current_user
from .. import models
from .ingredientes import recalcular_recetas_con_ingrediente

router = APIRouter(prefix="/api/compras", tags=["compras"])

class ItemOCIn(BaseModel):
    ingrediente_id: int
    cantidad: float
    precio_unitario: float

class OrdenCompraCreate(BaseModel):
    proveedor_id: int
    notas: Optional[str] = None
    items: List[ItemOCIn]

@router.get("")
def listar(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    ocs = db.query(models.OrdenCompra).order_by(models.OrdenCompra.fecha_emision.desc()).limit(100).all()
    return [
        {
            "id": oc.id,
            "proveedor": oc.proveedor.nombre,
            "estado": oc.estado,
            "fecha_emision": oc.fecha_emision,
            "fecha_entrega": oc.fecha_entrega,
            "total": oc.total,
            "items_count": len(oc.items),
        }
        for oc in ocs
    ]

@router.get("/{id}")
def obtener(id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    oc = db.query(models.OrdenCompra).filter(models.OrdenCompra.id == id).first()
    if not oc:
        raise HTTPException(404, "Orden no encontrada")
    return {
        "id": oc.id,
        "proveedor_id": oc.proveedor_id,
        "proveedor": oc.proveedor.nombre,
        "estado": oc.estado,
        "fecha_emision": oc.fecha_emision,
        "total": oc.total,
        "notas": oc.notas,
        "items": [
            {
                "id": it.id,
                "ingrediente_id": it.ingrediente_id,
                "ingrediente": it.ingrediente.nombre,
                "cantidad": it.cantidad,
                "precio_unitario": it.precio_unitario,
                "subtotal": it.subtotal,
            }
            for it in oc.items
        ],
    }

@router.post("")
def crear(data: OrdenCompraCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    total = sum(it.cantidad * it.precio_unitario for it in data.items)
    oc = models.OrdenCompra(
        proveedor_id=data.proveedor_id,
        estado="borrador",
        total=total,
        notas=data.notas,
        usuario_id=current_user.id,
    )
    db.add(oc)
    db.flush()
    for it in data.items:
        item = models.ItemOrdenCompra(
            orden_id=oc.id,
            ingrediente_id=it.ingrediente_id,
            cantidad=it.cantidad,
            precio_unitario=it.precio_unitario,
            subtotal=it.cantidad * it.precio_unitario,
        )
        db.add(item)
    db.commit()
    db.refresh(oc)
    return {"id": oc.id, "total": oc.total}

@router.post("/{id}/recibir")
def recibir(id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """
    Al recibir una OC:
    1. Actualiza el stock de cada ingrediente (+cantidad)
    2. Actualiza el costo_actual del ingrediente con el precio de la OC
    3. Registra en historial_costos si el precio cambió
    4. Recalcula automáticamente todas las recetas afectadas
    5. Genera movimientos de stock tipo 'compra'
    """
    oc = db.query(models.OrdenCompra).filter(models.OrdenCompra.id == id).first()
    if not oc:
        raise HTTPException(404, "Orden no encontrada")
    if oc.estado == "recibida":
        raise HTTPException(400, "Esta orden ya fue recibida")

    ingredientes_afectados = set()
    for item in oc.items:
        ing = db.query(models.Ingrediente).filter(models.Ingrediente.id == item.ingrediente_id).first()
        if not ing:
            continue

        # Actualizar stock
        stock_anterior = ing.stock_actual
        ing.stock_actual = round(ing.stock_actual + item.cantidad, 4)

        # Registrar movimiento de stock
        mov = models.MovimientoStock(
            ingrediente_id=ing.id,
            tipo="compra",
            cantidad=item.cantidad,
            stock_anterior=stock_anterior,
            stock_nuevo=ing.stock_actual,
            motivo=f"Compra OC #{oc.id} - {oc.proveedor.nombre}",
            referencia_id=oc.id,
            usuario_id=current_user.id,
        )
        db.add(mov)

        # Si el precio cambió, actualizar costo y registrar historial
        if abs(item.precio_unitario - ing.costo_actual) > 0.0001:
            historial = models.HistorialCosto(
                ingrediente_id=ing.id,
                costo_anterior=ing.costo_actual,
                costo_nuevo=item.precio_unitario,
                motivo=f"Actualización por OC #{oc.id} - {oc.proveedor.nombre}",
                usuario_id=current_user.id,
            )
            db.add(historial)
            ing.costo_actual = item.precio_unitario
            ingredientes_afectados.add(ing.id)

    oc.estado = "recibida"
    oc.fecha_entrega = datetime.utcnow()
    db.commit()

    # Recalcular recetas para todos los ingredientes con costo actualizado
    for ing_id in ingredientes_afectados:
        recalcular_recetas_con_ingrediente(db, ing_id)

    return {
        "ok": True,
        "ingredientes_actualizados": len(ingredientes_afectados),
        "mensaje": f"OC recibida. Se actualizaron costos de {len(ingredientes_afectados)} ingrediente(s) y se recalcularon las recetas afectadas."
    }

@router.put("/{id}/estado")
def cambiar_estado(id: int, estado: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    oc = db.query(models.OrdenCompra).filter(models.OrdenCompra.id == id).first()
    if not oc:
        raise HTTPException(404, "No encontrada")
    oc.estado = estado
    db.commit()
    return {"ok": True}
