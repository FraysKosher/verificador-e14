#!/usr/bin/env python3
"""
main.py — Verificador E-14 Presidenciales 2026 (Unificado 1ra y 2da Vuelta)
Servidor FastAPI + Uvicorn, listo para Railway
"""

import sqlite3
import os
from pathlib import Path
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Verificador E-14", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# --- CONFIGURACIÓN DE VUELTAS ---
VUELTAS = {
    1: {
        "db": os.environ.get("DB_PATH_V1", "e14_index.db"),
        "url": "https://divulgacione14presidente.registraduria.gov.co"
    },
    2: {
        "db": os.environ.get("DB_PATH_V2", "e14_index_2Vuelta.db"),
        "url": "https://e14segundavueltapresidente.registraduria.gov.co"
    }
}

DEPARTAMENTOS = {
    "01": "Antioquia",       "03": "Atlántico",
    "05": "Bolívar",         "07": "Boyacá",
    "09": "Caldas",          "11": "Cauca",
    "12": "Cesar",           "13": "Córdoba",
    "15": "Cundinamarca",    "16": "Bogotá D.C.",
    "17": "Chocó",           "19": "Huila",
    "21": "Magdalena",       "23": "Nariño",
    "24": "Risaralda",       "25": "Norte de Santander",
    "26": "Quindío",         "27": "Santander",
    "28": "Sucre",           "29": "Tolima",
    "31": "Valle del Cauca", "40": "Arauca",
    "44": "Caquetá",         "46": "Casanare",
    "48": "La Guajira",      "50": "Guainía",
    "52": "Meta",            "54": "Guaviare",
    "56": "San Andrés",      "60": "Amazonas",
    "64": "Putumayo",        "68": "Vaupés",
    "72": "Vichada",         "88": "Consulados",
}

COLS = ["idTransmissionCode","numberStand","expectedName","status",
        "status_label","idCorporationCode","idStand","standCode",
        "idZoneCode","idDepartmentCode","municipalityCode","departamento","url_pdf"]

# Conexión dinámica dependiendo de la vuelta
def get_conn(vuelta: int):
    if vuelta not in VUELTAS:
        raise HTTPException(400, "Vuelta no válida.")
    
    db_path = VUELTAS[vuelta]["db"]
    if not Path(db_path).exists():
        raise HTTPException(500, f"No se encontró la base de datos de la vuelta {vuelta} ({db_path}).")
        
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

def formatear_codigo(codigo: str) -> str:
    c = str(codigo).zfill(7)
    return f"{c[0]}-{c[1:3]}-{c[3:5]}-{c[5:7]}"

def construir_url_pdf(r: dict, vuelta: int) -> str:
    base = f"{VUELTAS[vuelta]['url']}/assets/temis/pdf"
    depto  = r["idDepartmentCode"].zfill(2)
    mpio   = r["municipalityCode"].zfill(3)
    zona   = r["idZoneCode"].zfill(3)
    puesto = r["standCode"].zfill(2)
    mesa   = r["numberStand"].zfill(3)
    return f"{base}/{depto}/{mpio}/{zona}/{puesto}/{mesa}/PRE/{r['expectedName']}"

def enriquecer(row, vuelta: int) -> dict:
    r = dict(row)
    r["depto_nombre"]      = DEPARTAMENTOS.get(r["idDepartmentCode"], f"Código {r['idDepartmentCode']}")
    r["codigo_formateado"] = formatear_codigo(r["idTransmissionCode"])
    r["url_pdf_directa"]   = construir_url_pdf(r, vuelta)
    r["url_visor_oficial"] = VUELTAS[vuelta]['url']
    return r

# ── Rutas API ─────────────────────────────────────────────────────────────────

@app.get("/api/buscar")
def buscar_codigo(
    codigo: str = Query(..., description="Código de transmisión"),
    vuelta: int = Query(2, description="Vuelta electoral (1 o 2)")
):
    codigo_norm = codigo.replace("-", "").replace(" ", "").strip()
    if not codigo_norm:
        raise HTTPException(400, "Código vacío")
    try:
        con = get_conn(vuelta)
        row = con.execute(
            "SELECT * FROM mesas WHERE idTransmissionCode = ?", (codigo_norm,)
        ).fetchone()
        con.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error de base de datos: {e}")
        
    if not row:
        return JSONResponse({"error": f"El código '{codigo}' no se encontró en la vuelta {vuelta}."})
    return enriquecer(row, vuelta)

