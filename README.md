# Verificador E-14 — Presidenciales Colombia 2026 (1ra y 2da Vuelta)

Herramienta de verificación ciudadana independiente de actas E-14.
Permite buscar cualquier formulario oficial por su código de transmisión (ej. `X 6-45-25-18 X`) o por ubicación geográfica. Esta versión unificada integra los datos tanto de la primera como de la segunda vuelta electoral en una sola interfaz, cruzando los datos de preconteo (Delegados) con los escrutinios finales (Claveros).

## Arquitectura del Proyecto

El proyecto está dividido en dos grandes componentes: un **Pipeline de Datos (ETL)** que se ejecuta localmente y un **Servidor Web** ligero diseñado para despliegues en la nube.

### Estructura de Directorios

| Ruta / Archivo | Descripción |
|---|---|
| `main.py` | Servidor FastAPI con la interfaz frontend (HTML/JS/CSS inyectado) y selector unificado. |
| `indexador_maestro.py` | Pipeline ETL concurrente. Indexa, descarga URLs y realiza auditoría forense. |
| `/bases_de_datos/` | Contiene los archivos `.db` (SQLite) optimizados y listos para producción. |
| `/datos_crudos/` | Carpeta local ignorada en Git. Contiene los JSON oficiales y reportes `.csv`. |
| `requirements.txt` | Dependencias exclusivas del servidor (`fastapi`, `uvicorn`). |
| `Procfile` / `nixpacks.toml` | Archivos de configuración para el despliegue automático en Railway. |

## Motor de Indexación (`indexador_maestro.py`)

Para evitar bloqueos por IP (WAF/Cloudflare) y proteger la infraestructura en la nube, la indexación de las 122,000+ mesas se realiza en local mediante un script robusto dividido en 3 fases:

1. **Fase 1 (Preconteo):** Carga masiva (UPSERT) de los JSON de delegados a la base de datos SQLite.
2. **Fase 2 (Escrutinios):** Extracción concurrente dinámica. Utiliza 40 hilos para la Primera Vuelta y 15 hilos tácticos para la Segunda Vuelta, evadiendo el *Rate Limiting* (Errores 429) y recuperando enlaces mediante indexación negativa en expresiones regulares.
3. **Fase 3 (Auditoría Forense):** Cruza el total de mesas instaladas vs mesas escrutadas. Discrimina los faltantes del exterior (Consulados/Departamento 88) y exporta un reporte `.csv` con las anomalías nacionales.

## Despliegue y Ejecución

### Correr el servidor localmente

1. Instala las dependencias del servidor web:
```bash
pip install -r requirements.txt

```

2. Arranca el servidor local con Uvicorn:

```bash
uvicorn main:app --reload

```

3. Abre `http://localhost:8000` en tu navegador web.

### Actualización de Datos en Producción (Railway)

1. Descarga manualmente los archivos `allTransmissionCodes.json` más recientes desde el portal de la Registraduría y guárdalos en `/datos_crudos/` como `delegados_v1.json` y `delegados_v2.json`.
2. Ejecuta el pipeline ETL para actualizar tus bases de datos `.db` locales:

```bash
python indexador_maestro.py

```

*(Nota: Para ejecutar este script necesitas instalar localmente `requests` y `tqdm`).*
3. Haz commit y empuja los cambios a GitHub:

```bash
git add .
git commit -m "Actualización de mesas escrutadas"
git push origin main

```

4. **Railway** detectará el nuevo *commit*, extraerá únicamente los `.db` actualizados y el `main.py`, y redesplegará la aplicación automáticamente sin tiempos de caída.

## Fuentes de Datos

Los datos son extraídos e indexados directamente de los portales oficiales de la Registraduría Nacional del Estado Civil de Colombia:

* **Visor Delegados Primera Vuelta:** `divulgacione14presidente.registraduria.gov.co`
* **Visor Delegados Segunda Vuelta:** `e14segundavueltapresidente.registraduria.gov.co`
* **Visor de Escrutinios Primera Vuelta:** `escrutiniospresidente2026.registraduria.gov.co`
* **Visor de Escrutinios Segunda Vuelta:** `https://escrutinios2vueltapresidente2026.registraduria.gov.co`

```

