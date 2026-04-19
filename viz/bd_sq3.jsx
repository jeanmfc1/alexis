// -----------------------------------------------------------------------
// viz/bd_sq3.jsx
// BD / sq3 -- Therapeutic Area Trajectory (stacked area + movers)
//
// Data source : ALEXIS_DATA.sq3  (from analytics/bd_sq3.py)
// Globals     : modColor, humanMod
// -----------------------------------------------------------------------

const SQ3_TA_PALETTE = [
  "#3B82F6", "#8B5CF6", "#EC4899", "#EF4444", "#F59E0B",
  "#22C55E", "#14B8A6", "#06B6D4", "#A78BFA", "#F97316",
  "#84CC16", "#EAB308",
];

function SQ3TATrajectory({ data, color }) {
  if (!data || !data.available) {
    return (
      <div style={{ padding:"24px", fontFamily:"var(--fm)",
        fontSize:12, color:"var(--muted)", textAlign:"center" }}>
        {data?.reason || "No master DB history available."}
      </div>
    );
  }

  const periods = data.periods || [];
  const tas     = data.tas || [];
  const movers_up   = data.movers_growing   || [];
  const movers_down = data.movers_declining || [];

  const [selectedTA, setSelectedTA] = useState(null);
  const [hoverIdx,   setHoverIdx]   = useState(null);

  const taColorOf = (name) => {
    const i = tas.findIndex(t => t.name === name);
    return i >= 0 ? SQ3_TA_PALETTE[i % SQ3_TA_PALETTE.length] : "#64748B";
  };

  // ── Build stacked area paths ─────────────────────────────────────────
  const W = 860, H = 260, PAD_L = 46, PAD_B = 22, PAD_T = 8, PAD_R = 12;
  const chartW = W - PAD_L - PAD_R;
  const chartH = H - PAD_T - PAD_B;

  const x = (i) => PAD_L + (i / Math.max(1, periods.length - 1)) * chartW;

  // Cumulative per period (bottom to top = tas order)
  const stack = periods.map((_, pi) => {
    let acc = 0;
    return tas.map(t => {
      const v = t.history[pi]?.count || 0;
      const band = { lo: acc, hi: acc + v, v };
      acc += v;
      return band;
    });
  });
  const maxY = Math.max(1, ...stack.map(row => row[row.length - 1]?.hi || 0));
  const y = (v) => PAD_T + chartH - (v / maxY) * chartH;

  // Build SVG path for each TA band (top curve + bottom curve reversed)
  const paths = tas.map((t, ti) => {
    let d = "";
    for (let pi = 0; pi < periods.length; pi++) {
      const hi = stack[pi][ti].hi;
      d += (pi === 0 ? "M " : " L ") + x(pi) + " " + y(hi);
    }
    for (let pi = periods.length - 1; pi >= 0; pi--) {
      const lo = stack[pi][ti].lo;
      d += " L " + x(pi) + " " + y(lo);
    }
    d += " Z";
    return {
      d, name: t.name,
      color: taColorOf(t.name),
    };
  });

  // y-axis ticks
  const yTicks = [0, 0.25, 0.5, 0.75, 1.0].map(p => Math.round(maxY * p));

  // ── Compact TA history row for a single TA (used in movers cards) ───
  const MiniLine = ({ history, hue, w = 120, h = 28 }) => {
    const counts = (history || []).map(h => h.count);
    if (counts.length < 2) return null;
    const mx = Math.max(...counts, 1), mn = Math.min(...counts);
    const rng = Math.max(1, mx - mn);
    const pts = counts.map((c, i) => {
      const cx = (i / (counts.length - 1)) * w;
      const cy = h - ((c - mn) / rng) * (h - 2) - 1;
      return cx + "," + cy;
    }).join(" ");
    return (
      <svg width={w} height={h} style={{ display:"block" }}>
        <polyline points={pts} fill="none" stroke={hue} strokeWidth={1.5}
          strokeLinecap="round" strokeLinejoin="round"/>
        <circle cx={(counts.length-1)/(counts.length-1)*w}
          cy={h - ((counts[counts.length-1] - mn)/rng)*(h-2) - 1}
          r={2.5} fill={hue}/>
      </svg>
    );
  };

  return (
    <div style={{ padding:"0 12px" }}>
      {/* Header + meta */}
      <div style={{ display:"flex", alignItems:"center", gap:10,
        marginBottom:10, fontFamily:"var(--fm)", fontSize:10,
        color:"var(--muted)", letterSpacing:"0.06em" }}>
        <span><b style={{ color:"var(--text)" }}>{data.meta.periods_loaded}</b> periods</span>
        <span style={{ color:"var(--dim)" }}>|</span>
        <span>{periods[0]} → {data.current_period}</span>
        <span style={{ color:"var(--dim)" }}>|</span>
        <span>excluding {data.meta.excluded_tas.join(" / ")}</span>
      </div>

      {/* Stacked area chart */}
      <div style={{ background:"var(--surf2)",
        border:"1px solid var(--border)", borderRadius:8,
        padding:"14px 16px", marginBottom:14 }}>
        <div style={{ fontFamily:"var(--fm)", fontSize:9,
          letterSpacing:"0.14em", color:color.mid,
          textTransform:"uppercase", marginBottom:8 }}>
          Drug trials by therapeutic area (stacked)
        </div>
        <div style={{ display:"flex", gap:14 }}>
          <svg width={W} height={H}
            onMouseLeave={() => setHoverIdx(null)}
            style={{ flexShrink:0 }}>
            <defs>
              {paths.map((p, i) => (
                <linearGradient key={i} id={"sq3-grad-"+i}
                  x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={p.color} stopOpacity={0.85}/>
                  <stop offset="100%" stopColor={p.color} stopOpacity={0.35}/>
                </linearGradient>
              ))}
            </defs>
            {/* Y axis lines */}
            {yTicks.map((v, i) => (
              <g key={i}>
                <line x1={PAD_L} x2={W - PAD_R}
                  y1={y(v)} y2={y(v)}
                  stroke="var(--border)" strokeDasharray="2,4"/>
                <text x={PAD_L - 6} y={y(v) + 3} textAnchor="end"
                  style={{ fontFamily:"var(--fm)", fontSize:9,
                    fill:"var(--dim)" }}>{v}</text>
              </g>
            ))}
            {/* Bands */}
            {paths.map((p, i) => (
              <path key={p.name} d={p.d}
                fill={"url(#sq3-grad-" + i + ")"}
                stroke={p.color} strokeWidth={0.6}
                style={{ cursor:"pointer",
                  opacity: selectedTA && selectedTA !== p.name ? 0.25 : 1,
                  transition:"opacity 0.2s" }}
                onClick={() => setSelectedTA(
                  selectedTA === p.name ? null : p.name)}/>
            ))}
            {/* Hover guide line */}
            {hoverIdx !== null && (
              <line x1={x(hoverIdx)} x2={x(hoverIdx)}
                y1={PAD_T} y2={PAD_T + chartH}
                stroke="var(--cyan)" strokeWidth={1} strokeDasharray="3,3"
                opacity={0.6}/>
            )}
            {/* X axis hover hit areas */}
            {periods.map((p, i) => (
              <rect key={i} x={x(i) - (chartW/periods.length)/2}
                y={PAD_T} width={chartW/periods.length} height={chartH}
                fill="transparent"
                onMouseEnter={() => setHoverIdx(i)}/>
            ))}
            {/* X axis labels (every ~4th for readability) */}
            {periods.map((p, i) => (
              (i === 0 || i === periods.length-1 || i % Math.ceil(periods.length/6) === 0) && (
                <text key={"lbl"+i} x={x(i)} y={H - 6}
                  textAnchor={i === 0 ? "start" : i === periods.length-1 ? "end" : "middle"}
                  style={{ fontFamily:"var(--fm)", fontSize:9,
                    fill:"var(--dim)" }}>
                  {p.replace("_", " ")}
                </text>
              )
            ))}
          </svg>

          {/* Legend + hover tooltip */}
          <div style={{ flex:1, minWidth:0 }}>
            {hoverIdx !== null && (
              <div style={{ padding:"10px 12px", marginBottom:10,
                background:"var(--surf3)", borderRadius:6,
                border:"1px solid var(--border)" }}>
                <div style={{ fontFamily:"var(--fm)", fontSize:10,
                  color:"var(--cyan)", letterSpacing:"0.08em",
                  marginBottom:6 }}>
                  {periods[hoverIdx]?.replace("_", " ")} · total {data.period_totals[periods[hoverIdx]]}
                </div>
                {tas.slice().reverse().map(t => {
                  const v = t.history[hoverIdx]?.count || 0;
                  if (v === 0) return null;
                  return (
                    <div key={t.name} style={{ display:"flex",
                      alignItems:"center", gap:6,
                      padding:"2px 0", fontSize:11 }}>
                      <span style={{ width:8, height:8, borderRadius:2,
                        background:taColorOf(t.name) }}/>
                      <span style={{ flex:1, color:"var(--text)" }}>{t.name}</span>
                      <span style={{ fontFamily:"var(--fm)",
                        color:"var(--muted)" }}>{v}</span>
                    </div>
                  );
                })}
              </div>
            )}
            <div style={{ fontFamily:"var(--fm)", fontSize:9,
              letterSpacing:"0.12em", color:"var(--dim)",
              textTransform:"uppercase", marginBottom:6 }}>
              Legend (click to isolate)
            </div>
            <div style={{ display:"flex", flexDirection:"column",
              gap:3, maxHeight:190, overflowY:"auto" }}>
              {tas.map(t => {
                const active = selectedTA === t.name;
                return (
                  <div key={t.name} onClick={() =>
                      setSelectedTA(active ? null : t.name)}
                    style={{ cursor:"pointer", display:"flex",
                      alignItems:"center", gap:6, padding:"3px 6px",
                      borderRadius:4,
                      background: active ? taColorOf(t.name)+"22" : "transparent",
                      border: active ? "1px solid "+taColorOf(t.name)+"50" : "1px solid transparent" }}>
                    <span style={{ width:10, height:10, borderRadius:2,
                      background:taColorOf(t.name) }}/>
                    <span style={{ flex:1, fontSize:11,
                      color: active ? "var(--text)" : "var(--muted)",
                      fontWeight: active ? 600 : 400 }}>
                      {t.name}
                    </span>
                    <span style={{ fontFamily:"var(--fm)", fontSize:10,
                      color: active ? "var(--text)" : "var(--dim)" }}>
                      {t.current_count}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Movers section */}
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr",
        gap:14 }}>
        <MoversPanel title="Fastest growing TAs"
          rows={movers_up} accent="#22C55E"
          taColorOf={taColorOf} color={color}/>
        <MoversPanel title="Fastest declining TAs"
          rows={movers_down} accent="#EF4444"
          taColorOf={taColorOf} color={color}/>
      </div>
    </div>
  );
}

function MoversPanel({ title, rows, accent, taColorOf, color }) {
  return (
    <div style={{ background:"var(--surf2)",
      border:"1px solid var(--border)", borderRadius:8,
      padding:"14px 16px" }}>
      <div style={{ display:"flex", alignItems:"center", gap:8,
        marginBottom:10 }}>
        <span style={{ width:8, height:8, borderRadius:2, background:accent }}/>
        <div style={{ fontFamily:"var(--fm)", fontSize:9,
          letterSpacing:"0.14em", color:accent,
          textTransform:"uppercase" }}>
          {title}
        </div>
      </div>
      <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
        {rows.length === 0 && (
          <div style={{ color:"var(--muted)", fontSize:11,
            padding:"10px 0", textAlign:"center" }}>
            not enough history to rank
          </div>
        )}
        {rows.map(r => {
          const counts = r.history.map(h => h.count);
          const mx = Math.max(...counts, 1), mn = Math.min(...counts);
          const rng = Math.max(1, mx - mn);
          const w = 110, h = 24;
          const pts = counts.map((c, i) => {
            const cx = (i / (counts.length - 1 || 1)) * w;
            const cy = h - ((c - mn) / rng) * (h - 2) - 1;
            return cx + "," + cy;
          }).join(" ");
          const hue = taColorOf(r.name);
          return (
            <div key={r.name} style={{ display:"flex",
              alignItems:"center", gap:10,
              padding:"6px 8px", borderRadius:5,
              background:"var(--surf3)",
              borderLeft:"2px solid "+hue }}>
              <div style={{ flex:1, minWidth:0 }}>
                <div style={{ fontSize:12, color:"var(--text)",
                  fontWeight:600, overflow:"hidden",
                  textOverflow:"ellipsis", whiteSpace:"nowrap" }}
                  title={r.name}>
                  {r.name}
                </div>
                <div style={{ fontFamily:"var(--fm)", fontSize:10,
                  color:"var(--muted)", marginTop:2 }}>
                  {r.current_count} current · peak {r.peak_count} · YoY {
                    r.yoy_delta >= 0 ? "+" : ""}{r.yoy_delta}
                </div>
              </div>
              <svg width={w} height={h} style={{ flexShrink:0 }}>
                <polyline points={pts} fill="none" stroke={accent}
                  strokeWidth={1.5} strokeLinecap="round"/>
              </svg>
              <div style={{ width:66, textAlign:"right",
                fontFamily:"var(--fm)", fontSize:13, fontWeight:600,
                color:accent }}>
                {r.total_growth_pct >= 0 ? "+" : ""}{r.total_growth_pct}%
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
