# beam_aci_flexure.py
from dataclasses import dataclass
from math import pi, ceil, sqrt
import os
from datetime import datetime

@dataclass
class BeamACIInput:
    span_m: float
    b_mm: float
    h_mm: float
    cover_mm: float
    dl_kN_per_m: float
    ll_kN_per_m: float
    fc_MPa: float
    fy_MPa: float

@dataclass
class BeamACIResult:
    factored_load_kN_per_m: float
    factored_Mu_kNm: float
    effective_depth_mm: float
    required_As_mm2: float
    bar_dia_mm: int
    n_bars: int
    provided_As_mm2: float
    utilization_percent: float

def design_aci_beam(data: BeamACIInput) -> BeamACIResult:
    """
    Simplified ACI flexure design (v1)
    Units: span in m, b/h/cover in mm, loads in kN/m, fc and fy in MPa (N/mm^2)
    """
    # Effective depth
    d = float(data.h_mm) - float(data.cover_mm) - 10.0
    if d <= 0:
        raise ValueError("Effective depth <= 0. Check section depth and cover.")

    # Factored load (ACI combo) and moment (simply supported UDL)
    wu = 1.2 * float(data.dl_kN_per_m) + 1.6 * float(data.ll_kN_per_m)  # kN/m
    Mu = wu * (float(data.span_m) ** 2) / 8.0  # kN-m

    # Convert Mu to N-mm
    Mu_Nmm = Mu * 1e6

    # Lever arm approx (jd ~ 0.9d)
    jd = 0.9 * d  # mm

    # Flexural steel area (As)
    As_req = Mu_Nmm / (0.87 * float(data.fy_MPa) * jd)

    # Minimum steel (practical default 0.18% of b*d)
    As_min = 0.0018 * float(data.b_mm) * d
    if As_req < As_min:
        As_req = As_min

    # Provide bars - choose a practical bar diameter & count
    standard_dias = [12, 16, 20, 25, 32]  # mm
    chosen_dia = None
    chosen_n = None
    chosen_prov = None

    for dia in standard_dias:
        area_bar = pi * (dia ** 2) / 4.0
        n = max(2, ceil(As_req / area_bar))  # minimum 2 bars preferred
        # choose compact arrangement with up to 6 bars
        if n <= 6:
            chosen_dia = int(dia)
            chosen_n = int(n)
            chosen_prov = n * area_bar
            break

    if chosen_dia is None:
        dia = standard_dias[-1]
        area_bar = pi * (dia ** 2) / 4.0
        chosen_n = int(ceil(As_req / area_bar))
        chosen_dia = int(dia)
        chosen_prov = chosen_n * area_bar

    utilization = (As_req / chosen_prov) * 100.0 if chosen_prov and chosen_prov > 0 else 0.0

    return BeamACIResult(
        factored_load_kN_per_m=round(wu, 3),
        factored_Mu_kNm=round(Mu, 3),
        effective_depth_mm=round(d, 2),
        required_As_mm2=round(As_req, 2),
        bar_dia_mm=chosen_dia,
        n_bars=chosen_n,
        provided_As_mm2=round(chosen_prov, 2),
        utilization_percent=round(utilization, 2),
    )


# --------------------------
# Shear check helper (ACI-style simplified)
# --------------------------
def shear_check_udl(data: BeamACIInput, wu_kN_per_m: float, d_mm: float):
    """
    Simplified shear check for simply-supported beam with UDL.
    Returns a dict with results and recommended stirrup spacing (mm) if needed.
    """
    # 1) Shear force at support for simply-supported UDL: Vu = wu * L / 2 (kN)
    Vu_kN = float(wu_kN_per_m) * float(data.span_m) / 2.0
    Vu_N = Vu_kN * 1000.0  # N

    # 2) Concrete shear strength Vc (N) - simplified ACI form:
    Vc_N = 0.17 * sqrt(float(data.fc_MPa)) * float(data.b_mm) * float(d_mm)

    # 3) Strength reduction phi for shear (ACI) ~ 0.75
    phi_shear = 0.75
    phiVc_N = phi_shear * Vc_N

    result = {
        "Vu_kN": round(Vu_kN, 3),
        "Vc_kN": round(Vc_N / 1000.0, 3),
        "phiVc_kN": round(phiVc_N / 1000.0, 3),
        "needs_shear_reinf": False,
        "recommended_stirrup_dia_mm": None,
        "recommended_spacing_mm": None,
    }

    # 4) If Vu <= phiVc -> no vertical shear reinforcement required
    if Vu_N <= phiVc_N:
        return result

    # 5) Otherwise compute required shear reinforcement (Av/s)
    Asv_one_leg = (pi * (8 ** 2) / 4.0)   # area of 8mm bar (mm^2)
    Asv_total = 2 * Asv_one_leg          # 2-legged stirrup
    Av_over_s = (Vu_N - phiVc_N) / (0.87 * float(data.fy_MPa) * float(d_mm))  # mm^2 per mm

    if Av_over_s <= 0:
        spacing_mm = min(0.75 * float(d_mm), 300.0)
    else:
        spacing_mm = Asv_total / Av_over_s

    spacing_limit = min(0.75 * float(d_mm), 300.0)
    spacing_mm = min(spacing_mm, spacing_limit)

    result.update({
        "needs_shear_reinf": True,
        "recommended_stirrup_dia_mm": 8,
        "recommended_spacing_mm": round(spacing_mm, 1),
        "Av_over_s_mm2_per_mm": round(Av_over_s, 9),
    })

    return result


