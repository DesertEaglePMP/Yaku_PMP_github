#!/usr/bin/env python3
"""
YAKU · Agua de los bofedales vista por NISAR            (versión 7 · Yaku_v05 · reanuda descargas cortadas)

FORMA MÁS FÁCIL: abra este archivo en VS Code y presione el botón ▶ (Run).
Aparece un menú; elija 1 para probar. Las librerías que falten se instalan solas.

===========================================================================
NASA Space Apps Challenge 2026 · Desafío "Bailando con los SAR" · Equipo HIDROTECH

SI DISCLOSURE (Super Intelligence use): this code was written with the assistance of
Claude (Anthropic), a large language model, and was reviewed and tested by the HIDROTECH team.

Descarga y procesa productos NISAR L2 GCOV (banda L, HH/HV, γ⁰ en potencia
lineal con corrección radiométrica de terreno) sobre un bofedal altoandino y
genera:
  1) yaku_datos.json  -> se carga en la app web YAKU (pestaña "Datos NISAR")
  2) yaku_resumen.csv -> áreas y volúmenes de agua por fecha (para el informe)

Uso
---
  Windows: doble clic en INICIAR_YAKU_v05.bat  (o: python Yaku_v05.py)  -> menú:
    1 Probar (sin internet) · 2 Ver imágenes NISAR · 3 Descargar · 4 Procesar · 5 Cambiar área · 6 Salir

  Línea de comandos (opcional):
    python Yaku_v05.py prueba
    python Yaku_v05.py descargar --solo-listar
    python Yaku_v05.py descargar --track 75 --direccion ASCENDING --max-fechas 6
    python Yaku_v05.py procesar --entrada datos_nisar_cachi --agua-auto

  Área por defecto: cabecera del río Cachi, Huamanga, Ayacucho (bbox -74.85 -13.60 -74.30 -13.10).
  Las librerías que falten (numpy, h5py, pyproj, asf_search, rasterio) se instalan solas.
"""
from __future__ import annotations

__si_disclosure__ = "Code generated with assistance of Claude (Anthropic); reviewed and tested by team HIDROTECH."

import argparse
import base64
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
import importlib.util
import subprocess
from pathlib import Path

print(f"Python {sys.version.split()[0]} · {sys.executable}")
if sys.version_info < (3, 9):
    sys.exit("Se necesita Python 3.9 o más nuevo. Instálelo desde https://www.python.org/downloads/")

LIBRERIAS = {"numpy": "numpy", "h5py": "h5py", "pyproj": "pyproj", "asf_search": "asf_search",
             "rasterio": "rasterio"}


def asegurar_librerias(extra: dict | None = None) -> None:
    """Instala con pip las librerías que falten, en el mismo Python que ejecuta el script."""
    pedidas = {**LIBRERIAS, **(extra or {})}
    faltan = [pkg for mod, pkg in pedidas.items() if importlib.util.find_spec(mod) is None]
    if not faltan:
        return
    print(f"Instalando librerías que faltan: {', '.join(faltan)}")
    print("(solo pasa la primera vez; puede tardar 1–3 minutos)\n")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", *faltan])
    except subprocess.CalledProcessError:
        v = f"{sys.version_info.major}.{sys.version_info.minor}"
        if sys.version_info >= (3, 14):
            sys.exit(f"\nNo se pudieron instalar: este Python ({v}) es demasiado nuevo y algunas librerías\n"
                     "(h5py, rasterio) todavía no tienen versión lista para él.\n"
                     "SOLUCIÓN: en VS Code presione Ctrl+Shift+P > 'Python: Select Interpreter'\n"
                     "y elija Python 3.12 o 3.13. Luego cierre la terminal (papelera) y presione ▶.")
        sys.exit("\nNo se pudieron instalar. Abra la terminal y ejecute:\n"
                 f'  "{sys.executable}" -m pip install {" ".join(faltan)}')
    importlib.invalidate_caches()
    print("\nLibrerías instaladas.\n")


asegurar_librerias()
import numpy as np  # noqa: E402

# Carpeta donde está este archivo: todo se guarda aquí, se ejecute desde donde se ejecute
BASE = Path(__file__).resolve().parent
BBOX_MILLOC = [-76.40, -11.62, -76.30, -11.52]   # lon_min lat_min lon_max lat_max

# Áreas predefinidas: (nombre, bbox lon_min lat_min lon_max lat_max, pixel de salida en m)
AREAS = {
    "cachi": ("Huamanga · cabecera del río Cachi (Apacheta, Vinchos)",
              [-74.85, -13.60, -74.30, -13.10], 60),
    "huamanga": ("Provincia de Huamanga completa (rectángulo aproximado)",
                 [-74.75, -13.60, -73.85, -12.90], 90),
    "milloc": ("Laguna Milloc · Lima (sitio de prueba)", BBOX_MILLOC, 30),
}
AREA_DEFECTO = "cachi"

GRID = "/science/LSAR/GCOV/grids/frequencyA"
NODATA_I16 = -32768
FECHA_PROVISIONAL = "2026-06-17"   # primeras adquisiciones con productos calibrados (PROVISIONAL)

# Combinaciones track/frame con modos de calibración no utilizables antes de agosto 2026
# (NISAR Data User Guide, "Provisional Product Known Issues", 30-jul-2026)
TRACK_FRAME_MALOS = {("161", "174"), ("161", "175"), ("169", "090"), ("169", "091")}

# ----------------------------------------------------------------------------
# Parámetros por defecto (idénticos a los de la app web)
# ----------------------------------------------------------------------------
PARAMS = dict(
    agua_hh_max=-16.0,   # dB  agua abierta (punto de partida; mejor usar --agua-auto)
    agua_hv_max=-20.0,   # dB  el piso de ruido de NISAR está cerca de -23 dB: no exigir menos
    bof_hh_min=-9.0,     # dB  vegetación de bofedal saturada (heurístico: calibrar)
    bof_frec_min=0.30,   # fracción de fechas saturadas para considerar "bofedal"
    rango_min_db=1.5,    # dB  rango temporal mínimo para que el índice de humedad sea fiable
    turba_m=2.0,         # m   espesor medio de turba
    capa_activa_m=0.5,   # m   capa superior que se humedece / seca en la temporada
    theta_sat=0.90,      # m3/m3 contenido volumétrico de agua de turba saturada
    theta_min=0.55,      # m3/m3 contenido de agua de turba en su estado más seco observado
    prof_agua_m=1.0,     # m   profundidad media de lagunas / ojos de agua
    elev_min=3800.0,     # m   los bofedales altoandinos están sobre ~3800 m (Cachi: mayoría >4100 m)
    pend_max=15.0,       # %   bofedales y lagunas ocupan fondos planos; evita sombras de radar
)

