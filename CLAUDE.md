# TUESTE — Sistema Operativo CP

Sistema de gestión para el Centro de Producción (CP) de TUESTE. Permite administrar recetas, costos, ventas, stock, estado de resultados y producción.

## Stack

- **Backend:** Python + FastAPI, SQLAlchemy ORM, PostgreSQL
- **Frontend:** HTML/JS single-page app con Alpine.js y Tailwind CSS (archivo único: `app/static/index.html`)
- **Deploy:** Railway → https://web-production-47696.up.railway.app
- **Repo GitHub:** https://github.com/tueste23/tueste-sistema
- **Login:** admin@tueste.com / tueste2024

## Estructura de archivos

```
sistema/
├── app/
│   ├── main.py                  # FastAPI app, auth, seed inicial, sirve el frontend
│   ├── models.py                # Todos los modelos SQLAlchemy (una sola base de datos)
│   ├── database.py              # Conexión a PostgreSQL via DATABASE_URL (Railway env var)
│   ├── auth.py                  # JWT con HS256, Bearer token
│   ├── static/
│   │   └── index.html           # TODA la UI — Alpine.js SPA, no hay archivos separados
│   └── routers/
│       ├── ingredientes.py      # CRUD ingredientes + conteo de stock (POST /api/ingredientes/conteo)
│       ├── recetas.py           # CRUD recetas con rendimiento y costo calculado
│       ├── ventas.py            # Ventas con datos fiscales, fecha opcional, DELETE endpoint
│       ├── compras.py           # Órdenes de compra
│       ├── dashboard.py         # KPIs + Estado de Resultados (/api/dashboard/pl)
│       ├── maestros.py          # Locales, categorías, proveedores, productos, gastos fijos
│       ├── gastos_variables.py  # Gastos variables con categoría y mes/año
│       ├── clientes.py          # Clientes del CP
│       ├── pedidos.py           # Pedidos de clientes
│       └── produccion.py        # Registros de producción diaria
├── importar_recetas_cp.py       # Importa ingredientes + recetas desde RECETAS MASTER.xlsx
├── corregir_rendimiento.py      # Re-importa recetas con rendimiento correcto
├── importar_eerr.py             # Importa 6 meses EERR (ventas + gastos) — re-runnable, borra y recarga
├── actualizar_mes.py            # Actualiza un mes específico del EERR desde el Excel
│                                # Uso: python3 actualizar_mes.py 7 2026
└── CLAUDE.md                    # Este archivo
```

## Modelos principales

### Ingrediente
- `stock_actual` — teórico, calculado automáticamente por trazabilidad (compras, ventas, producción)
- `stock_real` — físico, ingresado manualmente en el conteo de inventario
- `fecha_conteo` — cuándo se hizo el último conteo físico
- `costo_actual` — precio por unidad, usado para calcular costo de recetas

### Receta
- `rendimiento` — cuántas unidades produce la preparación (ej: 70 medialunas)
- `costo_calculado` — costo por porción = suma(ingredientes) / rendimiento
- Calculado automáticamente al crear/actualizar

### Venta
- `tipo_fiscal`: "fiscal" / "no_fiscal"
- `tipo_comprobante`: "factura_a" / "factura_b" / "factura_c" / "ticket"
- `numero_comprobante`: string opcional (ej: "0001-00000123")
- `medio_pago`: "efectivo" / "transferencia" / "debito" / "credito" / "mercado_pago"
- `cuit_receptor` + `razon_social_receptor`: requeridos para Factura A
- `canal`: "mostrador" / "delivery" / "online" / "resumen_mensual"
- `fecha`: datetime — si se pasa `date`, se guarda a las 12:00 UTC para evitar desfasaje horario (Argentina = UTC-3)
- Ventas con canal "resumen_mensual" son resúmenes históricos del EERR, se filtran en la UI

### GastoFijo
- Categorías: "alquiler" / "servicios" / "varios"
- Indexado por `mes` + `anio`

### GastoVariable
- Categorías: "materia_prima" / "rrhh" / "operativo" / "marketing"
- Indexado por `mes` + `anio`

## Estado de Resultados (/api/dashboard/pl)

Lógica de cálculo:
1. **CMV**: si hay `costo_total` en ventas (ventas con receta) → lo usa. Si no (resúmenes históricos) → usa gastos variables con categoria="materia_prima"
2. **Margen bruto** = ventas - CMV
3. **Gastos variables** (excluye materia_prima ya contada como CMV): rrhh, operativo, marketing
4. **Gastos fijos**: alquiler, servicios, varios
5. **Resultado neto** = margen bruto - gastos variables - gastos fijos

## Importación de datos Excel

### RECETAS MASTER.xlsx
- Pestaña "PRECIO PROVEEDORES": ingredientes con costo
- Pestañas "PASTELERIA CP" y "PASTELERIA PARA TUESTE": recetas en bloques horizontales (cols 1, 6, 11)
- Rendimiento calculado: `round(costo_total / costo_porcion)` desde las fórmulas del Excel
- Budines/tortas/pastafrolas: rendimiento = 1 (se venden enteras aunque digan "RINDE 9 PORCIONES")
- Precio de venta: col+2 ($) para productos rinde>1; col+3 (Total $) para productos rinde=1

### CENTRO PRODUCCIÓN EERRs 2026.xlsx
- Pestaña "GASTOS": datos mensuales, estructura de 100 filas por mes
- Columna 32 = "Total mes" de cada ítem
- Junio 2026: total real = $12,820,702.50 (el Excel tenía dato parcial, se corrigió manualmente)
- Script `actualizar_mes.py` lee el Excel y actualiza un mes sin afectar los demás

## Flujo de deploy

```bash
# Hacer cambios en archivos
git add .
git commit -m "descripción del cambio"
git push
# Railway redeploya automáticamente en ~2 minutos
```

## Zona horaria

Railway corre en UTC. Argentina = UTC-3. Para evitar que fechas como "2026-01-01" se guarden como "2025-12-31 21:00" al mostrarlas en hora local, las ventas con fecha manual se guardan a las **12:00 UTC** (`dtime(12, 0, 0)`).

## Scripts de mantenimiento

```bash
# Actualizar un mes del EERR (leer del Excel y subir al sistema)
python3 actualizar_mes.py 7 2026   # → Julio 2026

# Re-importar todo el EERR desde cero (borra y recarga los 6 meses)
python3 importar_eerr.py

# Re-importar recetas con rendimiento (borra productos/recetas y recarga)
python3 corregir_rendimiento.py
```

## Pendientes / conocidos

- 5 productos sin precio externo en Excel (se fijan manualmente en el sistema):
  TORTA DE RICOTA, CHOCOTORTA, BUDIN MARMOLADO RINDE 9 PORCIONES, PASTAFROLA ENTERA/RINDE 8 PORCIONES, MARQUISE
- Salarios de junio 2026 = $0 en el EERR (dato no disponible aún, se carga cuando se conozca)
- El CMV del Estado de Resultados para meses históricos viene de gastos_variables categoria="materia_prima", no de las recetas (porque los resúmenes mensuales usan el producto "VENTAS HISTÓRICAS CP" que no tiene receta)
