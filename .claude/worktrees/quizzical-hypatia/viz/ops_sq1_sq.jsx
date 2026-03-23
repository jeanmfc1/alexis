// ─────────────────────────────────────────────────────────────────────────
// viz/ops_sq1_sq.jsx
// Operations / sq1 — Workload Forecast by Complexity Tier
//
// Data source : ALEXIS_DATA.sq10  (dict from ops_sq1.py)
// Injected by : analytics/ops_sq1.py -> sq10_workload_forecast()
// ─────────────────────────────────────────────────────────────────────────

const TIER_COLORS = {
  Critical: "#EF4444",
  High:     "#F59E0B",
  Medium:   "#38BDF8",
  Low:      "#6B7280",
};

const PLATFORM_COLORS = {
  LCMS:   "#22C55E",
  LBA:    "#A78BFA",
  Hybrid: "#FBBF24",
};

// -- Waffle Grid ----------------------------------------------------------
// 10x10 = 100 cells.  Each cell = 1% of total trial volume.

function WaffleGrid({ tiers }) {
  const size = 180, pad = 4, gap = 2, cols = 10;
  const cell = (size - 2 * pad - (cols - 1) * gap) / cols;

  const cells = [];
  for (const tier of tiers) {
    const count = Math.round(tier.pct_volume);
    for (let i = 0; i < count && cells.length < 100; i++) {
      cells.push(TIER_COLORS[tier.name] || "#6B7280");
    }
  }
  while (cells.length < 100) cells.push(TIER_COLORS.Low);

  return (
    <svg width={size} height={size} style={{ display: "block" }}>
      {cells.map((color, i) => {
        const col = i % cols;
        const row = Math.floor(i / cols);
        const x   = pad + col * (cell + gap);
        const y   = pad + row * (cell + gap);
        return (
          <rect key={i} x={x} y={y} width={cell} height={cell}
                rx={2} fill={color} opacity={0.85} />
        );
      })}
    </svg>
  );
}

// -- Donut Ring -----------------------------------------------------------

function WorkloadDonut({ tiers, size = 180 }) {
  const cx = size / 2, cy = size / 2;
  const outer = size / 2 - 4, inner = outer * 0.6;
  const total = tiers.reduce((s, t) => s + t.workload, 0) || 1;
  let startAngle = -90;

  function arcPath(start, end, r1, r2) {
    const toRad = (d) => (d * Math.PI) / 180;
    const x1 = cx + r2 * Math.cos(toRad(start));
    const y1 = cy + r2 * Math.sin(toRad(start));
    const x2 = cx + r2 * Math.cos(toRad(end));
    const y2 = cy + r2 * Math.sin(toRad(end));
    const x3 = cx + r1 * Math.cos(toRad(end));
    const y3 = cy + r1 * Math.sin(toRad(end));
    const x4 = cx + r1 * Math.cos(toRad(start));
    const y4 = cy + r1 * Math.sin(toRad(start));
    const large = end - start > 180 ? 1 : 0;
    return [
      "M", x1, y1, "A", r2, r2, 0, large, 1, x2, y2,
      "L", x3, y3, "A", r1, r1, 0, large, 0, x4, y4, "Z"
    ].join(" ");
  }

  const arcs = [];
  for (const tier of tiers) {
    if (tier.workload <= 0) continue;
    const sweep = (tier.workload / total) * 360;
    const end = startAngle + sweep;
    arcs.push(
      <path key={tier.name}
            d={arcPath(startAngle, end - 0.5, inner, outer)}
            fill={TIER_COLORS[tier.name] || "#6B7280"} />
    );
    startAngle = end;
  }

  return (
    <svg width={size} height={size} style={{ display: "block" }}>
      {arcs}
      <text x={cx} y={cy - 8} textAnchor="middle"
            style={{ fill: "var(--text)", fontSize: 20, fontWeight: 700, fontFamily: "var(--fm)" }}>
        {(total / 1000).toFixed(1)}k
      </text>
      <text x={cx} y={cy + 12} textAnchor="middle"
            style={{ fill: "var(--muted)", fontSize: 10, fontFamily: "var(--fm)" }}>
        workload pts
      </text>
    </svg>
  );
}

