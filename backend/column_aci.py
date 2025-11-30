# column_aci.py
"""
Simplified ACI-style short-column design (axial).
- Units: inputs in mm / MPa / kN / m (as indicated)
"""

from dataclasses import dataclass
from math import pi, ceil
from typing import Dict, Any, Optional

STANDARD_BAR_DIAMETERS_MM = [10, 12, 16, 20, 25, 32]


@dataclass
class ColumnACIInput:
    Pu_kN: float                    # factored axial load (kN)
    b_mm: float                     # column width mm
    d_mm: float                     # column depth mm
    cover_mm: float                 # clear cover mm
    fc_MPa: float                   # concrete strength MPa
    fy_MPa: float                   # steel yield MPa
    unsupported_length_m: float = 0.0  # unsupported length (m) for slenderness check (optional)
    tie_dia_mm: Optional[int] = None
    min_steel_percent: float = 0.01   # 1% default minimum steel


@dataclass
class ColumnACIResult:
    Ag_mm2: float
    As_req_mm2: float
    As_provided_mm2: float
    bar_dia_mm: int
    n_bars: int
    phiPn_kN: float
    utilization_percent: float
    short_column: bool
    notes: Dict[str, Any]


def area_of_bar_mm2(d_mm: float) -> float:
    return pi * (d_mm ** 2) / 4.0


def _is_short_column(inp: ColumnACIInput) -> (bool, Dict[str, float]):
    b = float(inp.b_mm)
    d = float(inp.d_mm)
    L = max(0.0, inp.unsupported_length_m) * 1000.0  # convert to mm
    small = min(b, d)
    r = small / (12 ** 0.5) if small > 0 else 0.0
    kl_over_r = (L / r) if r > 0 else float("inf")
    short = kl_over_r <= 12.0
    return short, {"L_mm": L, "r_mm": r, "kl_over_r": kl_over_r}


def design_short_column(inp: ColumnACIInput) -> ColumnACIResult:
    b = float(inp.b_mm)
    d = float(inp.d_mm)
    Ag = b * d                         # mm^2
    Pu_N = float(inp.Pu_kN) * 1000.0   # N

    fc = float(inp.fc_MPa)   # N/mm2
    fy = float(inp.fy_MPa)   # N/mm2

    phi = 0.65

    short, slender_info = _is_short_column(inp)

    denom = phi * (fy - 0.85 * fc)
    numerator = Pu_N - phi * 0.85 * fc * Ag

    notes = {
        "formula": "phi*(0.85*fc*(Ag-As) + fy*As) >= Pu",
        "slender_check": slender_info,
        "phi_used": phi,
    }

    if denom <= 0:
        raise ValueError(
            "Unsolvable for As with current materials (fy <= 0.85*fc). "
            "Increase cross-section area or use different steel/concrete."
        )

    As_req_mm2 = numerator / denom
    if As_req_mm2 < 0:
        As_req_mm2 = 0.0

    As_min = max(0.0, inp.min_steel_percent * Ag)
    if As_req_mm2 < As_min:
        As_req_mm2 = As_min
        notes["min_steel_enforced_mm2"] = As_min

    chosen_bar = None
    chosen_n = None
    chosen_As_prov = None

    for dia in STANDARD_BAR_DIAMETERS_MM:
        a_bar = area_of_bar_mm2(dia)
        n_bars = int(ceil(As_req_mm2 / a_bar))
        if n_bars < 4:
            n_bars = 4
        As_prov = n_bars * a_bar
        if As_prov >= As_req_mm2:
            chosen_bar = int(dia)
            chosen_n = int(n_bars)
            chosen_As_prov = As_prov
            break

    if chosen_bar is None:
        dia = STANDARD_BAR_DIAMETERS_MM[-1]
        a_bar = area_of_bar_mm2(dia)
        n_bars = int(ceil(As_req_mm2 / a_bar))
        chosen_bar = int(dia)
        chosen_n = int(n_bars)
        chosen_As_prov = n_bars * a_bar

    phiPn_N = phi * (0.85 * fc * (Ag - chosen_As_prov) + fy * chosen_As_prov)
    phiPn_kN = phiPn_N / 1000.0
    utilization = (float(inp.Pu_kN) / phiPn_kN) * 100.0 if phiPn_kN > 0 else 999.9

    result = ColumnACIResult(
        Ag_mm2=Ag,
        As_req_mm2=round(As_req_mm2, 3),
        As_provided_mm2=round(chosen_As_prov, 3),
        bar_dia_mm=chosen_bar,
        n_bars=int(chosen_n),
        phiPn_kN=round(phiPn_kN, 3),
        utilization_percent=round(utilization, 2),
        short_column=short,
        notes=notes,
    )

    return result


if __name__ == "__main__":
    example = ColumnACIInput(
        Pu_kN=2000.0,
        b_mm=400.0,
        d_mm=400.0,
        cover_mm=40.0,
        fc_MPa=30.0,
        fy_MPa=420.0,
        unsupported_length_m=3.0,
    )

    print("Running example short-column design (conservative)...")
    try:
        res = design_short_column(example)
        import json
        print(json.dumps(res.__dict__, indent=2))
    except Exception as e:
        print("Error:", e)