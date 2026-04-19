// -----------------------------------------------------------------------
// viz/ops_sq12.jsx
// Ops / sq12 -- Phase Transition Pipeline (Sankey-style flow)
//
// Data source : ALEXIS_DATA.sq12  (from analytics/ops_sq12.py)
// Globals     : modColor, humanMod
// -----------------------------------------------------------------------

const SQ12_PHASE_COLORS = {
  "EARLY_PHASE1": "#C4B5FD",
  "PHASE1":       "#A78BFA",
  "PHASE1/PHASE2":"#7DD3FC",
  "PHASE2":       "#38BDF8",
  "PHASE2/PHASE3":"#86EFAC",
  "PHASE3":       "#22C55E",
  "PHASE4":       "#FB923C",
  "MARKETED":     "#F59E0B",
  "NA":           "#6B7280",
  "":             "#4B5563",
  "-":            "#4B5563",
};
const SQ12_PHASE_ORDER = [
  "EARLY_PHASE1", "PHASE1", "PHASE1/PHASE2",
  "PHASE2", "PHASE2/PHASE3", "PHASE3", "PHASE4", "MARKETED",
];
const SQ12_PHASE_LABEL = {
  "EARLY_PHASE1": "Early P1", "PHASE1": "Phase 1",
  "PHASE1/PHASE2": "P1/2", "PHASE2": "Phase 2",
  "PHASE2/PHASE3": "P2/3", "PHASE3": "Phase 3",
  "PHASE4": "Phase 4", "MARKETED": "Marketed",
};

