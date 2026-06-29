#!/bin/bash
# ────────────────────────────────────────────────────────────
# TUESTE — Script de inicio local
# Ejecutar con: bash iniciar.sh
# ────────────────────────────────────────────────────────────

echo ""
echo "☕  TUESTE — Sistema de Gestión"
echo "─────────────────────────────────"

# 1. Instalar dependencias si no están
if ! python3 -c "import fastapi" 2>/dev/null; then
  echo "→ Instalando dependencias..."
  pip3 install -r requirements.txt
fi

# 2. Arrancar el servidor
echo "→ Iniciando servidor..."
echo "→ Abrí tu navegador en: http://localhost:8000"
echo ""
echo "  Usuario: admin@tueste.com"
echo "  Contraseña: tueste2024"
echo ""
echo "  (Ctrl+C para detener)"
echo "─────────────────────────────────"

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
