"""Endpoints para pedidos de clientes."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from ..database import get_db
from ..auth import get_current_user
from .. import models

router = APIRouter(tags=["pedidos"])

# ─── Schemas ──────────────────────────────────────────────────────────────────

class ItemPedidoIn(BaseModel):
    producto_id: int
    cantidad: float
    precio_unitario: float

class PedidoIn(BaseModel):
    cliente_id: int
    fecha_entrega: Optional[str] = None
    notas: Optional[str] = None
    items: List[ItemPedidoIn]

class ActualizarEstadoIn(BaseModel):
    estado: str  # pendiente, en_produccion, entregado, parcial, cancelado

class EntregarItemIn(BaseModel):
    item_id: int
    cantidad_entregada: float

# ─── Pedidos ──────────────────────────────────────────────────────────────────

@router.get("/api/pedidos")
def listar_pedidos(estado: Optional[str] = None, cliente_id: Optional[int] = None,
                   db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    q = db.query(models.Pedido).order_by(models.Pedido.fecha_pedido.desc())
    if estado:
        q = q.filter(models.Pedido.estado == estado)
    if cliente_id:
        q = q.filter(models.Pedido.cliente_id == cliente_id)
    pedidos = q.all()
    return [
        {
            "id": p.id,
            "cliente_id": p.cliente_id,
            "cliente": p.cliente.nombre,
            "fecha_pedido": p.fecha_pedido,
            "fecha_entrega": p.fecha_entrega,
            "estado": p.estado,
            "total": p.total,
            "monto_pagado": p.monto_pagado,
            "pendiente_cobro": p.total - p.monto_pagado,
            "notas": p.notas,
            "cant_items": len(p.items),
        }
        for p in pedidos
    ]

@router.get("/api/pedidos/{id}")
def obtener_pedido(id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    p = db.query(models.Pedido).filter(models.Pedido.id == id).first()
    if not p:
        raise HTTPException(404, "Pedido no encontrado")
    return {
        "id": p.id,
        "cliente_id": p.cliente_id,
        "cliente": p.cliente.nombre,
        "fecha_pedido": p.fecha_pedido,
        "fecha_entrega": p.fecha_entrega,
        "estado": p.estado,
        "total": p.total,
        "monto_pagado": p.monto_pagado,
        "notas": p.notas,
        "items": [
            {
                "id": it.id,
                "producto_id": it.producto_id,
                "producto": it.producto.nombre,
                "cantidad": it.cantidad,
                "precio_unitario": it.precio_unitario,
                "subtotal": it.subtotal,
                "cantidad_entregada": it.cantidad_entregada,
                "pendiente": it.cantidad - it.cantidad_entregada,
            }
            for it in p.items
        ],
    }

@router.post("/api/pedidos")
def crear_pedido(data: PedidoIn, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    cliente = db.query(models.Cliente).filter(models.Cliente.id == data.cliente_id).first()
    if not cliente:
        raise HTTPException(404, "Cliente no encontrado")

    total = sum(it.cantidad * it.precio_unitario for it in data.items)

    from datetime import datetime
    fecha_entrega = None
    if data.fecha_entrega:
        try:
            fecha_entrega = datetime.fromisoformat(data.fecha_entrega)
        except Exception:
            pass

    pedido = models.Pedido(
        cliente_id=data.cliente_id,
        fecha_entrega=fecha_entrega,
        total=total,
        monto_pagado=0.0,
        notas=data.notas,
        usuario_id=current_user.id,
    )
    db.add(pedido)
    db.flush()

    for it in data.items:
        item = models.ItemPedido(
            pedido_id=pedido.id,
            producto_id=it.producto_id,
            cantidad=it.cantidad,
            precio_unitario=it.precio_unitario,
            subtotal=it.cantidad * it.precio_unitario,
            cantidad_entregada=0.0,
        )
        db.add(item)

    # Registrar cargo en cuenta corriente del cliente
    mov = models.MovimientoCuenta(
        cliente_id=data.cliente_id,
        tipo="cargo",
        monto=total,
        descripcion=f"Pedido #{pedido.id}",
        pedido_id=pedido.id,
    )
    db.add(mov)
    cliente.saldo += total

    db.commit()
    db.refresh(pedido)
    return {"id": pedido.id, "total": total}

@router.put("/api/pedidos/{id}/estado")
def actualizar_estado(id: int, data: ActualizarEstadoIn,
                      db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    p = db.query(models.Pedido).filter(models.Pedido.id == id).first()
    if not p:
        raise HTTPException(404, "No encontrado")
    p.estado = data.estado
    db.commit()
    return {"ok": True}

@router.post("/api/pedidos/{id}/pago")
def registrar_pago(id: int, monto: float,
                   db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    p = db.query(models.Pedido).filter(models.Pedido.id == id).first()
    if not p:
        raise HTTPException(404, "No encontrado")

    p.monto_pagado = min(p.monto_pagado + monto, p.total)

    # Reflejar en cuenta corriente
    cliente = db.query(models.Cliente).filter(models.Cliente.id == p.cliente_id).first()
    mov = models.MovimientoCuenta(
        cliente_id=p.cliente_id,
        tipo="pago",
        monto=monto,
        descripcion=f"Pago pedido #{id}",
        pedido_id=id,
    )
    db.add(mov)
    cliente.saldo = max(0, cliente.saldo - monto)

    db.commit()
    return {"ok": True, "monto_pagado": p.monto_pagado}

@router.put("/api/pedidos/{id}/entregar")
def registrar_entrega(id: int, items: List[EntregarItemIn],
                      db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    p = db.query(models.Pedido).filter(models.Pedido.id == id).first()
    if not p:
        raise HTTPException(404, "No encontrado")

    for entrega in items:
        item = db.query(models.ItemPedido).filter(models.ItemPedido.id == entrega.item_id).first()
        if item:
            item.cantidad_entregada = min(item.cantidad, entrega.cantidad_entregada)

    # Recalcular estado
    total_items = sum(it.cantidad for it in p.items)
    total_entregado = sum(it.cantidad_entregada for it in p.items)
    if total_entregado >= total_items:
        p.estado = "entregado"
    elif total_entregado > 0:
        p.estado = "parcial"

    db.commit()
    return {"ok": True, "estado": p.estado}

@router.delete("/api/pedidos/{id}")
def cancelar_pedido(id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    p = db.query(models.Pedido).filter(models.Pedido.id == id).first()
    if not p:
        raise HTTPException(404, "No encontrado")
    if p.estado == "entregado":
        raise HTTPException(400, "No se puede cancelar un pedido ya entregado")
    p.estado = "cancelado"
    # Revertir cargo en cuenta si no fue pagado
    pendiente = p.total - p.monto_pagado
    if pendiente > 0:
        cliente = db.query(models.Cliente).filter(models.Cliente.id == p.cliente_id).first()
        if cliente:
            cliente.saldo = max(0, cliente.saldo - pendiente)
            db.add(models.MovimientoCuenta(
                cliente_id=p.cliente_id,
                tipo="nota_credito",
                monto=pendiente,
                descripcion=f"Cancelación pedido #{id}",
                pedido_id=id,
            ))
    db.commit()
    return {"ok": True}
