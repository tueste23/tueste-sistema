"""Endpoints para clientes y cuenta corriente."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
from ..database import get_db
from ..auth import get_current_user
from .. import models

router = APIRouter(tags=["clientes"])

# ─── Schemas ──────────────────────────────────────────────────────────────────

class ClienteIn(BaseModel):
    nombre: str
    tipo: str = "externo"  # interno, externo
    contacto: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    direccion: Optional[str] = None
    limite_credito: float = 0.0

class MovimientoIn(BaseModel):
    tipo: str  # cargo, pago, nota_credito
    monto: float
    descripcion: Optional[str] = None
    pedido_id: Optional[int] = None

# ─── Clientes ─────────────────────────────────────────────────────────────────

@router.get("/api/clientes")
def listar_clientes(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    clientes = db.query(models.Cliente).filter(models.Cliente.activo == True).all()
    return [
        {
            "id": c.id,
            "nombre": c.nombre,
            "tipo": c.tipo,
            "contacto": c.contacto,
            "telefono": c.telefono,
            "email": c.email,
            "direccion": c.direccion,
            "limite_credito": c.limite_credito,
            "saldo": c.saldo,
            "en_deuda": c.saldo > 0,
        }
        for c in clientes
    ]

@router.get("/api/clientes/{id}")
def obtener_cliente(id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    c = db.query(models.Cliente).filter(models.Cliente.id == id).first()
    if not c:
        raise HTTPException(404, "Cliente no encontrado")
    movimientos = [
        {
            "id": m.id,
            "tipo": m.tipo,
            "monto": m.monto,
            "descripcion": m.descripcion,
            "pedido_id": m.pedido_id,
            "fecha": m.fecha,
        }
        for m in sorted(c.movimientos_cuenta, key=lambda x: x.fecha, reverse=True)
    ]
    return {
        "id": c.id,
        "nombre": c.nombre,
        "tipo": c.tipo,
        "contacto": c.contacto,
        "telefono": c.telefono,
        "email": c.email,
        "direccion": c.direccion,
        "limite_credito": c.limite_credito,
        "saldo": c.saldo,
        "movimientos": movimientos,
    }

@router.post("/api/clientes")
def crear_cliente(data: ClienteIn, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    c = models.Cliente(**data.dict())
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"id": c.id}

@router.put("/api/clientes/{id}")
def actualizar_cliente(id: int, data: ClienteIn, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    c = db.query(models.Cliente).filter(models.Cliente.id == id).first()
    if not c:
        raise HTTPException(404, "No encontrado")
    for k, v in data.dict(exclude_unset=True).items():
        setattr(c, k, v)
    db.commit()
    return {"ok": True}

@router.delete("/api/clientes/{id}")
def eliminar_cliente(id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    c = db.query(models.Cliente).filter(models.Cliente.id == id).first()
    if not c:
        raise HTTPException(404, "No encontrado")
    c.activo = False
    db.commit()
    return {"ok": True}

# ─── Cuenta corriente ─────────────────────────────────────────────────────────

@router.post("/api/clientes/{id}/movimientos")
def registrar_movimiento(id: int, data: MovimientoIn,
                         db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    c = db.query(models.Cliente).filter(models.Cliente.id == id).first()
    if not c:
        raise HTTPException(404, "Cliente no encontrado")

    mov = models.MovimientoCuenta(
        cliente_id=id,
        tipo=data.tipo,
        monto=data.monto,
        descripcion=data.descripcion,
        pedido_id=data.pedido_id,
    )
    db.add(mov)

    # Actualizar saldo: cargo suma deuda, pago/nota_credito la resta
    if data.tipo == "cargo":
        c.saldo += data.monto
    else:
        c.saldo -= data.monto

    db.commit()
    return {"ok": True, "saldo_nuevo": c.saldo}

# ─── Rentabilidad por cliente ─────────────────────────────────────────────────

@router.get("/api/clientes/{id}/rentabilidad")
def rentabilidad_cliente(id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    c = db.query(models.Cliente).filter(models.Cliente.id == id).first()
    if not c:
        raise HTTPException(404, "No encontrado")

    pedidos = db.query(models.Pedido).filter(
        models.Pedido.cliente_id == id,
        models.Pedido.estado == "entregado"
    ).all()

    total_ventas = sum(p.total for p in pedidos)
    total_cobrado = sum(p.monto_pagado for p in pedidos)
    total_items = 0
    costo_total = 0.0

    for pedido in pedidos:
        for item in pedido.items:
            total_items += item.cantidad_entregada
            if item.producto.receta:
                costo_total += item.producto.receta.costo_calculado * item.cantidad_entregada

    margen = ((total_ventas - costo_total) / total_ventas * 100) if total_ventas > 0 else 0

    return {
        "cliente": c.nombre,
        "total_pedidos": len(pedidos),
        "total_ventas": total_ventas,
        "total_cobrado": total_cobrado,
        "saldo_pendiente": c.saldo,
        "costo_estimado": costo_total,
        "margen_pct": round(margen, 1),
    }

# ─── Alertas de deuda ─────────────────────────────────────────────────────────

@router.get("/api/clientes/alertas/deuda")
def alertas_deuda(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    clientes_deuda = db.query(models.Cliente).filter(
        models.Cliente.activo == True,
        models.Cliente.saldo > 0
    ).order_by(models.Cliente.saldo.desc()).all()

    return [
        {
            "id": c.id,
            "nombre": c.nombre,
            "saldo": c.saldo,
            "limite_credito": c.limite_credito,
            "supera_limite": c.saldo > c.limite_credito and c.limite_credito > 0,
        }
        for c in clientes_deuda
    ]
