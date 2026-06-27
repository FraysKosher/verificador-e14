#!/usr/bin/env python3
"""
indexador_maestro.py
====================
Pipeline ETL definitivo con Concurrencia Dinámica y Transparencia HTTP.
"""

import sqlite3
import requests
import json
import time
import threading
import re
import os
import sys
import csv
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tqdm import tqdm

# ==========================================
# CONFIGURACIÓN MAESTRA (Concurrencia Dinámica)
# ==========================================
CONFIG = {
    1: {
        "nombre": "Primera Vuelta Presidencial 2026",
        "pdf_delegados": "https://divulgacione14presidente.registraduria.gov.co/assets/temis/pdf_files",
        "url_claveros_idx": "https://escrutiniospresidente2026.registraduria.gov.co/data/index.json",
        "url_claveros_base": "https://escrutiniospresidente2026.registraduria.gov.co/",
        "db_file": "bases_de_datos/presidente2026_v1.db",
        "json_file": "datos_crudos/delegados_v1.json",
        "csv_faltantes": "datos_crudos/faltantes_v1.csv",
        "workers": 40  # Alta velocidad para caché fuerte
    },
    2: {
        "nombre": "Segunda Vuelta Presidencial 2026",
        "pdf_delegados": "https://e14segundavueltapresidente.registraduria.gov.co/assets/temis/pdf_files",
        "url_claveros_idx": "https://escrutinios2vueltapresidente2026.registraduria.gov.co/data/index.json",
        "url_claveros_base": "https://escrutinios2vueltapresidente2026.registraduria.gov.co/",
        "db_file": "bases_de_datos/presidente2026_v2.db",
        "json_file": "datos_crudos/delegados_v2.json",
        "csv_faltantes": "datos_crudos/faltantes_v2.csv",
        "workers": 15  # Velocidad táctica para evitar bloqueos del WAF
    }
}

DEPARTAMENTOS = {
    "01": "Antioquia",       "03": "Atlántico",      "05": "Bolívar",         "07": "Boyacá",
    "09": "Caldas",          "11": "Cauca",          "12": "Cesar",           "13": "Córdoba",
    "15": "Cundinamarca",    "16": "Bogotá D.C.",    "17": "Chocó",           "19": "Huila",
    "21": "Magdalena",       "23": "Nariño",         "24": "Risaralda",       "25": "Norte de Santander",
    "26": "Quindío",         "27": "Santander",      "28": "Sucre",           "29": "Tolima",
    "31": "Valle del Cauca", "40": "Arauca",         "44": "Caquetá",         "46": "Casanare",
    "48": "La Guajira",      "50": "Guainía",        "52": "Meta",            "54": "Guaviare",
    "56": "San Andrés",      "60": "Amazonas",       "64": "Putumayo",        "68": "Vaupés",
    "72": "Vichada",         "88": "Consulados",
}

thread_local = threading.local()
telemetria = {"ok": 0, "timeout": 0, "http_error": 0, "regex_fail": 0}
telemetria_lock = threading.Lock()

def crear_carpetas():
    Path("bases_de_datos").mkdir(exist_ok=True)
    Path("datos_crudos").mkdir(exist_ok=True)

def get_session(max_workers):
    """Genera una sesión transparente sin enmascaramiento para evitar bloqueos TLS."""
    if not hasattr(thread_local, "session"):
        s = requests.Session()
        
        # Backoff más largo (1.0) para darle respiro real al servidor si nos frena
        retries = Retry(
            total=5, 
            backoff_factor=1.0, 
            status_forcelist=[429, 500, 502, 503, 504]
        )
        
        adapter = HTTPAdapter(max_retries=retries, pool_connections=max_workers, pool_maxsize=max_workers)
        s.mount('https://', adapter)
        s.mount('http://', adapter)
        
        # Cero headers sintéticos. Regresamos al comportamiento exitoso del script original.
        thread_local.session = s
    return thread_local.session

