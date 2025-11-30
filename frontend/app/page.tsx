"use client";
import React, { useEffect, useState } from "react";

/**
 * page.tsx — improved UI remake
 * - clearer layout, components for forms and results
 * - dedicated Punching & Serviceability cards
 * - keeps the same backend interaction and payload logic as your original file
 *
 * Drop into your project to replace the previous page.tsx.
 */

/* ----------------------------- Helpers & Types ---------------------------- */

type Tab = "beam" | "slab" | "column" | "footing" | "combined";

const backend = "http://127.0.0.1:8010";

function fmt(n: any, digits = 2) {
  if (n === null || n === undefined) return "-";
  if (typeof n === "number") return n.toFixed(digits);
  const parsed = Number(String(n).replace(",", "."));
  return Number.isFinite(parsed) ? parsed.toFixed(digits) : String(n);
}

function findKeyRecursive(obj: any, keyName: string): any | null {
  if (!obj || typeof obj !== "object") return null;
  if (keyName in obj) return obj[keyName];
  for (const k of Object.keys(obj)) {
    const v = obj[k];
    if (v && typeof v === "object") {
      const found = findKeyRecursive(v, keyName);
      if (found !== null && found !== undefined) return found;
    }
  }
  return null;
}

function findReportPaths(obj: any): { txt?: string; html?: string; pdf?: string } | null {
  if (!obj || typeof obj !== "object") return null;
  if (obj.report_paths && typeof obj.report_paths === "object") return obj.report_paths;
  for (const k of Object.keys(obj)) {
    const val = obj[k];
    if (val && typeof val === "object") {
      const found = findReportPaths(val);
      if (found) return found;
    }
  }
  return null;
}

