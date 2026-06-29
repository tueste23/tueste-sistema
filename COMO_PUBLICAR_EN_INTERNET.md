# Publicar TUESTE en Internet — Guía paso a paso

## Opción recomendada: Railway (gratis para empezar)

### Paso 1: Crear cuenta
1. Ir a **railway.app**
2. Registrarse con Google o GitHub

### Paso 2: Subir el código a GitHub
1. Ir a **github.com** → New repository → nombre: `tueste-sistema`
2. En tu computadora, abrir Terminal en la carpeta `sistema/`
3. Ejecutar:
```bash
git init
git add .
git commit -m "TUESTE Sistema v1.0"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/tueste-sistema.git
git push -u origin main
```

### Paso 3: Conectar Railway con GitHub
1. En Railway → New Project → Deploy from GitHub repo
2. Seleccionar `tueste-sistema`
3. Railway detecta automáticamente el `railway.toml` y arranca el servidor

### Paso 4: Agregar variable de entorno de seguridad
En Railway → tu proyecto → Variables → agregar:
```
SECRET_KEY = una-clave-larga-y-secreta-que-solo-vos-conozcas
```

### Paso 5: Listo
Railway te da una URL como `https://tueste-sistema.up.railway.app`
Esa es la dirección de tu sistema. Se puede acceder desde cualquier celular o computadora.

---

## Para usar localmente (en tu computadora)

```bash
cd sistema/
bash iniciar.sh
```

Abrir: http://localhost:8000

Usuario: admin@tueste.com
Contraseña: tueste2024
