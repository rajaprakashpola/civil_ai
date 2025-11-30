"""
engine/combined_footing.py

Helper that orchestrates combined footing design:
 - Supports single-pad legacy mode (Pu_kN + assumed_side_m)
 - Supports two-column combined (P1 & P2) with optional strap
 - Calls engine.footing.run_footing_design for pad sizing and reinforcement
 - Attaches punching and serviceability results and a basic takeoff summary

Output format:
{
  "inputs": {...},
  "results": {
     "mode": "single" | "two_column",
     "total_load_kN": ...,
     "required_area_m2": ...,
     "pad_side_m": ...,
     "drawing_params": {...},
     "engine_results": {...},
     "punching": {...},
     "serviceability": {...},
     "takeoff": {...}
  }
}
"""

from typing import Dict, Any, Optional
import math

# relative imports
try:
    from .footing import run_footing_design, FootingInput
    from . import punching as punching_module
    from . import serviceability as serviceability_module
    from . import drawings as drawings_module
except Exception:
    # fallback if running as script
    import footing as run_footing_design_module  # type: ignore
    from importlib import import_module
    punching_module = import_module("punching")
    serviceability_module = import_module("serviceability")
    drawings_module = import_module("drawings")
    run_footing_design = run_footing_design_module.run_footing_design

def design_combined(params: Dict[str, Any], write_reports: bool = True) -> Dict[str, Any]:
    p = dict(params)
    mode = "single" if p.get("Pu_kN") else "two_column"
    out_inputs = p.copy()

    if mode == "single":
        # use existing footing engine for single pad
        inp = FootingInput(
            Pu_kN = float(p.get("Pu_kN")),
            col_b_mm = float(p.get("col_b_mm") or 300.0),
            col_d_mm = float(p.get("col_d_mm") or 300.0),
            soil_allow_kN_per_m2 = float(p.get("soil_allow_kN_per_m2") or 150.0),
            pad_depth_mm = float(p.get("pad_depth_mm") or 500.0),
            fc_MPa = float(p.get("fc_MPa") or 25.0),
            fy_MPa = float(p.get("fy_MPa") or 415.0),
            eccentricity_x_m = float(p.get("eccentricity_x_m") or 0.0),
            eccentricity_y_m = float(p.get("eccentricity_y_m") or 0.0),
            assumed_side_m = float(p.get("assumed_side_m")) if p.get("assumed_side_m") else None,
            cover_mm = float(p.get("cover_mm") or 25.0),
            bar_dia_mm = float(p.get("bar_dia_mm") or 10.0),
            target_spacing_mm = float(p.get("target_spacing_mm") or 150.0),
        )
        results, = run_footing_design(inp, write_reports=write_reports) if isinstance(run_footing_design(inp), tuple) else (run_footing_design(inp, write_reports=write_reports),)
        # run_footing_design returns results (proto returns tuple earlier; safe-guard)
        engine_results = results
        total_load_kN = float(p.get("Pu_kN"))
        pad_side_m = engine_results.get("side_m") or (engine_results.get("drawing_params",{}).get("pad_side_m"))
    else:
        # two-column combined
        P1 = float(p.get("P1_kN") or 0.0)
        P2 = float(p.get("P2_kN") or 0.0)
        total_load_kN = P1 + P2
        soil_allow = float(p.get("soil_allow_kN_per_m2") or 150.0)

        # compute required area and pad side (square approximate)
        required_area_m2 = (total_load_kN * 1000.0) / (soil_allow * 1000.0)  # simple division -> gives m2
        pad_side_m = math.sqrt(required_area_m2)
        # prepare a FootingInput for internal run
        inp = FootingInput(
            Pu_kN = total_load_kN,
            col_b_mm = float(p.get("col1_b_mm") or 300.0),
            col_d_mm = float(p.get("col1_d_mm") or 300.0),
            soil_allow_kN_per_m2 = soil_allow,
            pad_depth_mm = float(p.get("pad_depth_mm") or 500.0),
            fc_MPa = float(p.get("fc_MPa") or 25.0),
            fy_MPa = float(p.get("fy_MPa") or 415.0),
            eccentricity_x_m = float(p.get("eccentricity_x_m") or 0.0),
            eccentricity_y_m = float(p.get("eccentricity_y_m") or 0.0),
            assumed_side_m = float(pad_side_m),
            cover_mm = float(p.get("cover_mm") or 25.0),
            bar_dia_mm = float(p.get("bar_dia_mm") or 10.0),
            target_spacing_mm = float(p.get("target_spacing_mm") or 150.0),
        )
        results, = run_footing_design(inp, write_reports=write_reports) if isinstance(run_footing_design(inp), tuple) else (run_footing_design(inp, write_reports=write_reports),)
        engine_results = results
        # attach strap info if included
    # attach punching and serviceability (use modules)
    punch = {}
    service = {}
    try:
        punch = punching_module.punching_check_aci(
            Pu_kN = total_load_kN,
            col_b_mm = float(p.get("col1_b_mm") or p.get("col_b_mm") or 300.0),
            col_d_mm = float(p.get("col1_d_mm") or p.get("col_d_mm") or 300.0),
            pad_depth_mm = float(p.get("pad_depth_mm") or 500.0),
            fc_MPa = float(p.get("fc_MPa") or 25.0),
            phi = float(p.get("phi") or 0.75),
            eccentricity_x_m = float(p.get("eccentricity_x_m") or 0.0),
            eccentricity_y_m = float(p.get("eccentricity_y_m") or 0.0),
            column_location = str(p.get("column_location") or "interior"),
        )
    except Exception as e:
        punch = {"error": f"punching check failed: {e}"}

    try:
        # approximate serviceability: use spacing + cover from engine results or params
        spacing_used = engine_results.get("spacing_mm") or p.get("target_spacing_mm") or p.get("spacing_mm") or 150
        cover_used = engine_results.get("drawing_params", {}).get("cover_mm") or p.get("cover_mm") or 25
        stress_steel = float(p.get("fy_MPa") or 415.0) / 2.0
        service = serviceability_module.crack_width_check(
            bar_spacing_mm = float(spacing_used),
            cover_mm = float(cover_used),
            stress_steel_MPa = float(stress_steel),
            bar_dia_mm = float(p.get("bar_dia_mm") or 12.0)
        )
    except Exception as e:
        service = {"error": f"serviceability check failed: {e}"}

    # add a minimal takeoff summary using drawings helper if available
    takeoff = {}
    try:
        draw_params = engine_results.get("drawing_params", {})
        takeoff = drawings_module.estimate_takeoff_from_drawingparams(draw_params)
    except Exception:
        takeoff = {}

    results_out = {
        "mode": mode,
        "total_load_kN": round(float(total_load_kN), 3),
        "soil_allow_kN_per_m2": float(p.get("soil_allow_kN_per_m2") or p.get("soil_allow") or 150.0),
        "required_area_m2": round(float(engine_results.get("A_final_m2", engine_results.get("A_req_m2", 0.0))), 6),
        "pad_side_m": round(float(engine_results.get("side_m") or pad_side_m), 3),
        "drawing_params": engine_results.get("drawing_params", {}),
        "engine_results": engine_results,
        "punching": punch,
        "serviceability": service,
        "takeoff": takeoff,
    }

    return {"inputs": out_inputs, "results": results_out}