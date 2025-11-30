# drawings.py
"""
Lightweight drawings + takeoff helpers for civil_ai

Features:
- generate_plan_svg(kind, params): create a simple plan SVG for pad/beam/column/slab
- generate_elev_svg(kind, params): create a simple elevation SVG
- generate_dxf_stub(kind, params): stub DXF (text placeholder) — replace with real DXF writer if needed
- generate_drawings(kind, params, out_dir, write_reports): orchestration function used by backend endpoint
- estimate_takeoff_from_drawingparams(d): robust takeoff helper (pad side, bar counts, steel mass, concrete volume)
- estimate_bar_length_for_pad(d): small helper for pad bar length

Notes:
- This is intentionally simple and deterministic so engineers can visually confirm output quickly.
- If you have a DXF writer (ezdxf), replace the DXF stub with real code.
"""

import os
import math
import datetime
from typing import Dict, Any, Optional, Tuple

# constants
STEEL_DENSITY_KG_M3 = 7850.0
DEFAULT_OUT_DIR = os.environ.get("CIVIL_AI_DRAWINGS_DIR", "./reports/drawings")


# -------------------------
# Utility file helpers
# -------------------------
def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)
    return path


def write_text_file(path: str, content: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def timestamp_str():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


# -------------------------
# Simple SVG generators
# -------------------------
def _svg_header(width_px: int = 1000, height_px: int = 600, bg: str = "#ffffff") -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_px}" height="{height_px}" viewBox="0 0 {width_px} {height_px}" style="background:{bg};font-family:Arial,Helvetica,sans-serif">\n'

def _svg_footer() -> str:
    return "</svg>\n"


