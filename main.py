#!/usr/bin/env python3
"""
main.py — Verificador E-14 Presidenciales 2026
Servidor FastAPI + Uvicorn, listo para Railway
"""

import sqlite3
import os
from pathlib import Path
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

DB_PATH = os.environ.get("DB_PATH", "e14_index.db")

app = FastAPI(title="Verificador E-14", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

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

# Conexión con pool de lectura (check_same_thread=False es seguro en modo read-only)
def get_conn():
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True,
                          check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

def formatear_codigo(codigo: str) -> str:
    c = str(codigo).zfill(7)
    return f"{c[0]}-{c[1:3]}-{c[3:5]}-{c[5:7]}"

def construir_url_pdf(r: dict) -> str:
    base = "https://divulgacione14presidente.registraduria.gov.co/assets/temis/pdf"
    depto  = r["idDepartmentCode"].zfill(2)
    mpio   = r["municipalityCode"].zfill(3)
    zona   = r["idZoneCode"].zfill(3)
    puesto = r["standCode"].zfill(2)
    mesa   = r["numberStand"].zfill(3)
    return f"{base}/{depto}/{mpio}/{zona}/{puesto}/{mesa}/PRE/{r['expectedName']}"

def enriquecer(row) -> dict:
    r = dict(row)
    r["depto_nombre"]      = DEPARTAMENTOS.get(r["idDepartmentCode"], f"Código {r['idDepartmentCode']}")
    r["codigo_formateado"] = formatear_codigo(r["idTransmissionCode"])
    r["url_pdf_directa"]   = construir_url_pdf(r)
    return r

# ── Rutas API ─────────────────────────────────────────────────────────────────

@app.get("/api/buscar")
def buscar_codigo(codigo: str = Query(..., description="Código de transmisión")):
    codigo_norm = codigo.replace("-", "").replace(" ", "").strip()
    if not codigo_norm:
        raise HTTPException(400, "Código vacío")
    try:
        con = get_conn()
        row = con.execute(
            "SELECT * FROM mesas WHERE idTransmissionCode = ?", (codigo_norm,)
        ).fetchone()
        con.close()
    except Exception as e:
        raise HTTPException(500, f"Error de base de datos: {e}")
    if not row:
        return JSONResponse({"error": f"El código '{codigo}' no se encontró en ninguna mesa de Colombia."})
    return enriquecer(row)

@app.get("/api/lugar")
def buscar_lugar(
    depto:  str = Query(...),
    mpio:   str = Query(...),
    zona:   str = Query(...),
    puesto: str = Query(...),
    mesa:   str = Query(...),
):
    try:
        con = get_conn()
        rows = con.execute("""
            SELECT * FROM mesas
            WHERE idDepartmentCode=? AND municipalityCode=?
              AND idZoneCode=? AND standCode=? AND numberStand=?
        """, (depto.zfill(2), mpio.zfill(3), zona.zfill(2),
              puesto.zfill(2), mesa.zfill(3))).fetchall()
        con.close()
    except Exception as e:
        raise HTTPException(500, f"Error de base de datos: {e}")
    if not rows:
        return JSONResponse({"error": "No se encontró ninguna mesa con esos datos."})
    return [enriquecer(r) for r in rows]

@app.get("/api/stats")
def stats():
    con = get_conn()
    total = con.execute("SELECT COUNT(*) FROM mesas").fetchone()[0]
    por_status = con.execute(
        "SELECT status, COUNT(*) as n FROM mesas GROUP BY status ORDER BY n DESC"
    ).fetchall()
    con.close()
    return {"total_mesas": total, "por_status": [dict(r) for r in por_status]}

# ── Frontend ──────────────────────────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Verificador E-14 — Presidenciales 2026</title>
<style>
  :root {
    --bg:#f7f6f2; --surface:#fff; --border:#e0ddd8;
    --text:#1a1917; --muted:#6b6966; --faint:#a8a6a1;
    --primary:#01696f; --primary-hover:#0c4e54;
    --radius:10px; --shadow:0 2px 16px rgba(0,0,0,.08);
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
       background:var(--bg);color:var(--text);min-height:100vh;
       display:flex;flex-direction:column;align-items:center;padding:2rem 1rem}
  header{text-align:center;margin-bottom:2rem}
  header .logo{font-size:2rem;margin-bottom:.5rem}
  header h1{font-size:1.5rem;font-weight:700;margin-bottom:.25rem}
  header p{color:var(--muted);font-size:.9rem}
  .card{background:var(--surface);border:1px solid var(--border);
        border-radius:var(--radius);box-shadow:var(--shadow);
        padding:1.75rem;width:100%;max-width:580px;margin-bottom:1.5rem}
  .tabs{display:flex;gap:.5rem;margin-bottom:1.5rem}
  .tab{flex:1;padding:.6rem 1rem;border:2px solid var(--border);
       border-radius:8px;background:var(--bg);color:var(--muted);
       font-size:.875rem;font-weight:500;cursor:pointer;transition:all .15s}
  .tab.active{border-color:var(--primary);color:var(--primary);background:#e8f4f4}
  .tab:hover:not(.active){border-color:var(--faint);color:var(--text)}
  .panel{display:none}.panel.active{display:block}
  label{display:block;font-size:.8rem;font-weight:600;color:var(--muted);
        text-transform:uppercase;letter-spacing:.05em;margin-bottom:.4rem}
  input{width:100%;padding:.75rem 1rem;border:2px solid var(--border);
        border-radius:8px;font-size:1rem;color:var(--text);
        background:var(--bg);transition:border-color .15s;outline:none}
  input:focus{border-color:var(--primary);background:#fff}
  input::placeholder{color:var(--faint)}
  .hint{font-size:.78rem;color:var(--faint);margin-top:.35rem}
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-top:1rem}
  .grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1rem;margin-top:1rem}
  .field{display:flex;flex-direction:column}
  .btn-buscar{width:100%;margin-top:1.25rem;padding:.85rem;
    background:var(--primary);color:white;border:none;border-radius:8px;
    font-size:1rem;font-weight:600;cursor:pointer;transition:background .15s;
    display:flex;align-items:center;justify-content:center;gap:.5rem}
  .btn-buscar:hover{background:var(--primary-hover)}
  #resultado{display:none}
  .result-card{border-radius:var(--radius);padding:1.5rem;border:1px solid}
  .result-card.found{background:#edf7ed;border-color:#4caf50}
  .result-card.warn{background:#fff8e1;border-color:#ffb300}
  .result-card.error{background:#fdf0f0;border-color:#e57373}
  .result-title{font-size:1rem;font-weight:700;margin-bottom:1rem;
                display:flex;align-items:center;gap:.5rem}
  .found .result-title{color:#1b5e20}
  .warn  .result-title{color:#5d4000}
  .error .result-title{color:#7f0000}
  .result-grid{display:grid;grid-template-columns:1fr 1fr;gap:.6rem 1.5rem}
  .result-item{display:flex;flex-direction:column}
  .result-label{font-size:.72rem;font-weight:600;text-transform:uppercase;
                letter-spacing:.05em;color:var(--muted)}
  .result-value{font-size:1rem;font-weight:600;color:var(--text);margin-top:.1rem}
  .code-big{font-size:1.4rem;font-weight:800;color:var(--primary);
            letter-spacing:.05em;margin-bottom:1rem}
  .status-ok{display:inline-flex;align-items:center;gap:.3rem;padding:.2rem .7rem;
             border-radius:99px;font-size:.8rem;font-weight:600;
             background:#d4edda;color:#155724}
  .status-warn{display:inline-flex;align-items:center;gap:.3rem;padding:.2rem .7rem;
               border-radius:99px;font-size:.8rem;font-weight:600;
               background:#fff3cd;color:#856404}
  hr.div{border:none;border-top:1px solid var(--border);margin:1rem 0}
  .btns{display:flex;gap:.75rem;flex-wrap:wrap;margin-top:.25rem}
  .btn-pdf{padding:.55rem 1.1rem;border:none;border-radius:6px;
           font-size:.875rem;font-weight:600;cursor:pointer;
           display:inline-flex;align-items:center;gap:.4rem;transition:opacity .15s}
  .btn-pdf:hover{opacity:.85}
  .btn-dl{background:#01696f;color:white}
  .btn-visor{background:#555;color:white}
  footer{color:var(--faint);font-size:.78rem;text-align:center;
         margin-top:1rem;max-width:500px;line-height:1.6}
  footer a{color:var(--primary)}
  .spinner{display:none;width:18px;height:18px;border:2px solid rgba(255,255,255,.4);
           border-top-color:white;border-radius:50%;animation:spin .6s linear infinite}
  @keyframes spin{to{transform:rotate(360deg)}}
  .loading .spinner{display:inline-block}
  .loading .btn-text{display:none}
</style>
</head>
<body>
<header>
  <div class="logo">🗳️</div>
  <h1>Verificador de Actas E-14</h1>
  <p>Elección Presidencia y Vicepresidencia — Mayo 31 de 2026</p>
</header>

<div class="card">
  <div class="tabs">
    <button class="tab active" onclick="switchTab('codigo')">🔢 Por código del PDF</button>
    <button class="tab"        onclick="switchTab('lugar')">📍 Por ubicación</button>
  </div>
  <div id="panel-codigo" class="panel active">
    <form onsubmit="buscarCodigo(event)">
      <label>Código de transmisión</label>
      <input id="inp-codigo" type="text" placeholder="Ej: 5-57-43-15 o 5574315"
             autocomplete="off" spellcheck="false"/>
      <p class="hint">Es el número impreso en el formulario como X 5-57-43-15 X</p>
      <button type="submit" class="btn-buscar">
        <div class="spinner"></div>
        <span class="btn-text">🔍 Buscar</span>
      </button>
    </form>
  </div>
  <div id="panel-lugar" class="panel">
    <form onsubmit="buscarLugar(event)">
      <div class="grid2">
        <div class="field"><label>Departamento</label>
          <input id="l-dep" placeholder="Ej: 16" maxlength="4"/></div>
        <div class="field"><label>Municipio</label>
          <input id="l-mpio" placeholder="Ej: 001" maxlength="4"/></div>
      </div>
      <div class="grid3">
        <div class="field"><label>Zona</label>
          <input id="l-zona" placeholder="Ej: 12" maxlength="4"/></div>
        <div class="field"><label>Puesto</label>
          <input id="l-puesto" placeholder="Ej: 17" maxlength="4"/></div>
        <div class="field"><label>Mesa</label>
          <input id="l-mesa" placeholder="Ej: 001" maxlength="4"/></div>
      </div>
      <p class="hint" style="margin-top:.75rem">Datos tal como aparecen en el encabezado del E-14</p>
      <button type="submit" class="btn-buscar">
        <div class="spinner"></div>
        <span class="btn-text">🔍 Buscar</span>
      </button>
    </form>
  </div>
</div>

<div class="card" id="resultado">
  <div id="resultado-inner"></div>
</div>

<footer>
  122,002 mesas indexadas · Fuente: Registraduría Nacional del Estado Civil<br>
  Herramienta de verificación ciudadana. Datos oficiales en
  <a href="https://divulgacione14presidente.registraduria.gov.co" target="_blank">registraduria.gov.co</a>
</footer>

<script>
function switchTab(tab) {
  document.querySelectorAll('.tab').forEach((t,i) => {
    t.classList.toggle('active', (i===0&&tab==='codigo')||(i===1&&tab==='lugar'));
  });
  document.getElementById('panel-codigo').classList.toggle('active', tab==='codigo');
  document.getElementById('panel-lugar').classList.toggle('active',  tab==='lugar');
  document.getElementById('resultado').style.display = 'none';
}
function setLoading(btn, on) {
  btn.classList.toggle('loading', on);
  btn.disabled = on;
}
async function buscarCodigo(e) {
  e.preventDefault();
  const btn = e.target.querySelector('button');
  const codigo = document.getElementById('inp-codigo').value.trim();
  if (!codigo) return;
  setLoading(btn, true);
  try {
    const r = await fetch('/api/buscar?codigo=' + encodeURIComponent(codigo));
    mostrarResultado(await r.json());
  } finally { setLoading(btn, false); }
}
async function buscarLugar(e) {
  e.preventDefault();
  const btn = e.target.querySelector('button');
  const p = new URLSearchParams({
    depto: document.getElementById('l-dep').value.trim(),
    mpio:  document.getElementById('l-mpio').value.trim(),
    zona:  document.getElementById('l-zona').value.trim(),
    puesto:document.getElementById('l-puesto').value.trim(),
    mesa:  document.getElementById('l-mesa').value.trim(),
  });
  setLoading(btn, true);
  try {
    const r = await fetch('/api/lugar?' + p);
    const data = await r.json();
    mostrarResultado(Array.isArray(data) ? data[0] : data);
  } finally { setLoading(btn, false); }
}
function mostrarResultado(data) {
  const box   = document.getElementById('resultado');
  const inner = document.getElementById('resultado-inner');
  box.style.display = 'block';
  box.scrollIntoView({behavior:'smooth', block:'start'});
  if (data.error) {
    inner.innerHTML = `
      <div class="result-card error">
        <div class="result-title">❌ No encontrado</div>
        <p style="color:#7f0000;font-size:.9rem">${data.error}</p>
        <p style="color:#a00;font-size:.82rem;margin-top:.75rem">
          Si el código proviene de un E-14 publicado en redes, puede indicar que
          el número fue alterado, es de otra elección, o la imagen es falsa.
        </p>
      </div>`;
    return;
  }
  const isOk = data.status === 11;
  const cardClass   = isOk ? 'found' : 'warn';
  const estadoBadge = isOk
    ? '<span class="status-ok">✅ Acta transmitida</span>'
    : '<span class="status-warn">🔎 Revisar manualmente</span>';
  const pdfUrl   = data.url_pdf_directa;
  const visorUrl = 'https://divulgacione14presidente.registraduria.gov.co';
  inner.innerHTML = `
    <div class="result-card ${cardClass}">
      <div class="result-title">✅ E-14 verificado</div>
      <div class="code-big">X ${data.codigo_formateado} X</div>
      <div class="result-grid">
        <div class="result-item">
          <span class="result-label">Departamento</span>
          <span class="result-value">${data.depto_nombre}</span>
          <span style="font-size:.75rem;color:var(--muted)">código ${data.idDepartmentCode}</span>
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
      <p style="font-size:.82rem;color:var(--muted);margin-bottom:.75rem">
        Descarga o consulta el PDF oficial de esta mesa:
      </p>
      <div class="btns">
        <button class="btn-pdf btn-dl"
          onclick="window.open('${pdfUrl}','_blank')">
          ⬇️ Descargar E-14 (PDF oficial)
        </button>
        <button class="btn-pdf btn-visor"
          onclick="window.open('${visorUrl}','_blank')">
          🔗 Visor oficial
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
