#!/usr/bin/env python3
"""
e14_indexar.py  v2
==================
Descarga el allTransmissionCodes.json en streaming (chunk a chunk),
lo guarda localmente y luego construye la base de datos SQLite.

Si la descarga ya fue hecha antes (existe el .json local), la omite
y va directo a construir la DB — útil si se interrumpe a mitad.

Requisitos: pip install requests tqdm
"""

import requests
import json
import sqlite3
from pathlib import Path

JSON_URL = (
    "https://divulgacione14presidente.registraduria.gov.co"
    "/assets/temis/divipol_json/allTransmissionCodes.json"
)

# ⚠️ Ajusta BASE_PDF con la URL que veas al hacer "Descargar Acta" en el portal
BASE_PDF = (
    "https://divulgacione14presidente.registraduria.gov.co"
    "/assets/temis/pdf_files"
)

JSON_LOCAL = Path("allTransmissionCodes.json")
DB_PATH    = Path("e14_index.db")

DEPARTAMENTOS = {
    "01": "Bogotá D.C.",        "05": "Antioquia",
    "08": "Atlántico",          "11": "Bogotá D.C.",
    "13": "Bolívar",            "15": "Boyacá",
    "17": "Caldas",             "18": "Caquetá",
    "19": "Cauca",              "20": "Cesar",
    "23": "Córdoba",            "25": "Cundinamarca",
    "27": "Chocó",              "41": "Huila",
    "44": "La Guajira",         "47": "Magdalena",
    "50": "Meta",               "52": "Nariño",
    "54": "N. de Santander",    "63": "Quindío",
    "66": "Risaralda",          "68": "Santander",
    "70": "Sucre",              "73": "Tolima",
    "76": "Valle del Cauca",    "81": "Arauca",
    "85": "Casanare",           "86": "Putumayo",
    "88": "Archipiélagos",      "91": "Amazonas",
    "94": "Guainía",            "95": "Guaviare",
    "97": "Vaupés",             "99": "Vichada",
}

STATUS_LABELS = {3: "Transmitida", 11: "Con novedad"}

# ─── PASO 1: Descarga en streaming ───────────────────────────────────────────

def descargar_json():
    if JSON_LOCAL.exists():
        size_mb = JSON_LOCAL.stat().st_size / 1024 / 1024
        print(f"ℹ️  Archivo local encontrado ({size_mb:.1f} MB). Omitiendo descarga.")
        return

    print("📥 Descargando allTransmissionCodes.json en streaming...")
    print("   (archivo grande ~30-80 MB, puede tomar varios minutos)\n")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, */*",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }

    # Sin timeout de lectura (None) — el archivo puede ser muy grande
    with requests.get(JSON_URL, headers=headers, stream=True, timeout=(15, None)) as r:
        r.raise_for_status()

        total = int(r.headers.get("Content-Length", 0))
        descargado = 0
        CHUNK = 1024 * 512  # 512 KB por chunk

        with open(JSON_LOCAL, "wb") as f:
            for chunk in r.iter_content(chunk_size=CHUNK):
                if chunk:
                    f.write(chunk)
                    descargado += len(chunk)
                    if total:
                        pct = descargado / total * 100
                        mb  = descargado / 1024 / 1024
                        print(f"\r   {pct:5.1f}%  ({mb:.1f} MB)", end="", flush=True)
                    else:
                        mb = descargado / 1024 / 1024
                        print(f"\r   {mb:.1f} MB descargados...", end="", flush=True)

    size_mb = JSON_LOCAL.stat().st_size / 1024 / 1024
    print(f"\n✅ Guardado: {JSON_LOCAL}  ({size_mb:.1f} MB)")

# ─── PASO 2: Procesar JSON y crear SQLite ────────────────────────────────────

def construir_db():
    print("\n⚙️  Leyendo JSON y construyendo base de datos...")

    with open(JSON_LOCAL, encoding="utf-8") as f:
        raw = json.load(f)

    mesas = []
    for status_key, status_val in raw["data"].items():
        for nodo in status_val.get("nodes", []):
            mesas.append(nodo)

    print(f"   Mesas encontradas: {len(mesas):,}")

    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS mesas (
            idTransmissionCode  TEXT PRIMARY KEY,
            numberStand         TEXT,
            expectedName        TEXT,
            status              INTEGER,
            status_label        TEXT,
            idCorporationCode   TEXT,
            idStand             TEXT,
            standCode           TEXT,
            idZoneCode          TEXT,
            idDepartmentCode    TEXT,
            municipalityCode    TEXT,
            departamento        TEXT,
            url_pdf             TEXT
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_code ON mesas(idTransmissionCode)")

    registros = []
    for m in mesas:
        depto    = DEPARTAMENTOS.get(m.get("idDepartmentCode", ""), "Desconocido")
        status   = m.get("idTransmissionCodeStatus", 0)
        expected = m.get("expectedName", "")
        url_pdf  = f"{BASE_PDF}/{expected}" if expected else ""
        registros.append((
            m.get("idTransmissionCode"),
            m.get("numberStand"),
            expected,
            status,
            STATUS_LABELS.get(status, str(status)),
            m.get("idCorporationCode"),
            m.get("idStand"),
            m.get("standCode"),
            m.get("idZoneCode"),
            m.get("idDepartmentCode"),
            m.get("municipalityCode"),
            depto,
            url_pdf,
        ))

    con.executemany(
        "INSERT OR REPLACE INTO mesas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        registros,
    )
    con.commit()

    size_kb = DB_PATH.stat().st_size / 1024
    print(f"✅ Base de datos creada: {DB_PATH}  ({size_kb:.0f} KB)")
    print(f"   Total mesas indexadas: {len(registros):,}")
    con.close()

# ─── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    descargar_json()
    construir_db()
    print("\n🎉 ¡Listo! Ahora corre:  python e14_buscar.py")
    print("   O borra allTransmissionCodes.json para liberar espacio")
    print("   (la DB SQLite ya tiene todo lo necesario)")