# ==========================================
# FASE 1: DELEGADOS
# ==========================================
def fase_1_delegados(cfg):
    json_path = Path(cfg["json_file"])
    db_path = Path(cfg["db_file"])
    print(f"\n--- FASE 1: PRECONTEO DELEGADOS ({cfg['nombre']}) ---")
    
    if not json_path.exists():
        print(f"❌ ERROR: No se encontró {json_path}")
        sys.exit(1)

    print(f"📂 Cargando JSON local {json_path.name}...")
    with open(json_path, encoding="utf-8") as f:
        raw = json.load(f)

    mesas = [nodo for status_val in raw["data"].values() for nodo in status_val.get("nodes", [])]
    
    con = sqlite3.connect(db_path)
    cursor = con.cursor()
    cursor.execute("PRAGMA journal_mode = WAL;")
    cursor.execute("PRAGMA synchronous = OFF;")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mesas (
            idTransmissionCode TEXT PRIMARY KEY, numberStand TEXT, expectedName TEXT,
            status INTEGER, status_label TEXT, idCorporationCode TEXT,
            idStand TEXT, standCode TEXT, idZoneCode TEXT, idDepartmentCode TEXT,
            municipalityCode TEXT, departamento TEXT, url_pdf TEXT, url_claveros TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metadata_auditoria (
            fecha_ejecucion TEXT, etapa TEXT, delegados INT, claveros INT, faltantes INT, estado TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_code ON mesas(idTransmissionCode)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_mesas_native ON mesas(idDepartmentCode, municipalityCode, idZoneCode, standCode, numberStand)")

    registros = []
    for m in mesas:
        depto = DEPARTAMENTOS.get(m.get("idDepartmentCode", ""), "Desconocido")
        expected = m.get("expectedName", "")
        url_pdf = f"{cfg['pdf_delegados']}/{expected}" if expected else ""
        registros.append((
            m.get("idTransmissionCode"), m.get("numberStand"), expected, m.get("idTransmissionCodeStatus", 0),
            "Transmitida" if m.get("idTransmissionCodeStatus") == 3 else "Con Novedad",
            m.get("idCorporationCode"), m.get("idStand"), m.get("standCode"), m.get("idZoneCode"),
            m.get("idDepartmentCode"), m.get("municipalityCode"), depto, url_pdf
        ))

    cursor.execute("BEGIN TRANSACTION;")
    for i in tqdm(range(0, len(registros), 5000), desc="Guardando registros base", unit="lote"):
        lote = registros[i:i+5000]
        cursor.executemany("""
            INSERT INTO mesas 
            (idTransmissionCode, numberStand, expectedName, status, status_label, idCorporationCode, 
             idStand, standCode, idZoneCode, idDepartmentCode, municipalityCode, departamento, url_pdf) 
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(idTransmissionCode) DO UPDATE SET 
                expectedName = excluded.expectedName,
                status = excluded.status,
                status_label = excluded.status_label,
                url_pdf = excluded.url_pdf
        """, lote)
    
    con.commit()
    con.close()
    print(f"✅ Fase 1 completada con éxito. {len(registros)} mesas base consolidadas.")

# ==========================================
# FASE 2: CLAVEROS
# ==========================================
def procesar_puesto_claveros(url_puesto, base_url, max_workers):
    global telemetria
    
    try:
        # Aumentamos ligeramente la paciencia de lectura para los hilos controlados
        r = get_session(max_workers).get(url_puesto, timeout=(4.0, 15.0))
        if r.status_code != 200:
            with telemetria_lock: telemetria["http_error"] += 1
            return []
        mesas_puesto = r.json()
    except requests.exceptions.Timeout:
        with telemetria_lock: telemetria["timeout"] += 1
        return []
    except Exception:
        with telemetria_lock: telemetria["http_error"] += 1
        return [] 
    
    actualizaciones = []
    regex_ok = False
    
    for mesa_info in mesas_puesto:
        ruta_pdf_cruda = mesa_info.get("nombre_archivo", "")
        if ruta_pdf_cruda:
            url_final = f"{base_url[:-1]}{ruta_pdf_cruda}"
            nombre_pdf = ruta_pdf_cruda.split('/')[-1]
            match = re.search(r'E14_PRE_(\d+)_(\d+)_(\d+)_(\d+)_(\d+)_(\d+)', nombre_pdf)
            
            if match:
                regex_ok = True
                actualizaciones.append((url_final, match.group(1).zfill(2), match.group(2).zfill(3), 
                                      match.group(3)[-2:], match.group(5).zfill(2), match.group(6).zfill(3)))
            else:
                partes = [p for p in ruta_pdf_cruda.split('/') if p]
                if len(partes) >= 5:
                    regex_ok = True
                    try:
                        depto    = partes[-5].zfill(2)
                        mpio     = partes[-4].zfill(3)
                        zona     = partes[-3][-2:] 
                        puesto   = partes[-2].zfill(2)
                        num_mesa = str(mesa_info.get("numero", "")).zfill(3)
                        actualizaciones.append((url_final, depto, mpio, zona, puesto, num_mesa))
                    except IndexError:
                        continue
    
    with telemetria_lock:
        if regex_ok:
            telemetria["ok"] += 1
        elif len(mesas_puesto) > 0:
            telemetria["regex_fail"] += 1
            
    return actualizaciones

def fase_2_claveros(cfg):
    global telemetria
    telemetria = {"ok": 0, "timeout": 0, "http_error": 0, "regex_fail": 0}
    max_w = cfg["workers"]
    
    print(f"\n--- FASE 2: ESCRUTINIOS CLAVEROS ({cfg['nombre']}) ---")
    print(f"⚙️  Concurrencia asignada: {max_w} hilos")
    
    con = sqlite3.connect(cfg["db_file"])
    cursor = con.cursor()
    
    print("🌐 Conectando al índice maestro de Claveros...")
    try:
        index_data = get_session(max_w).get(cfg["url_claveros_idx"], timeout=15).json()
    except Exception as e:
        print(f"❌ ERROR CRÍTICO al descargar el índice central: {e}")
        con.close()
        return

    rutas_mesas = [f"{cfg['url_claveros_base']}{r}{a}" for r, a in index_data.items() if "actas-documentos/" in r and "/mesas/" in r]
    
    actualizaciones = []
    with ThreadPoolExecutor(max_workers=max_w) as executor:
        futuros = {executor.submit(procesar_puesto_claveros, url, cfg["url_claveros_base"], max_w): url for url in rutas_mesas}
        
        for futuro in tqdm(as_completed(futuros), total=len(rutas_mesas), desc="Descargando endpoints", unit="puesto"):
            if res := futuro.result(): 
                actualizaciones.extend(res)

    print(f"💾 Guardando {len(actualizaciones)} enlaces mapeados en la base de datos...")
    cursor.execute("BEGIN TRANSACTION;")
    cursor.executemany("""
        UPDATE mesas 
        SET url_claveros = ? 
        WHERE idDepartmentCode = ? AND municipalityCode = ? AND idZoneCode = ? AND standCode = ? AND numberStand = ?
    """, actualizaciones)
    
    filas_afectadas = cursor.rowcount
    con.commit()
    con.close()
    
    print(f"✅ FASE 2 FINALIZADA. (URLs Procesadas: {len(actualizaciones)} | Filas DB Impactadas: {filas_afectadas})")
    print(f"🔍 TELEMETRÍA DE RED & EXTRACCIÓN:")
    print(f"   - Conexiones Exitosas     : {telemetria['ok']}")
    print(f"   - Hilos Caídos por Timeout: {telemetria['timeout']}")
    print(f"   - Errores HTTP (Bloqueos) : {telemetria['http_error']}")
    print(f"   - Fallos de Mapeo (Regex) : {telemetria['regex_fail']}")

# ==========================================
# FASE 3: AUDITORÍA FORENSE AUTOMÁTICA
# ==========================================
def fase_3_validacion(cfg):
    print(f"\n--- FASE 3: AUDITORÍA FORENSE AUTOMÁTICA ({cfg['nombre']}) ---")
    con = sqlite3.connect(cfg["db_file"])
    cursor = con.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM mesas")
    total_delegados = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM mesas WHERE url_claveros IS NOT NULL")
    total_claveros = cursor.fetchone()[0]
    
    total_sin_claveros = total_delegados - total_claveros
    cobertura = (total_claveros / total_delegados) * 100 if total_delegados > 0 else 0
    
    cursor.execute("""
        SELECT idDepartmentCode, departamento, COUNT(*) 
        FROM mesas 
        WHERE url_claveros IS NULL 
        GROUP BY idDepartmentCode, departamento 
        ORDER BY COUNT(*) DESC
    """)
    faltantes_agrupados = cursor.fetchall()
    
    consulados_count = next((f[2] for f in faltantes_agrupados if f[0] == '88'), 0)
    otros_count = total_sin_claveros - consulados_count
    
    print("\n================ RESUMEN DE CONTROL ================")
    print(f"  Preconteo Base (Total Mesas) : {total_delegados}")
    print(f"  Escrutinio Base (Indexadas)  : {total_claveros}")
    print(f"  Tasa de Cobertura Final      : {cobertura:.2f}%")
    print("----------------------------------------------------")
    print(f"  Ausencias Esperadas (Consulados) : {consulados_count}")
    print(f"  Anomalías Detectadas (Nacionales): {otros_count}")
    print("====================================================\n")
    
    if total_sin_claveros > 0:
        if otros_count == 0:
            estado_certificacion = "OK_CON_CONSULADOS"
            print("✅ CERTIFICACIÓN FORENSE: INTEGRIDAD VALIDADA (Faltantes exclusivos del Exterior/Consulados)")
        else:
            estado_certificacion = "ADVERTENCIA_FALTANTES"
            print("⚠️ ALERTAS FORENSES DETECTADAS (Mesas nacionales sin documento de escrutinio):")
            for d in faltantes_agrupados:
                print(f"   - {d[1]} (ID {d[0]}): {d[2]} mesas huérfanas")
            
            cursor.execute("""
                SELECT idDepartmentCode, departamento, municipalityCode, idZoneCode, standCode, numberStand 
                FROM mesas 
                WHERE url_claveros IS NULL AND idDepartmentCode != '88'
            """)
            mesas_huerfanas = cursor.fetchall()
            
            if mesas_huerfanas:
                csv_path = cfg['csv_faltantes']
                with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(['DepartamentoID', 'Departamento', 'Municipio', 'Zona', 'Puesto', 'Mesa'])
                    writer.writerows(mesas_huerfanas)
                print(f"\n📂 Registro detallado exportado a: {csv_path}")
    else:
        estado_certificacion = "OK_100_PORCIENTO"
        print("✅ CERTIFICACIÓN FORENSE: COBERTURA TOTAL ABSOLUTA (100% Indexado)")
        
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO metadata_auditoria (fecha_ejecucion, etapa, delegados, claveros, faltantes, estado)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (fecha_actual, cfg['nombre'], total_delegados, total_claveros, total_sin_claveros, estado_certificacion))
    con.commit()
    con.close()

# ==========================================
# PUNTO DE ENTRADA
# ==========================================
if __name__ == "__main__":
    crear_carpetas()
    print("========================================")
    print("  🗳️ INDEXADOR MAESTRO E-14 (2026)")
    print("========================================")
    print("1. Procesar Primera Vuelta")
    print("2. Procesar Segunda Vuelta")
    print("3. Procesar AMBAS Vueltas")
    opcion = input("Selecciona una opción de ejecución (1/2/3): ").strip()
    
    vueltas_a_procesar = [1, 2] if opcion == "3" else [int(opcion)] if opcion in ["1", "2"] else []
    
    if not vueltas_a_procesar:
        print("❌ Opción no válida. Abortando pipeline.")
    else:
        for v in vueltas_a_procesar:
            fase_1_delegados(CONFIG[v])
            fase_2_claveros(CONFIG[v])
            fase_3_validacion(CONFIG[v])
        print("\n🎉 Pipeline de auditoría finalizado por completo.")