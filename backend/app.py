"""
Civil AI backend launcher with optional PDF generation endpoint.
- keeps beam/slab/column/footing endpoints
- normalizes report_paths returned by modules into /reports/<basename>
- adds POST /api/reports/generate_pdf which converts an existing HTML report
  (served under /reports/) into a PDF using WeasyPrint if available, otherwise
  falls back to wkhtmltopdf or headless Chrome/Chromium.
- includes a simple, dependency-light drawing generator fallback for quick SVG output.
- adds a combined/strap/eccentric footing endpoint (defensive: filters args to FootingInput).
"""

import os
import sys
import subprocess
import shutil
import inspect
from typing import Optional, Dict, Any
from datetime import datetime
from math import sqrt

from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

# try to import weasyprint (optional)
try:
    from weasyprint import HTML  # type: ignore
    WEASYPRINT_AVAILABLE = True
except Exception:
    WEASYPRINT_AVAILABLE = False

# make project root + backend available for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
BACKEND_DIR = os.path.dirname(__file__)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# attempt to import design modules (fail fast with clear message)
try:
    from beam_aci_flexure import (
        BeamACIInput,
        design_aci_beam,
        shear_check_udl,
        generate_report,
    )
except Exception as e:
    raise ImportError(f"Failed to import beam_aci_flexure: {e}")

try:
    from slab_aci import run_slab_design
except Exception as e:
    raise ImportError(f"Failed to import slab_aci: {e}")

try:
    from column_aci import ColumnACIInput, design_short_column
except Exception as e:
    raise ImportError(f"Failed to import column_aci: {e}")

# optional footing module
try:
    from footing import FootingInput, run_footing_design
except Exception:
    FootingInput = None
    run_footing_design = None

# optional external drawings module (if you create backend/drawings.py later)
try:
    # expected signature: generate_drawing_for_design(kind: str, params: dict, write_reports: bool) -> dict
    from drawings import generate_drawing_for_design  # type: ignore
except Exception:
    generate_drawing_for_design = None  # we'll provide a lightweight fallback below

DEFAULT_ALLOW_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
]

def _get_allow_origins() -> list[str]:
    raw = os.getenv("BACKEND_ALLOW_ORIGINS", "")
    if not raw:
        return DEFAULT_ALLOW_ORIGINS
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins or DEFAULT_ALLOW_ORIGINS


