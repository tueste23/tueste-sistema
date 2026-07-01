from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base
import enum

# ─── Enums ────────────────────────────────────────────────────────────────────

class TipoLocal(str, enum.Enum):
    cafeteria = "cafeteria"
    restaurante = "restaurante"
    produccion = "produccion"

class TipoMovStock(str, enum.Enum):
    entrada = "entrada"
    salida = "salida"
    ajuste = "ajuste"
    produccion = "produccion"
    venta = "venta"
    compra = "compra"

class EstadoOC(str, enum.Enum):
    borrador = "borrador"
    enviada = "enviada"
    recibida = "recibida"
    cancelada = "cancelada"

# ─── Usuarios ─────────────────────────────────────────────────────────────────

class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True)
    nombre = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    rol = Column(String(50), default="operario")  # dueno, gerente, compras, cocina, contador, operario
    activo = Column(Boolean, default=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())

# ─── Locales ──────────────────────────────────────────────────────────────────

class Local(Base):
    __tablename__ = "locales"
    id = Column(Integer, primary_key=True)
    nombre = Column(String(100), nullable=False)
    tipo = Column(String(50), nullable=False)
    activo = Column(Boolean, default=True)

# ─── Categorías ───────────────────────────────────────────────────────────────

class Categoria(Base):
    __tablename__ = "categorias"
    id = Column(Integer, primary_key=True)
    nombre = Column(String(100), nullable=False)
    tipo = Column(String(50), nullable=False)  # producto | ingrediente
    margen_objetivo = Column(Float, default=0.65)  # 65% por defecto

    productos = relationship("Producto", back_populates="categoria")
    ingredientes = relationship("Ingrediente", back_populates="categoria")

# ─── Proveedores ──────────────────────────────────────────────────────────────

class Proveedor(Base):
    __tablename__ = "proveedores"
    id = Column(Integer, primary_key=True)
    nombre = Column(String(150), nullable=False)
    contacto = Column(String(150))
    telefono = Column(String(50))
    email = Column(String(150))
    condicion_pago = Column(String(100))
    activo = Column(Boolean, default=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())

    ingredientes = relationship("Ingrediente", back_populates="proveedor_principal")
    ordenes_compra = relationship("OrdenCompra", back_populates="proveedor")

# ─── Ingredientes / Insumos ───────────────────────────────────────────────────

