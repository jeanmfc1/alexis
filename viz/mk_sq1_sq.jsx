// ─────────────────────────────────────────────────────────────────────────
// viz/mk_sq1_sq.jsx
// MK / sq1 — Modality Landscape for Thought Leadership Content
//
// Data source : ALEXIS_DATA.sq4  (from analytics/mk_sq1.py → sq1_full_history())
// Injected by : pipelines/generate_quarterly_viz.py
//
// Side-by-side layout:
//   LEFT  (~40%) — Hero Donut with colored arcs per modality
//   RIGHT (~60%) — Clickable legend grid → opens detail modal
// ─────────────────────────────────────────────────────────────────────────

function SQ1ModalityLandscape({ data, color }) {
  if (!data?.available) return (
    <div style={{ fontFamily:"var(--fm)", fontSize:12, color:"var(--muted)",
      padding:"20px 0" }}>
      No modality landscape data available.
    </div>
  );

  const [hoveredMod, setHoveredMod] = React.useState(null);
  const [selectedMod, setSelectedMod] = React.useState(null);

  const mods = data.modalities || [];
  const total = data.total_drug_trials || 0;
  const periods = data.periods || [];

  // ── Phase colors (reuse from bd_sq2) ──────────────────────────────────────────────────
  const PHASE_COLORS = {
    PHASE1:"#60a5fa", PHASE2:"#34d399", PHASE3:"#fbbf24",
    PHASE4:"#f87171", NA:"#6b7280",
    "EARLY_PHASE1":"#93c5fd", "PHASE1/PHASE2":"#5eead4",
    "PHASE2/PHASE3":"#a3e635",
  };
  const phaseColor = k => {
    if (PHASE_COLORS[k]) return PHASE_COLORS[k];
    for (const [pk, pc] of Object.entries(PHASE_COLORS)) {
      if (k.toUpperCase().includes(pk)) return pc;
    }
    return "#6b7280";
  };

  // ── Phase bucket helper ───────────────────────────────────────────────────────
  const bucketPhase = dist => {
    const b = { P1:0, P2:0, P3:0, P4:0, Other:0 };
    for (const [k, v] of Object.entries(dist || {})) {
      const u = k.toUpperCase();
      if (u.includes("PHASE1") && !u.includes("PHASE2")) b.P1 += v;
      else if (u.includes("PHASE2") && !u.includes("PHASE3")) b.P2 += v;
      else if (u.includes("PHASE3")) b.P3 += v;
      else if (u.includes("PHASE4")) b.P4 += v;
      else b.Other += v;
    }
    return b;
  };
  const BUCKET_COLORS = { P1:"#60a5fa", P2:"#34d399", P3:"#fbbf24", P4:"#f87171", Other:"#6b7280" };

  // ── Trend colors ──────────────────────────────────────────────────────────
  const trendColor = t => t === "growing" ? "#34d399" : t === "declining" ? "#f87171" : "#6b7280";
  const trendIcon = t => t === "growing" ? "▲" : t === "declining" ? "▼" : "●";

  // ── Sponsor class colors ──────────────────────────────────────────────────
  const CLASS_COLORS = { INDUSTRY:"#60a5fa", NIH:"#fbbf24", OTHER:"#6b7280" };

  // ── CSV export ────────────────────────────────────────────────────────────
  const exportCSV = () => {
    const header = "Modality,Count,Pct,Trend,Growth Rate,YoY Delta,Maturity,Sponsors,Complexity";
    const rows = mods.map(m =>
      [humanMod(m.name), m.count, m.pct, m.trend || "", m.growth_rate || "",
       m.delta_yoy_count || "", m.maturity, m.unique_sponsors, m.complexity_weight].join(",")
    );
    const blob = new Blob([header + "\n" + rows.join("\n")], { type:"text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "modality_landscape.csv";
    a.click();
  };

  // ═══════════════════════════════════════════════════════════════════════
  // DONUT ARCS
  // ═══════════════════════════════════════════════════════════════════════
  const R = 110, SW = 36, cx = 140, cy = 140, viewBox = "0 0 280 280";

  const donutArcs = React.useMemo(() => {
    let cumAngle = -90;
    return mods.map(m => {
      const angle = (m.count / total) * 360;
      const startAngle = cumAngle;
      cumAngle += angle;
      const endAngle = cumAngle;
      const largeArc = angle > 180 ? 1 : 0;
      const toRad = d => d * Math.PI / 180;
      const x1 = cx + R * Math.cos(toRad(startAngle));
      const y1 = cy + R * Math.sin(toRad(startAngle));
      const x2 = cx + R * Math.cos(toRad(endAngle));
      const y2 = cy + R * Math.sin(toRad(endAngle));
      return { ...m, startAngle, endAngle, largeArc, x1, y1, x2, y2, angle };
    });
  }, [mods, total]);

  // ═══════════════════════════════════════════════════════════════════════
  // SPARKLINE
  // ═══════════════════════════════════════════════════════════════════════
  const Sparkline = ({ history, width = 64, height = 24, showLabels = false, yoyPeriod = null }) => {
    if (!history || history.length < 2) return null;
    const filtered = showLabels ? history.filter(h => (h.period || "").endsWith("Q4")) : history;
    if (filtered.length < 2) return null;
    const counts = filtered.map(h => h.count);


    const maxC = Math.max(...counts);
    const minC = Math.min(...counts);
    const range = maxC - minC || 1;
    const labelH = showLabels ? 14 : 0;
    const chartH = height - labelH;
    const coords = counts.map((c, i) => ({
      x: (i / (counts.length - 1)) * width,
      y: chartH - ((c - minC) / range) * (chartH - 2) - 1,
    }));
    const points = coords.map(p => `${p.x},${p.y}`).join(" ");
    const lastTrend = counts[counts.length - 1] >= counts[0] ? "#34d399" : "#f87171";
    return (
      <svg width={width} height={height} style={{ display:"block" }}>
        <polyline points={points} fill="none" stroke={lastTrend} strokeWidth={1.5}
          strokeLinecap="round" strokeLinejoin="round" />
        {showLabels && coords.map((p, i) => {
          const isYoy = yoyPeriod && filtered[i].period === yoyPeriod;
          return (
            <circle key={"d"+i} cx={p.x} cy={p.y} r={isYoy ? 3.5 : 2}
              fill={isYoy ? "#fbbf24" : lastTrend} stroke={isYoy ? "#fff" : "none"}
              strokeWidth={isYoy ? 1 : 0} />
          );
        })}
        {showLabels && filtered.map((h, i) => {
          const x = coords[i].x;
          const yr = (h.period || "").replace("_Q", " Q");
          if (i !== 0 && i !== filtered.length - 1 && i % 2 !== 0) return null;
          return (
            <text key={"l"+i} x={x} y={height - 1} textAnchor={i === 0 ? "start" : i === filtered.length - 1 ? "end" : "middle"}
              style={{ fontSize:7, fontFamily:"var(--fm)", fill:"var(--dim)" }}>
              {yr}
            </text>
          );
        })}
      </svg>
    );
  };

  // ═══════════════════════════════════════════════════════════════════════
  // DETAIL MODAL
  // ═══════════════════════════════════════════════════════════════════════
  const DetailModal = ({ m, meta, periods, onClose }) => {
    if (!m) return null;

    const pb = bucketPhase(m.phase_dist);
    const phaseTotal = Object.values(pb).reduce((a, b) => a + b, 0);
    const classTotal = Object.values(m.sponsor_class_split || {}).reduce((a, b) => a + b, 0);

    return (
      <div
        onClick={onClose}
        style={{
          position:"fixed", top:0, left:0, right:0, bottom:0,
          background:"rgba(0,0,0,0.6)", display:"flex", alignItems:"center",
          justifyContent:"center", zIndex:9999,
        }}>
        <div
          onClick={e => e.stopPropagation()}
          style={{
            background:"var(--surf2)", border:"1px solid var(--border)",
            borderRadius:10, padding:"24px 28px", width:680, maxWidth:"90vw",
            maxHeight:"85vh", overflowY:"auto", position:"relative",
          }}>

          {/* Close button */}
          <button
            onClick={onClose}
            style={{
              position:"absolute", top:12, right:14, background:"none",
              border:"none", color:"var(--muted)", fontSize:18, cursor:"pointer",
              fontFamily:"var(--fm)", lineHeight:1, padding:"2px 6px",
            }}>
            ✕
          </button>

          {/* Header: name + count + pct + YoY delta */}
          <div>
            <div style={{ display:"flex", alignItems:"baseline", gap:8, flexWrap:"wrap" }}>
              <span style={{ fontFamily:"var(--fh)", fontSize:18, fontWeight:700,
                color:modColor(m.name) }}>
                {humanMod(m.name)}
              </span>
              <span style={{ fontFamily:"var(--fm)", fontSize:13, color:"var(--muted)" }}>
                {fmt(m.count)} · {m.pct}%
              </span>
              {m.delta_yoy_count != null && (
                <span style={{ fontFamily:"var(--fm)", fontSize:11,
                  color: m.delta_yoy_count >= 0 ? "#34d399" : "#f87171" }}>
                  {m.delta_yoy_count >= 0 ? "▲" : "▼"} {Math.abs(m.delta_yoy_count)} YoY
                </span>
              )}
            </div>
            {periods?.length > 0 && (
              <div style={{ fontFamily:"var(--fm)", fontSize:10, color:"var(--muted)", marginTop:4 }}>
                {periods[periods.length - 1].replace("_", " ")}
              </div>
            )}

            {/* Trend badge + sparkline */}
            <div style={{ display:"flex", alignItems:"center", gap:10, marginTop:8 }}>
              {m.trend && (
                <span style={{ fontFamily:"var(--fm)", fontSize:10, padding:"2px 8px",
                  borderRadius:4, background: trendColor(m.trend) + "22",
                  color: trendColor(m.trend), letterSpacing:"0.06em" }}>
                  {trendIcon(m.trend)} {m.trend.toUpperCase()}
                  {m.growth_rate != null ? ` ${m.growth_rate > 0 ? "+" : ""}${m.growth_rate}%` : ""}
                </span>
              )}
              <Sparkline history={m.history} width={280} height={48} showLabels yoyPeriod={(() => { const lp = periods?.[periods.length - 1]; const ym = lp?.match(/(\d{4})_Q(\d)/); return ym ? `${parseInt(ym[1]) - 1}_Q${ym[2]}` : null; })()} />
            </div>
          </div>

          {/* Top TAs */}
          {m.top_tas?.length > 0 && (
            <div style={{ marginTop:16 }}>
              <div style={{ fontFamily:"var(--fm)", fontSize:9, color:"var(--dim)",
                marginBottom:5, letterSpacing:"0.06em", textTransform:"uppercase" }}>
                Top Therapeutic Areas
              </div>
              <div style={{ display:"flex", flexWrap:"wrap", gap:5 }}>
                {m.top_tas.slice(0, 5).map(ta => (
                  <span key={ta.name} style={{ fontFamily:"var(--fm)", fontSize:10,
                    padding:"3px 8px", borderRadius:4, background:"var(--border)",
                    color:"var(--muted)", whiteSpace:"nowrap" }}>
                    {ta.name}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Phase distribution */}
          <div style={{ marginTop:16 }}>
            <div style={{ fontFamily:"var(--fm)", fontSize:9, color:"var(--dim)",
              marginBottom:4, letterSpacing:"0.06em", textTransform:"uppercase" }}>
              Phase Distribution
            </div>
            <div style={{ display:"flex", height:8, borderRadius:4, overflow:"hidden" }}>
              {Object.entries(BUCKET_COLORS).map(([bk, bc]) => {
                const w = phaseTotal > 0 ? (pb[bk] / phaseTotal) * 100 : 0;
                if (w < 0.5) return null;
                return <div key={bk} style={{ width:`${w}%`, background:bc, minWidth:2 }} />;
              })}
            </div>
            <div style={{ display:"flex", gap:10, marginTop:4 }}>
              {Object.entries(BUCKET_COLORS).map(([bk, bc]) => {
                const n = pb[bk];
                if (!n) return null;
                return (
                  <span key={bk} style={{ fontFamily:"var(--fm)", fontSize:9, color:"var(--dim)" }}>
                    <span style={{ color:bc }}>{bk}</span> {Math.round(n / phaseTotal * 100)}%
                  </span>
                );
              })}
            </div>
          </div>

          {/* Sponsor diversity */}
          <div style={{ marginTop:16 }}>
            <div style={{ fontFamily:"var(--fm)", fontSize:9, color:"var(--dim)",
              marginBottom:4, letterSpacing:"0.06em", textTransform:"uppercase" }}>
              {fmt(m.unique_sponsors)} Sponsors
            </div>
            <div style={{ display:"flex", height:6, borderRadius:3, overflow:"hidden" }}>
              {Object.entries(CLASS_COLORS).map(([ck, cc]) => {
                const n = (m.sponsor_class_split || {})[ck] || 0;
                const w = classTotal > 0 ? (n / classTotal) * 100 : 0;
                if (w < 0.5) return null;
                return <div key={ck} style={{ width:`${w}%`, background:cc, minWidth:2 }} />;
              })}
            </div>
            <div style={{ display:"flex", gap:10, marginTop:3 }}>
              {Object.entries(CLASS_COLORS).map(([ck, cc]) => {
                const n = (m.sponsor_class_split || {})[ck] || 0;
                if (!n) return null;
                return (
                  <span key={ck} style={{ fontFamily:"var(--fm)", fontSize:9, color:"var(--dim)" }}>
                    <span style={{ color:cc }}>{ck}</span> {Math.round(n / classTotal * 100)}%
                  </span>
                );
              })}
            </div>
          </div>

          {/* Maturity badge + complexity weight */}
          <div style={{ display:"flex", alignItems:"center", gap:8, marginTop:16 }}>
            {(() => {
              const matColors = {
                "FIH-heavy":"#60a5fa", "Dose finding-heavy":"#34d399",
                "Comparative-heavy":"#fbbf24", "RWE-heavy":"#f87171",
              };
              const c = matColors[m.maturity] || "#6b7280";
              return (
                <span style={{ fontFamily:"var(--fm)", fontSize:10, padding:"2px 8px",
                  borderRadius:4, background:c+"22", color:c }}>
                  {m.maturity === "balanced" ? "Balanced pipeline" : m.maturity}
                  {m.maturity_dominant_pct ? ` (${m.maturity_dominant_pct}%)` : ""}
                </span>
              );
            })()}
            <span style={{ fontFamily:"var(--fm)", fontSize:9, color:"var(--dim)" }}>
              CW: {m.complexity_weight}×
            </span>
          </div>
        </div>
      </div>
    );
  };

  // ═══════════════════════════════════════════════════════════════════════
  // RENDER
  // ═══════════════════════════════════════════════════════════════════════
  return (
    <div>
      {/* CSV export — top-right */}
      <div style={{ display:"flex", justifyContent:"flex-end", marginBottom:8 }}>
        <button onClick={exportCSV}
          style={{ fontFamily:"var(--fm)", fontSize:10, color:color.mid, background:"none",
            border:`1px solid ${color.accent}33`, borderRadius:4, padding:"3px 10px",
            cursor:"pointer", letterSpacing:"0.08em" }}>
          ⬇ CSV
        </button>
      </div>

      {/* ── Main layout: side-by-side ── */}
      <div style={{ display:"flex", gap:24, alignItems:"flex-start" }}>

        {/* LEFT — Donut */}
        <div style={{ flex:"0 0 280px", display:"flex", flexDirection:"column",
          alignItems:"center" }}>
          <div style={{ position:"relative", width:280, height:280 }}>
            <svg viewBox={viewBox} width={280} height={280}>
              {donutArcs.map((arc, i) => {
                const isHovered = hoveredMod === arc.name;
                if (arc.angle < 0.5) return null;
                return (
                  <path key={i}
                    d={`M ${arc.x1} ${arc.y1} A ${R} ${R} 0 ${arc.largeArc} 1 ${arc.x2} ${arc.y2}`}
                    fill="none"
                    stroke={modColor(arc.name)}
                    strokeWidth={isHovered ? SW + 8 : SW}
                    opacity={hoveredMod && !isHovered ? 0.3 : 1}
                    style={{ transition:"all 0.15s", cursor:"pointer" }}
                    onMouseEnter={() => setHoveredMod(arc.name)}
                    onMouseLeave={() => setHoveredMod(null)}
                  />
                );
              })}
            </svg>
            {/* Center label */}
            <div style={{ position:"absolute", top:0, left:0, width:280, height:280,
              display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center",
              pointerEvents:"none" }}>
              <div style={{ fontFamily:"var(--fh)", fontSize:28, fontWeight:700, color:"var(--text)" }}>
                {fmt(total)}
              </div>
              <div style={{ fontFamily:"var(--fm)", fontSize:10, color:"var(--muted)",
                letterSpacing:"0.12em", textTransform:"uppercase" }}>
                Drug Trials
              </div>
            </div>
            {/* Hover tooltip */}
            {hoveredMod && (() => {
              const m = mods.find(x => x.name === hoveredMod);
              if (!m) return null;
              return (
                <div style={{ position:"absolute", top:-8, left:"50%", transform:"translateX(-50%)",
                  background:"var(--surf)", border:"1px solid var(--border)", borderRadius:6,
                  padding:"6px 10px", pointerEvents:"none", whiteSpace:"nowrap", zIndex:10 }}>
                  <span style={{ fontFamily:"var(--fm)", fontSize:11, fontWeight:600, color:"var(--text)" }}>
                    {humanMod(m.name)}
                  </span>
                  <span style={{ fontFamily:"var(--fm)", fontSize:11, color:"var(--muted)", marginLeft:8 }}>
                    {fmt(m.count)} · {m.pct}%
                  </span>
                </div>
              );
            })()}
          </div>

          {/* Period info below donut */}
          {periods.length > 1 && (
            <div style={{ fontFamily:"var(--fm)", fontSize:9, color:"var(--dim)",
              marginTop:10, letterSpacing:"0.08em", textAlign:"center" }}>
              {periods.length} periods · {periods[0]} → {periods[periods.length - 1]}
            </div>
          )}
        </div>

        {/* RIGHT — Clickable legend grid */}
        <div style={{ flex:1, minWidth:0 }}>
          <div style={{ fontFamily:"var(--fm)", fontSize:10, color:"var(--muted)",
            marginBottom:8, letterSpacing:"0.06em" }}>
            Click for more details:
          </div>
          <div style={{ display:"grid", gridTemplateColumns:"repeat(3, minmax(0,1fr))", gap:8 }}>
            {mods.map(m => {
              const isHovered = hoveredMod === m.name;
              const isSelected = selectedMod === m.name;
              return (
                <div
                  key={m.name}
                  onClick={() => setSelectedMod(m.name)}
                  onMouseEnter={() => setHoveredMod(m.name)}
                  onMouseLeave={() => setHoveredMod(null)}
                  style={{
                    background: isHovered || isSelected ? "var(--surf)" : "var(--surf2)",
                    borderRadius:6,
                    border: `1px solid ${isHovered || isSelected ? color.accent + "44" : "var(--border)"}`,
                    borderLeft: `3px solid ${modColor(m.name)}`,
                    padding:"10px 12px",
                    cursor:"pointer",
                    transition:"all 0.15s",
                    minWidth:0, overflow:"hidden",
                  }}>
                  <div style={{ fontFamily:"var(--fh)", fontSize:12, fontWeight:700,
                    color:"var(--text)", whiteSpace:"nowrap", overflow:"hidden",
                    textOverflow:"ellipsis" }}>
                    {humanMod(m.name)}
                  </div>
                  <div style={{ display:"flex", alignItems:"baseline", gap:6, marginTop:3 }}>
                    <span style={{ fontFamily:"var(--fm)", fontSize:11, color:"var(--muted)" }}>
                      {fmt(m.count)}
                    </span>
                    <span style={{ fontFamily:"var(--fm)", fontSize:9, color:"var(--dim)" }}>
                      {m.pct}%
                    </span>
                    {m.trend && (
                      <span style={{ fontFamily:"var(--fm)", fontSize:9,
                        color:trendColor(m.trend), marginLeft:"auto" }}>
                        {trendIcon(m.trend)}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Footer meta */}
      <div style={{ fontFamily:"var(--fm)", fontSize:9, color:"var(--dim)",
        marginTop:12, textAlign:"right", letterSpacing:"0.06em" }}>
        Source: {data.meta?.master_db_file} · {fmt(total)} drug trials ·
        {data.meta?.unique_modalities} modalities · {data.meta?.periods_loaded} periods
      </div>

      {/* Modal overlay */}
      {selectedMod && (
        <DetailModal
          m={mods.find(x => x.name === selectedMod)}
          meta={data.meta}
          periods={data.periods}
          onClose={() => setSelectedMod(null)}
        />
      )}
    </div>
  );
}
