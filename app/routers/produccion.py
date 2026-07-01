"""Endpoints para producción diaria del CP."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from ..database import get_db
from ..auth import get_current_user
from .. import models

router = APIRouter(tags=["produccion"])

# ─── Schemas ──────────────────────────────────────────────────────────────────

class ItemProduccionIn(BaseModel):
    producto_id: int
    cantidad: float
    destino: str = "stock"  # stock, entrega
    pedido_id: Optional[int] = None

class ConsumoIn(BaseModel):
    ingrediente_id: int
    cantidad_teorica: float = 0.0
    cantidad_real: float

class ProduccionIn(BaseModel):
    operario: Optional[str] = None
    notas: Optional[str] = None
    items: List[ItemProduccionIn]
    consumos: Optional[List[ConsumoIn]] = []

# ─── Producción ───────────────────────────────────────────────────────────────

@router.get("/api/produccion")
def listar_producciones(limit: int = 30,
                        db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    prods = db.query(models.ProduccionDiaria)\
              .order_by(models.ProduccionDiaria.fecha.desc())\
              .limit(limit).all()
    return [
        {
            "id": p.id,
            "fecha": p.fecha,
            "operario": p.operario,
            "notas": p.notas,
            "costo_total_teorico": p.costo_total_teorico,
            "costo_total_real": p.costo_total_real,
            "cant_productos": len(p.items),
            "para_entrega": sum(it.cantidad for it in p.items if it.destino == "entrega"),
            "para_stock": sum(it.cantidad for it in p.items if it.destino == "stock"),
        }
        for p in prods
    ]

@router.get("/api/produccion/{id}")
def obtener_produccion(id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    p = db.query(models.ProduccionDiaria).filter(models.ProduccionDiaria.id == id).first()
    if not p:
        raise HTTPException(404, "Producción no encontrada")

    return {
        "id": p.id,
        "fecha": p.fecha,
        "operario": p.operario,
        "notas": p.notas,
        "costo_total_teorico": p.costo_total_teorico,
        "costo_total_real": p.costo_total_real,
        "items": [
            {
                "id": it.id,
                "producto_id": it.producto_id,
                "producto": it.producto.nombre,
                "cantidad": it.cantidad,
                "destino": it.destino,
                "pedido_id": it.pedido_id,
                "costo_teorico": it.costo_teorico,
            }
            for it in p.items
        ],
        "consumos": [
            {
                "id": c.id,
                "ingrediente_id": c.ingrediente_id,
                "ingrediente": c.ingrediente.nombre,
                "unidad": c.ingrediente.unidad,
                "cantidad_teorica": c.cantidad_teorica,
                "cantidad_real": c.cantidad_real,
                "diferencia": c.diferencia,
            }
            for c in p.consumos
        ],
    }

@router.post("/api/produccion")
def registrar_produccion(data: ProduccionIn,
                         db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    prod = models.ProduccionDiaria(
        operario=data.operario,
        notas=data.notas,
    )
    db.add(prod)
    db.flush()

    costo_teorico_total = 0.0
    costo_real_total = 0.0

    # Items de producción
    for it in data.items:
        producto = db.query(models.Producto).filter(models.Producto.id == it.producto_id).first()
        costo_teorico = 0.0
        if producto and producto.receta:
            costo_teorico = producto.receta.costo_calculado * it.cantidad

        item = models.ItemProduccion(
            produccion_id=prod.id,
            producto_id=it.producto_id,
            cantidad=it.cantidad,
            destino=it.destino,
            pedido_id=it.pedido_id,
            costo_teorico=costo_teorico,
        )
        db.add(item)
        costo_teorico_total += costo_teorico

        # Si va a stock, actualizar stock del ingrediente base no aplica aquí (es producto terminado)
        # Si destino es entrega, marcar en pedido si corresponde
        if it.destino == "entrega" and it.pedido_id:
            item_pedido = db.query(models.ItemPedido).filter(
                models.ItemPedido.pedido_id == it.pedido_id,
                models.ItemPedido.producto_id == it.producto_id,
            ).first()
            if item_pedido:
                item_pedido.cantidad_entregada = min(
                    item_pedido.cantidad,
                    item_pedido.cantidad_entregada + it.cantidad
                )

    # Consumos de materia prima
    for c in (data.consumos or []):
        ing = db.query(models.Ingrediente).filter(models.Ingrediente.id == c.ingrediente_id).first()
        if not ing:
            continue

        diferencia = c.cantidad_real - c.cantidad_teorica
        consumo = models.ConsumoProduccion(
            produccion_id=prod.id,
            ingrediente_id=c.ingrediente_id,
            cantidad_teorica=c.cantidad_teorica,
            cantidad_real=c.cantidad_real,
            diferencia=diferencia,
        )
        db.add(consumo)

        # Descontar del stock
        anterior = ing.stock_actual
        ing.stock_actual = max(0, ing.stock_actual - c.cantidad_real)
        db.add(models.MovimientoStock(
            ingrediente_id=ing.id,
            tipo="produccion",
            cantidad=-c.cantidad_real,
            stock_anterior=anterior,
            stock_nuevo=ing.stock_actual,
            motivo=f"Producción #{prod.id}",
        ))

        costo_real_total += c.cantidad_real * ing.costo_actual

    prod.costo_total_teorico = costo_teorico_total
    prod.costo_total_real = costo_real_total

    db.commit()
    db.refresh(prod)
    return {
        "id": prod.id,
        "costo_teorico": costo_teorico_total,
        "costo_real": costo_real_total,
        "diferencia_costo": costo_real_total - costo_teorico_total,
    }

# ─── CMV teórico vs real ──────────────────────────────────────────────────────

@router.get("/api/produccion/cmv/comparacion")
def comparar_cmv(mes: Optional[int] = None, anio: Optional[int] = None,
                 db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    from datetime import datetime
    ahora = datetime.utcnow()
    mes = mes or ahora.month
    anio = anio or ahora.year

    prods = db.query(models.ProduccionDiaria).all()
    prods = [p for p in prods if p.fecha.month == mes and p.fecha.year == anio]

    total_teorico = sum(p.costo_total_teorico for p in prods)
    total_real = sum(p.costo_total_real for p in prods)

    # Ventas del mes para calcular % CMV
    pedidos_mes = db.query(models.Pedido).filter(
        models.Pedido.estado == "entregado"
    ).all()
    pedidos_mes = [p for p in pedidos_mes if p.fecha_pedido.month == mes and p.fecha_pedido.year == anio]
    total_ventas = sum(p.total for p in pedidos_mes)

    cmv_teorico_pct = (total_teorico / total_ventas * 100) if total_ventas > 0 else 0
    cmv_real_pct = (total_real / total_ventas * 100) if total_ventas > 0 else 0

    # Detalle por ingrediente
    consumos_detalle = {}
    for p in prods:
        for c in p.consumos:
            nombre = c.ingrediente.nombre
            if nombre not in consumos_detalle:
                consumos_detalle[nombre] = {"teorico": 0, "real": 0, "unidad": c.ingrediente.unidad}
            consumos_detalle[nombre]["teorico"] += c.cantidad_teorica
            consumos_detalle[nombre]["real"] += c.cantidad_real

    detalle = [
        {
            "ingrediente": k,
            "unidad": v["unidad"],
            "cantidad_teorica": round(v["teorico"], 3),
            "cantidad_real": round(v["real"], 3),
            "diferencia": round(v["real"] - v["teorico"], 3),
        }
        for k, v in sorted(consumos_detalle.items(), key=lambda x: abs(x[1]["real"] - x[1]["teorico"]), reverse=True)
    ]

    return {
        "mes": mes,
        "anio": anio,
        "total_ventas": total_ventas,
        "costo_teorico": total_teorico,
        "costo_real": total_real,
        "diferencia": total_real - total_teorico,
        "cmv_teorico_pct": round(cmv_teorico_pct, 1),
        "cmv_real_pct": round(cmv_real_pct, 1),
        "detalle_ingredientes": detalle,
    }
