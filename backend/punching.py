"""
engine/punching.py

ACI-style punching shear check (improved prototype).
Returns a detailed dict with:
 - inputs
 - results: Vu, v_u (MPa), v_c (MPa), phiVc (N), utilization_percent, punching_safe
 - recommended shear reinforcement if needed: Av/s (mm2/mm), recommended_stirrup_dia_mm, spacing_mm
Notes:
 - This is still a simplified implementation suitable for an engineering app prototype.
 - Handles square or rectangular column area, computes critical perimeter at d/2,
   supports corner/edge vs interior detection via column location fields (optional).
"""

from typing import Dict, Any, Optional
import math

def _area_of_bar_mm2(dia_mm: float) -> float:
    return math.pi * (dia_mm ** 2) / 4.0

def punching_check_aci(
    Pu_kN: float,
    col_b_mm: float,
    col_d_mm: float,
    pad_depth_mm: float,
    fc_MPa: float,
    phi: float = 0.75,
    column_location: Optional[str] = "interior",  # "interior" | "edge" | "corner" (affects perimeter multiplier)
    eccentricity_x_m: Optional[float] = 0.0,
    eccentricity_y_m: Optional[float] = 0.0,
    alpha_factor: Optional[float] = 1.0,  # user override multiplier for conservative checks
) -> Dict[str, Any]:
    """
    Perform a simplified punching shear check.
    Units:
      - Pu_kN : applied factored axial load (kN)
      - col_b_mm, col_d_mm : column cross-section (mm)
      - pad_depth_mm : overall pad depth (mm) (used to compute d_eff)
      - fc_MPa : concrete compressive strength (MPa)
    Returns a dictionary with detailed results.
    """

    # Basic conversions and sanity
    Pu_N = float(Pu_kN) * 1000.0
    b = max(1.0, float(col_b_mm))
    d = max(1.0, float(col_d_mm))
    pad_depth = max(1.0, float(pad_depth_mm))

    # Effective depth: conservative assumption: cover + 10mm clear + bar diameter ~ use 0.8*pad_depth
    d_eff_mm = max(10.0, 0.8 * pad_depth)

    # Area of column loaded face (mm2)
    col_area_mm2 = b * d

    # Critical perimeter at d/2 around loaded area (approx)
    # For rectangular column, perimeter = 2*(b + d) + 8*(d_eff) ??? Standard: b0 = 2*(b + d) + 4*pi*d_eff -- but simpler:
    # More accepted approach: b0 = 2*(b + d) + 4 * d_eff (approx offset d/2 around)
    # We'll compute b0 as rectangle expanded by d_eff on each side: perimeter = 2*(b + d + 4*d_eff/2) -> 2*(b + d + d_eff*2) => approx
    # Simpler widely used: b0 = 2*(b + d) + 8 * d_eff/2 -> reduce to 2*(b + d) + 4*d_eff
    b0_mm = 2.0 * (b + d) + 4.0 * d_eff_mm

    # Adjust perimeter for corner/edge behaviour (ACI uses different perimeters for interior vs edge vs corner)
    loc = (column_location or "interior").lower()
    if loc == "corner":
        perimeter_factor = 0.5  # corner cuts effective perimeter roughly in half - conservative
    elif loc == "edge":
        perimeter_factor = 0.75
    else:
        perimeter_factor = 1.0

    b0_eff_mm = b0_mm * perimeter_factor

    # Shear stress demand v_u (in MPa) = Vu / (b0 * d)
    Vu_N = Pu_N  # for pad, using axial as punching demand (conservative). For eccentric loads, demand may increase — include simple ecc factor:
    # Simple eccentricity amplification: if ecc exists relative to pad side, amplify Vu demand a bit
    ecc = max(abs(eccentricity_x_m or 0.0), abs(eccentricity_y_m or 0.0))
    ecc_amp = 1.0 + min(0.5, ecc / max(0.01, (math.sqrt(b * d) / 1000.0)))  # simple heuristic
    Vu_adj_N = Vu_N * ecc_amp * float(alpha_factor)

    # v_u (MPa)
    v_u_MPa = Vu_adj_N / (b0_eff_mm * d_eff_mm) / 1e6 * 1e6  # Keep units consistent -> Vu/(b0*d) gives N/mm2 -> MPa
    # v_c according to ACI simplified: 0.33*sqrt(fc) (MPa) for slabs; for footings using slab-type behavior we keep same baseline
    v_c_MPa = 0.33 * math.sqrt(max(1.0, float(fc_MPa)))

    # phi Vc (N)
    Vc_N = v_c_MPa * (b0_eff_mm * d_eff_mm)
    phiVc_N = float(phi) * Vc_N

    safe = phiVc_N >= Vu_adj_N
    util_percent = (Vu_adj_N / phiVc_N) * 100.0 if phiVc_N > 0 else 999.9

    # If not safe, recommend shear reinforcement (Av/s)
    shear_reinf = {
        "needs_shear_reinf": False,
        "Av_over_s_mm2_per_mm": None,
        "recommended_stirrup_dia_mm": None,
        "recommended_spacing_mm": None,
        "assumptions": "Two-legged 8mm stirrups assumed for recommendation unless specified otherwise."
    }

    if not safe:
        # Required shear capacity to cover deficit
        deficit_N = Vu_adj_N - phiVc_N
        # target stress to be carried by shear reinforcement: use 0.87*fy*(Av/s)*d
        # => Av/s = deficit_N / (0.87 * fy * d_eff)
        # We'll provide generic Av/s and then map to standard stirrup sizes & spacing.
        # Use fy default 415 MPa if not passed via inputs (caller may supply if needed)
        fy_assumed_MPa = 415.0
        Av_over_s = deficit_N / (0.87 * fy_assumed_MPa * d_eff_mm)  # mm2 per mm

        # Recommend 2-legged stirrups of 8mm or 10mm and compute spacing
        for stir_d in (10, 8):
            Asv_one_leg = _area_of_bar_mm2(stir_d)
            Asv_two_leg = 2.0 * Asv_one_leg
            if Av_over_s <= 0:
                spacing_mm = min(0.75 * d_eff_mm, 300.0)
            else:
                spacing_mm_calc = Asv_two_leg / Av_over_s
                spacing_mm = min(spacing_mm_calc, min(0.75 * d_eff_mm, 300.0))
            # accept spacing not less than 75 mm
            if spacing_mm >= 75:
                shear_reinf.update({
                    "needs_shear_reinf": True,
                    "Av_over_s_mm2_per_mm": round(Av_over_s, 9),
                    "recommended_stirrup_dia_mm": stir_d,
                    "recommended_spacing_mm": round(spacing_mm, 1),
                })
                break
        # fallback if loop didn't break
        if not shear_reinf["needs_shear_reinf"]:
            shear_reinf.update({
                "needs_shear_reinf": True,
                "Av_over_s_mm2_per_mm": round(Av_over_s, 9),
                "recommended_stirrup_dia_mm": 10,
                "recommended_spacing_mm": int(min(0.75 * d_eff_mm, 300.0))
            })

    out = {
        "inputs": {
            "Pu_kN": float(Pu_kN),
            "col_b_mm": b,
            "col_d_mm": d,
            "pad_depth_mm": pad_depth,
            "d_eff_mm": round(d_eff_mm, 2),
            "fc_MPa": float(fc_MPa),
            "phi": float(phi),
            "column_location": loc,
            "eccentricity_x_m": float(eccentricity_x_m or 0.0),
            "eccentricity_y_m": float(eccentricity_y_m or 0.0),
            "alpha_factor": float(alpha_factor or 1.0),
        },
        "results": {
            "Vu_N": float(Vu_N),
            "Vu_adj_N": round(float(Vu_adj_N), 2),
            "v_u_MPa": round(float(v_u_MPa), 6),
            "vc_MPa": round(float(v_c_MPa), 6),
            "Vc_N": round(float(Vc_N), 2),
            "phiVc_N": round(float(phiVc_N), 2),
            "utilization_percent": round(float(util_percent), 2),
            "punching_safe": bool(safe),
            "b0_mm": round(b0_mm, 2),
            "b0_eff_mm": round(b0_eff_mm, 2),
            "d_eff_mm": round(d_eff_mm, 2),
            "notes": "Improved prototype punching check. Replace with full code per ACI/IS for production."
        }
    }

    out["results"].update(shear_reinf)
    return out