class Ingrediente(Base):
    __tablename__ = "ingredientes"
    id = Column(Integer, primary_key=True)
    nombre = Column(String(150), nullable=False)
    unidad = Column(String(30), nullable=False)  # kg, litro, unidad, g, ml, etc.
    costo_actual = Column(Float, default=0.0)   # costo por unidad
    stock_actual = Column(Float, default=0.0)
    stock_minimo = Column(Float, default=0.0)
    categoria_id = Column(Integer, ForeignKey("categorias.id"), nullable=True)
    proveedor_id = Column(Integer, ForeignKey("proveedores.id"), nullable=True)
    activo = Column(Boolean, default=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    actualizado_en = Column(DateTime(timezone=True), onupdate=func.now())

    categoria = relationship("Categoria", back_populates="ingredientes")
    proveedor_principal = relationship("Proveedor", back_populates="ingredientes")
    historial_costos = relationship("HistorialCosto", back_populates="ingrediente", order_by="HistorialCosto.fecha.desc()")
    items_receta = relationship("ItemReceta", back_populates="ingrediente")
    movimientos_stock = relationship("MovimientoStock", back_populates="ingrediente")

class HistorialCosto(Base):
    __tablename__ = "historial_costos"
    id = Column(Integer, primary_key=True)
    ingrediente_id = Column(Integer, ForeignKey("ingredientes.id"), nullable=False)
    costo_anterior = Column(Float)
    costo_nuevo = Column(Float)
    motivo = Column(String(200))
    fecha = Column(DateTime(timezone=True), server_default=func.now())
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    ingrediente = relationship("Ingrediente", back_populates="historial_costos")

# ─── Productos (lo que se vende) ──────────────────────────────────────────────

class Producto(Base):
    __tablename__ = "productos"
    id = Column(Integer, primary_key=True)
    nombre = Column(String(150), nullable=False)
    descripcion = Column(Text)
    precio_venta = Column(Float, nullable=False)
    categoria_id = Column(Integer, ForeignKey("categorias.id"), nullable=True)
    local_id = Column(Integer, ForeignKey("locales.id"), nullable=True)
    activo = Column(Boolean, default=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())

    categoria = relationship("Categoria", back_populates="productos")
    receta = relationship("Receta", back_populates="producto", uselist=False)
    items_venta = relationship("ItemVenta", back_populates="producto")

# ─── Recetas ──────────────────────────────────────────────────────────────────

class Receta(Base):
    __tablename__ = "recetas"
    id = Column(Integer, primary_key=True)
    producto_id = Column(Integer, ForeignKey("productos.id"), unique=True, nullable=False)
    rendimiento = Column(Float, default=1.0)     # porciones que rinde
    descripcion = Column(Text)
    costo_calculado = Column(Float, default=0.0) # se actualiza automáticamente
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    actualizado_en = Column(DateTime(timezone=True), onupdate=func.now())

    producto = relationship("Producto", back_populates="receta")
    items = relationship("ItemReceta", back_populates="receta", cascade="all, delete-orphan")

class ItemReceta(Base):
    __tablename__ = "items_receta"
    id = Column(Integer, primary_key=True)
    receta_id = Column(Integer, ForeignKey("recetas.id"), nullable=False)
    ingrediente_id = Column(Integer, ForeignKey("ingredientes.id"), nullable=False)
    cantidad = Column(Float, nullable=False)
    unidad = Column(String(30))

    receta = relationship("Receta", back_populates="items")
    ingrediente = relationship("Ingrediente", back_populates="items_receta")

# ─── Stock / Inventario ───────────────────────────────────────────────────────

class MovimientoStock(Base):
    __tablename__ = "movimientos_stock"
    id = Column(Integer, primary_key=True)
    ingrediente_id = Column(Integer, ForeignKey("ingredientes.id"), nullable=False)
    local_id = Column(Integer, ForeignKey("locales.id"), nullable=True)
    tipo = Column(String(30), nullable=False)   # entrada, salida, ajuste, venta, compra, produccion
    cantidad = Column(Float, nullable=False)
    stock_anterior = Column(Float)
    stock_nuevo = Column(Float)
    motivo = Column(String(200))
    referencia_id = Column(Integer)             # id de OC, venta, produccion, etc.
    fecha = Column(DateTime(timezone=True), server_default=func.now())
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    ingrediente = relationship("Ingrediente", back_populates="movimientos_stock")

# ─── Compras ──────────────────────────────────────────────────────────────────

class OrdenCompra(Base):
    __tablename__ = "ordenes_compra"
    id = Column(Integer, primary_key=True)
    proveedor_id = Column(Integer, ForeignKey("proveedores.id"), nullable=False)
    estado = Column(String(30), default="borrador")  # borrador, enviada, recibida, cancelada
    fecha_emision = Column(DateTime(timezone=True), server_default=func.now())
    fecha_entrega = Column(DateTime(timezone=True), nullable=True)
    total = Column(Float, default=0.0)
    notas = Column(Text)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    proveedor = relationship("Proveedor", back_populates="ordenes_compra")
    items = relationship("ItemOrdenCompra", back_populates="orden", cascade="all, delete-orphan")

class ItemOrdenCompra(Base):
    __tablename__ = "items_orden_compra"
    id = Column(Integer, primary_key=True)
    orden_id = Column(Integer, ForeignKey("ordenes_compra.id"), nullable=False)
    ingrediente_id = Column(Integer, ForeignKey("ingredientes.id"), nullable=False)
    cantidad = Column(Float, nullable=False)
    precio_unitario = Column(Float, nullable=False)
    subtotal = Column(Float, nullable=False)

    orden = relationship("OrdenCompra", back_populates="items")
    ingrediente = relationship("Ingrediente")

# ─── Ventas ───────────────────────────────────────────────────────────────────

class Venta(Base):
    __tablename__ = "ventas"
    id = Column(Integer, primary_key=True)
    local_id = Column(Integer, ForeignKey("locales.id"), nullable=True)
    fecha = Column(DateTime(timezone=True), server_default=func.now())
    total = Column(Float, default=0.0)
    costo_total = Column(Float, default=0.0)
    descuento = Column(Float, default=0.0)
    canal = Column(String(50), default="mostrador")  # mostrador, delivery, online
    notas = Column(Text)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    local = relationship("Local")
    items = relationship("ItemVenta", back_populates="venta", cascade="all, delete-orphan")

class ItemVenta(Base):
    __tablename__ = "items_venta"
    id = Column(Integer, primary_key=True)
    venta_id = Column(Integer, ForeignKey("ventas.id"), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False)
    cantidad = Column(Float, nullable=False, default=1)
    precio_unitario = Column(Float, nullable=False)
    costo_unitario = Column(Float, default=0.0)
    subtotal = Column(Float, nullable=False)

    venta = relationship("Venta", back_populates="items")
    producto = relationship("Producto", back_populates="items_venta")

# ─── Producción ───────────────────────────────────────────────────────────────

class OrdenProduccion(Base):
    __tablename__ = "ordenes_produccion"
    id = Column(Integer, primary_key=True)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False)
    local_destino_id = Column(Integer, ForeignKey("locales.id"), nullable=True)
    cantidad = Column(Float, nullable=False)
    estado = Column(String(30), default="pendiente")  # pendiente, en_proceso, finalizada
    fecha = Column(DateTime(timezone=True), server_default=func.now())
    costo_total = Column(Float, default=0.0)
    notas = Column(Text)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    producto = relationship("Producto")
    local_destino = relationship("Local")

