# engine/footing.py
"""
Footing (isolated pad) design helper.

Simple implementation for dev/testing:
 - Calculates required bearing area from Pu and allowable soil.
 - Assumes square pad unless assumed_side_m provided.
 - Uses pad depth as provided (pad_depth_mm).
 - Provides a simple reinforcement estimate using a grid/spacing approach and writes a small report.

This module calls engine.punching.punching_check_aci and
engine.serviceability.crack_width_check for prototype checks.
"""
import os
import math
import json
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

# relative imports — keep these files together in the same package (engine/)
try:
    from . import punching
    from . import serviceability
except Exception:
    # fallback if imported as script (helps during quick tests)
    import punching  # type: ignore
    import serviceability  # type: ignore

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
REPORTS_DIR = os.path.join(PROJECT_ROOT, "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)


class FootingInput(BaseModel):
    Pu_kN: float
    col_b_mm: Optional[float] = None
    col_d_mm: Optional[float] = None
    soil_allow_kN_per_m2: float
    pad_depth_mm: float
    fc_MPa: float
    fy_MPa: float
    eccentricity_x_m: Optional[float] = 0.0
    eccentricity_y_m: Optional[float] = 0.0
    assumed_side_m: Optional[float] = None
    # optional designer preferences
    cover_mm: Optional[float] = 25.0
    bar_dia_mm: Optional[float] = 10.0
    target_spacing_mm: Optional[float] = 150.0  # desired bar spacing for grid


def _write_reports(prefix: str, inputs: dict, results: dict):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    txt_name = f"{prefix}_report_{ts}.txt"
    html_name = f"{prefix}_report_{ts}.html"
    txt_path = os.path.join(REPORTS_DIR, txt_name)
    html_path = os.path.join(REPORTS_DIR, html_name)

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("Footing design report\n")
        f.write("=====================\n\n")
        f.write("Inputs:\n")
        f.write(json.dumps(inputs, indent=2))
        f.write("\n\nResults:\n")
        f.write(json.dumps(results, indent=2))

    with open(html_path, "w", encoding="utf-8") as f:
        f.write("<html><body style='font-family:Arial,Helvetica,sans-serif;padding:16px;'><h1>Footing design report</h1>\n")
        f.write("<h2>Inputs</h2><pre>{}</pre>\n".format(json.dumps(inputs, indent=2)))
        f.write("<h2>Results</h2><pre>{}</pre>\n".format(json.dumps(results, indent=2)))
        f.write("</body></html>")

    # return filesystem paths (API layer will normalise to /reports/<file>)
    return {"txt": txt_path, "html": html_path}


def run_footing_design(inp: FootingInput, write_reports: bool = True):
    """
    Very simple footing design logic for prototyping.

    Returns a results dict which includes drawing_params, punching and serviceability checks.
    """
    # --- defaults & sanity ---
    col_b_mm = float(inp.col_b_mm) if inp.col_b_mm is not None else 300.0
    col_d_mm = float(inp.col_d_mm) if inp.col_d_mm is not None else 300.0
    cover_mm = float(inp.cover_mm) if getattr(inp, "cover_mm", None) is not None else 25.0
    bar_dia_mm = float(inp.bar_dia_mm) if getattr(inp, "bar_dia_mm", None) is not None else 10.0
    spacing_mm = float(inp.target_spacing_mm) if getattr(inp, "target_spacing_mm", None) is not None else 150.0

    # convert units
    Pu_N = float(inp.Pu_kN) * 1000.0
    q_allow = float(inp.soil_allow_kN_per_m2) * 1000.0

    if q_allow <= 0:
        raise ValueError("soil_allow_kN_per_m2 must be > 0")

    A_req_m2 = Pu_N / q_allow  # m^2
    if A_req_m2 <= 0:
        raise ValueError("computed required area <= 0")

    # assumed side (square) or compute from required area
    if inp.assumed_side_m and float(inp.assumed_side_m) > 0:
        side_m = float(inp.assumed_side_m)
        A_used_m2 = side_m * side_m
    else:
        side_m = math.sqrt(A_req_m2)
        A_used_m2 = A_req_m2

    # effective pad depth (mm provided)
    depth_mm = float(inp.pad_depth_mm)
    depth_m = depth_mm / 1000.0

    # simple eccentricity adjustment (keeps prototype behavior)
    ecc_effect = 1.0
    ecc = max(abs(inp.eccentricity_x_m or 0), abs(inp.eccentricity_y_m or 0))
    if ecc > 0 and side_m > 0:
        ecc_effect = 1.0 + min(0.5, ecc / side_m)  # cap effect to +50%

    # final used area
    A_final_m2 = A_used_m2 * ecc_effect
    A_final_mm2 = A_final_m2 * 1e6

    # crude steel estimate: grid spacing and bar dia to compute provided steel area
    side_mm = side_m * 1000.0
    usable_width_mm = max(1.0, side_mm - 2.0 * cover_mm)

    if spacing_mm <= 0:
        spacing_mm = 150.0
    # number of bars along one row such that spacing <= requested spacing
    n_per_row = max(2, int(math.floor(usable_width_mm / spacing_mm)))
    if n_per_row < 2:
        n_per_row = 2

    n_layers = 2  # top & bottom
    n_bars_total = n_per_row * n_layers

    single_bar_area_mm2 = math.pi * (bar_dia_mm / 2.0) ** 2
    provided_As_mm2 = n_bars_total * single_bar_area_mm2

    # required steel by area% method (compatibility)
    steel_ratio = 0.003
    As_req_mm2 = max(100.0, A_final_mm2 * steel_ratio)

    # coarse attempt to meet As_req by adding bars
    if provided_As_mm2 < As_req_mm2:
        missing = As_req_mm2 - provided_As_mm2
        add_bars = int(math.ceil(missing / single_bar_area_mm2))
        add_per_row = int(math.ceil(add_bars / n_layers))
        n_per_row = n_per_row + add_per_row
        n_bars_total = n_per_row * n_layers
        provided_As_mm2 = n_bars_total * single_bar_area_mm2

    results = {
        "A_req_m2": round(A_req_m2, 6),
        "side_m": round(side_m, 3),
        "A_used_m2": round(A_used_m2, 6),
        "eccentricity_m": round(ecc, 3),
        "ecc_effect_factor": round(ecc_effect, 3),
        "A_final_m2": round(A_final_m2, 6),
        "pad_depth_mm": depth_mm,
        "As_req_mm2": round(As_req_mm2, 2),
        "bar_dia_mm": bar_dia_mm,
        "spacing_mm": round(spacing_mm, 1),
        "n_per_row": int(n_per_row),
        "n_layers": int(n_layers),
        "n_bars_total": int(n_bars_total),
        "provided_As_mm2": round(provided_As_mm2, 2),
        "notes": {
            "method": "prototype/grid reinforcement -> choose bar dia & spacing -> adjust to meet crude As_req",
            "assumptions": "square pad, two layers (top+bottom) used for counting; improve later for detailed rebar layout."
        }
    }

    # drawing params for drawings module
    drawing_info = {
        "pad_side_m": round(side_m, 3),
        "pad_depth_mm": depth_mm,
        "cover_mm": cover_mm,
        "bar_dia_mm": bar_dia_mm,
        "n_per_row": int(n_per_row),
        "n_layers": int(n_layers),
        "spacing_mm": round(spacing_mm, 1),
    }
    results["drawing_params"] = drawing_info

    # --- punching shear check (prototype) ---
    try:
        punch = punching.punching_check_aci(
            Pu_kN=float(inp.Pu_kN),
            col_b_mm=float(col_b_mm),
            col_d_mm=float(col_d_mm),
            pad_depth_mm=float(depth_mm),
            fc_MPa=float(inp.fc_MPa),
        )
    except Exception as e:
        punch = {"error": f"punching check failed: {e}"}

    # --- serviceability: crude crack width using spacing/cover and assumed steel stress ---
    try:
        spacing_used = results.get("spacing_mm", 150)
        cover_used = drawing_info.get("cover_mm", 25)
        # approximate steel stress for serviceability indicator: half of fy (heuristic)
        stress_steel = float(inp.fy_MPa) / 2.0 if getattr(inp, "fy_MPa", None) else 200.0

        crack = serviceability.crack_width_check(
            bar_spacing_mm=float(spacing_used),
            cover_mm=float(cover_used),
            stress_steel_MPa=float(stress_steel),
        )
    except Exception as e:
        crack = {"error": f"crack width check failed: {e}"}

    results["punching"] = punch
    results["serviceability"] = crack

    if write_reports:
        rp = _write_reports("footing", inp.dict(), results)
        results["report_paths"] = rp

    return results