function SQ12TransitionPipeline({ data, color }) {
  if (!data || !data.available) {
    return (
      <div style={{ padding:"24px", fontFamily:"var(--fm)",
        fontSize:12, color:"var(--muted)", textAlign:"center" }}>
        {data?.reason || "No transition-pipeline data."}
      </div>
    );
  }

  const [hoverKey, setHoverKey] = useState(null);
  const [selectedKey, setSelectedKey] = useState(null);

  const windows = data.windows || [];
  const trans   = data.transitions || [];
  const flagged = data.flagged || [];
  const anchor  = data.forecast_anchor;

  // ── Sankey layout ──────────────────────────────────────────────────
  // Columns: NOW, +1y, +2y, +3y -- but transitions carry (from_phase,
  // to_phase, year_offset).  For a visual Sankey we treat:
  //   - Left-side nodes per column = from_phase at that year offset
  //   - Right-side nodes per column = to_phase at (year_offset + 1)
  // For simplicity we render 4 columns where each column shows the
  // distribution of trials *completing* in that window, grouped by
  // current phase; flows cross to the next column representing the
  // predicted next-phase bucket a year later.

  const COLS = windows;
  const W = 860, H = 300;
  const COL_W  = (W - 40) / COLS.length;
  const PAD    = 18;
  const NODE_W = 14;

  // For each column, list phases sorted by SQ12_PHASE_ORDER
  const colNodes = COLS.map(win => {
    const rows = [];
    for (const ph of SQ12_PHASE_ORDER) {
      const n = win.by_phase[ph] || 0;
      if (n > 0) rows.push({ phase: ph, count: n });
    }
    return rows;
  });

  // Normalise heights by column total
  const maxColCount = Math.max(1, ...COLS.map(w => w.count));
  const scale = (H - PAD*2) / maxColCount;

  // Node positions per column
  const nodePos = colNodes.map((rows, ci) => {
    let y = PAD;
    const pos = [];
    rows.forEach(r => {
      const h = Math.max(2, r.count * scale);
      pos.push({ phase: r.phase, count: r.count, y, h,
        x: 20 + ci * COL_W + (COL_W - NODE_W) / 2 });
      y += h + 4;
    });
    return pos;
  });

  // Flows: each transition with year_offset k goes from column k to col k+1
  const flows = trans
    .filter(t => t.year_offset + 1 < COLS.length)
    .map(t => {
      const ci = t.year_offset;
      const src = (nodePos[ci] || []).find(n => n.phase === t.from_phase);
      const dst = (nodePos[ci + 1] || []).find(n => n.phase === t.to_phase);
      if (!src || !dst) return null;
      const hy = Math.max(1, t.count * scale);
      return { t, ci, src, dst, hy };
    })
    .filter(Boolean);

  // Stack flows within each source+dst node (so they don't all originate
  // from the node center -- they slide down proportionally)
  const srcOffset = new Map();
  const dstOffset = new Map();
  flows.forEach(f => {
    const sk = f.src.x + "_" + f.src.phase;
    const dk = f.dst.x + "_" + f.dst.phase;
    const soff = srcOffset.get(sk) || 0;
    const doff = dstOffset.get(dk) || 0;
    f.y1 = f.src.y + soff;
    f.y2 = f.dst.y + doff;
    srcOffset.set(sk, soff + f.hy);
    dstOffset.set(dk, doff + f.hy);
  });

  const pathFor = (f) => {
    const x1 = f.src.x + NODE_W;
    const x2 = f.dst.x;
    const cx1 = x1 + (x2 - x1) * 0.5;
    const cx2 = x1 + (x2 - x1) * 0.5;
    return (
      "M " + x1 + " " + f.y1 +
      " C " + cx1 + " " + f.y1 + " " + cx2 + " " + f.y2 + " " + x2 + " " + f.y2 +
      " L " + x2 + " " + (f.y2 + f.hy) +
      " C " + cx2 + " " + (f.y2 + f.hy) + " " + cx1 + " " + (f.y1 + f.hy) +
      " " + x1 + " " + (f.y1 + f.hy) + " Z"
    );
  };

  const keyOf = (f) =>
    f.ci + ":" + f.src.phase + "->" + f.dst.phase;
  const hoveredFlow = hoverKey
    ? flows.find(f => keyOf(f) === hoverKey)
    : null;
  const selectedFlow = selectedKey
    ? flows.find(f => keyOf(f) === selectedKey)
    : null;

  return (
    <div style={{ padding:"0 12px" }}>
      {/* Header strip */}
      <div style={{ display:"flex", gap:10, marginBottom:14 }}>
        {[
          {label:"ACTIVE DRUG TRIALS", value:data.meta.active_trials},
          {label:"WITH COMPLETION DATE",
           value:data.meta.trials_with_completion,
           sub: data.meta.completion_coverage_pct + "% coverage"},
          {label:"COMPLETING ≤12 MO",
           value:(windows[0]?.count || 0),
           tone:color.accent},
          {label:"STALE (past due)",
           value:data.meta.stale_count,
           tone: data.meta.stale_count > 50 ? "#EF4444" : "var(--muted)"},
        ].map((k, i) => (
          <div key={i} style={{ flex:1, background:"var(--surf2)",
            border:"1px solid "+color.accent+"22", borderRadius:8,
            padding:"12px 14px" }}>
            <div style={{ fontFamily:"var(--fm)", fontSize:9,
              color:"var(--muted)", letterSpacing:"0.14em" }}>
              {k.label}
            </div>
            <div style={{ fontFamily:"var(--fh)", fontSize:24, fontWeight:700,
              color: k.tone || "var(--text)", marginTop:2 }}>
              {k.value.toLocaleString()}
            </div>
            {k.sub && (
              <div style={{ fontFamily:"var(--fm)", fontSize:10,
                color:"var(--muted)", marginTop:2 }}>{k.sub}</div>
            )}
          </div>
        ))}
      </div>

      {/* Sankey */}
      <div style={{ background:"var(--surf2)",
        border:"1px solid var(--border)", borderRadius:8,
        padding:"14px 16px", marginBottom:14 }}>
        <div style={{ display:"flex", alignItems:"center",
          justifyContent:"space-between", marginBottom:10 }}>
          <div style={{ fontFamily:"var(--fm)", fontSize:9,
            letterSpacing:"0.14em", color:color.mid,
            textTransform:"uppercase" }}>
            Phase transition flow (anchor: {anchor})
          </div>
          {selectedFlow && (
            <button onClick={() => setSelectedKey(null)}
              style={{ background:"transparent",
                border:"1px solid var(--border2)", color:"var(--muted)",
                borderRadius:4, padding:"3px 10px",
                fontFamily:"var(--fm)", fontSize:10, cursor:"pointer" }}>
              clear selection
            </button>
          )}
        </div>

        <svg width={W} height={H} style={{ display:"block" }}>
          {/* Flow paths (bottom layer) */}
          {flows.map(f => {
            const k = keyOf(f);
            const hue = SQ12_PHASE_COLORS[f.src.phase] || "#4B5563";
            const active = hoverKey === k || selectedKey === k;
            return (
              <path key={k} d={pathFor(f)} fill={hue}
                opacity={ (selectedKey && selectedKey !== k) ? 0.06
                        : (hoverKey && hoverKey !== k)     ? 0.20
                        : active                           ? 0.65
                        :                                    0.38 }
                style={{ cursor:"pointer", transition:"opacity 0.15s" }}
                onMouseEnter={() => setHoverKey(k)}
                onMouseLeave={() => setHoverKey(null)}
                onClick={() => setSelectedKey(
                  selectedKey === k ? null : k)}/>
            );
          })}
          {/* Column header labels */}
          {COLS.map((w, i) => (
            <text key={"col"+i} x={20 + i * COL_W + COL_W / 2} y={12}
              textAnchor="middle"
              style={{ fontFamily:"var(--fm)", fontSize:10,
                letterSpacing:"0.08em", fill:"var(--muted)",
                textTransform:"uppercase" }}>
              {w.label} · {w.count}
            </text>
          ))}
          {/* Nodes (phase blocks) */}
          {nodePos.map((col, ci) =>
            col.map(n => {
              const hue = SQ12_PHASE_COLORS[n.phase] || "#4B5563";
              return (
                <g key={ci + "_" + n.phase}>
                  <rect x={n.x} y={n.y} width={NODE_W} height={n.h}
                    fill={hue}
                    style={{ filter:"drop-shadow(0 0 4px " + hue + "55)" }}/>
                  <text x={n.x + NODE_W + 6} y={n.y + Math.min(n.h, 14)}
                    style={{ fontFamily:"var(--fm)", fontSize:10,
                      fill:"var(--text)" }}>
                    {SQ12_PHASE_LABEL[n.phase] || n.phase}
                  </text>
                  <text x={n.x + NODE_W + 6} y={n.y + Math.min(n.h, 14) + 11}
                    style={{ fontFamily:"var(--fm)", fontSize:9,
                      fill:"var(--muted)" }}>
                    {n.count}
                  </text>
                </g>
              );
            })
          )}
        </svg>
      </div>

      {/* Flow drill-down */}
      {(hoveredFlow || selectedFlow) && (() => {
        const f = selectedFlow || hoveredFlow;
        const hue = SQ12_PHASE_COLORS[f.src.phase] || "#4B5563";
        const windowLabel = COLS[f.ci]?.label || "";
        return (
          <div style={{ background:"var(--surf2)",
            border:"1px solid "+hue+"40", borderRadius:8,
            padding:"14px 16px", marginBottom:14 }}>
            <div style={{ display:"flex", alignItems:"center",
              gap:10, marginBottom:10 }}>
              <span style={{ fontFamily:"var(--fh)", fontSize:18,
                fontWeight:700, color:"var(--text)" }}>
                {f.t.count}
              </span>
              <span style={{ fontFamily:"var(--fm)", fontSize:11,
                color:"var(--muted)" }}>
                trials transitioning
              </span>
              <span style={{ fontFamily:"var(--fm)", fontSize:11,
                padding:"2px 8px", borderRadius:6, color:hue,
                background:hue+"20",
                border:"1px solid "+hue+"40" }}>
                {SQ12_PHASE_LABEL[f.t.from_phase] || f.t.from_phase}
              </span>
              <span style={{ color:"var(--muted)" }}>→</span>
              <span style={{ fontFamily:"var(--fm)", fontSize:11,
                padding:"2px 8px", borderRadius:6,
                color: SQ12_PHASE_COLORS[f.t.to_phase] || "#4B5563",
                background: (SQ12_PHASE_COLORS[f.t.to_phase] || "#4B5563")+"20",
                border: "1px solid " + (SQ12_PHASE_COLORS[f.t.to_phase] || "#4B5563") + "40" }}>
                {SQ12_PHASE_LABEL[f.t.to_phase] || f.t.to_phase}
              </span>
              <span style={{ color:"var(--dim)" }}>·</span>
              <span style={{ fontFamily:"var(--fm)", fontSize:11,
                color:"var(--muted)" }}>{windowLabel}</span>
            </div>
            <div style={{ display:"flex", gap:4, flexWrap:"wrap",
              marginBottom:10 }}>
              {Object.entries(f.t.modalities || {}).map(([m, n]) => (
                <span key={m} style={{ fontFamily:"var(--fm)", fontSize:10,
                  padding:"2px 6px", borderRadius:8,
                  background:modColor(m)+"20", color:modColor(m),
                  border:"1px solid "+modColor(m)+"30" }}>
                  {humanMod(m)} · {n}
                </span>
              ))}
            </div>
            <div style={{ display:"grid",
              gridTemplateColumns:"repeat(auto-fill, minmax(260px, 1fr))",
              gap:6 }}>
              {(f.t.examples || []).map(ex => (
                <a key={ex.nct_id} href={ex.source_url || "#"} target="_blank"
                   rel="noreferrer" style={{ padding:"6px 10px",
                     background:"var(--surf3)", borderRadius:4,
                     textDecoration:"none",
                     borderLeft:"2px solid "+hue }}>
                  <div style={{ display:"flex", gap:6, alignItems:"center" }}>
                    <span style={{ fontFamily:"var(--fm)", fontSize:10,
                      color:"var(--cyan)" }}>{ex.nct_id}</span>
                    {ex.modality && (
                      <span style={{ fontFamily:"var(--fm)", fontSize:9,
                        color:modColor(ex.modality),
                        padding:"1px 5px", borderRadius:5,
                        background:modColor(ex.modality)+"20",
                        border:"1px solid "+modColor(ex.modality)+"30" }}>
                        {humanMod(ex.modality)}
                      </span>
                    )}
                    <span style={{ fontFamily:"var(--fm)", fontSize:9,
                      color:"var(--muted)", marginLeft:"auto" }}>
                      {ex.projected_completion}
                    </span>
                  </div>
                  <div style={{ fontSize:11, color:"var(--text)",
                    marginTop:3, lineHeight:1.3 }}>
                    {ex.title}
                  </div>
                </a>
              ))}
            </div>
          </div>
        );
      })()}

      {/* Flagged list (stale + near-term completions) */}
      {flagged.length > 0 && (
        <div style={{ background:"var(--surf2)",
          border:"1px solid var(--border)", borderRadius:8,
          padding:"14px 16px" }}>
          <div style={{ fontFamily:"var(--fm)", fontSize:9,
            letterSpacing:"0.14em", color:color.mid,
            textTransform:"uppercase", marginBottom:10 }}>
            Flagged trials ({flagged.length})
          </div>
          <div style={{ display:"grid",
            gridTemplateColumns:"repeat(auto-fill, minmax(280px, 1fr))",
            gap:6, maxHeight:260, overflowY:"auto" }}>
            {flagged.map((f, i) => {
              const isStale = f.reason.startsWith("stale");
              const tone = isStale ? "#EF4444" : "#F59E0B";
              return (
                <div key={i} style={{ padding:"8px 10px",
                  background:"var(--surf3)", borderRadius:4,
                  borderLeft:"2px solid "+tone }}>
                  <div style={{ display:"flex", gap:6, alignItems:"center" }}>
                    <span style={{ fontFamily:"var(--fm)", fontSize:10,
                      color:"var(--cyan)" }}>{f.nct_id}</span>
                    <span style={{ fontFamily:"var(--fm)", fontSize:9,
                      padding:"1px 5px", borderRadius:4,
                      color:tone, background:tone+"18",
                      border:"1px solid "+tone+"30" }}>
                      {isStale
                        ? f.days_overdue + "d overdue"
                        : f.days_out + "d out"}
                    </span>
                    {f.phase && (
                      <span style={{ fontFamily:"var(--fm)", fontSize:9,
                        color:"var(--muted)" }}>{f.phase}</span>
                    )}
                  </div>
                  <div style={{ fontSize:11, color:"var(--text)",
                    marginTop:3, lineHeight:1.3 }}>{f.title}</div>
                  <div style={{ fontFamily:"var(--fm)", fontSize:10,
                    color:"var(--muted)", marginTop:3 }}>
                    {f.sponsor || "-"} · PCD: {f.projected_completion}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