def generate_plan_svg(kind: str, params: Dict[str, Any], width_px: int = 1000, height_px: int = 600) -> str:
    """
    Generate a simple plan-view SVG. Supports 'footing'/'combined'/'beam'/'slab'/'column'.
    Uses drawing_params if present in params.
    """
    # Basic canvas
    svg = _svg_header(width_px, height_px, bg="#ffffff")
    pad_side_m = None
    if isinstance(params, dict):
        pad_side_m = params.get("pad_side_m") or params.get("assumed_side_m") or (params.get("width_mm") / 1000.0 if params.get("width_mm") else None)

    # helper coords
    cx = width_px // 2
    cy = height_px // 2
    scale = 200  # px per meter (approx) for visual scale; will adapt if pad large
    try:
        if pad_side_m:
            scale = min(250, max(80, int(200 / max(0.3, pad_side_m))))
    except Exception:
        scale = 200

    # Title
    svg += f'<text x="16" y="22" font-size="14" fill="#111">civil_ai — plan: {kind} — {timestamp_str()}</text>\n'

    if kind in ("footing", "combined"):
        side_m = float(pad_side_m or params.get("pad_side_m") or params.get("assumed_side_m") or 1.0)
        side_px = int(side_m * scale)
        # top-left of pad
        x = cx - side_px // 2
        y = cy - side_px // 2
        # pad rectangle
        svg += f'<rect x="{x}" y="{y}" width="{side_px}" height="{side_px}" fill="#f3f4f6" stroke="#0f172a" stroke-width="2"/>\n'
        # column(s)
        # single pad: place column at center; combined: draw two columns separated by spacing if provided
        if kind == "combined" and params.get("col1_b_mm") and params.get("col2_b_mm") and params.get("spacing_m"):
            b1 = max(0.15, (params.get("col1_b_mm") or 300) / 1000.0)
            b2 = max(0.15, (params.get("col2_b_mm") or 300) / 1000.0)
            spacing_m = float(params.get("spacing_m") or 1.0)
            # convert to px
            b1_px = int(b1 * scale)
            b2_px = int(b2 * scale)
            sep_px = int(spacing_m * scale)
            # place two columns horizontally centered
            cx1 = cx - sep_px // 2
            cx2 = cx + sep_px // 2
            cy_col = cy
            svg += f'<rect x="{cx1 - b1_px//2}" y="{cy_col - b1_px//2}" width="{b1_px}" height="{b1_px}" fill="#111827" />\n'
            svg += f'<rect x="{cx2 - b2_px//2}" y="{cy_col - b2_px//2}" width="{b2_px}" height="{b2_px}" fill="#111827" />\n'
            # strap (if provided)
            if params.get("strap") or params.get("include_strap"):
                strap_w_mm = params.get("strap", {}).get("width_mm") if params.get("strap") else params.get("strap_width_mm")
                strap_w_m = (strap_w_mm or 300) / 1000.0
                strap_h_px = int(0.1 * scale)
                sx1 = min(cx1, cx2) - 40
                sx = sx1
                sy = cy + b1_px//2 + 12
                svg += f'<rect x="{sx}" y="{sy}" width="{abs(cx2 - cx1) + 80}" height="{strap_h_px}" fill="#fde68a" stroke="#b45309" />\n'
                svg += f'<text x="{sx+6}" y="{sy+strap_h_px-4}" font-size="10" fill="#92400e">strap</text>\n'
        else:
            # single column central
            col_b = float(params.get("col_b_mm") or params.get("col1_b_mm") or 300) / 1000.0
            col_px = int(max(6, col_b * scale))
            svg += f'<rect x="{cx - col_px//2}" y="{cy - col_px//2}" width="{col_px}" height="{col_px}" fill="#111827" />\n'

        # dimensions text
        svg += f'<text x="{x + 6}" y="{y + 14}" font-size="12" fill="#111">pad {side_m:.3f} m × {side_m:.3f} m</text>\n'
    elif kind == "beam":
        # beam plan: long rectangle with reinforcement lines
        length_m = float(params.get("span_m") or 4.0)
        width_m = float((params.get("b_mm") or 300) / 1000.0)
        len_px = int(length_m * scale)
        wid_px = int(width_m * scale)
        x = cx - len_px // 2
        y = cy - wid_px // 2
        svg += f'<rect x="{x}" y="{y}" width="{len_px}" height="{wid_px}" fill="#f8fafc" stroke="#0f172a"/>\n'
        # bars: simple lines
        n_bars = int(params.get("n_bars") or 4)
        for i in range(n_bars):
            tx = x + 8 + i * max(10, (len_px - 16) // max(1, n_bars - 1))
            svg += f'<line x1="{tx}" y1="{y+4}" x2="{tx}" y2="{y+wid_px-4}" stroke="#0b1220" stroke-width="2"/>\n'
        svg += f'<text x="{x+6}" y="{y+14}" font-size="12" fill="#111">beam {length_m:.2f} m × {width_m*1000:.0f} mm</text>\n'
    elif kind == "slab":
        span = float(params.get("span_m") or 3.0)
        thr = float(params.get("thickness_mm") or 150) / 1000.0
        side_px = int(min(width_px - 120, span * scale))
        x = cx - side_px // 2
        y = cy - side_px // 2
        svg += f'<rect x="{x}" y="{y}" width="{side_px}" height="{side_px}" fill="#eef2ff" stroke="#0b1220"/>\n'
        # mesh lines approximate
        spacing_mm = float(params.get("spacing_mm") or params.get("bar_spacing_mm") or 200)
        spacing_px = max(6, int(spacing_mm / 1000.0 * scale))
        for sx in range(x + spacing_px, x + side_px, spacing_px):
            svg += f'<line x1="{sx}" y1="{y}" x2="{sx}" y2="{y+side_px}" stroke="#0b1220" stroke-width="1" opacity="0.5"/>\n'
        svg += f'<text x="{x+6}" y="{y+14}" font-size="12" fill="#111">slab {span:.2f} m (thk {thr*1000:.0f} mm)</text>\n'
    elif kind == "column":
        b = float(params.get("b_mm") or 300) / 1000.0
        d = float(params.get("d_mm") or 300) / 1000.0
        bw = int(b * scale)
        dh = int(d * scale)
        svg += f'<rect x="{cx - bw//2}" y="{cy - dh//2}" width="{bw}" height="{dh}" fill="#111827" />\n'
        svg += f'<text x="{cx - bw//2 + 6}" y="{cy - dh//2 + 14}" font-size="12" fill="#fff">column {b:.3f} × {d:.3f} m</text>\n'
    else:
        svg += f'<text x="{cx-80}" y="{cy}" font-size="12" fill="#111">kind not supported for plan</text>\n'

    svg += _svg_footer()
    return svg


def generate_elev_svg(kind: str, params: Dict[str, Any], width_px: int = 600, height_px: int = 400) -> str:
    """
    Simple elevation SVG (side view)
    """
    svg = _svg_header(width_px, height_px, bg="#ffffff")
    svg += f'<text x="10" y="20" font-size="12" fill="#111">elevation: {kind} — {timestamp_str()}</text>\n'
    cx = width_px // 2
    cy = height_px // 2

    if kind in ("footing", "combined"):
        depth_mm = float(params.get("pad_depth_mm") or params.get("pad_depth") or 400)
        pad_w_m = float(params.get("pad_side_m") or params.get("assumed_side_m") or (params.get("width_mm", 0) / 1000.0) or 1.0)
        pad_h_px = int(max(20, depth_mm / 1000.0 * 150))
        pad_w_px = int(min(width_px - 80, pad_w_m * 150))
        x = cx - pad_w_px // 2
        y = cy - pad_h_px // 2
        svg += f'<rect x="{x}" y="{y}" width="{pad_w_px}" height="{pad_h_px}" fill="#f3f4f6" stroke="#0f172a" />\n'
        # reinforcement approximate lines (two layers)
        svg += f'<line x1="{x+10}" y1="{y+10}" x2="{x+pad_w_px-10}" y2="{y+10}" stroke="#0b1220" stroke-width="2"/>\n'
        svg += f'<line x1="{x+10}" y1="{y+pad_h_px-10}" x2="{x+pad_w_px-10}" y2="{y+pad_h_px-10}" stroke="#0b1220" stroke-width="2"/>\n'
        svg += f'<text x="{x+6}" y="{y+14}" font-size="11" fill="#111">pad depth: {depth_mm:.0f} mm</text>\n'
    elif kind == "beam":
        depth_mm = float(params.get("h_mm") or 350)
        len_m = float(params.get("span_m") or 4.0)
        depth_px = int(depth_mm / 1000.0 * 180)
        len_px = int(min(width_px - 80, len_m * 120))
        x = cx - len_px // 2
        y = cy - depth_px // 2
        svg += f'<rect x="{x}" y="{y}" width="{len_px}" height="{depth_px}" fill="#fff7ed" stroke="#0f172a"/>\n'
        # top & bottom steel
        svg += f'<line x1="{x+8}" y1="{y+12}" x2="{x+len_px-8}" y2="{y+12}" stroke="#0b1220" stroke-width="2"/>\n'
        svg += f'<line x1="{x+8}" y1="{y+depth_px-12}" x2="{x+len_px-8}" y2="{y+depth_px-12}" stroke="#0b1220" stroke-width="2"/>\n'
        svg += f'<text x="{x+6}" y="{y+14}" font-size="11" fill="#111">beam depth: {depth_mm:.0f} mm</text>\n'
    else:
        svg += f'<text x="{cx-80}" y="{cy}" font-size="12" fill="#111">elev not supported</text>\n'

    svg += _svg_footer()
    return svg


# -------------------------
# DXF stub (text placeholder)
# -------------------------
def generate_dxf_stub(kind: str, params: Dict[str, Any]) -> str:
    """
    Simple textual DXF placeholder. Replace with real DXF writer for production (e.g. ezdxf).
    """
    lines = [
        "0",
        "SECTION",
        "2",
        "HEADER",
        "0",
        "ENDSEC",
        "0",
        "SECTION",
        "2",
        "ENTITIES",
        f"0\nTEXT\n1\nDrawing kind: {kind}\n2\nGenerated: {timestamp_str()}",
        "0",
        "ENDSEC",
        "0",
        "EOF",
    ]
    return "\n".join(lines)


# -------------------------
# Takeoff helpers
# -------------------------
def estimate_bar_length_for_pad(d: Dict[str, Any]) -> float:
    """
    Estimate average bar length (m) for a square pad given pad_side_m and cover.
    """
    pad_side_m = float(d.get("pad_side_m") or d.get("assumed_side_m") or (d.get("width_mm", 0) / 1000.0) or 0.0)
    cover_mm = float(d.get("cover_mm") or 25.0)
    # assume top & bottom layers: bar length = pad_side - 2*cover
    length_m = max(0.0, pad_side_m - 2.0 * (cover_mm / 1000.0))
    return length_m


def estimate_takeoff_from_drawingparams(d: Dict[str, Any]) -> Dict[str, Any]:
    """
    Given drawing_params produced by engine modules, estimate common takeoff numbers:
     - pad_side_m
     - pad_depth_mm
     - n_per_row, n_layers, total_bars
     - bar_length_m, total_steel_length_m, steel_mass_kg
     - concrete_volume_m3
    """

    try:
        pad_side_m = float(d.get("pad_side_m") or d.get("assumed_side_m") or 0.0)
        depth_mm = float(d.get("pad_depth_mm") or d.get("pad_depth") or d.get("depth_mm") or 400.0)
        cover_mm = float(d.get("cover_mm") or 25.0)
        bar_dia_mm = float(d.get("bar_dia_mm") or d.get("bar_dia") or d.get("bar_dia_mm") or 10.0)
        n_per_row = int(d.get("n_per_row") or d.get("n_bars") or 0)
        n_layers = int(d.get("n_layers") or 2)
        spacing_mm = float(d.get("spacing_mm") or d.get("target_spacing_mm") or 150.0)

        # estimate bar length
        bar_length_m = estimate_bar_length_for_pad(d)
        total_bars = n_per_row * n_layers

        # fallback calc if n_per_row not provided
        if n_per_row == 0 and spacing_mm > 0 and pad_side_m > 0:
            usable_mm = max(1.0, pad_side_m * 1000.0 - 2.0 * cover_mm)
            n_per_row = max(1, int(math.floor(usable_mm / spacing_mm)))
            total_bars = n_per_row * n_layers

        total_length_m = total_bars * bar_length_m
        # steel mass
        area_mm2 = math.pi * (bar_dia_mm ** 2) / 4.0
        area_m2 = area_mm2 / 1e6
        steel_volume_m3 = area_m2 * total_length_m
        steel_mass_kg = steel_volume_m3 * STEEL_DENSITY_KG_M3

        # concrete volume (square pad): pad_side^2 * depth (m)
        concrete_vol_m3 = (pad_side_m ** 2) * (depth_mm / 1000.0)

        return {
            "pad_side_m": round(pad_side_m, 3),
            "pad_depth_mm": round(depth_mm, 1),
            "n_per_row": int(n_per_row),
            "n_layers": int(n_layers),
            "total_bars": int(total_bars),
            "bar_length_m": round(bar_length_m, 3),
            "total_steel_length_m": round(total_length_m, 3),
            "steel_mass_kg": round(steel_mass_kg, 2),
            "concrete_volume_m3": round(concrete_vol_m3, 3),
            "bar_dia_mm": round(bar_dia_mm, 1),
            "spacing_mm": round(spacing_mm, 1),
        }
    except Exception as e:
        return {"error": "takeoff_estimate_failed", "exception": str(e)}


# -------------------------
# Orchestration for backend endpoint
# -------------------------
def generate_drawings(kind: str, params: Dict[str, Any], out_dir: Optional[str] = None, write_reports: bool = True) -> Dict[str, Any]:
    """
    Main entry to create drawing files. Returns a dict:
      { "files": { "svg_plan": "/reports/drawings/xxx.svg", "svg_elev": "...", "dxf": "..." }, "drawing_params": {...}, "takeoff": {...} }

    - kind: 'beam'|'slab'|'column'|'footing'|'combined'
    - params: drawing params or engine results drawing_params
    - out_dir: where to write files (default: ./reports/drawings)
    """
    out_dir = out_dir or DEFAULT_OUT_DIR
    ensure_dir(out_dir)

    stamp = timestamp_str()
    safe_kind = (kind or "unknown").replace("/", "_")

    # generate plan svg content
    plan_svg_txt = generate_plan_svg(safe_kind, params)
    plan_fname = f"{safe_kind}_plan_{stamp}.svg"
    plan_path = os.path.join(out_dir, plan_fname)
    write_text_file(plan_path, plan_svg_txt)

    # generate elevation svg content
    elev_svg_txt = generate_elev_svg(safe_kind, params)
    elev_fname = f"{safe_kind}_elev_{stamp}.svg"
    elev_path = os.path.join(out_dir, elev_fname)
    write_text_file(elev_path, elev_svg_txt)

    # generate DXF stub
    dxf_txt = generate_dxf_stub(safe_kind, params)
    dxf_fname = f"{safe_kind}_{stamp}.dxf"
    dxf_path = os.path.join(out_dir, dxf_fname)
    write_text_file(dxf_path, dxf_txt)

    # Build returned file URLs/paths — keep same shape your frontend expects
    # If your server serves /reports/ from project root, strip leading '.' ; keep both local path & web path
    web_base = "/reports/drawings"
    files = {}
    files["svg_plan"] = f"{web_base}/{plan_fname}"
    files["svg_elev"] = f"{web_base}/{elev_fname}"
    files["dxf"] = f"{web_base}/{dxf_fname}"

    # compute takeoff summary if drawing_params present
    drawing_params = params.get("drawing_params") if isinstance(params, dict) and params.get("drawing_params") else params
    takeoff = estimate_takeoff_from_drawingparams(drawing_params or {})

    out = {
        "files": files,
        "local_paths": {"svg_plan": plan_path, "svg_elev": elev_path, "dxf": dxf_path},
        "drawing_params": drawing_params or {},
        "takeoff": takeoff,
    }

    return out


# -------------------------
# Quick CLI test helper (optional)
# -------------------------
if __name__ == "__main__":  # quick local test
    sample_params = {
        "pad_side_m": 1.414,
        "pad_depth_mm": 500,
        "cover_mm": 25,
        "bar_dia_mm": 10,
        "n_per_row": 39,
        "n_layers": 2,
        "spacing_mm": 150,
    }
    r = generate_drawings("footing", sample_params, out_dir="./reports/drawings", write_reports=True)
    print("Generated:", r)