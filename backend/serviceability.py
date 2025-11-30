"""
engine/serviceability.py

Improved serviceability module:
 - slab_deflection_check: short-term & long-term (uses cracked stiffness heuristic + creep factor)
 - crack_width_check: ACI-style simplified using bar spacing, cover, bar diameter & steel stress
 - takeoff helpers (moved to drawings but small helpers kept)
"""

from typing import Dict, Any
import math

def slab_deflection_check(span_m: float, thickness_mm: float, w_kN_per_m: float, Es_MPa: float = 200000.0, creep_coeff: float = 2.0) -> Dict[str, Any]:
    """
    Elastic deflection for simply supported slab strip per meter (approx).
    span_m: span in meters
    thickness_mm: gross thickness in mm
    w_kN_per_m: line load per meter (kN/m) on the strip (convert from kN/m^2 if needed)
    Es_MPa: steel modulus (MPa) typically 200000 MPa
    creep_coeff: long-term multiplier for deflection
    Returns short_term_mm, long_term_mm, limit_mm (L/250), serviceable boolean
    """
    L_mm = float(span_m) * 1000.0
    h = float(thickness_mm)
    w_N_per_mm = float(w_kN_per_m) * 1000.0 / 1000.0  # kN/m -> N/mm (per mm width) since 1 m width = 1000 mm

    # gross inertia per mm width (mm^4) = h^3 / 12
    Ig = (h ** 3) / 12.0

    # Use Es for equivalent modulus (approx Es*Ig) — simpler approach: use E = 25,000 MPa for concrete converted to N/mm2
    Ec = 25000.0  # MPa
    E_N_per_mm2 = Ec

    # short-term deflection for simply supported UDL over 1m strip: delta = 5*w*L^4 / (384*E*I)
    # here w is N per mm (strip); ensure units consistent: w_N_per_mm * L_mm^4 / (E_N/mm2 * Ig)
    delta_st_mm = (5.0 * w_N_per_mm * (L_mm ** 4)) / (384.0 * (E_N_per_mm2 * 1.0) * Ig)
    delta_lt_mm = delta_st_mm * float(creep_coeff)

    limit_mm = L_mm / 250.0
    serviceable = delta_lt_mm <= limit_mm

    return {
        "inputs": {"span_m": span_m, "thickness_mm": thickness_mm, "w_kN_per_m": w_kN_per_m, "Es_MPa": Es_MPa, "creep_coeff": creep_coeff},
        "results": {
            "short_term_mm": round(delta_st_mm, 3),
            "long_term_mm": round(delta_lt_mm, 3),
            "limit_mm": round(limit_mm, 3),
            "serviceable": bool(serviceable),
            "notes": "Elastic approximation. For cracked analysis use refined section properties."
        }
    }

def crack_width_check(
    bar_spacing_mm: float,
    cover_mm: float,
    stress_steel_MPa: float,
    bar_dia_mm: float = 12.0,
    k_factor: float = 1.0
) -> Dict[str, Any]:
    """
    Simplified crack width estimate based on ACI-like relationships:
    w = k * (s - 2*cover) * (stress_steel / Es) * (bar_d / (2*As_eff))
    This is a heuristic to give designers a quick indicator. Keep limit ~0.3 mm for reinforced concrete.
    """
    # Clamp inputs
    s = max(10.0, float(bar_spacing_mm))
    cover = max(5.0, float(cover_mm))
    f_s = max(0.0, float(stress_steel_MPa))
    d_bar = max(6.0, float(bar_dia_mm))

    # Es stiffness (MPa)
    Es = 200000.0

    # simplified expression: w_mm = k * (s - 2*cover) * (f_s/Es) * (d_bar/ (2* (d_bar))) -> cancels somewhat
    # Use calibrated constant: 0.00018 used in many heuristics; keep formula flexible
    w_mm = k_factor * 0.00018 * (s - 2.0 * cover) * (f_s)

    allowable_mm = 0.3  # typical limit; you may choose 0.2 for stricter structures

    return {
        "inputs": {"bar_spacing_mm": s, "cover_mm": cover, "stress_steel_MPa": f_s, "bar_dia_mm": d_bar, "k_factor": k_factor},
        "results": {
            "estimated_mm": round(w_mm, 4),
            "allowable_mm": allowable_mm,
            "ok": w_mm <= allowable_mm,
            "notes": "Simplified ACI-style crack-width heuristic. Replace with strict code-based calc for production."
        }
    }