#!/usr/bin/env python3
"""
YAKU Monitor · actualización automática diaria (la ejecuta GitHub Actions).
Descarga de la NASA, sin contraseña:
  - NASA POWER (diario): lluvia, temperatura, radiación solar y humedad relativa
  - NASA CMR: últimas pasadas del radar NISAR (GCOV) sobre el área
y escribe datos/monitor.json, que la app lee aunque no haya internet.

SI disclosure: code generated with assistance of Claude (Anthropic); reviewed and tested by team HIDROTECH.
"""
import json
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PUNTO = {"nombre": "Bofedal Apacheta · cabecera del río Cachi", "lat": -13.351, "lon": -74.659, "elev_m": 4210}
BBOX = (-74.85, -13.60, -74.30, -13.10)
PARAMS = ["PRECTOTCORR", "T2M", "T2M_MAX", "T2M_MIN", "ALLSKY_SFC_SW_DWN", "RH2M"]
NISAR = "NISAR_L2_GCOV_PROVISIONAL_V1"
SALIDA = Path(__file__).resolve().parent.parent / "datos" / "monitor.json"


def get_json(url, intentos=3):
    ultimo = None
    for _ in range(intentos):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                return json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001
            ultimo = e
    raise ultimo


def power(dias=400):
    fin = date.today()
    ini = fin - timedelta(days=dias)
    q = urllib.parse.urlencode({
        "parameters": ",".join(PARAMS), "community": "AG", "latitude": PUNTO["lat"],
        "longitude": PUNTO["lon"], "start": ini.strftime("%Y%m%d"), "end": fin.strftime("%Y%m%d"),
        "format": "JSON", "site-elevation": PUNTO["elev_m"]})
    j = get_json("https://power.larc.nasa.gov/api/temporal/daily/point?" + q)
    par = j["properties"]["parameter"]
    fechas = sorted(par[PARAMS[0]].keys())
    out = {"fechas": [f"{f[:4]}-{f[4:6]}-{f[6:]}" for f in fechas]}
    for p in PARAMS:
        out[p] = [None if (v := par[p].get(f, -999)) is None or v <= -998 else v for f in fechas]
    return out


def nisar(dias=200):
    ini = (date.today() - timedelta(days=dias)).isoformat()
    q = urllib.parse.urlencode({
        "short_name": NISAR, "bounding_box": ",".join(map(str, BBOX)),
        "temporal": f"{ini}T00:00:00Z,", "sort_key": "-start_date", "page_size": 100})
    j = get_json("https://cmr.earthdata.nasa.gov/search/granules.json?" + q)
    vistos, out = set(), []
    for e in j.get("feed", {}).get("entry", []):
        t = e.get("title", "")
        if "QA_STATS" in t or t in vistos:
            continue
        vistos.add(t)
        partes = t.split("_")
        track = direc = None
        try:
            i = partes.index("GCOV")
            track, direc = partes[i + 2], partes[i + 3]
        except (ValueError, IndexError):
            pass
        out.append({"fecha": e.get("time_start", "")[:10], "titulo": t, "track": track, "dir": direc})
    return out


def main():
    previo = {}
    if SALIDA.exists():
        try:
            previo = json.loads(SALIDA.read_text())
        except json.JSONDecodeError:
            previo = {}
    datos = {"formato": "yaku-monitor-1", "punto": PUNTO, "bbox": BBOX,
             "actualizado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "fuentes": {"clima": "NASA POWER (daily, AG community)", "radar": f"NASA CMR · {NISAR}"}}
    errores = []
    try:
        datos["power"] = power()
    except Exception as e:  # noqa: BLE001
        errores.append(f"POWER: {e}")
        datos["power"] = previo.get("power")
    try:
        datos["nisar"] = nisar()
    except Exception as e:  # noqa: BLE001
        errores.append(f"CMR: {e}")
        datos["nisar"] = previo.get("nisar", [])
    datos["errores"] = errores
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(datos, ensure_ascii=False))
    n = len(datos["power"]["fechas"]) if datos.get("power") else 0
    print(f"monitor.json: {n} días de clima, {len(datos['nisar'])} pasadas NISAR, errores: {errores or 'ninguno'}")
    if not datos.get("power"):
        sys.exit(1)


if __name__ == "__main__":
    main()
