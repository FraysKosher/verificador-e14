# Verificador E-14 — Presidenciales Colombia 2026

Herramienta de verificación ciudadana de actas E-14.
Permite buscar cualquier formulario por su código de transmisión
(el número impreso como `X 5-57-43-15 X`) o por ubicación geográfica.

## Archivos

| Archivo | Descripción |
|---|---|
| `main.py` | Servidor FastAPI |
| `e14_index.db` | Base de datos SQLite con 122,002 mesas |
| `requirements.txt` | Dependencias Python |
| `Procfile` | Comando de arranque para Railway |

## Correr localmente

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Abre http://localhost:8000

## Desplegar en Railway

1. Subir este repositorio a GitHub
2. En railway.app: New Project → Deploy from GitHub repo
3. Seleccionar el repositorio
4. Railway detecta todo automáticamente

## Fuente de datos

Registraduría Nacional del Estado Civil de Colombia  
https://divulgacione14presidente.registraduria.gov.co