# Nombre de archivo NISAR, p. ej.:
# NISAR_L2_PR_GCOV_006_172_A_008_2005_DHDH_A_20251204T024618_20251204T024653_X05007_N_F_J_001.h5
RE_NOMBRE = re.compile(
    r"GCOV_(?P<ciclo>\d{3})_(?P<track>\d{3})_(?P<dir>[AD])_(?P<frame>\d{3})_(?P<modo>\w{4})_"
    r"(?P<pol>[A-Z]{4})_[A-Z]_(?P<inicio>\d{8})T\d{6}_\d{8}T\d{6}_(?P<crid>[A-Z]\d{5})")


def info_nombre(nombre: str) -> dict:
    m = RE_NOMBRE.search(nombre)
    if not m:
        d = re.search(r"(20\d{6})T\d{6}", nombre)
        return {"fecha": datetime.strptime(d.group(1), "%Y%m%d").strftime("%Y-%m-%d")} if d else {}
    g = m.groupdict()
    g["fecha"] = datetime.strptime(g["inicio"], "%Y%m%d").strftime("%Y-%m-%d")
    g["beta"] = g["crid"].startswith("X")      # BETA = pre-calibración (CRID < P05023)
    return g


# ----------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------
def box_filter(a: np.ndarray, k: int = 3) -> np.ndarray:
    """Filtro de media k×k que ignora NaN (reduce el speckle del radar)."""
    pad = k // 2
    valid = np.isfinite(a).astype(np.float64)
    v = np.where(np.isfinite(a), a, 0.0)
    vp = np.pad(v, pad, mode="edge")
    mp = np.pad(valid, pad, mode="edge")
    s = np.zeros_like(v)
    n = np.zeros_like(v)
    for dy in range(k):
        for dx in range(k):
            s += vp[dy:dy + a.shape[0], dx:dx + a.shape[1]]
            n += mp[dy:dy + a.shape[0], dx:dx + a.shape[1]]
    with np.errstate(invalid="ignore", divide="ignore"):
        out = s / n
    out[n == 0] = np.nan
    return out