# ─── Gastos fijos ─────────────────────────────────────────────────────────────

class GastoFijo(Base):
    __tablename__ = "gastos_fijos"
    id = Column(Integer, primary_key=True)
    concepto = Column(String(200), nullable=False)
    monto = Column(Float, nullable=False)
    local_id = Column(Integer, ForeignKey("locales.id"), nullable=True)
    mes = Column(Integer, nullable=False)  # 1-12
    anio = Column(Integer, nullable=False)
    categoria = Column(String(100))  # alquiler, sueldos, servicios, etc.
    creado_en = Column(DateTime(timezone=True), server_default=func.now())

# ─── Gastos variables ─────────────────────────────────────────────────────────

class GastoVariable(Base):
    __tablename__ = "gastos_variables"
    id = Column(Integer, primary_key=True)
    concepto = Column(String(200), nullable=False)
    monto = Column(Float, nullable=False)
    categoria = Column(String(100))  # packaging, limpieza, gas, etc.
    proveedor_id = Column(Integer, ForeignKey("proveedores.id"), nullable=True)
    fecha = Column(DateTime(timezone=True), server_default=func.now())
    mes = Column(Integer, nullable=False)
    anio = Column(Integer, nullable=False)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())

    proveedor = relationship("Proveedor")

# ─── Clientes ─────────────────────────────────────────────────────────────────

class Cliente(Base):
    __tablename__ = "clientes"
    id = Column(Integer, primary_key=True)
    nombre = Column(String(150), nullable=False)
    tipo = Column(String(50), default="externo")  # interno (tueste), externo
    contacto = Column(String(150))
    telefono = Column(String(50))
    email = Column(String(150))
    direccion = Column(String(250))
    limite_credito = Column(Float, default=0.0)
    saldo = Column(Float, default=0.0)  # positivo = nos deben, negativo = les debemos
    activo = Column(Boolean, default=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())

    pedidos = relationship("Pedido", back_populates="cliente")
    movimientos_cuenta = relationship("MovimientoCuenta", back_populates="cliente")

