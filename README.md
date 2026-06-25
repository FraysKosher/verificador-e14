
# Verificador E-14 — Presidenciales Colombia 2026 (1ra y 2da Vuelta)

Herramienta de verificación ciudadana independiente de actas E-14.
Permite buscar cualquier formulario oficial por su código de transmisión (el número impreso como `X 5-57-43-15 X`) o por ubicación geográfica. Esta versión unificada integra los datos tanto de la primera como de la segunda vuelta electoral en una sola interfaz.

## Archivos Principales

| Archivo | Descripción |
|---|---|
| `main.py` | Servidor FastAPI con la interfaz frontend y selector unificado de vueltas. |
| `e14_index.db` | Base de datos SQLite - Primera Vuelta (122,016 actas). |
| `e14_index_2Vuelta.db` | Base de datos SQLite - Segunda Vuelta (122,019 actas). |
| `e14_indexar*.py` | Scripts locales de Python para procesar los JSON y construir las bases de datos. |
| `requirements.txt` | Dependencias de Python (`fastapi`, `uvicorn`, etc.). |
| `Procfile` / `nixpacks.toml` | Archivos de configuración para el despliegue automático en Railway. |

## Correr localmente

1. Instala las dependencias necesarias:
```bash
pip install -r requirements.txt

```

2. Arranca el servidor local con Uvicorn:

```bash
uvicorn main:app --reload

```

3. Abre [http://localhost:8000](https://www.google.com/search?q=http://localhost:8000) en tu navegador web.

## ¿Cómo actualizar la base de datos en producción?

Debido a las protecciones de seguridad (WAF/Cloudflare) en los servidores de la Registraduría, la actualización de datos se realiza localmente para evitar bloqueos por IP en la nube:

1. Descarga manualmente los archivos `allTransmissionCodes.json` más recientes desde el portal oficial.
2. Ejecuta los indexadores locales para actualizar tus archivos `.db`:
```bash
python e14_indexar.py
python e14_indexar_2Vuelta.py

```


3. Haz commit y empuja los cambios a GitHub:
```bash
git add .
git commit -m "Actualización de mesas escrutadas"
git push origin main

```


4. **Railway** detectará el nuevo *commit*, descargará las bases de datos actualizadas y redesplegará la aplicación automáticamente sin tiempos de caída.

## Fuentes de Datos

Los datos son extraídos e indexados directamente de los portales oficiales de la Registraduría Nacional del Estado Civil de Colombia:

* **Primera Vuelta:** [divulgacione14presidente.registraduria.gov.co](https://divulgacione14presidente.registraduria.gov.co)
* **Segunda Vuelta:** [e14segundavueltapresidente.registraduria.gov.co](https://e14segundavueltapresidente.registraduria.gov.co)