def to_db(lin: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        d = 10.0 * np.log10(lin)
    d[~np.isfinite(d)] = np.nan
    return d


def utm_epsg(lon: float, lat: float) -> int:
    zone = int((lon + 180) // 6) + 1
    return (32700 if lat < 0 else 32600) + zone


def enc_i16(a_db: np.ndarray) -> str:
    q = np.where(np.isfinite(a_db), np.round(a_db * 100), NODATA_I16)
    q = np.clip(q, -32768, 32767).astype("<i2")
    return base64.b64encode(q.tobytes()).decode()


def otsu(valores: np.ndarray, bins: int = 256) -> float:
    """Umbral de Otsu (minimiza la varianza intra-clase) sobre valores en dB."""
    v = valores[np.isfinite(valores)]
    v = v[(v > -35) & (v < 5)]
    h, e = np.histogram(v, bins=bins)
    c = (e[:-1] + e[1:]) / 2
    w0 = np.cumsum(h)
    w1 = w0[-1] - w0
    m0 = np.cumsum(h * c) / np.maximum(w0, 1)
    m1 = (np.sum(h * c) - np.cumsum(h * c)) / np.maximum(w1, 1)
    between = w0 * w1 * (m0 - m1) ** 2
    k = int(np.argmax(between))
    return float(c[k]), float(m1[k] - m0[k])          # umbral y separación entre clases (dB)


# ----------------------------------------------------------------------------
# 1) Búsqueda y descarga
# ----------------------------------------------------------------------------
ARCHIVO_TOKEN = BASE / ".earthdata_token"     # el token se guarda aquí (no compartir este archivo)


def token_guardado():
    try:
        t = ARCHIVO_TOKEN.read_text().strip()
        return t or None
    except OSError:
        return None


def guardar_token(t):
    try:
        ARCHIVO_TOKEN.write_text(t)
    except OSError:
        pass


def borrar_token():
    try:
        ARCHIVO_TOKEN.unlink()
    except OSError:
        pass


def sesion(a):
    import asf_search as asf
    s = asf.ASFSession()
    token = a.token or os.environ.get("EARTHDATA_TOKEN") or token_guardado()
    try:
        if token:
            s.auth_with_token(token)
        elif a.usuario:
            import getpass
            print("Escriba su contraseña de Earthdata. NO se verá nada al escribir (es normal);")
            print("al terminar presione Enter.")
            s.auth_with_creds(a.usuario, getpass.getpass("Contraseña: "))
        else:
            sys.exit("Falta el token de Earthdata (use la opción 3 del menú, que lo pide).")
    except Exception as e:
        if "Authentication" in type(e).__name__ or "401" in str(e):
            if token:
                # La verificación de asf_search falla si la cuenta aún no autorizó la aplicación de ASF.
                # Se intenta igual descargando con el token directamente.
                print("Aviso: no se pudo verificar el token con ASF; se intentará descargar igual.")
                s.headers.update({"Authorization": f"Bearer {token}"})
                return s
            sys.exit("NASA rechazó el usuario o la contraseña.\n"
                     "  Use su NOMBRE DE USUARIO de Earthdata (no el correo) o, mejor, un token.")
            sys.exit("NASA rechazó el usuario o la contraseña.\n"
                     "  Use su NOMBRE DE USUARIO de Earthdata (no el correo) o, mejor, un token.")
        raise
    return s


def elegir_fechas(fechas: list[str], n: int) -> list[str]:
    """n fechas repartidas de forma pareja en el periodo (incluye la primera y la última)."""
    fechas = sorted(fechas)
    if n <= 0 or n >= len(fechas):
        return fechas
    idx = sorted({round(i * (len(fechas) - 1) / (n - 1)) for i in range(n)}) if n > 1 else [len(fechas) - 1]
    return [fechas[i] for i in idx]


def archivo_completo(ruta: Path, esperado: int) -> bool:
    """True si el archivo tiene el tamaño esperado (o, si no se conoce, si se abre como HDF5 válido)."""
    tam = ruta.stat().st_size
    if esperado:
        return tam == esperado
    if tam < 1_000_000:
        return False
    try:
        import h5py
        with h5py.File(ruta, "r") as f:
            return GRID in f
    except Exception:
        return False


def cmd_descargar(a):
    import asf_search as asf

    lon0, lat0, lon1, lat1 = a.bbox
    wkt = f"POLYGON(({lon0} {lat0},{lon1} {lat0},{lon1} {lat1},{lon0} {lat1},{lon0} {lat0}))"
    opts = dict(intersectsWith=wkt, start=a.inicio, end=a.fin,
                processingLevel=["GCOV"], dataset=["NISAR"], maxResults=2000)
    if a.direccion:
        opts["flightDirection"] = a.direccion
    if a.track:
        opts["relativeOrbit"] = int(a.track)
    s = None if a.solo_listar else sesion(a)      # buscar es público: solo descargar requiere login
    if s:
        opts["session"] = s
    print("Buscando en el archivo de NASA/ASF...")
    res = asf.search(opts=asf.ASFSearchOptions(**opts))

    # orbita (track-dir) -> fecha -> lista de (url, bytes, nombre, frame, pol)
    orbitas: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for r in res:
        p = r.properties
        nombre = p.get("fileName") or p.get("sceneName") or ""
        inf = info_nombre(nombre)
        if inf.get("fecha", "9999") < FECHA_PROVISIONAL or inf.get("beta"):
            continue                                  # BETA / pre-calibración: se omite
        if (inf.get("track"), inf.get("frame")) in TRACK_FRAME_MALOS and inf["fecha"] < "2026-08-01":
            continue
        cand = [p.get("url")] + list(p.get("additionalUrls") or [])
        h5 = [u for u in cand if u and str(u).endswith(".h5") and "QA_STATS" not in str(u)]
        if not h5:
            continue
        b = p.get("bytes") or 0
        if isinstance(b, dict):                       # asf_search >= 8: {archivo: {"bytes": n, ...}}
            b = sum(v.get("bytes", 0) for k, v in b.items()
                    if isinstance(v, dict) and str(k).endswith(".h5") and "QA_STATS" not in str(k))
        clave = f"{int(inf.get('track', 0))}-{inf.get('dir', '?')}"
        orbitas[clave][inf["fecha"]].append((h5[0], b, nombre, inf.get("frame", "?"), inf.get("pol", "?")))

    if not orbitas:
        sys.exit("No se encontraron productos GCOV calibrados para esta área y fechas.")

    print(f"\n{'ÓRBITA':<8}{'FECHAS':>7}{'FRAMES':>10}{'GB TOTAL':>10}{'GB/FECHA':>10}  POLARIZ.")
    resumen = []
    for k, fechas in orbitas.items():
        gb = sum(x[1] for v in fechas.values() for x in v) / 1e9
        frames = sorted({x[3] for v in fechas.values() for x in v})
        pols = sorted({x[4] for v in fechas.values() for x in v})
        resumen.append((len(fechas), k, frames, gb, pols))
    resumen.sort(reverse=True)
    for n, k, frames, gb, pols in resumen:
        print(f"{k:<8}{n:>7}{','.join(frames):>10}{gb:>10.1f}{gb / n:>10.1f}  {','.join(pols)}")
    mejor = resumen[0][1]
    print(f"\nRecomendada: órbita {mejor} (track {mejor.split('-')[0]}, "
          f"dirección {'ASCENDING' if mejor.endswith('A') else 'DESCENDING'}).")
    print("Fechas disponibles en esa órbita:", ", ".join(sorted(orbitas[mejor])))
    if any(p not in ("DHDH", "?") for r_ in resumen for p in r_[4]):
        print("Aviso: hay productos sin HV (no DHDH). La app funciona igual; el agua se detecta solo con HH.")
    if a.solo_listar:
        return

    # Descargar solo UNA órbita (la indicada o la recomendada) y como máximo N fechas
    clave = mejor
    if a.track:
        cands = [k for k in orbitas if k.split("-")[0] == str(int(a.track))]
        if a.direccion:
            cands = [k for k in cands if k.endswith(a.direccion[0])]
        if not cands:
            sys.exit(f"No hay datos para el track {a.track}. Revise la lista.")
        clave = max(cands, key=lambda k: len(orbitas[k]))
    fechas = elegir_fechas(list(orbitas[clave]), a.max_fechas)
    items = [x for f in fechas for x in orbitas[clave][f]]
    out = BASE / a.salida
    out.mkdir(parents=True, exist_ok=True)
    pendientes, incompletos = [], 0
    for url, b, nombre, *_ in items:
        destino = out / url.rsplit("/", 1)[-1]
        if destino.exists():
            if archivo_completo(destino, b):
                continue                              # ya descargado completo
            destino.unlink()                          # quedó a medias (corte de luz, reinicio...): se borra
            incompletos += 1
        pendientes.append(url)
    if incompletos:
        print(f"Se encontraron {incompletos} archivo(s) incompleto(s) de una descarga cortada; se volverán a bajar.")
    gb = sum(x[1] for x in items) / 1e9
    print(f"\nÓrbita {clave}: {len(fechas)} fechas ({', '.join(fechas)})")
    print(f"{len(items)} archivos, {gb:.1f} GB en total; faltan {len(pendientes)} por descargar en {out}")
    if not pendientes:
        print("Todo ya estaba descargado.")
        return
    if getattr(a, "confirmar", True):
        if input("¿Descargar ahora? (s/n): ").strip().lower() not in ("s", "si", "sí", "y"):
            print("Descarga cancelada.")
            return
    try:
        asf.download_urls(pendientes, str(out), session=s, processes=a.procesos)
    except Exception as e:
        if "401" in str(e) or "403" in str(e) or "Unauthorized" in str(e) or "Forbidden" in str(e):
            sys.exit("NASA no autorizó la descarga. Falta autorizar la aplicación de ASF una sola vez:\n"
                     "  1) Abra https://search.asf.alaska.edu en el navegador\n"
                     "  2) Clic en 'Sign in' (arriba a la derecha) y entre con su usuario de Earthdata\n"
                     "  3) Acepte lo que le pregunte (autorizar aplicación / términos de uso)\n"
                     "  4) Vuelva aquí y repita la opción 3")
        raise
    # Comprobar que no se guardaron páginas de error en lugar de imágenes
    malos = [f for f in out.glob("*.h5") if f.stat().st_size < 1_000_000]
    if malos:
        for f in malos:
            f.unlink()
        sys.exit("Algunas descargas llegaron vacías (acceso no autorizado). Autorice ASF así:\n"
                 "  1) Abra https://search.asf.alaska.edu  2) 'Sign in' con su usuario de Earthdata\n"
                 "  3) Acepte lo que le pregunte  4) Repita la opción 3")
    print("Listo. Si se cortó el internet, vuelva a ejecutar: solo baja lo que falta.")


# ----------------------------------------------------------------------------
# 2) Lectura y apilado en una grilla común
# ----------------------------------------------------------------------------
def grilla_objetivo(bbox, pixel):
    from pyproj import Transformer
    lon0, lat0, lon1, lat1 = bbox
    epsg = utm_epsg((lon0 + lon1) / 2, (lat0 + lat1) / 2)
    tr = Transformer.from_crs(4326, epsg, always_xy=True)
    xs, ys = tr.transform([lon0, lon1, lon0, lon1], [lat0, lat0, lat1, lat1])
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    w = int(np.ceil((x1 - x0) / pixel))
    h = int(np.ceil((y1 - y0) / pixel))
    X = x0 + (np.arange(w) + 0.5) * pixel
    Y = y1 - (np.arange(h) + 0.5) * pixel        # norte arriba
    return epsg, X, Y


def muestrear(lectura, xs, ys, epsg_s, epsg_t, X, Y, pixel):
    """lectura(r0,r1,c0,c1) -> array lineal. Devuelve dB promediado a la grilla objetivo."""
    from pyproj import Transformer
    XX, YY = np.meshgrid(X, Y)
    if epsg_s != epsg_t:
        XX, YY = Transformer.from_crs(epsg_t, epsg_s, always_xy=True).transform(XX, YY)
    dx, dy = xs[1] - xs[0], ys[1] - ys[0]
    ci = np.floor((XX - (xs[0] - dx / 2)) / dx).astype(np.int64)
    ri = np.floor((YY - (ys[0] - dy / 2)) / dy).astype(np.int64)
    inside = (ci >= 0) & (ci < xs.size) & (ri >= 0) & (ri < ys.size)
    if not inside.any():
        return None
    f = max(1, int(round(pixel / abs(dx))))           # pixeles nativos por pixel de salida
    r0 = max(ri[inside].min() - f, 0)
    c0 = max(ci[inside].min() - f, 0)
    r1 = min(ri[inside].max() + 2 * f, ys.size)
    c1 = min(ci[inside].max() + 2 * f, xs.size)
    sub = lectura(r0, r1, c0, c1).astype(np.float32)
    sub[~(sub > 0)] = np.nan
    # Promedio por bloques f×f (multilook): reduce el speckle y la memoria
    h, w = (sub.shape[0] // f) * f, (sub.shape[1] // f) * f
    sub = sub[:h, :w]
    ok = np.isfinite(sub)
    S = np.where(ok, sub, 0).reshape(h // f, f, w // f, f).sum(axis=(1, 3), dtype=np.float64)
    N = ok.reshape(h // f, f, w // f, f).sum(axis=(1, 3))
    del sub, ok
    with np.errstate(invalid="ignore", divide="ignore"):
        gruesa = np.where(N > 0, S / np.maximum(N, 1), np.nan)
    if f < 3:                                          # poco promedio: suavizado extra 3×3
        gruesa = box_filter(gruesa, 3)
    gr = np.clip((ri - r0) // f, 0, gruesa.shape[0] - 1)
    gc = np.clip((ci - c0) // f, 0, gruesa.shape[1] - 1)
    v = np.full(XX.shape, np.nan)
    v[inside] = gruesa[gr[inside], gc[inside]]
    return to_db(v)


# ----------------------------------------------------------------------------
# DEM Copernicus GLO-30 (altitud y pendiente) — público, sin cuenta
# ----------------------------------------------------------------------------
def nombre_tile_dem(lat: int, lon: int) -> str:
    ns, ew = ("N" if lat >= 0 else "S"), ("E" if lon >= 0 else "W")
    return f"Copernicus_DSM_COG_10_{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00_DEM"


def dem_en_grilla(epsg, X, Y, pixel):
    """Altitud (m) y pendiente (%) en la grilla de salida. Usa copias locales en ./dem si existen."""
    asegurar_librerias({"rasterio": "rasterio"})
    import math
    import rasterio
    from rasterio.windows import Window
    from pyproj import Transformer
    XX, YY = np.meshgrid(X, Y)
    lon, lat = Transformer.from_crs(epsg, 4326, always_xy=True).transform(XX, YY)
    elev = np.full(XX.shape, np.nan, dtype=np.float32)
    for la in range(math.floor(lat.min()), math.floor(lat.max()) + 1):
        for lo in range(math.floor(lon.min()), math.floor(lon.max()) + 1):
            nom = nombre_tile_dem(la, lo)
            local = BASE / "dem" / f"{nom}.tif"
            src = str(local) if local.exists() else \
                f"https://copernicus-dem-30m.s3.amazonaws.com/{nom}/{nom}.tif"
            sel = (lat >= la) & (lat < la + 1) & (lon >= lo) & (lon < lo + 1)
            if not sel.any():
                continue
            print(f"  DEM {nom} {'(local)' if local.exists() else '(internet)'}")
            with rasterio.open(src) as ds:
                inv = ~ds.transform
                cc, rr = inv * (lon[sel], lat[sel])
                rr = np.clip(np.floor(rr).astype(int), 0, ds.height - 1)
                cc = np.clip(np.floor(cc).astype(int), 0, ds.width - 1)
                r0, c0 = rr.min(), cc.min()
                win = Window(c0, r0, cc.max() - c0 + 1, rr.max() - r0 + 1)
                data = ds.read(1, window=win).astype(np.float32)
                elev[sel] = data[rr - r0, cc - c0]
    gy, gx = np.gradient(elev, pixel)
    pend = np.hypot(gx, gy) * 100.0
    return elev, pend.astype(np.float32)


def leer_h5(path: Path, epsg_t, X, Y, pixel):
    import h5py
    inf = info_nombre(path.name)
    with h5py.File(path, "r") as f:
        if GRID not in f:
            raise ValueError("no es un GCOV (¿archivo QA_STATS?)")
        g = f[GRID]
        epsg_s = int(np.array(g["projection"][()]).flat[0])
        xs, ys = g["xCoordinates"][:], g["yCoordinates"][:]
        mask = g["mask"] if "mask" in g else None
        out = dict(fecha=inf.get("fecha"), orbita=f"{inf.get('track','?')}-{inf.get('dir','?')}",
                   frame=inf.get("frame"), track=inf.get("track"), beta=inf.get("beta", False),
                   archivo=path.name)
        if not out["fecha"]:
            t = g.file["/science/LSAR/identification/zeroDopplerStartTime"][()]
            out["fecha"] = (t.decode() if isinstance(t, bytes) else str(t))[:10]
        for pol, key in (("HHHH", "hh"), ("HVHV", "hv")):
            if pol not in g:
                out[key] = None
                continue
            def lectura(r0, r1, c0, c1, ds=g[pol]):
                a = ds[r0:r1, c0:c1].astype(np.float64)
                if mask is not None:
                    m = mask[r0:r1, c0:c1]
                    a[(m == 0) | (m == 255)] = np.nan   # 0 inválido, 255 fuera de la adquisición
                return a
            out[key] = muestrear(lectura, xs, ys, epsg_s, epsg_t, X, Y, pixel)
        if out["hh"] is None:
            return None
    return out


def leer_tifs(grupo: list[Path], epsg_t, X, Y, pixel):
    """GeoTIFF extraídos con Harmony (un archivo por polarización)."""
    asegurar_librerias({"rasterio": "rasterio"})
    import rasterio
    out = None
    for p in grupo:
        pol = "hh" if "HHHH" in p.name.upper() else "hv" if "HVHV" in p.name.upper() else None
        if not pol:
            continue
        inf = info_nombre(p.name)
        with rasterio.open(p) as ds:
            t = ds.transform
            xs = t.c + (np.arange(ds.width) + 0.5) * t.a
            ys = t.f + (np.arange(ds.height) + 0.5) * t.e
            epsg_s = ds.crs.to_epsg()
            nod = ds.nodata
            def lectura(r0, r1, c0, c1, ds=ds):
                from rasterio.windows import Window
                a = ds.read(1, window=Window(c0, r0, c1 - c0, r1 - r0)).astype(np.float64)
                if nod is not None:
                    a[a == nod] = np.nan
                return a
            if out is None:
                out = dict(fecha=inf.get("fecha"), orbita=f"{inf.get('track','?')}-{inf.get('dir','?')}",
                           frame=inf.get("frame"), track=inf.get("track"), beta=inf.get("beta", False),
                           archivo=p.name, hh=None, hv=None)
            out[pol] = muestrear(lectura, xs, ys, epsg_s, epsg_t, X, Y, pixel)
    return out if out and out["hh"] is not None and out["fecha"] else None


# ----------------------------------------------------------------------------
# 3) Análisis (misma lógica que la app web)
# ----------------------------------------------------------------------------
def clasificar_agua(hh, hv, p):
    hv_ok = np.isfinite(hv)
    return (hh < p["agua_hh_max"]) & np.where(hv_ok, hv < p["agua_hv_max"], True)


def zonas(elev, pend, p):
    """Dónde puede haber agua (terreno plano) y bofedal (plano y alto). Sin DEM: todo vale."""
    if elev is None:
        return True, True
    sin = ~np.isfinite(elev)
    plano = sin | (pend <= p["pend_max"])
    alto = sin | (elev >= p["elev_min"])
    return plano, plano & alto


def analizar(hh, hv, pixel_m, p=PARAMS, elev=None, pend=None):
    """hh, hv: arrays (T, H, W) en dB. Devuelve lista de dicts por fecha."""
    T = hh.shape[0]
    valid = np.isfinite(hh)
    z_agua, z_bof = zonas(elev, pend, p)
    agua = clasificar_agua(hh, hv, p) & valid & z_agua
    sat = (~agua) & (hh >= p["bof_hh_min"]) & valid & z_bof
    nval = valid.sum(0)
    frec = np.where(nval > 0, sat.sum(0) / np.maximum(nval, 1), 0)
    bofedal = frec >= p["bof_frec_min"]

    with np.errstate(all="ignore"):
        hmin = np.nanmin(np.where(valid, hh, np.nan), axis=0)
        hmax = np.nanmax(np.where(valid, hh, np.nan), axis=0)
    rng = hmax - hmin
    ok = rng >= p["rango_min_db"]
    a_px = pixel_m * pixel_m
    prof = max(p["turba_m"] - p["capa_activa_m"], 0)
    res = []
    for t in range(T):
        with np.errstate(all="ignore"):
            smi = np.clip(np.where(ok, (hh[t] - hmin) / np.where(ok, rng, 1), 0.5), 0, 1)
        theta = p["theta_min"] + smi * (p["theta_sat"] - p["theta_min"])
        b = bofedal & valid[t] & ~agua[t]
        n_b = int(b.sum())
        n_w = int(agua[t].sum())
        v_prof = n_b * a_px * prof * p["theta_sat"]
        v_act = float(theta[b].sum() * a_px * p["capa_activa_m"])
        v_sup = n_w * a_px * p["prof_agua_m"]
        res.append(dict(
            area_bofedal_ha=n_b * a_px / 1e4,
            area_saturada_ha=int((sat[t] & bofedal).sum()) * a_px / 1e4,
            area_agua_ha=n_w * a_px / 1e4,
            humedad_media_pct=float(smi[b].mean() * 100) if n_b else float("nan"),
            vol_turba_profunda_m3=v_prof,
            vol_capa_activa_m3=v_act,
            vol_superficial_m3=v_sup,
            vol_total_m3=v_prof + v_act + v_sup,
            cobertura_pct=float(valid[t].mean() * 100),
        ))
    return res


def cmd_procesar(a):
    ent = BASE / a.entrada
    h5s = sorted(ent.glob("*.h5"))
    tifs = sorted(list(ent.glob("*.tif")) + list(ent.glob("*.tiff")))
    if not h5s and not tifs:
        sys.exit(f"No hay archivos .h5 ni .tif en {ent}")
    epsg, X, Y = grilla_objetivo(a.bbox, a.pixel)
    print(f"Grilla de salida: EPSG:{epsg}  {X.size}×{Y.size} px de {a.pixel} m")

    escenas = []
    for fp in h5s:
        if "QA_STATS" in fp.name:
            continue
        try:
            s = leer_h5(fp, epsg, X, Y, a.pixel)
        except Exception as e:
            print(f"  ! {fp.name}: {e}")
            continue
        if s:
            escenas.append(s)
        else:
            print(f"  - {fp.name}: no cubre el área o no tiene HH")
    if tifs:
        grupos = defaultdict(list)
        for p in tifs:
            m = RE_NOMBRE.search(p.name)
            clave = m.group(0) if m else re.sub(r"(HHHH|HVHV).*", "", p.name, flags=re.I)
            grupos[clave].append(p)
        for g in grupos.values():
            try:
                s = leer_tifs(g, epsg, X, Y, a.pixel)
            except ImportError:
                sys.exit("No se pudo cargar rasterio (necesario para GeoTIFF).")
            if s:
                escenas.append(s)
            else:
                print(f"  - {[p.name for p in g]}: sin fecha/HHHH en el nombre o fuera del área")

    # Filtros de calidad
    ok = []
    for s in escenas:
        if s["beta"] or s["fecha"] < FECHA_PROVISIONAL:
            print(f"  - {s['fecha']} {s['archivo']}: producto BETA (pre-calibración), se omite")
            continue
        if (s["track"], s["frame"]) in TRACK_FRAME_MALOS and s["fecha"] < "2026-08-01":
            print(f"  - {s['fecha']}: track/frame {s['track']}/{s['frame']} con modo de calibración, se omite")
            continue
        ok.append(s)
    if not ok:
        sys.exit("Ninguna escena útil.")

    # Una sola geometría de órbita (mezclarlas cambia el brillo por el ángulo de incidencia)
    if not a.todas_orbitas:
        top = Counter(s["orbita"] for s in ok).most_common(1)[0][0]
        if len({s["orbita"] for s in ok}) > 1:
            print(f"Varias órbitas encontradas; se usa {top} (use --todas-orbitas para mezclarlas)")
        ok = [s for s in ok if s["orbita"] == top]

    # Unir productos parciales de la misma fecha (cambios de modo dentro de un frame)
    por_fecha = {}
    for s in sorted(ok, key=lambda s: s["fecha"]):
        if s["fecha"] not in por_fecha:
            por_fecha[s["fecha"]] = s
            continue
        b = por_fecha[s["fecha"]]
        for k in ("hh", "hv"):
            if b[k] is None:
                b[k] = s[k]
            elif s[k] is not None:
                b[k] = np.where(np.isfinite(b[k]), b[k], s[k])
    escenas = []
    for f, s in por_fecha.items():
        if s["hv"] is None:
            s["hv"] = np.full_like(s["hh"], np.nan)
        cob = np.isfinite(s["hh"]).mean()
        if cob < a.cobertura_min:
            print(f"  - {f}: cubre solo {cob:.0%} del área, se omite")
            continue
        print(f"  + {f}  órbita {s['orbita']}  cobertura {cob:.0%}  HV {'sí' if np.isfinite(s['hv']).any() else 'NO'}")
        escenas.append(s)
    if len(escenas) < 2:
        sys.exit("Se necesitan al menos 2 fechas de la misma órbita (ideal: 5 o más).")

    hh = np.stack([s["hh"] for s in escenas])
    hv = np.stack([s["hv"] for s in escenas])
    fechas = [s["fecha"] for s in escenas]

    p = dict(PARAMS)
    elev = pend = None
    if not getattr(a, "sin_dem", False):
        print("\nLeyendo altitud (DEM Copernicus 30 m)...")
        try:
            elev, pend = dem_en_grilla(epsg, X, Y, a.pixel)
            print(f"  Altitud en el área: {np.nanmin(elev):.0f}–{np.nanmax(elev):.0f} m; "
                  f"zona apta para bofedal (≥{p['elev_min']:.0f} m y ≤{p['pend_max']:.0f} % de pendiente): "
                  f"{(zonas(elev, pend, p)[1]).mean():.0%} del área")
        except Exception as e:
            print(f"  ! No se pudo leer el DEM ({type(e).__name__}: {e}).")
            print("    Se sigue sin máscara de altitud: puede confundir ciudades y chacras con bofedal.")
            elev = pend = None

    # Umbral de agua por Otsu: solo en terreno plano y sobre la mitad oscura del histograma
    # (el agua suele ser una fracción pequeña del área). Se acepta solo si el agua se separa
    # claramente del terreno; si no, se mantiene el valor por defecto.
    plano = zonas(elev, pend, p)[0]
    vals = hh[:, plano] if elev is not None else hh
    vals = vals[np.isfinite(vals)]
    u, sep = otsu(vals[vals < np.median(vals)])
    print(f"\nOtsu (HH, terreno plano, mitad oscura): {u:.1f} dB, separación {sep:.1f} dB "
          f"(valor por defecto: {PARAMS['agua_hh_max']} dB)")
    if a.agua_auto:
        if -24 <= u <= -14 and sep >= 4:
            p["agua_hh_max"] = round(u, 1)
            print(f"  -> se usa {p['agua_hh_max']} dB como umbral de agua")
        else:
            print("  -> no hay contraste claro agua/terreno (poca agua en el área); se usa el valor por defecto")
    pct = np.nanpercentile(hh, [5, 25, 50, 75, 95])
    print("Percentiles HH (dB) 5/25/50/75/95:", " / ".join(f"{x:.1f}" for x in pct))

    res = analizar(hh, hv, a.pixel, p, elev, pend)
    a.csv, a.salida = str(BASE / a.csv), str(BASE / a.salida)
    with open(a.csv, "w", newline="") as fh:
        w = csv.writer(fh)
        keys = list(res[0].keys())
        w.writerow(["fecha"] + keys)
        for f_, r in zip(fechas, res):
            w.writerow([f_] + [round(r[k], 2) for k in keys])
    print(f"Resumen -> {a.csv}")

    data = dict(
        formato="yaku-1", version=2, sitio=a.sitio, bbox=list(a.bbox), epsg=epsg,
        pixel_m=a.pixel, ancho=int(X.size), alto=int(Y.size), fechas=fechas,
        orbitas=[s["orbita"] for s in escenas], archivos=[s["archivo"] for s in escenas],
        escala="dB*100 int16 little-endian, nodata=-32768",
        parametros=p, otsu_hh_db=u, otsu_separacion_db=sep,
        hh=[enc_i16(x) for x in hh], hv=[enc_i16(x) for x in hv], demo=False,
        dem=enc_i16(elev / 100.0) if elev is not None else None,       # m (guardado como m/100*100)
        pend=enc_i16(pend / 10.0) if pend is not None else None,      # % ×10
    )
    Path(a.salida).write_text(json.dumps(data))
    mb = Path(a.salida).stat().st_size / 1e6
    print(f"Datos para la app -> {a.salida} ({mb:.1f} MB)")
    if mb > 60:
        print("  Archivo muy grande para el navegador: aumente --pixel (p. ej. 90) o reduzca el área.")


# ----------------------------------------------------------------------------
# 4) Prueba sin internet
# ----------------------------------------------------------------------------
def cmd_prueba(a):
    import h5py
    from pyproj import Transformer
    d = BASE / "prueba_nisar"
    d.mkdir(exist_ok=True)
    tr = Transformer.from_crs(4326, 32718, always_xy=True)
    x0, y0 = tr.transform(-76.42, -11.50)
    x1, y1 = tr.transform(-76.28, -11.64)
    xs, ys = np.arange(x0, x1, 20.0), np.arange(y0, y1, -20.0)
    XX, YY = np.meshgrid(xs, ys)
    cx, cy = tr.transform(-76.356, -11.577)
    r = np.hypot(XX - cx, YY - cy)
    rng = np.random.default_rng(0)
    for fecha, w in (("20260628", 0.85), ("20260816", 0.35), ("20260921", 0.25), ("20261108", 0.7)):
        hh = np.full(XX.shape, 10 ** (-12 / 10))
        hv = np.full(XX.shape, 10 ** (-19 / 10))
        bof = (r > 400) & (r < 1500)
        hh[bof] = 10 ** ((-12 + 8 * w) / 10)
        hv[bof] = 10 ** ((-19 + 6 * w) / 10)
        hh[r < 400] = 10 ** (-23 / 10)
        hv[r < 400] = 10 ** (-27 / 10)
        nombre = (f"NISAR_L2_PR_GCOV_010_172_A_008_2005_DHDH_A_{fecha}T101010_{fecha}T101030"
                  f"_P05023_N_F_J_001.h5")
        with h5py.File(d / nombre, "w") as f:
            g = f.create_group(GRID)
            g["HHHH"] = (hh * rng.gamma(9, 1 / 9, XX.shape)).astype("f4")
            g["HVHV"] = (hv * rng.gamma(9, 1 / 9, XX.shape)).astype("f4")
            g["xCoordinates"], g["yCoordinates"] = xs, ys
            g["projection"] = np.uint32(32718)
            g["mask"] = np.ones(XX.shape, "u1")
    print(f"Archivos sintéticos en {d}/ — procesando...\n")
    ns = argparse.Namespace(entrada="prueba_nisar", bbox=[-76.40, -11.62, -76.30, -11.52], pixel=30.0,
                            sitio="Prueba sintética", salida="prueba_yaku_datos.json",
                            csv="prueba_resumen.csv", todas_orbitas=False, agua_auto=True,
                            cobertura_min=0.5, sin_dem=True)
    cmd_procesar(ns)
    print("\n✔ Instalación correcta.")
    print(f"  Archivo para la app: {BASE / 'prueba_yaku_datos.json'}")


# ----------------------------------------------------------------------------
# 5) Menú interactivo (al presionar ▶ en VS Code)
# ----------------------------------------------------------------------------
def preguntar(texto, defecto=""):
    r = input(f"{texto}" + (f" [{defecto}]" if defecto else "") + ": ").strip()
    return r or defecto


def pedir_token():
    t = token_guardado()
    if t:
        return t, None
    print("\nSe necesita su TOKEN de NASA Earthdata (solo la primera vez; queda guardado).")
    print("  1) Entre a https://urs.earthdata.nasa.gov e inicie sesión")
    print("  2) Clic en 'Generate Token' > botón verde 'Generate Token'")
    print("  3) Copie el texto largo que aparece (empieza con 'eyJ...')")
    print("  4) Péguelo aquí con CLIC DERECHO del mouse (o Ctrl+V) y presione Enter")
    print("Si prefiere usar usuario y contraseña, solo presione Enter.\n")
    t = input("Token: ").strip().strip('"').strip("'")
    if t:
        if len(t) < 100:
            print("  Ojo: el texto parece muy corto para un token; revise que lo copió completo.")
        guardar_token(t)
        print("  Token guardado en el archivo .earthdata_token (no lo comparta).")
        return t, None
    u = preguntar("Nombre de USUARIO de Earthdata (no el correo)")
    return None, u or None


def args_area(clave):
    nombre, bbox, pixel = AREAS[clave]
    return dict(clave=clave, nombre=nombre, bbox=bbox, pixel=pixel,
                carpeta=f"datos_nisar_{clave}", json=f"yaku_{clave}.json", csv=f"yaku_{clave}_resumen.csv")


def elegir_area(actual):
    print("\nÁreas disponibles:")
    claves = list(AREAS)
    for n, k in enumerate(claves, 1):
        nombre, bbox, pixel = AREAS[k]
        km_x = abs(bbox[2] - bbox[0]) * 111 * np.cos(np.radians((bbox[1] + bbox[3]) / 2))
        km_y = abs(bbox[3] - bbox[1]) * 111
        print(f"  {n}. {nombre}  (~{km_x:.0f}×{km_y:.0f} km, pixel {pixel} m)")
    print(f"  {len(claves) + 1}. Otra área (escribir coordenadas)")
    op = preguntar("Elija el área", str(claves.index(actual) + 1))
    if op.isdigit() and 1 <= int(op) <= len(claves):
        return claves[int(op) - 1]
    if op == str(len(claves) + 1):
        print("Escriba lon_min lat_min lon_max lat_max (grados, oeste y sur negativos).")
        print("Ejemplo: -74.85 -13.60 -74.30 -13.10")
        try:
            bb = [float(x) for x in preguntar("Coordenadas").replace(",", " ").split()]
            assert len(bb) == 4 and bb[0] < bb[2] and bb[1] < bb[3]
        except (ValueError, AssertionError):
            print("Coordenadas no válidas; se mantiene el área anterior.")
            return actual
        km2 = abs(bb[2] - bb[0]) * abs(bb[3] - bb[1]) * 111 * 111
        pixel = int(max(30, min(150, round(np.sqrt(km2 * 1e6 / 1.0e6) / 10) * 10)))
        AREAS["propia"] = (preguntar("Nombre del área", "Mi área"), bb, pixel)
        return "propia"
    return actual


def menu():
    area = AREA_DEFECTO
    token = os.environ.get("EARTHDATA_TOKEN") or token_guardado()
    usuario = None
    while True:
        A = args_area(area)
        print("\n" + "=" * 66)
        print("  YAKU v05 · Agua de los bofedales con el radar NISAR")
        print(f"  Área: {A['nombre']}")
        print(f"        {A['bbox']}  · pixel {A['pixel']} m")
        print(f"  Carpeta de trabajo: {BASE}")
        print("=" * 66)
        print("  1. Probar que todo funciona (sin internet)")
        print("  2. Ver qué imágenes NISAR hay (no descarga nada)")
        print("  3. Descargar imágenes (la órbita recomendada, 6 fechas)")
        print("  4. Procesar las imágenes descargadas")
        print("  5. Cambiar de área")
        print("  6. Salir")
        print(f"  (Token de Earthdata: {'guardado ✔' if token else 'aún no ingresado'})")
        op = preguntar("\nElija una opción (1-6)")
        base = dict(bbox=A["bbox"], inicio=FECHA_PROVISIONAL, fin=datetime.now().strftime("%Y-%m-%d"),
                    token=token, usuario=usuario, direccion=None, track=None, salida=A["carpeta"],
                    procesos=1, solo_listar=False, max_fechas=6, confirmar=True)
        try:
            if op == "1":
                cmd_prueba(None)
            elif op == "2":
                cmd_descargar(argparse.Namespace(**{**base, "solo_listar": True}))
            elif op == "3":
                print("\nSe descargará la órbita con más fechas (recomendada).")
                track = preguntar("Si quiere otra, escriba su número de track; si no, solo Enter")
                n = preguntar("¿Cuántas fechas descargar? (3 = rápido, 6 = recomendado, 0 = todas)", "6")
                if not token and not usuario:
                    token, usuario = pedir_token()
                cmd_descargar(argparse.Namespace(**{**base, "token": token, "usuario": usuario,
                              "track": track or None, "max_fechas": int(n) if n.isdigit() else 6}))
            elif op == "4":
                cmd_procesar(argparse.Namespace(entrada=A["carpeta"], bbox=A["bbox"], pixel=float(A["pixel"]),
                             sitio=A["nombre"], salida=A["json"], csv=A["csv"], todas_orbitas=False,
                             agua_auto=True, cobertura_min=0.5, sin_dem=False))
                print(f"\n✔ Listo. Cargue {BASE / A['json']} en la app (pestaña 'Datos NISAR').")
                print(f"  Tabla para el informe: {BASE / A['csv']}")
            elif op == "5":
                area = elegir_area(area)
            elif op == "6":
                print("Hasta luego.")
                return
            else:
                print("Opción no válida.")
        except SystemExit as e:          # los errores del script no cierran el menú
            if e.code not in (None, 0):
                print(f"\n✘ {e.code}")
                if "rechazó" in str(e.code):     # credenciales malas: volver a pedirlas la próxima vez
                    token, usuario = None, None
        except KeyboardInterrupt:
            print("\nCancelado.")
        except Exception as e:           # errores inesperados: mostrar y seguir
            if any(k in type(e).__name__ for k in ("Connection", "Proxy", "Timeout", "SSL")):
                print("\n✘ No hay conexión con los servidores de la NASA.")
                print("  Revise su internet (o la red de la sede) e intente de nuevo.")
            print(f"\n✘ Error: {type(e).__name__}: {e}")
            print("  Copie este mensaje y compártalo para revisarlo.")
        input("\nPresione Enter para volver al menú...")


def main():
    if len(sys.argv) == 1:               # sin argumentos (botón ▶) -> menú
        menu()
        return
    ap = argparse.ArgumentParser(description="YAKU: agua de bofedales con NISAR GCOV")
    sp = ap.add_subparsers(dest="cmd", required=True)

    sp.add_parser("prueba", help="verificar la instalación con datos sintéticos").set_defaults(fn=cmd_prueba)

    d = sp.add_parser("descargar", help="buscar y descargar NISAR GCOV con asf_search")
    d.add_argument("--bbox", type=float, nargs=4, default=AREAS[AREA_DEFECTO][1], metavar=("LON0", "LAT0", "LON1", "LAT1"))
    d.add_argument("--inicio", default=FECHA_PROVISIONAL)
    d.add_argument("--fin", default=datetime.now().strftime("%Y-%m-%d"))
    d.add_argument("--token", help="token de Earthdata Login (o variable EARTHDATA_TOKEN)")
    d.add_argument("--usuario", help="usuario Earthdata (pide la contraseña)")
    d.add_argument("--direccion", choices=["ASCENDING", "DESCENDING"])
    d.add_argument("--track", help="número de track (órbita relativa), p. ej. 172")
    d.add_argument("--salida", default="datos_nisar")
    d.add_argument("--procesos", type=int, default=1)
    d.add_argument("--max-fechas", type=int, default=6, help="cuántas fechas bajar (repartidas); 0 = todas")
    d.add_argument("--si", dest="confirmar", action="store_false", help="no preguntar antes de descargar")
    d.add_argument("--solo-listar", action="store_true")
    d.set_defaults(fn=cmd_descargar)

    p = sp.add_parser("procesar", help="recortar, apilar y cuantificar")
    p.add_argument("--entrada", default="datos_nisar", help="carpeta con .h5 (o GeoTIFF de Harmony)")
    p.add_argument("--bbox", type=float, nargs=4, default=AREAS[AREA_DEFECTO][1], metavar=("LON0", "LAT0", "LON1", "LAT1"))
    p.add_argument("--pixel", type=float, default=60.0, help="tamaño de pixel de salida (m)")
    p.add_argument("--sitio", default=AREAS[AREA_DEFECTO][0])
    p.add_argument("--salida", default="yaku_datos.json")
    p.add_argument("--csv", default="yaku_resumen.csv")
    p.add_argument("--agua-auto", action="store_true", help="umbral de agua por el método de Otsu")
    p.add_argument("--todas-orbitas", action="store_true")
    p.add_argument("--cobertura-min", type=float, default=0.5)
    p.add_argument("--sin-dem", action="store_true", help="no usar la máscara de altitud/pendiente")
    p.set_defaults(fn=cmd_procesar)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