// -- Platform Bar ---------------------------------------------------------

function PlatformBar({ split, width = 160 }) {
  const total = (split.LCMS || 0) + (split.LBA || 0) + (split.Hybrid || 0);
  if (total === 0) return null;
  const h = 14;
  const segments = [];
  let x = 0;
  for (const plat of ["LCMS", "LBA", "Hybrid"]) {
    const count = split[plat] || 0;
    if (count === 0) continue;
    const w = (count / total) * width;
    segments.push(
      <rect key={plat} x={x} y={0} width={w} height={h}
            fill={PLATFORM_COLORS[plat]} rx={x === 0 ? 3 : 0} opacity={0.85} />
    );
    x += w;
  }
  return (
    <svg width={width} height={h} style={{ display: "block" }}>
      {segments}
    </svg>
  );
}

// -- CSV Export -----------------------------------------------------------

function exportSQ10CSV(tiers) {
  const headers = ["tier","volume","pct_volume","workload","pct_workload","LCMS","LBA","Hybrid"];
  const lines = [
    headers.join(","),
    ...tiers.map(t => [
      t.name, t.volume, t.pct_volume, t.workload, t.pct_workload,
      t.platform_split?.LCMS || 0, t.platform_split?.LBA || 0,
      t.platform_split?.Hybrid || 0,
    ].join(","))
  ];
  const blob = new Blob([lines.join("\n")], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "ops_sq1_workload_forecast.csv";
  a.click();
}

// -- Main Component -------------------------------------------------------

function SQ10WorkloadForecast({ data, color }) {
  const [expanded, setExpanded] = useState(null);

  if (!data?.available) return (
    <div style={{ fontFamily: "var(--fm)", fontSize: 12, color: "var(--muted)", padding: "20px 0" }}>
      No workload forecast data available.<br />
      <span style={{ color: "var(--dim)", fontSize: 11 }}>
        Run the quarterly pipeline with a master DB to generate this view.
      </span>
    </div>
  );

  const { tiers, grand_total_volume, grand_total_workload, meta } = data;

  return (
    <div style={{ fontFamily: "var(--fm)", fontSize: 12, color: "var(--text)" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                    marginBottom: 12 }}>
        <span style={{ fontSize: 11, color: "var(--muted)" }}>
          {(grand_total_volume || 0).toLocaleString()} drug trials scored |{" "}
          {(grand_total_workload || 0).toLocaleString()} workload points
        </span>
        <button onClick={() => exportSQ10CSV(tiers)}
                style={{ background: "none", border: "1px solid var(--border)",
                         borderRadius: 4, padding: "3px 10px", cursor: "pointer",
                         color: "var(--muted)", fontFamily: "var(--fm)", fontSize: 11 }}>
          CSV
        </button>
      </div>

      {/* Waffle + Donut */}
      <div style={{ display: "flex", gap: 32, justifyContent: "center",
                    flexWrap: "wrap", marginBottom: 20 }}>
        <div style={{ textAlign: "center" }}>
          <WaffleGrid tiers={tiers} />
          <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 4 }}>
            Trial Volume (each cell = 1%)
          </div>
        </div>
        <div style={{ textAlign: "center" }}>
          <WorkloadDonut tiers={tiers} />
          <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 4 }}>
            Weighted Workload
          </div>
        </div>
      </div>

      {/* Legend */}
      <div style={{ display: "flex", gap: 16, justifyContent: "center",
                    marginBottom: 16, flexWrap: "wrap" }}>
        {tiers.map(t => (
          <div key={t.name} style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{ width: 10, height: 10, borderRadius: 2,
                           background: TIER_COLORS[t.name], display: "inline-block" }} />
            <span style={{ fontSize: 11, color: "var(--text)" }}>{t.name}</span>
          </div>
        ))}
      </div>

      {/* Tier detail rows */}
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {tiers.map(t => {
          const isOpen = expanded === t.name;
          return (
            <div key={t.name}
                 style={{ background: "var(--surf2)", borderRadius: 6,
                          border: "1px solid var(--border)", overflow: "hidden" }}>
              <div onClick={() => setExpanded(isOpen ? null : t.name)}
                   style={{ display: "flex", alignItems: "center", gap: 12,
                            padding: "8px 12px", cursor: "pointer" }}>
                <span style={{ width: 10, height: 10, borderRadius: 2, flexShrink: 0,
                               background: TIER_COLORS[t.name] }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ fontWeight: 600, fontSize: 12 }}>{t.name}</span>
                  <span style={{ color: "var(--muted)", marginLeft: 8, fontSize: 11 }}>
                    {t.volume.toLocaleString()} trials ({t.pct_volume}%)
                  </span>
                  <span style={{ color: "var(--dim)", marginLeft: 8, fontSize: 11 }}>
                    {t.workload.toLocaleString()} pts ({t.pct_workload}%)
                  </span>
                </div>
                <PlatformBar split={t.platform_split || {}} width={120} />
                <span style={{ fontSize: 10, color: "var(--dim)", marginLeft: 4 }}>
                  {isOpen ? "\u25B2" : "\u25BC"}
                </span>
              </div>

              {isOpen && (
                <div style={{ padding: "8px 12px 12px 34px",
                              borderTop: "1px solid var(--border)",
                              display: "flex", gap: 32, flexWrap: "wrap", fontSize: 11 }}>
                  <div>
                    <div style={{ color: "var(--muted)", marginBottom: 4, fontWeight: 600 }}>
                      Top Modalities
                    </div>
                    {(t.top_modalities || []).map(m => (
                      <div key={m.name} style={{ display: "flex", justifyContent: "space-between",
                                                 gap: 12, color: "var(--text)" }}>
                        <span>{m.name.replace(/_/g, " ")}</span>
                        <span style={{ color: "var(--muted)" }}>{m.count}</span>
                      </div>
                    ))}
                  </div>
                  <div>
                    <div style={{ color: "var(--muted)", marginBottom: 4, fontWeight: 600 }}>
                      Phases
                    </div>
                    {(t.top_phases || []).map(p => (
                      <div key={p.name} style={{ display: "flex", justifyContent: "space-between",
                                                 gap: 12, color: "var(--text)" }}>
                        <span>{p.name}</span>
                        <span style={{ color: "var(--muted)" }}>{p.count}</span>
                      </div>
                    ))}
                  </div>
                  <div>
                    <div style={{ color: "var(--muted)", marginBottom: 4, fontWeight: 600 }}>
                      Top Therapeutic Areas
                    </div>
                    {(t.top_tas || []).map(ta => (
                      <div key={ta.name} style={{ display: "flex", justifyContent: "space-between",
                                                  gap: 12, color: "var(--text)" }}>
                        <span>{ta.name}</span>
                        <span style={{ color: "var(--muted)" }}>{ta.count}</span>
                      </div>
                    ))}
                  </div>
                  <div>
                    <div style={{ color: "var(--muted)", marginBottom: 4, fontWeight: 600 }}>
                      Platform Split
                    </div>
                    {["LCMS", "LBA", "Hybrid"].map(p => {
                      const c = (t.platform_split || {})[p] || 0;
                      if (c === 0) return null;
                      return (
                        <div key={p} style={{ display: "flex", alignItems: "center", gap: 6,
                                              color: "var(--text)" }}>
                          <span style={{ width: 8, height: 8, borderRadius: 1,
                                         background: PLATFORM_COLORS[p], display: "inline-block" }} />
                          <span>{p}</span>
                          <span style={{ color: "var(--muted)" }}>{c}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div style={{ marginTop: 12, fontSize: 10, color: "var(--dim)" }}>
        Source: {meta?.master_db_file || "master DB"} |{" "}
        Score = modality x phase x enrollment
      </div>
    </div>
  );
}
