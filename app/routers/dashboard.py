from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from datetime import datetime, timedelta
from ..database import get_db
from ..auth import get_current_user
from .. import models

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

@router.get("")
def dashboard(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    ahora = datetime.utcnow()
    mes_actual = ahora.month
    anio_actual = ahora.year
    mes_ant = mes_actual - 1 if mes_actual > 1 else 12
    anio_ant = anio_actual if mes_actual > 1 else anio_actual - 1
    hoy = ahora.date()

    def ventas_periodo(mes, anio):
        return db.query(models.Venta).filter(
            extract('month', models.Venta.fecha) == mes,
            extract('year', models.Venta.fecha) == anio,
        ).all()

    # ── Ventas mes actual ──
    ventas_mes = ventas_periodo(mes_actual, anio_actual)
    total_mes = sum(v.total for v in ventas_mes)
    costo_mes = sum(v.costo_total for v in ventas_mes)
    cant_ventas = len(ventas_mes)

    # ── Ventas mes anterior ──
    ventas_ant = ventas_periodo(mes_ant, anio_ant)
    total_mes_ant = sum(v.total for v in ventas_ant)

    # ── Ventas hoy ──
    ventas_hoy = db.query(models.Venta).filter(
        func.date(models.Venta.fecha) == hoy
    ).all()
    total_hoy = sum(v.total for v in ventas_hoy)

    # ── Ventas últimos 30 días por día ──
    hace_30 = ahora - timedelta(days=29)
    v30 = db.query(models.Venta).filter(models.Venta.fecha >= hace_30).all()
    por_dia = {}
    for v in v30:
        d = v.fecha.strftime("%d/%m")
        por_dia[d] = por_dia.get(d, 0) + v.total

    # ── Margen ──
    margen_bruto = total_mes - costo_mes
    margen_pct = margen_bruto / total_mes * 100 if total_mes > 0 else 0
    ticket_promedio = total_mes / cant_ventas if cant_ventas > 0 else 0
    variacion_ventas = ((total_mes - total_mes_ant) / total_mes_ant * 100) if total_mes_ant > 0 else 0

    # ── Stock crítico ──
    stock_critico = db.query(models.Ingrediente).filter(
        models.Ingrediente.activo == True,
        models.Ingrediente.stock_actual <= models.Ingrediente.stock_minimo,
        models.Ingrediente.stock_minimo > 0,
    ).count()

    # ── Compras del mes ──
    compras_mes = db.query(models.OrdenCompra).filter(
        extract('month', models.OrdenCompra.fecha_emision) == mes_actual,
        extract('year', models.OrdenCompra.fecha_emision) == anio_actual,
        models.OrdenCompra.estado == "recibida",
    ).all()
    total_compras = sum(c.total for c in compras_mes)

    # ── CMV sobre ventas ──
    cmv_pct = costo_mes / total_mes * 100 if total_mes > 0 else 0

    # ── Gastos fijos del mes ──
    gastos = db.query(models.GastoFijo).filter(
        models.GastoFijo.mes == mes_actual,
        models.GastoFijo.anio == anio_actual,
    ).all()
    total_gastos = sum(g.monto for g in gastos)

    # ── Resultado neto ──
    resultado_neto = margen_bruto - total_gastos
    rent_neta_pct = resultado_neto / total_mes * 100 if total_mes > 0 else 0

    # ── Top productos por ventas ──
    items_mes = db.query(models.ItemVenta).join(models.Venta).filter(
        extract('month', models.Venta.fecha) == mes_actual,
        extract('year', models.Venta.fecha) == anio_actual,
    ).all()
    prod_ventas = {}
    prod_margen = {}
    for it in items_mes:
        nombre = it.producto.nombre
        prod_ventas[nombre] = prod_ventas.get(nombre, 0) + it.subtotal
        prod_margen[nombre] = prod_margen.get(nombre, 0) + (it.subtotal - it.costo_unitario * it.cantidad)

    top_productos = sorted(
        [{"nombre": k, "ventas": round(v, 2), "margen": round(prod_margen.get(k, 0), 2)}
         for k, v in prod_ventas.items()],
        key=lambda x: x["ventas"], reverse=True
    )[:10]

    # ── Menores márgenes (productos con receta) ──
    recetas = db.query(models.Receta).all()
    margenes = []
    for r in recetas:
        if r.producto and r.producto.precio_venta > 0:
            m = (r.producto.precio_venta - r.costo_calculado) / r.producto.precio_venta * 100
            margenes.append({
                "producto": r.producto.nombre,
                "precio_venta": r.producto.precio_venta,
                "costo": r.costo_calculado,
                "margen_pct": round(m, 1),
            })
    peores_margenes = sorted(margenes, key=lambda x: x["margen_pct"])[:5]

    return {
        "resumen": {
            "total_ventas_mes": round(total_mes, 2),
            "total_ventas_hoy": round(total_hoy, 2),
            "variacion_vs_mes_anterior": round(variacion_ventas, 1),
            "margen_bruto": round(margen_bruto, 2),
            "margen_pct": round(margen_pct, 1),
            "cmv_pct": round(cmv_pct, 1),
            "ticket_promedio": round(ticket_promedio, 2),
            "cantidad_ventas_mes": cant_ventas,
            "total_compras_mes": round(total_compras, 2),
            "gastos_fijos_mes": round(total_gastos, 2),
            "resultado_neto": round(resultado_neto, 2),
            "rentabilidad_neta_pct": round(rent_neta_pct, 1),
            "stock_critico_count": stock_critico,
        },
        "ventas_por_dia": [{"fecha": k, "total": round(v, 2)} for k, v in sorted(por_dia.items())],
        "top_productos": top_productos,
        "peores_margenes": peores_margenes,
        "mes": mes_actual,
        "anio": anio_actual,
    }

@router.get("/pl")
def estado_resultados(mes: int = None, anio: int = None,
                       db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Estado de resultados (P&L) del mes."""
    ahora = datetime.utcnow()
    mes = mes or ahora.month
    anio = anio or ahora.year

    # ── Ventas ──
    ventas = db.query(models.Venta).filter(
        extract('month', models.Venta.fecha) == mes,
        extract('year', models.Venta.fecha) == anio,
    ).all()
    total_ventas = sum(v.total for v in ventas)

    # ── CMV: desde recetas (ventas diarias) + materia prima de gastos variables (histórico) ──
    cmv_recetas = sum(v.costo_total for v in ventas)

    # ── Gastos variables ──
    gv = db.query(models.GastoVariable).filter(
        models.GastoVariable.mes == mes,
        models.GastoVariable.anio == anio,
    ).all()

    # CMV histórico = materia prima de gastos variables (si no hay CMV de recetas)
    cmv_mp = sum(g.monto for g in gv if g.categoria == "materia_prima")
    costo_mercaderia = cmv_recetas if cmv_recetas > 0 else cmv_mp

    margen_bruto = total_ventas - costo_mercaderia

    # Gastos variables agrupados (excluye materia_prima si ya se usó como CMV)
    gv_por_cat = {}
    for g in gv:
        # Si la materia prima ya fue usada como CMV, no duplicar
        if cmv_recetas > 0 and g.categoria == "materia_prima":
            continue
        # Si la materia prima fue usada como CMV histórico, no la incluir de nuevo en gastos
        if cmv_recetas == 0 and g.categoria == "materia_prima":
            continue
        cat = g.categoria or "operativo"
        gv_por_cat[cat] = gv_por_cat.get(cat, 0) + g.monto
    total_gv = sum(gv_por_cat.values())

    # ── Gastos fijos ──
    gf = db.query(models.GastoFijo).filter(
        models.GastoFijo.mes == mes,
        models.GastoFijo.anio == anio,
    ).all()
    gf_por_cat = {}
    for g in gf:
        cat = g.categoria or "varios"
        gf_por_cat[cat] = gf_por_cat.get(cat, 0) + g.monto
    total_gf = sum(g.monto for g in gf)

    total_gastos = total_gv + total_gf
    resultado = margen_bruto - total_gastos

    return {
        "periodo": f"{mes}/{anio}",
        "ingresos": {"ventas": round(total_ventas, 2)},
        "costo_mercaderia": round(costo_mercaderia, 2),
        "costo_mp_historico": round(cmv_mp, 2),
        "margen_bruto": round(margen_bruto, 2),
        "margen_bruto_pct": round(margen_bruto / total_ventas * 100, 1) if total_ventas > 0 else 0,
        "gastos_variables": {k: round(v, 2) for k, v in gv_por_cat.items()},
        "total_gastos_variables": round(total_gv, 2),
        "gastos_fijos": {k: round(v, 2) for k, v in gf_por_cat.items()},
        "total_gastos_fijos": round(total_gf, 2),
        "total_gastos": round(total_gastos, 2),
        "resultado_neto": round(resultado, 2),
        "rentabilidad_pct": round(resultado / total_ventas * 100, 1) if total_ventas > 0 else 0,
    }