class MovimientoCuenta(Base):
    __tablename__ = "movimientos_cuenta"
    id = Column(Integer, primary_key=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    tipo = Column(String(30), nullable=False)  # cargo, pago, nota_credito
    monto = Column(Float, nullable=False)
    descripcion = Column(String(300))
    pedido_id = Column(Integer, ForeignKey("pedidos.id"), nullable=True)
    fecha = Column(DateTime(timezone=True), server_default=func.now())

    cliente = relationship("Cliente", back_populates="movimientos_cuenta")

# ─── Pedidos de clientes ──────────────────────────────────────────────────────

class Pedido(Base):
    __tablename__ = "pedidos"
    id = Column(Integer, primary_key=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    fecha_pedido = Column(DateTime(timezone=True), server_default=func.now())
    fecha_entrega = Column(DateTime(timezone=True), nullable=True)
    estado = Column(String(30), default="pendiente")  # pendiente, en_produccion, entregado, parcial, cancelado
    total = Column(Float, default=0.0)
    monto_pagado = Column(Float, default=0.0)
    notas = Column(Text)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    cliente = relationship("Cliente", back_populates="pedidos")
    items = relationship("ItemPedido", back_populates="pedido", cascade="all, delete-orphan")

class ItemPedido(Base):
    __tablename__ = "items_pedido"
    id = Column(Integer, primary_key=True)
    pedido_id = Column(Integer, ForeignKey("pedidos.id"), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False)
    cantidad = Column(Float, nullable=False)
    precio_unitario = Column(Float, nullable=False)
    cantidad_entregada = Column(Float, default=0.0)
    subtotal = Column(Float, nullable=False)

    pedido = relationship("Pedido", back_populates="items")
    producto = relationship("Producto")

# ─── Producción diaria ────────────────────────────────────────────────────────

class ProduccionDiaria(Base):
    __tablename__ = "produccion_diaria"
    id = Column(Integer, primary_key=True)
    fecha = Column(DateTime(timezone=True), server_default=func.now())
    operario = Column(String(100))
    notas = Column(Text)
    costo_total_teorico = Column(Float, default=0.0)   # según recetas
    costo_total_real = Column(Float, default=0.0)       # materia prima real usada
    creado_en = Column(DateTime(timezone=True), server_default=func.now())

    items = relationship("ItemProduccion", back_populates="produccion", cascade="all, delete-orphan")
    consumos = relationship("ConsumoProduccion", back_populates="produccion", cascade="all, delete-orphan")

class ItemProduccion(Base):
    __tablename__ = "items_produccion"
    id = Column(Integer, primary_key=True)
    produccion_id = Column(Integer, ForeignKey("produccion_diaria.id"), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False)
    cantidad = Column(Float, nullable=False)
    destino = Column(String(30), default="stock")  # entrega, stock
    pedido_id = Column(Integer, ForeignKey("pedidos.id"), nullable=True)  # si es para un pedido
    costo_teorico = Column(Float, default=0.0)

    produccion = relationship("ProduccionDiaria", back_populates="items")
    producto = relationship("Producto")

class ConsumoProduccion(Base):
    __tablename__ = "consumo_produccion"
    id = Column(Integer, primary_key=True)
    produccion_id = Column(Integer, ForeignKey("produccion_diaria.id"), nullable=False)
    ingrediente_id = Column(Integer, ForeignKey("ingredientes.id"), nullable=False)
    cantidad_teorica = Column(Float, default=0.0)   # según recetas
    cantidad_real = Column(Float, default=0.0)       # lo que realmente se usó
    diferencia = Column(Float, default=0.0)          # real - teorico

    produccion = relationship("ProduccionDiaria", back_populates="consumos")
    ingrediente = relationship("Ingrediente")
