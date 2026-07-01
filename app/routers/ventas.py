from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, date
from ..database import get_db
from ..auth import get_current_user
from .. import models

router = APIRouter(prefix="/api/ventas", tags=["ventas"])

class ItemVentaIn(BaseModel):
    producto_id: int
    cantidad: float = 1.0
    precio_unitario: Optional[float] = None  # si None, usa el precio del producto

class VentaCreate(BaseModel):
    local_id: Optional[int] = None
    canal: str = "mostrador"
    descuento: float = 0.0
    notas: Optional[str] = None
    fecha: Optional[date] = None   # si se omite, usa la fecha actual
    items: List[ItemVentaIn]

@router.get("")
def listar(
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    local_id: Optional[int] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    q = db.query(models.Venta).order_by(models.Venta.fecha.desc())
    if local_id:
        q = q.filter(models.Venta.local_id == local_id)
    if fecha_desde:
        q = q.filter(func.date(models.Venta.fecha) >= fecha_desde)
    if fecha_hasta:
        q = q.filter(func.date(models.Venta.fecha) <= fecha_hasta)
    ventas = q.limit(limit).all()
    return [
        {
            "id": v.id,
            "fecha": v.fecha,
            "local": v.local.nombre if v.local else None,
            "canal": v.canal,
            "total": v.total,
            "costo_total": v.costo_total,
            "margen": round((v.total - v.costo_total) / v.total * 100, 1) if v.total > 0 else 0,
            "items_count": len(v.items),
        }
        for v in ventas
    ]

@router.get("/resumen")
def resumen(
    mes: Optional[int] = None,
    anio: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    ahora = datetime.utcnow()
    mes = mes or ahora.month
    anio = anio or ahora.year

    ventas = db.query(models.Venta).filter(
        extract('month', models.Venta.fecha) == mes,
        extract('year', models.Venta.fecha) == anio,
    ).all()

    total_ventas = sum(v.total for v in ventas)
    total_costo = sum(v.costo_total for v in ventas)
    cant = len(ventas)
    ticket_promedio = total_ventas / cant if cant > 0 else 0
    margen_bruto = total_ventas - total_costo
    margen_pct = margen_bruto / total_ventas * 100 if total_ventas > 0 else 0

    # Ventas por día del mes
    por_dia = {}
    for v in ventas:
        dia = v.fecha.day
        por_dia[dia] = por_dia.get(dia, 0) + v.total

    return {
        "mes": mes, "anio": anio,
        "total_ventas": round(total_ventas, 2),
        "total_costo": round(total_costo, 2),
        "margen_bruto": round(margen_bruto, 2),
        "margen_pct": round(margen_pct, 1),
        "cantidad_ventas": cant,
        "ticket_promedio": round(ticket_promedio, 2),
        "por_dia": [{"dia": k, "total": round(v, 2)} for k, v in sorted(por_dia.items())],
    }

@router.get("/{id}")
def obtener(id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    v = db.query(models.Venta).filter(models.Venta.id == id).first()
    if not v:
        raise HTTPException(404, "Venta no encontrada")
    return {
        "id": v.id, "fecha": v.fecha, "canal": v.canal,
        "local": v.local.nombre if v.local else None,
        "total": v.total, "costo_total": v.costo_total, "descuento": v.descuento,
        "items": [
            {
                "producto": it.producto.nombre,
                "cantidad": it.cantidad,
                "precio_unitario": it.precio_unitario,
                "costo_unitario": it.costo_unitario,
                "subtotal": it.subtotal,
            }
            for it in v.items
        ],
    }

@router.post("")
def crear(data: VentaCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """
    Al registrar una venta:
    1. Crea la venta con sus items
    2. Descuenta automáticamente el stock de ingredientes según la receta de cada producto
    3. Calcula el costo real de la venta
    """
    total = 0.0
    costo_total = 0.0
    items_preparados = []

    for item_data in data.items:
        prod = db.query(models.Producto).filter(models.Producto.id == item_data.producto_id).first()
        if not prod:
            raise HTTPException(404, f"Producto {item_data.producto_id} no encontrado")
        precio = item_data.precio_unitario or prod.precio_venta
        costo_unit = prod.receta.costo_calculado if prod.receta else 0.0
        subtotal = precio * item_data.cantidad
        total += subtotal
        costo_total += costo_unit * item_data.cantidad
        items_preparados.append((prod, item_data.cantidad, precio, costo_unit, subtotal))

    total_final = max(total - data.descuento, 0)
    fecha_venta = datetime.combine(data.fecha, datetime.min.time()) if data.fecha else datetime.utcnow()
    venta = models.Venta(
        local_id=data.local_id,
        canal=data.canal,
        total=round(total_final, 2),
        costo_total=round(costo_total, 2),
        descuento=data.descuento,
        notas=data.notas,
        usuario_id=current_user.id,
        fecha=fecha_venta,
    )
    db.add(venta)
    db.flush()

    for prod, cantidad, precio, costo_unit, subtotal in items_preparados:
        item = models.ItemVenta(
            venta_id=venta.id,
            producto_id=prod.id,
            cantidad=cantidad,
            precio_unitario=precio,
            costo_unitario=costo_unit,
            subtotal=round(subtotal, 2),
        )
        db.add(item)

        # Descontar stock de ingredientes según la receta
        if prod.receta:
            for item_receta in prod.receta.items:
                ing = item_receta.ingrediente
                consumo = item_receta.cantidad * cantidad
                stock_anterior = ing.stock_actual
                ing.stock_actual = max(round(ing.stock_actual - consumo, 4), 0)
                mov = models.MovimientoStock(
                    ingrediente_id=ing.id,
                    tipo="venta",
                    cantidad=-consumo,
                    stock_anterior=stock_anterior,
                    stock_nuevo=ing.stock_actual,
                    motivo=f"Venta #{venta.id} - {prod.nombre}",
                    referencia_id=venta.id,
                    usuario_id=current_user.id,
                )
                db.add(mov)

    db.commit()
    return {"id": venta.id, "total": venta.total, "costo_total": venta.costo_total}