# --------------------------
# Simple report generator (text + HTML stub)
# --------------------------
def generate_report(data: BeamACIInput, beam_res: BeamACIResult, shear_res: dict, outname_prefix="beam_report"):
    os.makedirs("reports", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    txt_path = f"reports/{outname_prefix}_{ts}.txt"
    html_path = f"reports/{outname_prefix}_{ts}.html"

    # Plain text report
    lines = []
    lines.append("BEAM DESIGN REPORT")
    lines.append(f"Generated: {datetime.now().isoformat()}")
    lines.append("")
    lines.append("INPUTS:")
    lines.append(f" Span = {data.span_m} m")
    lines.append(f" Section = {data.b_mm} x {data.h_mm} mm (cover {data.cover_mm} mm)")
    lines.append(f" Loads (DL, LL) = {data.dl_kN_per_m}, {data.ll_kN_per_m} kN/m")
    lines.append(f" Materials: fc'={data.fc_MPa} MPa, fy={data.fy_MPa} MPa")
    lines.append("")
    lines.append("RESULTS (Flexure):")
    lines.append(f" Factored UDL = {beam_res.factored_load_kN_per_m} kN/m")
    lines.append(f" Factored Mu = {beam_res.factored_Mu_kNm} kN·m")
    lines.append(f" Effective depth d = {beam_res.effective_depth_mm} mm")
    lines.append(f" Required As = {beam_res.required_As_mm2} mm²")
    lines.append(f" Provided = {beam_res.n_bars}×{beam_res.bar_dia_mm} mm → {beam_res.provided_As_mm2} mm²")
    lines.append(f" Utilization = {beam_res.utilization_percent} %")
    lines.append("")
    lines.append("SHEAR CHECK:")
    for k, v in shear_res.items():
        lines.append(f" {k}: {v}")
    lines.append("")
    lines.append("NOTES:")
    lines.append("- This is a simplified automated check. Always cross-check for special cases.")
    lines.append("- Designer retains responsibility for final detailing.")

    with open(txt_path, "w") as f:
        f.write("\n".join(lines))

    # Simple HTML (easy to convert later to PDF)
    html_lines = ["<html><body style='font-family:Arial,Helvetica,sans-serif;padding:16px;'><h1>Beam Design Report</h1>"]
    html_lines += [f"<p><b>Generated:</b> {datetime.now().isoformat()}</p>"]
    html_lines += ["<h2>Inputs</h2><ul>"]
    html_lines += [f"<li>Span: {data.span_m} m</li>", f"<li>Section: {data.b_mm} x {data.h_mm} mm (cover {data.cover_mm} mm)</li>"]
    html_lines += [f"<li>Loads (DL, LL): {data.dl_kN_per_m}, {data.ll_kN_per_m} kN/m</li>"]
    html_lines += [f"<li>Materials: fc'={data.fc_MPa} MPa, fy={data.fy_MPa} MPa</li>"]
    html_lines += ["</ul><h2>Results (Flexure)</h2><ul>"]
    html_lines += [f"<li>Factored UDL: {beam_res.factored_load_kN_per_m} kN/m</li>",
                   f"<li>Factored Mu: {beam_res.factored_Mu_kNm} kN·m</li>",
                   f"<li>Effective depth d: {beam_res.effective_depth_mm} mm</li>",
                   f"<li>Required As: {beam_res.required_As_mm2} mm²</li>",
                   f"<li>Provided: {beam_res.n_bars}×{beam_res.bar_dia_mm} mm → {beam_res.provided_As_mm2} mm²</li>",
                   f"<li>Utilization: {beam_res.utilization_percent} %</li>"]
    html_lines += ["</ul><h2>Shear Check</h2><ul>"]
    for k, v in shear_res.items():
        html_lines += [f"<li>{k}: {v}</li>"]
    html_lines += ["</ul><p><i>Auto-generated summary. Cross-check before construction.</i></p></body></html>"]

    with open(html_path, "w") as f:
        f.write("\n".join(html_lines))

    return {"txt": txt_path, "html": html_path}