function buildUrl(pathOrUrl?: string | null) {
  if (!pathOrUrl) return null;
  if (/^https?:\/\//.test(pathOrUrl)) return pathOrUrl;
  const p = pathOrUrl.startsWith("/") ? pathOrUrl : `/${pathOrUrl}`;
  return `${backend}${p}`;
}

/* ------------------------------ Small UI bits ----------------------------- */

const pageStyles: React.CSSProperties = {
  padding: 28,
  maxWidth: 1100,
  margin: "0 auto",
  color: "white",
  fontFamily: "Inter, system-ui, -apple-system, 'Segoe UI', Roboto",
};

const cardStyleBase: React.CSSProperties = {
  background: "#071025",
  border: "1px solid #162433",
  borderRadius: 10,
  padding: 14,
  boxShadow: "0 6px 18px rgba(2,6,23,0.6)",
};

const labelStyle: React.CSSProperties = { display: "block", marginBottom: 8 };
const inputStyle: React.CSSProperties = { width: "100%", padding: 8, borderRadius: 6, border: "1px solid #203040", background: "#071020", color: "white" };
const sectionTitleStyle: React.CSSProperties = { marginBottom: 12, fontSize: 16, fontWeight: 700 };

/* ------------------------------ Main Component ---------------------------- */

export default function HomePage() {
  const [tab, setTab] = useState<Tab>("beam");

  // forms (strings to allow typing)
  const [beamForm, setBeamForm] = useState<any>({
    span_m: "4",
    b_mm: "300",
    h_mm: "350",
    cover_mm: "30",
    dl_kN_per_m: "12",
    ll_kN_per_m: "10",
    fc_MPa: "30",
    fy_MPa: "420",
  });

  const [slabForm, setSlabForm] = useState<any>({
    span_m: "3",
    thickness_mm: "150",
    dl_kN_per_m2: "5",
    ll_kN_per_m2: "3",
    fc_MPa: "30",
    fy_MPa: "420",
    cover_mm: "20",
    bar_dia_mm: "10",
  });

  const [colForm, setColForm] = useState<any>({
    Pu_kN: "250",
    b_mm: "300",
    d_mm: "300",
    cover_mm: "30",
    fc_MPa: "25",
    fy_MPa: "415",
    unsupported_length_m: "2",
  });

  const [footingForm, setFootingForm] = useState<any>({
    Pu_kN: "300",
    col_b_mm: "300",
    col_d_mm: "300",
    soil_allow_kN_per_m2: "150",
    pad_depth_mm: "400",
    fc_MPa: "25",
    fy_MPa: "415",
    eccentricity_x_m: "0",
    eccentricity_y_m: "0",
    assumed_side_m: "",
  });

  const [combinedForm, setCombinedForm] = useState<any>({
    single_mode: false,
    Pu_kN: "300",
    P1_kN: "200",
    P2_kN: "150",
    col1_b_mm: "300",
    col1_d_mm: "300",
    col2_b_mm: "300",
    col2_d_mm: "300",
    spacing_m: "1.0",
    soil_allow_kN_per_m2: "150",
    pad_depth_mm: "500",
    fc_MPa: "25",
    fy_MPa: "415",
    eccentricity_x_m: "0.0",
    eccentricity_y_m: "0.0",
    assumed_side_m: "",
    include_strap: false,
    strap_width_mm: "300",
    strap_thickness_mm: "150",
    strap_length_m: "1.0",
  });

  const [loading, setLoading] = useState(false);
  const [pdfBusy, setPdfBusy] = useState(false);
  const [drawingBusy, setDrawingBusy] = useState(false);
  const [drawingFiles, setDrawingFiles] = useState<any>(null);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState("");
  const [pdfSupported, setPdfSupported] = useState<boolean | null>(null);

  /* --------------------------- lifecycle: backend probe --------------------------- */
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const r = await fetch(`${backend}/`);
        if (!r.ok) throw new Error("backend unreachable");
        const j = await r.json();
        if (!mounted) return;
        setPdfSupported(Boolean(j.weasyprint));
      } catch {
        if (!mounted) return;
        setPdfSupported(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  /* ------------------------------ small helpers ------------------------------ */

  function handleChange(setter: any) {
    return (e: any) => {
      const { name, value, type, checked } = e.target;
      if (type === "checkbox") {
        setter((s: any) => ({ ...s, [name]: checked }));
      } else {
        setter((s: any) => ({ ...s, [name]: value }));
      }
    };
  }

  function normalizePayload(form: Record<string, any>) {
    const out: Record<string, any> = {};
    for (const k of Object.keys(form)) {
      const v = form[k];
      if (typeof v === "boolean") {
        out[k] = v;
        continue;
      }
      if (v === "" || v === null || v === undefined) {
        out[k] = null;
        continue;
      }
      if (typeof v === "number") {
        out[k] = v;
        continue;
      }
      const cleaned = String(v).replace(",", ".").trim();
      const n = Number(cleaned);
      out[k] = Number.isFinite(n) ? n : null;
    }
    return out;
  }

  async function postJSON(path: string, body: any) {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const res = await fetch(`${backend}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const txt = await res.text();
        try {
          const j = JSON.parse(txt);
          throw new Error(j.detail ?? JSON.stringify(j));
        } catch {
          throw new Error(txt || `HTTP ${res.status}`);
        }
      }
      const json = await res.json();
      setResult(json);
      setDrawingFiles(null);
    } catch (err: any) {
      setError(err?.message ?? "Error");
    } finally {
      setLoading(false);
    }
  }

  /* -------------------------- submit handlers (same endpoints) -------------------------- */

  const submitBeam = (e: any) => {
    e.preventDefault();
    postJSON("/api/design/beam", normalizePayload(beamForm));
  };
  const submitSlab = (e: any) => {
    e.preventDefault();
    postJSON("/api/design/slab", { ...normalizePayload(slabForm), write_reports: true });
  };
  const submitColumn = (e: any) => {
    e.preventDefault();
    postJSON("/api/design/column", normalizePayload(colForm));
  };
  const submitFooting = (e: any) => {
    e.preventDefault();
    postJSON("/api/design/footing", { ...normalizePayload(footingForm), write_reports: true });
  };
  const submitCombined = (e: any) => {
    e.preventDefault();
    const p = normalizePayload(combinedForm);
    if (p.single_mode) {
      const payload: any = {
        Pu_kN: p.Pu_kN,
        soil_allow_kN_per_m2: p.soil_allow_kN_per_m2,
        pad_depth_mm: p.pad_depth_mm,
        fc_MPa: p.fc_MPa,
        fy_MPa: p.fy_MPa,
        eccentricity_x_m: p.eccentricity_x_m,
        eccentricity_y_m: p.eccentricity_y_m,
        assumed_side_m: p.assumed_side_m,
        include_strap: p.include_strap,
        strap_width_mm: p.strap_width_mm,
        strap_thickness_mm: p.strap_thickness_mm,
        strap_length_m: p.strap_length_m,
      };
      postJSON("/api/design/combined_footing", { ...payload, write_reports: true });
    } else {
      const payload: any = {
        P1_kN: p.P1_kN,
        P2_kN: p.P2_kN,
        col1_b_mm: p.col1_b_mm,
        col1_d_mm: p.col1_d_mm,
        col2_b_mm: p.col2_b_mm,
        col2_d_mm: p.col2_d_mm,
        spacing_m: p.spacing_m,
        soil_allow_kN_per_m2: p.soil_allow_kN_per_m2,
        pad_depth_mm: p.pad_depth_mm,
        fc_MPa: p.fc_MPa,
        fy_MPa: p.fy_MPa,
        eccentricity_x_m: p.eccentricity_x_m,
        eccentricity_y_m: p.eccentricity_y_m,
        assumed_side_m: p.assumed_side_m,
        include_strap: p.include_strap,
        strap_width_mm: p.strap_width_mm,
        strap_thickness_mm: p.strap_thickness_mm,
        strap_length_m: p.strap_length_m,
      };
      postJSON("/api/design/combined_footing", { ...payload, write_reports: true });
    }
  };

  /* ----------------------------- PDF & drawing helpers ---------------------------- */

  async function generatePdfAndDownload(htmlPath: string) {
    setPdfBusy(true);
    setError("");
    try {
      const res = await fetch(`${backend}/api/reports/generate_pdf`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ report_path: htmlPath }),
      });
      if (!res.ok) {
        const txt = await res.text();
        try {
          const j = JSON.parse(txt);
          throw new Error(j.detail ?? JSON.stringify(j));
        } catch {
          throw new Error(txt || `HTTP ${res.status}`);
        }
      }
      const json = await res.json();
      const pdfPath = json.pdf_path;
      if (!pdfPath) throw new Error("No pdf_path returned");
      const pdfRes = await fetch(`${backend}${pdfPath}`);
      if (!pdfRes.ok) throw new Error("Failed to download PDF file from server");
      const blob = await pdfRes.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = pdfPath.split("/").pop() || "report.pdf";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      setError(String(err?.message ?? err));
    } finally {
      setPdfBusy(false);
    }
  }

  async function generateDrawing(kind: string, params: any) {
    setDrawingBusy(true);
    setError("");
    setDrawingFiles(null);
    try {
      const res = await fetch(`${backend}/api/drawings/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind, params, write_reports: true }),
      });
      if (!res.ok) {
        const txt = await res.text();
        try {
          const j = JSON.parse(txt);
          throw new Error(j.detail ?? JSON.stringify(j));
        } catch {
          throw new Error(txt || `HTTP ${res.status}`);
        }
      }
      const json = await res.json();
      setDrawingFiles(json.files || null);
    } catch (err: any) {
      setError(String(err?.message ?? err));
    } finally {
      setDrawingBusy(false);
    }
  }

  /* ----------------------- Small presentational components ---------------------- */

  function InputField({ name, label, value, onChange, type = "text" }: any) {
    return (
      <label style={labelStyle}>
        <div style={{ fontSize: 13, marginBottom: 6 }}>{label}</div>
        <input name={name} value={value ?? ""} onChange={onChange} type={type} inputMode="decimal" style={inputStyle} />
      </label>
    );
  }

  function SectionWrapper({ children, title }: any) {
    return (
      <div style={{ marginBottom: 18 }}>
        <div style={sectionTitleStyle}>{title}</div>
        <div style={{ ...cardStyleBase, padding: 16 }}>{children}</div>
      </div>
    );
  }

  /* ------------------------- Punching & Service cards ------------------------ */

  function PunchingCard({ punch }: { punch: any }) {
    if (!punch) {
      return (
        <div style={{ ...cardStyleBase, padding: 16 }}>
          <div style={{ fontWeight: 700, marginBottom: 6 }}>Punching shear</div>
          <div style={{ color: "#9ca3af", fontSize: 13 }}>No punching results produced.</div>
        </div>
      );
    }
    const results = punch.results ?? punch;
    const safe = results?.punching_safe ?? results?.safe ?? null;
    const util = results?.utilization_percent ?? results?.utilization ?? null;
    const Vu_kN = results?.Vu_kN ?? results?.Vu ?? results?.Vu_kN ?? null;
    const Vc_kN = results?.Vc_kN ?? results?.Vc ?? null;
    const phiVc_kN = results?.phiVc_kN ?? results?.phiVc ?? null;
    const b0_mm = results?.b0_mm ?? results?.b0 ?? null;
    const d_mm = results?.d_mm ?? results?.d_eff_mm ?? null;

    return (
      <div style={{ ...cardStyleBase }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 800 }}>Punching shear</div>
            <div style={{ fontSize: 12, color: "#9ca3af" }}>ACI quick check — critical perimeter & capacity</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontWeight: 800, color: safe ? "#86efac" : "#ffb4b4" }}>
              {safe === null || safe === undefined ? "Unknown" : safe ? "Safe" : "Review"}
            </div>
            {util ? <div style={{ fontSize: 12, color: "#9ca3af" }}>{fmt(util, 1)}% util</div> : null}
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 8 }}>
          <div>
            <div style={{ color: "#cbd5e1", fontSize: 12 }}>Applied shear, Vu</div>
            <div style={{ fontWeight: 700 }}>{Vu_kN ? `${fmt(Vu_kN, 2)} kN` : "-"}</div>
          </div>

          <div>
            <div style={{ color: "#cbd5e1", fontSize: 12 }}>Nominal capacity, Vc</div>
            <div style={{ fontWeight: 700 }}>{Vc_kN ? `${fmt(Vc_kN, 2)} kN` : "-"}</div>
          </div>

          <div>
            <div style={{ color: "#cbd5e1", fontSize: 12 }}>Design φVc</div>
            <div style={{ fontWeight: 700 }}>{phiVc_kN ? `${fmt(phiVc_kN, 2)} kN` : "-"}</div>
          </div>

          <div>
            <div style={{ color: "#cbd5e1", fontSize: 12 }}>Critical perimeter b₀</div>
            <div style={{ fontWeight: 700 }}>{b0_mm ? `${fmt(b0_mm, 0)} mm` : "-"}</div>
          </div>

          <div>
            <div style={{ color: "#cbd5e1", fontSize: 12 }}>Effective depth d</div>
            <div style={{ fontWeight: 700 }}>{d_mm ? `${fmt(d_mm, 0)} mm` : "-"}</div>
          </div>

          <div style={{ gridColumn: "1 / -1", marginTop: 8, color: "#9ca3af", fontSize: 13 }}>
            Notes: {results?.notes ?? "Simplified punching check — verify with detailed perimeter & reinforcement layout."}
          </div>
        </div>
      </div>
    );
  }

  function ServiceabilityCard({ svc }: { svc: any }) {
    if (!svc) {
      return (
        <div style={{ ...cardStyleBase, padding: 16 }}>
          <div style={{ fontWeight: 700, marginBottom: 6 }}>Serviceability</div>
          <div style={{ color: "#9ca3af", fontSize: 13 }}>No serviceability results produced.</div>
        </div>
      );
    }
    const results = svc.results ?? svc;
    const short_term = results?.short_term_mm ?? results?.short_term_deflection_mm ?? null;
    const long_term = results?.long_term_mm ?? results?.long_term_deflection_mm ?? null;
    const limit = results?.limit_mm ?? results?.limit ?? null;
    const serviceable = results?.serviceable ?? null;
    const crack_width = results?.estimated_crack_width_mm ?? results?.crack_width_mm ?? null;
    const crack_ok = results?.crack_ok ?? results?.ok ?? null;
    const crack_limit = results?.crack_limit_mm ?? results?.limit_mm ?? 0.4;

    return (
      <div style={{ ...cardStyleBase }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 800 }}>Serviceability</div>
            <div style={{ fontSize: 12, color: "#9ca3af" }}>Deflection & crack-width indicators</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontWeight: 800, color: serviceable ? "#86efac" : "#ffb4b4" }}>
              {serviceable === null || serviceable === undefined ? "Unknown" : serviceable ? "Serviceable" : "Review"}
            </div>
            {long_term ? <div style={{ fontSize: 12, color: "#9ca3af" }}>LT defl: {fmt(long_term, 2)} mm</div> : null}
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <div>
            <div style={{ color: "#cbd5e1", fontSize: 12 }}>Short-term deflection</div>
            <div style={{ fontWeight: 700 }}>{short_term ? `${fmt(short_term, 3)} mm` : "-"}</div>
            <div style={{ color: "#9ca3af", fontSize: 12 }}>Limit: {limit ? `${fmt(limit, 3)} mm` : "-"}</div>
          </div>

          <div>
            <div style={{ color: "#cbd5e1", fontSize: 12 }}>Estimated crack width</div>
            <div style={{ fontWeight: 700 }}>{crack_width ? `${fmt(crack_width, 4)} mm` : "-"}</div>
            <div style={{ color: crack_ok ? "#86efac" : "#ffb4b4", fontSize: 12 }}>
              {crack_ok === null || crack_ok === undefined ? `Limit ${fmt(crack_limit, 3)} mm` : crack_ok ? "OK" : "Above limit"}
            </div>
          </div>

          <div style={{ gridColumn: "1 / -1", marginTop: 8, color: "#9ca3af", fontSize: 13 }}>
            Notes: {results?.notes ?? "Simplified indicators — for final submission run detailed cracked-section and long-term analysis."}
          </div>
        </div>
      </div>
    );
  }

  /* ----------------------------- Render UI ------------------------------ */

  return (
    <main style={pageStyles}>
      <h1 style={{ marginBottom: 10 }}>Civil AI — Designer</h1>

      <div style={{ display: "flex", gap: 10, marginBottom: 18 }}>
        {(["beam", "slab", "column", "footing", "combined"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              padding: "8px 12px",
              background: tab === t ? "#2563eb" : "#1f2937",
              color: "white",
              borderRadius: 8,
              border: "none",
              cursor: "pointer",
            }}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {/* ---------- left / top: inputs per tab ---------- */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 420px", gap: 18 }}>
        <div>
          {/* Beam */}
          {tab === "beam" && (
            <SectionWrapper title="Beam design">
              <form onSubmit={submitBeam}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                  <InputField name="span_m" label="Span (m)" value={beamForm.span_m} onChange={handleChange(setBeamForm)} />
                  <InputField name="b_mm" label="Width b (mm)" value={beamForm.b_mm} onChange={handleChange(setBeamForm)} />
                  <InputField name="h_mm" label="Depth h (mm)" value={beamForm.h_mm} onChange={handleChange(setBeamForm)} />
                  <InputField name="cover_mm" label="Cover (mm)" value={beamForm.cover_mm} onChange={handleChange(setBeamForm)} />
                  <InputField name="dl_kN_per_m" label="Dead Load (kN/m)" value={beamForm.dl_kN_per_m} onChange={handleChange(setBeamForm)} />
                  <InputField name="ll_kN_per_m" label="Live Load (kN/m)" value={beamForm.ll_kN_per_m} onChange={handleChange(setBeamForm)} />
                  <InputField name="fc_MPa" label="fc' (MPa)" value={beamForm.fc_MPa} onChange={handleChange(setBeamForm)} />
                  <InputField name="fy_MPa" label="fy (MPa)" value={beamForm.fy_MPa} onChange={handleChange(setBeamForm)} />
                </div>

                <div style={{ marginTop: 12 }}>
                  <button type="submit" disabled={loading} style={{ padding: "10px 14px", borderRadius: 8, border: "none", background: "#1f7aef", color: "white" }}>
                    {loading ? "Running..." : "Run Beam Design"}
                  </button>
                </div>
              </form>
            </SectionWrapper>
          )}

          {/* Slab */}
          {tab === "slab" && (
            <SectionWrapper title="Slab design">
              <form onSubmit={submitSlab}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                  <InputField name="span_m" label="Span (m)" value={slabForm.span_m} onChange={handleChange(setSlabForm)} />
                  <InputField name="thickness_mm" label="Thickness (mm)" value={slabForm.thickness_mm} onChange={handleChange(setSlabForm)} />
                  <InputField name="dl_kN_per_m2" label="Dead load (kN/m²)" value={slabForm.dl_kN_per_m2} onChange={handleChange(setSlabForm)} />
                  <InputField name="ll_kN_per_m2" label="Live load (kN/m²)" value={slabForm.ll_kN_per_m2} onChange={handleChange(setSlabForm)} />
                  <InputField name="fc_MPa" label="fc' (MPa)" value={slabForm.fc_MPa} onChange={handleChange(setSlabForm)} />
                  <InputField name="fy_MPa" label="fy (MPa)" value={slabForm.fy_MPa} onChange={handleChange(setSlabForm)} />
                  <InputField name="cover_mm" label="Cover (mm)" value={slabForm.cover_mm} onChange={handleChange(setSlabForm)} />
                  <InputField name="bar_dia_mm" label="Bar dia (mm)" value={slabForm.bar_dia_mm} onChange={handleChange(setSlabForm)} />
                </div>
                <div style={{ marginTop: 12 }}>
                  <button type="submit" disabled={loading} style={{ padding: "10px 14px", borderRadius: 8, border: "none", background: "#1f7aef", color: "white" }}>
                    {loading ? "Running..." : "Run Slab Design"}
                  </button>
                </div>
              </form>
            </SectionWrapper>
          )}

          {/* Column */}
          {tab === "column" && (
            <SectionWrapper title="Column design">
              <form onSubmit={submitColumn}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                  <InputField name="Pu_kN" label="Pu (kN)" value={colForm.Pu_kN} onChange={handleChange(setColForm)} />
                  <InputField name="b_mm" label="Width b (mm)" value={colForm.b_mm} onChange={handleChange(setColForm)} />
                  <InputField name="d_mm" label="Depth d (mm)" value={colForm.d_mm} onChange={handleChange(setColForm)} />
                  <InputField name="cover_mm" label="Cover (mm)" value={colForm.cover_mm} onChange={handleChange(setColForm)} />
                  <InputField name="fc_MPa" label="fc' (MPa)" value={colForm.fc_MPa} onChange={handleChange(setColForm)} />
                  <InputField name="fy_MPa" label="fy (MPa)" value={colForm.fy_MPa} onChange={handleChange(setColForm)} />
                  <InputField name="unsupported_length_m" label="Unsupported length L (m)" value={colForm.unsupported_length_m} onChange={handleChange(setColForm)} />
                </div>
                <div style={{ marginTop: 12 }}>
                  <button type="submit" disabled={loading} style={{ padding: "10px 14px", borderRadius: 8, border: "none", background: "#1f7aef", color: "white" }}>
                    {loading ? "Running..." : "Run Column Design"}
                  </button>
                </div>
              </form>
            </SectionWrapper>
          )}

          {/* Footing */}
          {tab === "footing" && (
            <SectionWrapper title="Footing (pad) design">
              <form onSubmit={submitFooting}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                  <InputField name="Pu_kN" label="Pu (kN)" value={footingForm.Pu_kN} onChange={handleChange(setFootingForm)} />
                  <InputField name="col_b_mm" label="Column width (mm)" value={footingForm.col_b_mm} onChange={handleChange(setFootingForm)} />
                  <InputField name="col_d_mm" label="Column depth (mm)" value={footingForm.col_d_mm} onChange={handleChange(setFootingForm)} />
                  <InputField name="soil_allow_kN_per_m2" label="Allowable soil (kN/m²)" value={footingForm.soil_allow_kN_per_m2} onChange={handleChange(setFootingForm)} />
                  <InputField name="pad_depth_mm" label="Pad depth (mm)" value={footingForm.pad_depth_mm} onChange={handleChange(setFootingForm)} />
                  <InputField name="fc_MPa" label="fc' (MPa)" value={footingForm.fc_MPa} onChange={handleChange(setFootingForm)} />
                  <InputField name="fy_MPa" label="fy (MPa)" value={footingForm.fy_MPa} onChange={handleChange(setFootingForm)} />
                  <InputField name="assumed_side_m" label="Assumed side (m) (optional)" value={footingForm.assumed_side_m} onChange={handleChange(setFootingForm)} />
                </div>
                <div style={{ marginTop: 12 }}>
                  <button type="submit" disabled={loading} style={{ padding: "10px 14px", borderRadius: 8, border: "none", background: "#1f7aef", color: "white" }}>
                    {loading ? "Running..." : "Run Footing Design"}
                  </button>
                </div>
              </form>
            </SectionWrapper>
          )}

          {/* Combined */}
          {tab === "combined" && (
            <SectionWrapper title="Combined footing">
              <form onSubmit={submitCombined}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                  <label style={{ gridColumn: "1 / -1", display: "flex", gap: 8, alignItems: "center" }}>
                    <input name="single_mode" type="checkbox" checked={combinedForm.single_mode} onChange={handleChange(setCombinedForm)} />
                    <div style={{ fontSize: 13 }}>Single pad mode (send Pu_kN)</div>
                  </label>

                  {combinedForm.single_mode ? (
                    <>
                      <InputField name="Pu_kN" label="Pu (total kN)" value={combinedForm.Pu_kN} onChange={handleChange(setCombinedForm)} />
                      <InputField name="assumed_side_m" label="Assumed pad side (m)" value={combinedForm.assumed_side_m} onChange={handleChange(setCombinedForm)} />
                      <InputField name="soil_allow_kN_per_m2" label="Allowable soil (kN/m²)" value={combinedForm.soil_allow_kN_per_m2} onChange={handleChange(setCombinedForm)} />
                      <InputField name="pad_depth_mm" label="Pad depth (mm)" value={combinedForm.pad_depth_mm} onChange={handleChange(setCombinedForm)} />
                    </>
                  ) : (
                    <>
                      <InputField name="P1_kN" label="P1 (kN)" value={combinedForm.P1_kN} onChange={handleChange(setCombinedForm)} />
                      <InputField name="P2_kN" label="P2 (kN)" value={combinedForm.P2_kN} onChange={handleChange(setCombinedForm)} />
                      <InputField name="spacing_m" label="Spacing (m)" value={combinedForm.spacing_m} onChange={handleChange(setCombinedForm)} />
                      <InputField name="soil_allow_kN_per_m2" label="Allowable soil (kN/m²)" value={combinedForm.soil_allow_kN_per_m2} onChange={handleChange(setCombinedForm)} />
                    </>
                  )}

                  <div style={{ gridColumn: "1 / -1", marginTop: 6 }}>
                    <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
                      <input name="include_strap" type="checkbox" checked={combinedForm.include_strap} onChange={handleChange(setCombinedForm)} />
                      <div style={{ fontSize: 13 }}>Include strap</div>
                    </label>
                  </div>

                  <InputField name="fc_MPa" label="fc' (MPa)" value={combinedForm.fc_MPa} onChange={handleChange(setCombinedForm)} />
                  <InputField name="fy_MPa" label="fy (MPa)" value={combinedForm.fy_MPa} onChange={handleChange(setCombinedForm)} />
                </div>

                <div style={{ marginTop: 12 }}>
                  <button type="submit" disabled={loading} style={{ padding: "10px 14px", borderRadius: 8, border: "none", background: "#1f7aef", color: "white" }}>
                    {loading ? "Running..." : "Run Combined Footing"}
                  </button>
                </div>
              </form>
            </SectionWrapper>
          )}
        </div>

        {/* ---------- right column: quick actions + results cards ---------- */}
        <div>
          <div style={{ ...cardStyleBase, marginBottom: 14 }}>
            <div style={{ fontWeight: 800 }}>Quick actions</div>
            <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
              <button
                onClick={() => {
                  const rp = findReportPaths(result);
                  const htmlPath = rp?.html ?? rp?.txt ?? null;
                  if (!htmlPath) return setError("No report available to generate PDF.");
                  generatePdfAndDownload(htmlPath);
                }}
                disabled={!result || pdfBusy || pdfSupported === false}
                style={{ padding: "8px 10px", borderRadius: 8, border: "none", background: pdfBusy ? "#2c7a5b" : "#2f855a", color: "white" }}
              >
                {pdfBusy ? "Generating PDF..." : "Download PDF"}
              </button>

              <button
                onClick={() => {
                  // generate drawing using current tab values (same logic as previous file)
                  const sendParams =
                    tab === "beam"
                      ? { ...normalizePayload(beamForm), width_mm: Number(beamForm.b_mm || 300), depth_mm: Number(beamForm.h_mm || 300), n_bars: 4 }
                      : tab === "slab"
                      ? { ...normalizePayload(slabForm), width_mm: Number(slabForm.span_m || 3) * 1000, depth_mm: Number(slabForm.thickness_mm || 150), n_bars: 6 }
                      : tab === "column"
                      ? { ...normalizePayload(colForm), width_mm: Number(colForm.b_mm || 300), depth_mm: Number(colForm.d_mm || 300), n_bars: 8 }
                      : tab === "footing"
                      ? { ...normalizePayload(footingForm), width_mm: Number(footingForm.col_b_mm || 300), depth_mm: Number(footingForm.pad_depth_mm || 400), n_bars: 8 }
                      : (() => {
                          const p = normalizePayload(combinedForm);
                          const strap = p.include_strap
                            ? {
                                width_mm: Number(combinedForm.strap_width_mm || 300),
                                thickness_mm: Number(combinedForm.strap_thickness_mm || 150),
                                length_m: Number(combinedForm.strap_length_m || combinedForm.spacing_m || 1.0),
                              }
                            : undefined;
                          if (p.single_mode) {
                            return {
                              Pu_kN: p.Pu_kN,
                              assumed_side_m: p.assumed_side_m ? Number(p.assumed_side_m) : undefined,
                              width_mm: p.assumed_side_m ? Number(p.assumed_side_m) * 1000 : Number(p.col1_b_mm || 300),
                              depth_mm: Number(p.pad_depth_mm || 500),
                              n_bars: 8,
                              strap,
                            };
                          }
                          return {
                            P1_kN: p.P1_kN,
                            P2_kN: p.P2_kN,
                            col1_b_mm: Number(p.col1_b_mm || 300),
                            col1_d_mm: Number(p.col1_d_mm || 300),
                            col2_b_mm: Number(p.col2_b_mm || 300),
                            col2_d_mm: Number(p.col2_d_mm || 300),
                            spacing_m: Number(p.spacing_m || 1.0),
                            width_mm: Number(p.assumed_side_m ? p.assumed_side_m * 1000 : (p.col1_b_mm || 300)),
                            depth_mm: Number(p.pad_depth_mm || 500),
                            n_bars: 8,
                            strap,
                          };
                        })();

                  generateDrawing(tab, sendParams);
                }}
                disabled={!result || drawingBusy}
                style={{ padding: "8px 10px", borderRadius: 8, border: "none", background: drawingBusy ? "#234a7a" : "#2c5282", color: "white" }}
              >
                {drawingBusy ? "Generating..." : "Generate Drawing"}
              </button>
            </div>
            <div style={{ marginTop: 10, color: "#9ca3af", fontSize: 13 }}>
              Server PDF support: {pdfSupported === null ? "Checking..." : pdfSupported ? "Available" : "Unavailable"}
            </div>
          </div>

          {/* results area */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontWeight: 800, marginBottom: 8 }}>Results snapshot</div>

            {/* Show summary / simple fields */}
            <div style={{ ...cardStyleBase, padding: 12 }}>
              {result ? (
                <>
                  {/* design summary attempt */}
                  {(() => {
                    const drawing_params = findKeyRecursive(result, "drawing_params") || findKeyRecursive(result, "drawing") || null;
                    const engine_results = findKeyRecursive(result, "engine_results") || findKeyRecursive(result, "results") || null;
                    const pad_side_m = drawing_params?.pad_side_m ?? engine_results?.side_m ?? engine_results?.pad_side_m ?? null;
                    const n_per_row = drawing_params?.n_per_row ?? findKeyRecursive(result, "n_per_row") ?? null;
                    const spacing_mm = drawing_params?.spacing_mm ?? engine_results?.spacing_mm ?? null;
                    const provided_As = findKeyRecursive(result, "provided_As_mm2") ?? findKeyRecursive(result, "provided_As") ?? null;

                    return (
                      <div style={{ display: "grid", gap: 6 }}>
                        <div style={{ fontSize: 14, fontWeight: 700 }}>Design summary</div>
                        <div style={{ color: "#9ca3af" }}>
                          {pad_side_m ? <div>Pad side: {Number(pad_side_m).toFixed(3)} m</div> : null}
                          {n_per_row ? <div>Bars / row: {n_per_row}</div> : null}
                          {spacing_mm ? <div>Spacing: {spacing_mm} mm</div> : null}
                          {provided_As ? <div>Provided steel: {provided_As} mm²</div> : null}
                          {!pad_side_m && !n_per_row && !spacing_mm && !provided_As ? <div>No quick summary available for this result.</div> : null}
                        </div>
                      </div>
                    );
                  })()}
                </>
              ) : (
                <div style={{ color: "#9ca3af" }}>No results yet. Run a design to see results here.</div>
              )}
            </div>
          </div>

          {/* Punching & serviceability cards (separate) */}
          <div style={{ display: "grid", gap: 10 }}>
            <div>
              <div style={{ fontSize: 14, fontWeight: 800, marginBottom: 8 }}>Checks</div>
              <div style={{ display: "grid", gap: 10 }}>
                <PunchingCard
                  punch={
                    findKeyRecursive(result, "punching") ||
                    findKeyRecursive(result, "punch") ||
                    findKeyRecursive(result, "punching_check") ||
                    null
                  }
                />
                <ServiceabilityCard
                  svc={
                    findKeyRecursive(result, "serviceability") ||
                    findKeyRecursive(result, "service") ||
                    findKeyRecursive(result, "serviceability_check") ||
                    null
                  }
                />
              </div>
            </div>
          </div>

          {/* drawing files preview */}
          {drawingFiles && (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontWeight: 800, marginBottom: 8 }}>Drawings</div>
              <div style={{ ...cardStyleBase, padding: 12 }}>
                {drawingFiles.svg_plan && (
                  <div style={{ marginBottom: 8 }}>
                    <a href={`${backend}${drawingFiles.svg_plan}`} target="_blank" rel="noreferrer" style={{ color: "#5dade2" }}>
                      Open Plan (SVG)
                    </a>{" "}
                    ·{" "}
                    <a href={`${backend}${drawingFiles.svg_plan}`} download style={{ color: "#7ce67c" }}>
                      Download
                    </a>
                    <div style={{ marginTop: 8 }}>
                      <img src={`${backend}${drawingFiles.svg_plan}`} alt="plan" style={{ width: "100%", maxWidth: 380, borderRadius: 6, border: "1px solid #203040" }} />
                    </div>
                  </div>
                )}

                {drawingFiles.svg_elev && (
                  <div style={{ marginBottom: 8 }}>
                    <a href={`${backend}${drawingFiles.svg_elev}`} target="_blank" rel="noreferrer" style={{ color: "#5dade2" }}>
                      Open Elevation (SVG)
                    </a>{" "}
                    ·{" "}
                    <a href={`${backend}${drawingFiles.svg_elev}`} download style={{ color: "#7ce67c" }}>
                      Download
                    </a>
                  </div>
                )}

                {drawingFiles.dxf && (
                  <div>
                    <a href={`${backend}${drawingFiles.dxf}`} download style={{ color: "#f6c85f" }}>
                      Download DXF
                    </a>
                  </div>
                )}

                {drawingFiles.pdf && (
                  <div style={{ marginTop: 8 }}>
                    <a href={`${backend}${drawingFiles.pdf}`} target="_blank" rel="noreferrer" style={{ color: "#a78bfa" }}>
                      Open PDF
                    </a>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* error */}
      {error && <div style={{ marginTop: 14, color: "#ffb4b4" }}>Error: {error}</div>}

      {/* raw JSON collapse */}
      {result && (
        <details style={{ marginTop: 18, background: "#071022", padding: 10, borderRadius: 8 }}>
          <summary style={{ cursor: "pointer", color: "#9fb4d8" }}>Raw JSON</summary>
          <pre style={{ whiteSpace: "pre-wrap", marginTop: 8 }}>{JSON.stringify(result, null, 2)}</pre>
        </details>
      )}
    </main>
  );
}