@app.get("/api/lugar")
def buscar_lugar(
    depto:  str = Query(...),
    mpio:   str = Query(...),
    zona:   str = Query(...),
    puesto: str = Query(...),
    mesa:   str = Query(...),
    vuelta: int = Query(2, description="Vuelta electoral (1 o 2)")
):
    try:
        con = get_conn(vuelta)
        rows = con.execute("""
            SELECT * FROM mesas
            WHERE idDepartmentCode=? AND municipalityCode=?
              AND idZoneCode=? AND standCode=? AND numberStand=?
        """, (depto.zfill(2), mpio.zfill(3), zona.zfill(2),
              puesto.zfill(2), mesa.zfill(3))).fetchall()
        con.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error de base de datos: {e}")
        
    if not rows:
        return JSONResponse({"error": f"No se encontró ninguna mesa con esos datos en la vuelta {vuelta}."})
    return [enriquecer(r, vuelta) for r in rows]

# ── Frontend ──────────────────────────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Verificador E-14 — Presidenciales Colombia 2026</title>
<style>
  :root {
    --bg: #f4f6f8; 
    --surface: #ffffff; 
    --border: #dce1e6;
    --text: #1f2937; 
    --muted: #6b7280; 
    --faint: #9ca3af;
    --primary: #0f766e; 
    --primary-hover: #115e59;
    --radius: 12px; 
    --shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    background: var(--bg); color: var(--text); min-height: 100vh;
    display: flex; flex-direction: column; align-items: center; padding: 2.5rem 1rem;
  }
  header { text-align: center; margin-bottom: 2rem; }
  header .logo { font-size: 2.5rem; margin-bottom: 0.5rem; }
  header h1 { font-size: 1.75rem; font-weight: 800; letter-spacing: -0.025em; margin-bottom: 0.3rem; color: #111827; }
  header p { color: var(--muted); font-size: 0.95rem; }
  
  .card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); box-shadow: var(--shadow);
    padding: 2rem; width: 100%; max-width: 600px; margin-bottom: 1.5rem;
  }
  
  /* Selector Unificado Moderno (Segmented Control) */
  .vuelta-selector {
    display: flex; background: #e5e7eb; border-radius: 8px; padding: 4px; margin-bottom: 1.5rem;
  }
  .vuelta-selector input { display: none; }
  .vuelta-selector label {
    flex: 1; text-align: center; padding: 0.6rem; cursor: pointer;
    font-weight: 600; color: var(--muted); font-size: 0.9rem;
    border-radius: 6px; transition: all 0.2s ease; margin: 0;
  }
  .vuelta-selector input:checked + label {
    background: var(--surface); color: var(--primary); box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  }

  .tabs { display: flex; gap: 0.75rem; margin-bottom: 1.5rem; }
  .tab {
    flex: 1; padding: 0.7rem 1rem; border: 1px solid var(--border);
    border-radius: 8px; background: #f9fafb; color: var(--muted);
    font-size: 0.9rem; font-weight: 600; cursor: pointer; transition: all 0.2s;
  }
  .tab.active { border-color: var(--primary); color: var(--primary); background: #f0fdfa; }
  .tab:hover:not(.active) { background: #f3f4f6; color: var(--text); }
  .panel { display: none; } .panel.active { display: block; }
  
  label.input-label {
    display: block; font-size: 0.75rem; font-weight: 700; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem;
  }
  input[type="text"] {
    width: 100%; padding: 0.8rem 1rem; border: 1px solid #d1d5db;
    border-radius: 8px; font-size: 1rem; color: var(--text);
    background: #fff; transition: all 0.2s; outline: none; box-shadow: inset 0 1px 2px rgba(0,0,0,0.02);
  }
  input[type="text"]:focus { border-color: var(--primary); box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.1); }
  input[type="text"]::placeholder { color: var(--faint); }
  
  .hint { font-size: 0.8rem; color: var(--faint); margin-top: 0.4rem; }
  .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-top: 1rem; }
  .grid3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1rem; margin-top: 1rem; }
  .field { display: flex; flex-direction: column; }
  
  .btn-buscar {
    width: 100%; margin-top: 1.5rem; padding: 0.85rem;
    background: var(--primary); color: white; border: none; border-radius: 8px;
    font-size: 1rem; font-weight: 600; cursor: pointer; transition: background 0.2s, transform 0.1s;
    display: flex; align-items: center; justify-content: center; gap: 0.5rem;
    box-shadow: 0 2px 4px rgba(15, 118, 110, 0.2);
  }
  .btn-buscar:hover { background: var(--primary-hover); transform: translateY(-1px); }
  .btn-buscar:active { transform: translateY(0); }
  
  #resultado { display: none; }
  
  /* Tarjetas de resultados estilo profesional (Border acento) */
  .result-card { border-radius: var(--radius); padding: 1.5rem; border: 1px solid var(--border); background: #fff; }
  .result-card.found { border-left: 5px solid #10b981; }
  .result-card.warn { border-left: 5px solid #f59e0b; }
  .result-card.error { border-left: 5px solid #ef4444; }
  
  .result-title { font-size: 1.1rem; font-weight: 700; margin-bottom: 1.2rem; display: flex; align-items: center; gap: 0.5rem; }
  .found .result-title { color: #065f46; }
  .warn .result-title { color: #92400e; }
  .error .result-title { color: #991b1b; }
  
  .result-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem 1.5rem; }
  .result-item { display: flex; flex-direction: column; }
  .result-label { font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }
  .result-value { font-size: 1.05rem; font-weight: 600; color: var(--text); margin-top: 0.15rem; }
  
  .code-big { font-size: 1.5rem; font-weight: 800; color: var(--primary); letter-spacing: 0.05em; margin-bottom: 1.2rem; }
  
  .status-badge {
    display: inline-flex; align-items: center; gap: 0.3rem; padding: 0.25rem 0.75rem;
    border-radius: 99px; font-size: 0.8rem; font-weight: 700; margin-top: 0.15rem; width: fit-content;
  }
  .status-ok { background: #d1fae5; color: #065f46; }
  .status-warn { background: #fef3c7; color: #92400e; }
  
  hr.div { border: none; border-top: 1px solid var(--border); margin: 1.5rem 0; }
  
  .btns { display: flex; gap: 0.75rem; flex-wrap: wrap; margin-top: 1rem; }
  .btn-pdf {
    padding: 0.65rem 1.2rem; border: none; border-radius: 8px;
    font-size: 0.9rem; font-weight: 600; cursor: pointer;
    display: inline-flex; align-items: center; gap: 0.4rem; transition: all 0.2s;
  }
  .btn-dl { background: var(--primary); color: white; box-shadow: 0 2px 4px rgba(15, 118, 110, 0.2); }
  .btn-dl:hover { background: var(--primary-hover); }
  .btn-visor { background: #e5e7eb; color: #374151; }
  .btn-visor:hover { background: #d1d5db; }
  
  .alert-box {
    background: #fffbeb; border-left: 4px solid #f59e0b; color: #92400e;
    padding: 1rem; border-radius: 0 8px 8px 0; font-size: 0.85rem; margin-bottom: 1.5rem; line-height: 1.5;
  }

  .footer-status {
    background: #fff; padding: 1rem; border-radius: 8px; margin-bottom: 1.2rem; 
    border: 1px solid var(--border); color: var(--text); text-align: center; line-height: 1.5;
    box-shadow: 0 1px 3px rgba(0,0,0,0.02);
  }
  footer { color: var(--faint); font-size: 0.85rem; text-align: center; margin-top: 1rem; max-width: 500px; line-height: 1.6; }
  
  .spinner{display:none;width:18px;height:18px;border:2px solid rgba(255,255,255,.4);border-top-color:white;border-radius:50%;animation:spin .6s linear infinite}
  @keyframes spin{to{transform:rotate(360deg)}}
  .loading .spinner{display:inline-block}
  .loading .btn-text{display:none}
</style>
</head>
<body>
<header>
  <div class="logo">🗳️</div>
  <h1>Verificador de Actas E-14</h1>
  <p>Elección Presidencia y Vicepresidencia — Colombia 2026</p>
</header>

<div class="card">
  <!-- Selector Unificado Moderno -->
  <div class="vuelta-selector">
    <input type="radio" id="v1" name="vuelta" value="1" onchange="limpiarResultado()">
    <label for="v1">Primera Vuelta</label>
    
    <input type="radio" id="v2" name="vuelta" value="2" checked onchange="limpiarResultado()">
    <label for="v2">Segunda Vuelta</label>
  </div>

  <div class="tabs">
    <button class="tab active" onclick="switchTab('codigo')">🔢 Por código del PDF</button>
    <button class="tab"        onclick="switchTab('lugar')">📍 Por ubicación</button>
  </div>

  <div id="panel-codigo" class="panel active">
    <form onsubmit="buscarCodigo(event)">
      <label class="input-label">Código de transmisión</label>
      <input id="inp-codigo" type="text" placeholder="Ej: 6-45-25-18 o 6452518" autocomplete="off" spellcheck="false"/>
      <p class="hint">Es el número impreso en el formulario como X 6-45-25-18 X</p>
      <button type="submit" class="btn-buscar">
        <div class="spinner"></div>
        <span class="btn-text">🔍 Buscar Acta</span>
      </button>
    </form>
  </div>

  <div id="panel-lugar" class="panel">
    <form onsubmit="buscarLugar(event)">
      <div class="grid2">
        <div class="field"><label class="input-label">Departamento</label>
          <input id="l-dep" type="text" placeholder="Ej: 16" maxlength="4"/></div>
        <div class="field"><label class="input-label">Municipio</label>
          <input id="l-mpio" type="text" placeholder="Ej: 001" maxlength="4"/></div>
      </div>
      <div class="grid3">
        <div class="field"><label class="input-label">Zona</label>
          <input id="l-zona" type="text" placeholder="Ej: 20" maxlength="4"/></div>
        <div class="field"><label class="input-label">Puesto</label>
          <input id="l-puesto" type="text" placeholder="Ej: 03" maxlength="4"/></div>
        <div class="field"><label class="input-label">Mesa</label>
          <input id="l-mesa" type="text" placeholder="Ej: 001" maxlength="4"/></div>
      </div>
      <p class="hint" style="margin-top:.75rem">Datos tal como aparecen en el encabezado del E-14</p>
      <button type="submit" class="btn-buscar">
        <div class="spinner"></div>
        <span class="btn-text">🔍 Buscar Acta</span>
      </button>
    </form>
  </div>
</div>

<div class="card" id="resultado">
  <div id="resultado-inner"></div>
</div>

<footer>
  <div class="footer-status">
    <strong style="color: var(--primary);">📊 Estado de indexación (Total nacional: 122.020 mesas)</strong><br>
    <div style="margin-top: 0.5rem;">
      Primera Vuelta: <b>122.016</b> actas procesadas<br>
      Segunda Vuelta: <b>122.019</b> actas procesadas
    </div>
  </div>
  Fuente: Registraduría Nacional del Estado Civil.<br>
  Herramienta de verificación ciudadana independiente.
</footer>

<script>
function switchTab(tab) {
  document.querySelectorAll('.tab').forEach((t,i) => {
    t.classList.toggle('active', (i===0&&tab==='codigo')||(i===1&&tab==='lugar'));
  });
  document.getElementById('panel-codigo').classList.toggle('active', tab==='codigo');
  document.getElementById('panel-lugar').classList.toggle('active',  tab==='lugar');
  limpiarResultado();
}

function limpiarResultado() {
  document.getElementById('resultado').style.display = 'none';
}

function setLoading(btn, on) {
  btn.classList.toggle('loading', on);
  btn.disabled = on;
}

function getVueltaSeleccionada() {
  return document.querySelector('input[name="vuelta"]:checked').value;
}

async function buscarCodigo(e) {
  e.preventDefault();
  const btn = e.target.querySelector('button');
  const codigo = document.getElementById('inp-codigo').value.trim();
  const vuelta = getVueltaSeleccionada();
  
  if (!codigo) return;
  setLoading(btn, true);
  try {
    const r = await fetch(`/api/buscar?codigo=${encodeURIComponent(codigo)}&vuelta=${vuelta}`);
    mostrarResultado(await r.json(), vuelta);
  } finally { setLoading(btn, false); }
}

async function buscarLugar(e) {
  e.preventDefault();
  const btn = e.target.querySelector('button');
  const vuelta = getVueltaSeleccionada();
  
  const p = new URLSearchParams({
    depto:  document.getElementById('l-dep').value.trim(),
    mpio:   document.getElementById('l-mpio').value.trim(),
    zona:   document.getElementById('l-zona').value.trim(),
    puesto: document.getElementById('l-puesto').value.trim(),
    mesa:   document.getElementById('l-mesa').value.trim(),
    vuelta: vuelta
  });
  
  setLoading(btn, true);
  try {
    const r = await fetch('/api/lugar?' + p);
    const data = await r.json();
    mostrarResultado(Array.isArray(data) ? data[0] : data, vuelta);
  } finally { setLoading(btn, false); }
}

function mostrarResultado(data, vuelta) {
  const box   = document.getElementById('resultado');
  const inner = document.getElementById('resultado-inner');
  box.style.display = 'block';
  box.scrollIntoView({behavior:'smooth', block:'start'});

  if (data.error) {
    inner.innerHTML = `
      <div class="result-card error">
        <div class="result-title">❌ No encontrado</div>
        <p style="color:#991b1b;font-size:.95rem;font-weight:500;">${data.error}</p>
        <p style="color:#b91c1c;font-size:.85rem;margin-top:.75rem;line-height:1.4;">
          Verifica que la vuelta seleccionada sea correcta. Si el código proviene de redes, 
          puede indicar que el número fue alterado o es falso.
        </p>
      </div>`;
    return;
  }

  const isOk = data.status === 11;
  const cardClass   = isOk ? 'found' : 'warn';
  const estadoBadge = isOk
    ? '<span class="status-badge status-ok">✅ Acta transmitida</span>'
    : '<span class="status-badge status-warn">🔎 Revisar manualmente</span>';
    
  const pdfUrl   = data.url_pdf_directa;
  const visorUrl = data.url_visor_oficial;

  inner.innerHTML = `
    <div class="result-card ${cardClass}">
      <div class="result-title">✅ E-14 verificado (Vuelta ${vuelta})</div>
      <div class="code-big">X ${data.codigo_formateado} X</div>
      
      <div class="result-grid">
        <div class="result-item">
          <span class="result-label">Departamento</span>
          <span class="result-value">${data.depto_nombre}</span>
          <span style="font-size:.75rem;color:var(--faint)">código ${data.idDepartmentCode}</span>
        </div>
        <div class="result-item">
          <span class="result-label">Municipio</span>
          <span class="result-value">${data.municipalityCode}</span>
        </div>
        <div class="result-item">
          <span class="result-label">Zona</span>
          <span class="result-value">${data.idZoneCode}</span>
        </div>
        <div class="result-item">
          <span class="result-label">Puesto</span>
          <span class="result-value">${data.standCode}</span>
        </div>
        <div class="result-item">
          <span class="result-label">Mesa N°</span>
          <span class="result-value">${data.numberStand}</span>
        </div>
        <div class="result-item">
          <span class="result-label">Estado</span>
          ${estadoBadge}
        </div>
      </div>
      
      <hr class="div">
      
      <div class="alert-box">
        💡 <b>Nota técnica:</b> El servidor oficial suele enviar la foto rápida del E-14 a los celulares, y el escaneo definitivo a los computadores. Para ver la versión escaneada de alta resolución, te recomendamos <b>ingresar desde un PC</b>.
      </div>

      <p style="font-size:.85rem;color:var(--text);font-weight:600;margin-bottom:.75rem">
        Consulta el acta oficial de esta mesa:
      </p>
      
      <div class="btns">
        <button class="btn-pdf btn-dl" onclick="window.open('${pdfUrl}','_blank')">
          👁️ Ver / Descargar E-14 Oficial
        </button>
        <button class="btn-pdf btn-visor" onclick="window.open('${visorUrl}','_blank')">
          🔗 Visor Registraduría
        </button>
      </div>
    </div>`;
}
</script>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
def index():
    return HTML