app = FastAPI(title="Civil AI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# mount static /reports if folder exists (and ensure folder exists)
REPORTS_DIR = os.path.join(PROJECT_ROOT, "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)
if os.path.isdir(REPORTS_DIR):
    app.mount("/reports", StaticFiles(directory=REPORTS_DIR), name="reports")


def normalize_report_paths(full_paths_dict: Optional[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    out: Dict[str, Optional[str]] = {}
    if not full_paths_dict:
        return out
    for k, v in full_paths_dict.items():
        if not v:
            out[k] = None
            continue
        # if the module already returned a served path, keep it
        s = str(v)
        if s.startswith("/reports/"):
            out[k] = s
            continue
        fname = os.path.basename(s)
        out[k] = f"/reports/{fname}"
    return out

# ---------------- simple drawing fallback (minimal, no deps) ----------------
def _ts():
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def _write_simple_svg(content: str, prefix: str) -> Dict[str,str]:
    fname = f"{prefix}_{_ts()}.svg"
    abs_path = os.path.join(REPORTS_DIR, fname)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(content)
    return {"svg": f"/reports/{fname}", "svg_abs": abs_path}

def _make_plan_svg(params: Dict[str,Any]) -> Dict[str,str]:
    # very simple SVG: rectangle for section and red circles for bars
    b = float(params.get("width_mm", params.get("b_mm", 300)))
    d = float(params.get("depth_mm", params.get("d_mm", 300)))
    cover = float(params.get("cover_mm", params.get("cover_mm", 25)))
    bar_d = float(params.get("bar_dia_mm", params.get("bar_dia_mm", 10)))
    n_bars = int(params.get("n_bars", params.get("n_bars", 4) or 4))

    scale = 0.5  # px per mm
    w_px = max(40, int(b * scale))
    h_px = max(40, int(d * scale))
    margin = 20
    svg_w = w_px + margin*2
    svg_h = h_px + margin*2

    rect_x = margin
    rect_y = margin

    # compute bar positions (along width)
    xs = []
    if n_bars > 0:
        for i in range(n_bars):
            xs.append(rect_x + (i+1)*(w_px/(n_bars+1)))

    # build svg string
    circles = ""
    r_px = max(2, int(bar_d * scale / 2))
    for x in xs:
        y_top = rect_y + int(cover*scale)
        y_bot = rect_y + h_px - int(cover*scale)
        circles += f'<circle cx="{x:.2f}" cy="{y_top:.2f}" r="{r_px}" fill="#c62828" />'
        circles += f'<circle cx="{x:.2f}" cy="{y_bot:.2f}" r="{r_px}" fill="#c62828" />'

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">
      <rect x="{rect_x}" y="{rect_y}" width="{w_px}" height="{h_px}" fill="none" stroke="#000" stroke-width="1"/>
      {circles}
      <text x="10" y="{svg_h-10}" font-size="12">Plan: {int(b)}×{int(d)} mm | bars: {n_bars}×{int(bar_d)} mm</text>
    </svg>'''
    return _write_simple_svg(svg, "plan")

def _make_elev_svg(params: Dict[str,Any]) -> Dict[str,str]:
    length_m = float(params.get("length_m", params.get("span_m", 3.0)))
    depth = float(params.get("depth_mm", params.get("pad_depth_mm", 400)))
    n_bars = int(params.get("n_bars", 6))
    scale = 0.03  # px per mm for elevation (compress)
    L_px = max(200, int(length_m * 1000 * scale))
    h_px = max(40, int(depth * scale))
    margin = 20
    svg_w = max(300, L_px + margin*2)
    svg_h = h_px + margin*2 + 40

    pad_x = margin + 20
    pad_w = svg_w - pad_x - margin - 20
    pad_y = margin + 20

    lines = ""
    for i in range(n_bars):
        y = pad_y + 10 + int(i*(h_px-20)/(n_bars-1)) if n_bars>1 else pad_y + h_px//2
        lines += f'<line x1="{pad_x+10}" y1="{y}" x2="{pad_x+pad_w-10}" y2="{y}" stroke="#c62828" stroke-width="2"/>'

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">
      <line x1="{margin}" y1="{margin+10}" x2="{svg_w-margin}" y2="{margin+10}" stroke="#000" />
      <rect x="{pad_x}" y="{pad_y}" width="{pad_w}" height="{h_px}" fill="#efefef" stroke="#000"/>
      {lines}
      <text x="10" y="{svg_h-10}" font-size="12">Elevation | L={length_m} m, depth={int(depth)} mm</text>
    </svg>'''
    return _write_simple_svg(svg, "elev")

def _fallback_generate_drawing(kind: str, params: Dict[str,Any], write_reports: bool = True) -> Dict[str, Optional[str]]:
    out = {}
    try:
        plan = _make_plan_svg(params)
        out["svg_plan"] = plan["svg"]
        out["svg_plan_abs"] = plan["svg_abs"]
    except Exception:
        out["svg_plan"] = None
    try:
        elev = _make_elev_svg(params)
        out["svg_elev"] = elev["svg"]
        out["svg_elev_abs"] = elev["svg_abs"]
    except Exception:
        out["svg_elev"] = None
    # DXF not generated by fallback
    out["dxf"] = None
    return out

# If external generate_drawing_for_design not present, use fallback
if generate_drawing_for_design is None:
    generate_drawing_for_design = _fallback_generate_drawing  # type: ignore

# ---------------- BEAM ----------------
class BeamRequest(BaseModel):
    span_m: float
    b_mm: float
    h_mm: float
    cover_mm: float
    dl_kN_per_m: float
    ll_kN_per_m: float
    fc_MPa: float
    fy_MPa: float

@app.post("/api/design/beam")
def design_beam(req: BeamRequest):
    try:
        inp = BeamACIInput(**req.dict())
        beam_res = design_aci_beam(inp)
        shear_res = shear_check_udl(inp, wu_kN_per_m=beam_res.factored_load_kN_per_m, d_mm=beam_res.effective_depth_mm)
        paths = generate_report(inp, beam_res, shear_res)
        served = normalize_report_paths(paths)
        return {"beam": beam_res.__dict__, "shear": shear_res, "report_paths": served}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ---------------- SLAB ----------------
class SlabRequest(BaseModel):
    span_m: float
    thickness_mm: float
    dl_kN_per_m2: float
    ll_kN_per_m2: float
    fc_MPa: float
    fy_MPa: float
    cover_mm: Optional[float] = 20
    bar_dia_mm: Optional[int] = 10
    write_reports: Optional[bool] = True

@app.post("/api/design/slab")
def design_slab(req: SlabRequest):
    try:
        params = req.dict()
        write_reports = bool(params.pop("write_reports", True))
        result = run_slab_design(params, write_reports=write_reports)
        if isinstance(result, dict) and "report_paths" in result:
            result["report_paths"] = normalize_report_paths(result.get("report_paths"))
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ---------------- COLUMN ----------------
class ColumnRequest(BaseModel):
    Pu_kN: float
    b_mm: float
    d_mm: float
    cover_mm: float
    fc_MPa: float
    fy_MPa: float
    unsupported_length_m: Optional[float] = 0.0

@app.post("/api/design/column")
def design_column(req: ColumnRequest):
    try:
        inp = ColumnACIInput(**req.dict())
        res = design_short_column(inp)
        results = res.__dict__ if hasattr(res, "__dict__") else res
        if isinstance(results, dict) and "report_paths" in results:
            results["report_paths"] = normalize_report_paths(results.get("report_paths"))
        return {"inputs": req.dict(), "results": results}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ---------------- FOOTING ----------------
class FootingRequest(BaseModel):
    Pu_kN: float
    col_b_mm: float
    col_d_mm: float
    soil_allow_kN_per_m2: float
    pad_depth_mm: float
    fc_MPa: float
    fy_MPa: float
    eccentricity_x_m: Optional[float] = 0.0
    eccentricity_y_m: Optional[float] = 0.0
    assumed_side_m: Optional[float] = None
    write_reports: Optional[bool] = True

@app.post("/api/design/footing")
def design_footing_endpoint(req: FootingRequest):
    if run_footing_design is None or FootingInput is None:
        raise HTTPException(status_code=500, detail="footing module missing - add backend/footing.py")
    try:
        params = req.dict()
        write_reports = bool(params.pop("write_reports", True))
        finp = FootingInput(**params)
        res = run_footing_design(finp, write_reports=write_reports)
        results = res.__dict__ if hasattr(res, "__dict__") else res
        if isinstance(results, dict) and "report_paths" in results:
            results["report_paths"] = normalize_report_paths(results.get("report_paths"))
        return {"inputs": req.dict(), "results": results}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ---------------- COMBINED / STRAP / ECCENTRIC FOOTING ----------------
class CombinedFootingRequest(BaseModel):
    # support legacy single Pu_kN OR two-column inputs (P1 & P2)
    # legacy single value
    Pu_kN: Optional[float] = None

    # two-column inputs (preferred for combined footing)
    P1_kN: Optional[float] = None
    P2_kN: Optional[float] = None
    col1_b_mm: Optional[float] = None
    col1_d_mm: Optional[float] = None
    col2_b_mm: Optional[float] = None
    col2_d_mm: Optional[float] = None
    spacing_m: Optional[float] = None  # distance between column centroids (m)

    # common footing inputs
    soil_allow_kN_per_m2: float
    pad_depth_mm: float
    fc_MPa: float
    fy_MPa: float

    # eccentricities (optional)
    eccentricity_x_m: Optional[float] = 0.0
    eccentricity_y_m: Optional[float] = 0.0

    # strap details (optional)
    include_strap: Optional[bool] = False
    strap_width_mm: Optional[float] = None
    strap_thickness_mm: Optional[float] = None
    strap_length_m: Optional[float] = None

    # general
    assumed_side_m: Optional[float] = None
    write_reports: Optional[bool] = True

@app.post("/api/design/combined_footing")
def design_combined_footing(req: CombinedFootingRequest):
    """
    Defensive endpoint for combined / strap / eccentrically loaded footing.
    It accepts either:
      - legacy single Pu_kN (behaves like isolated footing),
      - or two-column inputs P1_kN & P2_kN with column sizes & spacing.
    It computes a simple combined pad size (square pad per column) by required area = total_load / soil_allow.
    The endpoint will construct a FootingInput if available and call run_footing_design, otherwise returns computed sizing + drawing_params.
    """
    params = req.dict()
    write_reports = bool(params.pop("write_reports", True))

    # Determine loads
    P1 = params.get("P1_kN")
    P2 = params.get("P2_kN")
    Pu_legacy = params.get("Pu_kN")

    if P1 is not None and P2 is not None:
        total_load = float(P1) + float(P2)
        used_mode = "two_column"
    elif Pu_legacy is not None:
        total_load = float(Pu_legacy)
        used_mode = "single_legacy"
    else:
        # if nothing provided, error
        raise HTTPException(status_code=400, detail="Provide either P1_kN & P2_kN for combined footing or Pu_kN for legacy single footing.")

    # soil pressure based sizing (simple): required_area_m2 = total_load / soil_allow
    soil_allow = float(params.get("soil_allow_kN_per_m2", 150.0))
    if soil_allow <= 0:
        raise HTTPException(status_code=400, detail="soil_allow_kN_per_m2 must be positive")

    required_area_m2 = float(total_load) / soil_allow  # m^2

    # choose pad side (square) unless assumed_side_m given
    assumed_side_m = params.get("assumed_side_m")
    if assumed_side_m not in (None, "", False):
        try:
            pad_side_m = float(assumed_side_m)
            if pad_side_m <= 0:
                pad_side_m = None
        except Exception:
            pad_side_m = None
    else:
        pad_side_m = None

    if pad_side_m is None:
        # simple: side = sqrt(area), but ensure it's at least column width and spacing logic
        side = sqrt(max(required_area_m2, 0.0001))
        # ensure side is at least max of column widths (if provided)
        col1_w_m = float(params.get("col1_b_mm") or params.get("col_b_mm") or 0) / 1000.0
        col2_w_m = float(params.get("col2_b_mm") or 0) / 1000.0
        max_col_w_m = max(col1_w_m, col2_w_m, 0.0)
        # if two columns spaced close, keep side at least column width plus a little clearance
        pad_side_m = max(side, max_col_w_m + 0.1)

    # Build drawing params (expected by drawings.py):
    drawing_params: Dict[str, Any] = {}
    drawing_params["assumed_side_m"] = float(pad_side_m)
    drawing_params["pad_depth_mm"] = float(params.get("pad_depth_mm"))
    drawing_params["n_bars"] = 6
    drawing_params["bar_dia_mm"] = 10
    drawing_params["cover_mm"] = 25

    # Add strap object if requested
    if bool(params.get("include_strap")):
        strap_obj = {}
        if params.get("strap_width_mm"):
            strap_obj["width_mm"] = float(params.get("strap_width_mm"))
        if params.get("strap_thickness_mm"):
            strap_obj["thickness_mm"] = float(params.get("strap_thickness_mm"))
        if params.get("strap_length_m"):
            strap_obj["length_m"] = float(params.get("strap_length_m"))
        # if spacing provided, prefer that for strap length
        if params.get("spacing_m") and (not strap_obj.get("length_m")):
            strap_obj["length_m"] = float(params.get("spacing_m"))
        # include strap in drawing params
        drawing_params["strap"] = strap_obj

    # Add column info for drawing convenience
    drawing_params["col1_b_mm"] = params.get("col1_b_mm") or params.get("col_b_mm")
    drawing_params["col1_d_mm"] = params.get("col1_d_mm") or params.get("col_d_mm")
    drawing_params["col2_b_mm"] = params.get("col2_b_mm")
    drawing_params["col2_d_mm"] = params.get("col2_d_mm")
    drawing_params["spacing_m"] = params.get("spacing_m")

    # Prepare response skeleton
    results: Dict[str, Any] = {
        "mode": used_mode,
        "total_load_kN": total_load,
        "soil_allow_kN_per_m2": soil_allow,
        "required_area_m2": required_area_m2,
        "pad_side_m": pad_side_m,
        "drawing_params": drawing_params,
    }

    # If run_footing_design available and FootingInput exists, try to build a FootingInput
    if run_footing_design is not None and FootingInput is not None:
        try:
            # Attempt to filter fields that FootingInput expects
            sig = inspect.signature(FootingInput)
            allowed = set(sig.parameters.keys())

            # Create a dictionary intended for FootingInput:
            finp_dict: Dict[str, Any] = {}

            # For combined we pass aggregated Pu_kN (total_load) and assign assumed_side_m if available
            finp_dict["Pu_kN"] = total_load
            # use column width param name if in signature
            if "col_b_mm" in allowed:
                # choose a representative column width (use col1 if present)
                finp_dict["col_b_mm"] = float(params.get("col1_b_mm") or params.get("col_b_mm") or 300.0)
            if "col_d_mm" in allowed:
                finp_dict["col_d_mm"] = float(params.get("col1_d_mm") or params.get("col_d_mm") or 300.0)
            if "soil_allow_kN_per_m2" in allowed:
                finp_dict["soil_allow_kN_per_m2"] = soil_allow
            if "pad_depth_mm" in allowed:
                finp_dict["pad_depth_mm"] = float(params.get("pad_depth_mm"))
            if "fc_MPa" in allowed:
                finp_dict["fc_MPa"] = float(params.get("fc_MPa"))
            if "fy_MPa" in allowed:
                finp_dict["fy_MPa"] = float(params.get("fy_MPa"))
            if "eccentricity_x_m" in allowed:
                finp_dict["eccentricity_x_m"] = float(params.get("eccentricity_x_m") or 0.0)
            if "eccentricity_y_m" in allowed:
                finp_dict["eccentricity_y_m"] = float(params.get("eccentricity_y_m") or 0.0)
            # pass assumed side if known
            if "assumed_side_m" in allowed:
                finp_dict["assumed_side_m"] = float(pad_side_m)

            # Construct FootingInput
            finp = FootingInput(**finp_dict)

            # attach strap extras if present (won't harm if FootingInput is simple object)
            extras = ["include_strap", "strap_width_mm", "strap_thickness_mm", "strap_length_m", "eccentricity_x_m", "eccentricity_y_m", "col2_b_mm", "col2_d_mm", "spacing_m"]
            for ex in extras:
                if ex in params and params[ex] is not None:
                    try:
                        setattr(finp, ex, params[ex])
                    except Exception:
                        # ignore if attribute cannot be set
                        pass

            # call run_footing_design
            res = run_footing_design(finp, write_reports=write_reports)
            res_obj = res.__dict__ if hasattr(res, "__dict__") else res
            if isinstance(res_obj, dict) and "report_paths" in res_obj:
                res_obj["report_paths"] = normalize_report_paths(res_obj.get("report_paths"))
            results["engine_results"] = res_obj
            return {"inputs": req.dict(), "results": results}
        except Exception as e:
            # if footing module fails, return computed sizing + drawing_params and note the error
            results["engine_error"] = str(e)
            return {"inputs": req.dict(), "results": results}

    # If footing engine not available, just return computed sizing and drawing params
    return {"inputs": req.dict(), "results": results}


# ---------------- DRAWINGS endpoint ----------------
class DrawingRequest(BaseModel):
    kind: str  # "beam"|"slab"|"column"|"footing"|"combined"
    params: Dict[str, Any]
    write_reports: Optional[bool] = True

@app.post("/api/drawings/generate")
def drawings_generate(req: DrawingRequest):
    if generate_drawing_for_design is None:
        raise HTTPException(status_code=500, detail="drawings generator missing")
    try:
        out = generate_drawing_for_design(req.kind, req.params, write_reports=bool(req.write_reports))
        # normalize served paths if they look like filenames
        normalized = {}
        for k, v in (out or {}).items():
            if isinstance(v, str) and v.startswith("/reports/"):
                normalized[k] = v
            elif isinstance(v, str) and os.path.isfile(v):
                normalized[k] = f"/reports/{os.path.basename(v)}"
            else:
                normalized[k] = v
        return {"kind": req.kind, "params": req.params, "files": normalized}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ---------------- PDF generation endpoint (WeasyPrint primary, wkhtmltopdf & Chrome fallback) ----------------
@app.post("/api/reports/generate_pdf")
def generate_pdf_endpoint(payload: dict = Body(...)):
    """
    Payload:
      { "report_path": "/reports/beam_report_....html" }
    Returns:
      { "pdf_path": "/reports/beam_report_....pdf" } on success

    Order of attempts:
      1) WeasyPrint (python lib) if available
      2) system wkhtmltopdf binary (if on PATH)
      3) headless Google Chrome / Chromium (app or binary on PATH)
    """
    report_path = payload.get("report_path")
    if not report_path:
        raise HTTPException(status_code=400, detail="report_path required (e.g. /reports/beam_report_xxx.html)")

    if not str(report_path).startswith("/reports/"):
        raise HTTPException(status_code=400, detail="report_path must start with /reports/")

    report_fname = os.path.basename(report_path)
    abs_html = os.path.join(REPORTS_DIR, report_fname)
    if not os.path.isfile(abs_html):
        raise HTTPException(status_code=404, detail=f"HTML report not found on disk: {abs_html}")

    pdf_fname = os.path.splitext(report_fname)[0] + ".pdf"
    abs_pdf = os.path.join(REPORTS_DIR, pdf_fname)

    # 1) Try WeasyPrint
    if WEASYPRINT_AVAILABLE:
        try:
            print("[generate_pdf] Trying WeasyPrint...")
            HTML(filename=abs_html).write_pdf(abs_pdf)
            if os.path.isfile(abs_pdf):
                print(f"[generate_pdf] WeasyPrint created: {abs_pdf}")
                return {"pdf_path": f"/reports/{pdf_fname}"}
        except Exception as e:
            print(f"[generate_pdf] WeasyPrint error: {e}. Falling back...")

    # 2) Try wkhtmltopdf if present
    wk = shutil.which("wkhtmltopdf")
    if wk:
        try:
            print(f"[generate_pdf] Trying wkhtmltopdf at: {wk}")
            cmd = [wk, "--enable-local-file-access", abs_html, abs_pdf]
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
            if os.path.isfile(abs_pdf):
                print(f"[generate_pdf] wkhtmltopdf created: {abs_pdf}")
                return {"pdf_path": f"/reports/{pdf_fname}"}
            else:
                print("[generate_pdf] wkhtmltopdf ran but PDF missing.")
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode() if e.stderr else str(e)
            print(f"[generate_pdf] wkhtmltopdf error: {stderr}")
        except Exception as e:
            print(f"[generate_pdf] wkhtmltopdf exception: {e}")

    # 3) Try headless Chrome/Chromium (common mac app paths + PATH names)
    chrome_candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "google-chrome",
        "chrome",
        "chromium",
        "chromium-browser",
        "brave-browser",
    ]
    chrome_path = None
    for candidate in chrome_candidates:
        if os.path.exists(candidate):
            chrome_path = candidate
            break
        found = shutil.which(candidate)
        if found:
            chrome_path = found
            break

    if chrome_path:
        try:
            print(f"[generate_pdf] Trying headless Chrome at: {chrome_path}")
            file_url = f"file://{abs_html}"
            # prefer new headless flag where available, fallback to classic
            cmd_new = [
                chrome_path,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                f"--print-to-pdf={abs_pdf}",
                file_url,
            ]
            try:
                subprocess.run(cmd_new, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            except subprocess.CalledProcessError:
                # retry with classic headless flag
                cmd_old = [
                    chrome_path,
                    "--headless",
                    "--disable-gpu",
                    "--no-sandbox",
                    f"--print-to-pdf={abs_pdf}",
                    file_url,
                ]
                subprocess.run(cmd_old, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)

            if os.path.isfile(abs_pdf):
                print(f"[generate_pdf] Chrome produced: {abs_pdf}")
                return {"pdf_path": f"/reports/{pdf_fname}"}
            else:
                print("[generate_pdf] Chrome ran but PDF missing.")
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode() if e.stderr else str(e)
            print(f"[generate_pdf] Chrome error: {stderr}")
        except Exception as e:
            print(f"[generate_pdf] Chrome exception: {e}")

    # Nothing worked
    detail = (
        "PDF generation unavailable. Attempts: WeasyPrint (python), wkhtmltopdf (system), headless Chrome/Chromium. "
        "Please install one of the following on the machine running the server:\n"
        " - Fix WeasyPrint native deps (cairo/pango/gdk-pixbuf/libffi) and reinstall weasyprint in your venv,\n"
        " - Install wkhtmltopdf binary (note: brew 'cask' for wkhtmltopdf is discontinued; prefer downloading a compatible binary or use brew formula if available),\n"
        " - Install Google Chrome / Chromium so headless printing works.\n"
        "Check backend logs for detailed stderr output."
    )
    raise HTTPException(status_code=501, detail=detail)

# ---------------- root ----------------
@app.get("/")
def root():
    return {"status": "ok", "service": "Civil AI Backend", "weasyprint": WEASYPRINT_AVAILABLE}

if __name__ == "__main__":
    # Prefer running uvicorn from your venv (run from backend/ directory):
    #   python -m uvicorn app:app --reload --host 127.0.0.1 --port 8010
    host = os.getenv("BACKEND_HOST", "127.0.0.1")
    port = int(os.getenv("BACKEND_PORT", "8010"))
    uvicorn.run("app:app", host=host, port=port, reload=True)