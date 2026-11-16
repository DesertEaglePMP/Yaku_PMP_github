# YAKU App v7 – Measuring the water stored in mountain wetlands with NISAR radar

**Team YAKU – HIDROTECH · NASA Space Apps Challenge 2026 · Challenge: "Dancing with SARs" (Earth Science)**

- CEO: Jaime Joseph Mañuico Mendoza
- Project Manager: Noemi Justina Tomaylla Berrocal
- Presentation website (YAKU Web): https://deserteaglepmp.github.io

YAKU ("water" in Quechua) uses NASA–ISRO **NISAR** L-band radar to map high-Andean peatlands (*bofedales*)
and other mountain wetlands, track their wetness through the seasons and estimate how much water they store.
It works for **any area, region or country**. Pilot site: the headwaters of the Cachi River (Ayacucho, Peru).

- **YAKU App (installable on any phone, no app store):** https://deserteaglepmp.github.io/Yaku_PMP_github/
- **Language:** English by default, full Spanish with the **ES** button.
- **Processing tool:** `Yaku_v07.py` (Windows: double-click `INICIAR_YAKU_v07.bat`)
- **Project report (Spanish):** `docs/YAKU_Proyecto_NASA_SpaceApps_2026_v3.docx`

## What's in the app (v7)
| Tab | What it does |
|---|---|
| **Explore map** (opens first) | Layered NISAR map (water & wetland, moisture, false colour, HH, HV), timeline, before/after slider, KPIs, wetland "sponge" diagram, validation against a reference inventory, per-audience guidance |
| **Live monitor** | Daily water balance for **any site** (enter name, coordinates, elevation, area) with NASA POWER climate and NASA CMR NISAR passes; reserve traffic light |
| **NISAR data** | How to download and process real data; load `yaku_*.json`; results table (copy as CSV) |
| **About the program** | Problem, solution and 5-step workflow |
| **Who it's for** | Researchers, public agencies, mining companies, communities & water managers |
| **How it works** | Data-flow diagram, radar scattering diagram, formulas and caveats |
| **Business model** | Plans, canvas, lean cost structure (technology US$ 0), editable 3-year projection, sustainability and SDGs |
| **NASA resources** | Every NASA / partner-agency resource and how YAKU uses it |
| **Team & AI** | Team YAKU – HIDROTECH, roadmap, AI-use statement, sources |

## How it works
1. Search and download calibrated NISAR L2 **GCOV** products (HH/HV, γ⁰) from ASF for one orbit (`asf_search`).
2. Crop, multilook (e.g. 60 m), convert to dB; mask terrain with the **Copernicus DEM** (≥ 3,800 m, slope ≤ 15 %).
3. Classify open water (Otsu threshold on HH) and saturated wetland (HH ≥ −9 dB); compute a relative wetness index.
4. Convert to volumes: wetland area × peat thickness × water content + open-water area × depth.
5. Daily monitor: water balance with NASA POWER (rain PRECTOTCORR, temperature T2M, radiation ALLSKY_SFC_SW_DWN;
   Makkink evapotranspiration), nudged to NISAR wetness whenever processed NISAR data are loaded.

A GitHub Action (`.github/workflows/actualizar_datos.yml`) refreshes `datos/monitor.json` daily for the pilot site,
so the monitor also works offline. Another Action (`procesar_nisar.yml`) downloads and processes NISAR in the cloud.

## Install on a phone (no Google Play / App Store)
YAKU is a Progressive Web App (PWA): it installs from the browser and works offline after the first visit.
Tap **📲 Install app** in the app for step-by-step help and a QR code.
- **Android (Chrome):** open the link → **Install app** (or menu ⋮ → *Install app*).
- **iPhone / iPad (Safari):** open the link → **Share** → **Add to Home Screen**.
- **Computer (Chrome / Edge):** install icon in the address bar.

## Run the processing tool
```
python Yaku_v07.py          # interactive menu: 1 test, 2 list, 3 download, 4 process, 5 area
```
Missing Python libraries are installed automatically (Python 3.12 or 3.13 recommended).
Downloading needs a free NASA Earthdata token (https://urs.earthdata.nasa.gov → Generate Token).
**Never commit `.earthdata_token`** (it is listed in `.gitignore`).
Put the `yaku_<area>.json` produced by option 4 in `datos/` and the app loads it automatically.

## Data
- NASA–ISRO NISAR L2 GCOV (PROVISIONAL), ASF DAAC – https://search.asf.alaska.edu/#/?dataset=NISAR
- NASA POWER – https://power.larc.nasa.gov/ · NASA CMR – https://cmr.earthdata.nasa.gov/
- Copernicus DEM GLO-30 (ESA) – https://registry.opendata.aws/copernicus-dem/
- Pilot-site reference: peatland inventory of the upper Cachi basin, 2013 – https://repositorioslatinoamericanos.uchile.cl/handle/2250/6587904

## Use of AI
Code and text drafts were produced with the assistance of **Claude (Anthropic)** and were reviewed, tested and
edited by team YAKU – HIDROTECH. All diagrams in the app are drawn as code (SVG); no AI-generated images.
The demo scene in the app is synthetic.

## License
MIT
