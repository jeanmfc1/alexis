// ─────────────────────────────────────────────────────────────────────────
// viz/ops_wq1.jsx
// Operations / wq1 — Velocity Dashboard (4 tiles)
//
// Data source : ALEXIS_DATA.wq10
// Injected by : analytics/ops_wq1.py → wq10_velocity_dashboard()
// ─────────────────────────────────────────────────────────────────────────

// ── Shared mini-sparkline SVG ─────────────────────────────────────────────
function MiniSparkline({ points, accentColor, width=220, height=64, showArea=true, fluid=false }) {
  if (!points || points.length < 2) return null;
  const vals  = points.map(p => p.drug_new ?? p.pct ?? 0);
  const maxV  = Math.max(...vals, 1);
  const minV  = Math.min(...vals, 0);
  const range = maxV - minV || 1;
  const pad   = { l:6, r:6, t:8, b:20 };
  const W = width  - pad.l - pad.r;
  const H = height - pad.t - pad.b;
  const x = i => pad.l + (i / (points.length - 1)) * W;
  const y = v => pad.t + H - ((v - minV) / range) * H;

  const ptCoords = points.map((p, i) => [x(i), y(p.drug_new ?? p.pct ?? 0)]);
  const lineD    = ptCoords.map(([px,py], i) => `${i===0?'M':'L'}${px.toFixed(1)},${py.toFixed(1)}`).join(' ');
  const areaD    = lineD
    + ` L${ptCoords[ptCoords.length-1][0].toFixed(1)},${(pad.t+H).toFixed(1)}`
    + ` L${ptCoords[0][0].toFixed(1)},${(pad.t+H).toFixed(1)} Z`;

  const gradId = `sg-${accentColor.replace(/[^a-z0-9]/gi,'')}`;

  const svgProps = fluid
    ? { viewBox:`0 0 ${width} ${height}`, preserveAspectRatio:"none",
        style:{ overflow:"visible", display:"block", width:"100%", height:"100%" } }
    : { width, height, style:{ overflow:"visible", display:"block" } };

  return (
    <svg {...svgProps}>
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor={accentColor} stopOpacity="0.25" />
          <stop offset="100%" stopColor={accentColor} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      {showArea && <path d={areaD} fill={`url(#${gradId})`} />}
      <path d={lineD} fill="none" stroke={accentColor} strokeWidth="1.8"
            strokeLinejoin="round" strokeLinecap="round" />
      {ptCoords.map(([px,py], i) => {
        const isCur = points[i].is_current;
        return (
          <g key={i}>
            <circle cx={px} cy={py} r={isCur ? 5 : 3}
              fill={isCur ? accentColor : "var(--bg)"}
              stroke={accentColor} strokeWidth={isCur ? 0 : 1.5} />
            {isCur && <circle cx={px} cy={py} r={8} fill={accentColor} opacity="0.18" />}
          </g>
        );
      })}
      {/* x-axis labels */}
      {points.map((p, i) => (
        <text key={i} x={x(i)} y={pad.t + H + 14}
          textAnchor="middle" fontSize="8"
          fill={p.is_current ? accentColor : "var(--dim)"}
          fontFamily="var(--fm)"
          fontWeight={p.is_current ? "600" : "400"}>
          {p.short_label}
        </text>
      ))}
    </svg>
  );
}

// ── Diverging bar chart ────────────────────────────────────────────────────
function DivergingBars({ bars, accentColor, labelFn }) {
  if (!bars || bars.length === 0) return (
    <div style={{ fontFamily:"var(--fm)", fontSize:11, color:"var(--muted)",
      padding:"12px 0" }}>No prior week data available.</div>
  );

  const gainers   = bars.filter(b => b.delta_pct >= 0)
                        .sort((a,b) => b.delta_pct - a.delta_pct)
                        .slice(0, 3);
  const decliners = bars.filter(b => b.delta_pct < 0)
                        .sort((a,b) => a.delta_pct - b.delta_pct)
                        .slice(0, 3);
  if (gainers.length + decliners.length === 0) return null;

  const maxAbs = Math.max(
    ...gainers.map(b => b.delta_pct),
    ...decliners.map(b => Math.abs(b.delta_pct)),
    1
  );

  const LABEL_W = 110;

  const Row = ({ b }) => {
    const isGain = b.delta_pct >= 0;
    const pct    = Math.abs(b.delta_pct) / maxAbs * 100;
    const barCol = isGain ? (accentColor || "#F59E0B") : "rgba(59,130,246,0.8)";
    const valCol = isGain ? "#F87171" : "#60A5FA";
    return (
      <div style={{ display:"flex", alignItems:"center", gap:0, height:24 }}>
        {/* Label */}
        <div title={b.label}
          style={{ width:LABEL_W, flexShrink:0, fontFamily:"var(--fb)", fontSize:10,
            color:"var(--text)", overflowX:"auto", overflowY:"hidden",
            whiteSpace:"nowrap", textAlign:"right", paddingRight:8 }}>
          {labelFn ? labelFn(b.label) : b.label}
        </div>

        {/* Left half-track — decliners grow leftward */}
        <div style={{ flex:1, display:"flex", justifyContent:"flex-end",
          alignItems:"center", position:"relative", height:"100%" }}>
          {!isGain && (
            <div style={{ width:`${pct}%`, height:10,
              background:barCol, borderRadius:"3px 0 0 3px",
              transition:"width 0.3s ease" }} />
          )}
        </div>

        {/* Zero line */}
        <div style={{ width:2, flexShrink:0, alignSelf:"stretch",
          background:"rgba(255,255,255,0.15)" }} />

        {/* Right half-track — gainers grow rightward */}
        <div style={{ flex:1, display:"flex", justifyContent:"flex-start",
          alignItems:"center", position:"relative", height:"100%" }}>
          {isGain && (
            <div style={{ width:`${pct}%`, height:10,
              background:barCol, borderRadius:"0 3px 3px 0",
              transition:"width 0.3s ease" }} />
          )}
        </div>

        {/* Value + count */}
        <div style={{ width:58, flexShrink:0, textAlign:"right",
          fontFamily:"var(--fm)", fontSize:10, fontWeight:600, color:valCol }}>
          {isGain ? "+" : ""}{b.delta_pct.toFixed(1)}%
        </div>
        <div style={{ width:32, flexShrink:0, fontFamily:"var(--fm)",
          fontSize:9, color:"var(--dim)", textAlign:"right" }}>
          n={b.current_n}
        </div>
      </div>
    );
  };

  return (
    <div style={{ display:"flex", flexDirection:"column", gap:2 }}>
      {gainers.map(b => <Row key={b.label} b={b} />)}
      {gainers.length > 0 && decliners.length > 0 && (
        <div style={{ height:1, background:"var(--border2)",
          margin:"4px 0", opacity:0.4 }} />
      )}
      {decliners.map(b => <Row key={b.label} b={b} />)}
      <div style={{ fontFamily:"var(--fm)", fontSize:8, color:"var(--dim)",
        marginTop:4, paddingLeft:LABEL_W + 8 }}>
        bars grow from center · red = above avg · blue = below avg
      </div>
    </div>
  );
}

// ── Phase 1 intake gauge ───────────────────────────────────────────────────
function Phase1Gauge({ data, accentColor }) {
  if (!data) return null;
  const { cur_pct, avg_pct, delta_pct, cur_count, sparkline, has_prior } = data;

  const R = 50, CX = 64, CY = 64;
  const toRad = deg => deg * Math.PI / 180;
  const arcPath = (pct, r) => {
    const startAngle = -210;
    const sweep      = 240 * Math.min(pct / 100, 1);
    const endAngle   = startAngle + sweep;
    const x1 = CX + r * Math.cos(toRad(startAngle));
    const y1 = CY + r * Math.sin(toRad(startAngle));
    const x2 = CX + r * Math.cos(toRad(endAngle));
    const y2 = CY + r * Math.sin(toRad(endAngle));
    const large = sweep > 180 ? 1 : 0;
    return sweep > 0
      ? `M${x1.toFixed(1)},${y1.toFixed(1)} A${r},${r} 0 ${large},1 ${x2.toFixed(1)},${y2.toFixed(1)}`
      : '';
  };

  const avgAngle = -210 + 240 * Math.min((avg_pct || 0) / 100, 1);
  const avgX = CX + R * Math.cos(toRad(avgAngle));
  const avgY = CY + R * Math.sin(toRad(avgAngle));

  return (
    <div style={{ display:"flex", gap:16, alignItems:"flex-start" }}>
      {/* Arc gauge */}
      <div style={{ flexShrink:0 }}>
        <svg width={128} height={92} style={{ overflow:"visible" }}>
          <path d={arcPath(100, R)} fill="none"
            stroke="var(--border2)" strokeWidth="7" strokeLinecap="round" />
          <path d={arcPath(cur_pct, R)} fill="none"
            stroke={accentColor} strokeWidth="7" strokeLinecap="round" />
          {has_prior && avg_pct != null && (
            <circle cx={avgX.toFixed(1)} cy={avgY.toFixed(1)} r="5"
              fill="var(--bg)" stroke="#F59E0B" strokeWidth="2" />
          )}
          <text x={CX} y={CY - 4} textAnchor="middle"
            fontSize="20" fontWeight="700" fill={accentColor}
            fontFamily="var(--fm)">
            {cur_pct.toFixed(1)}%
          </text>
          <text x={CX} y={CY + 14} textAnchor="middle"
            fontSize="8" fill="var(--muted)" fontFamily="var(--fm)">
            Phase 1
          </text>
        </svg>
      </div>
      {/* Stats + sparkline */}
      <div style={{ flex:1, minWidth:0 }}>
        <div style={{ display:"flex", alignItems:"baseline", gap:6, marginBottom:6 }}>
          <span style={{ fontFamily:"var(--fm)", fontSize:18,
            fontWeight:700, color:accentColor }}>
            {cur_count} trials
          </span>
          {has_prior && delta_pct != null && (
            <span style={{ fontFamily:"var(--fm)", fontSize:11, fontWeight:600,
              color: delta_pct > 1 ? "#EF4444" : delta_pct < -1 ? "#60A5FA" : "var(--muted)" }}>
              {delta_pct > 0 ? "+" : ""}{delta_pct.toFixed(1)}pp vs avg
            </span>
          )}
        </div>
        {has_prior && avg_pct != null && (
          <div style={{ fontFamily:"var(--fm)", fontSize:9,
            color:"var(--dim)", marginBottom:8 }}>
            ● avg {avg_pct.toFixed(1)}%
            <span style={{ marginLeft:8, color:"#F59E0B" }}>○ avg marker on gauge</span>
          </div>
        )}
        {sparkline && (
          <div style={{ marginTop:4 }}>
            <MiniSparkline
              points={sparkline.map(p => ({ ...p, drug_new: p.pct }))}
              accentColor={accentColor}
              width={180} height={58}
              showArea={false} />
          </div>
        )}
      </div>
    </div>
  );
}

// (Phase 1 highlight now comes from is_p1 flag in phase_breakdown data)

// ── Main wq10 component ────────────────────────────────────────────────────
function WQ10VelocityDashboard({ data, color }) {
  if (!data?.available) return (
    <div style={{ fontFamily:"var(--fm)", fontSize:12, color:"var(--muted)",
      padding:"20px 0" }}>
      No data — enriched file not loaded or no new drug registrations this window.
    </div>
  );

  const { sparkline, cur_drug_new, prior_avg_drug, pace_delta_pct,
          ta_top, ta_bars, mod_bars, phase1, phase_breakdown, has_prior, n_prior_weeks } = data;

  const ac = color.mid;

  let paceCopy = null;
  if (has_prior && pace_delta_pct != null) {
    const abs = Math.abs(pace_delta_pct);
    const dir = pace_delta_pct >= 0 ? "above" : "below";
    const col = pace_delta_pct >= 5  ? "#EF4444"
              : pace_delta_pct <= -5 ? "#60A5FA"
              : "var(--muted)";
    paceCopy = (
      <span style={{ fontFamily:"var(--fm)", fontSize:11, fontWeight:600, color:col }}>
        {pace_delta_pct >= 0 ? "▲" : "▼"} {abs.toFixed(1)}% {dir} {n_prior_weeks}-week avg
      </span>
    );
  }

  const tileStyle = {
    background:"var(--surf2)", border:"1px solid var(--border)",
    borderRadius:10, padding:"16px 18px",
    display:"flex", flexDirection:"column",
  };
  const tileTitle = txt => (
    <div style={{ fontFamily:"var(--fm)", fontSize:9, letterSpacing:"0.12em",
      color:"var(--dim)", marginBottom:10, textTransform:"uppercase" }}>
      {txt}
    </div>
  );

  return (
    <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gridAutoRows:"1fr", gap:14 }}>

      {/* Tile 1: Sparkline */}
      <div style={tileStyle}>
        {tileTitle("New Drug Registrations")}
        <div style={{ display:"flex", alignItems:"baseline", gap:8, marginBottom:6 }}>
          <span style={{ fontFamily:"var(--fm)", fontSize:28,
            fontWeight:700, color:ac, lineHeight:1 }}>
            {fmt(cur_drug_new)}
          </span>
          {has_prior && prior_avg_drug != null && (
            <span style={{ fontFamily:"var(--fm)", fontSize:11, color:"var(--muted)" }}>
              avg {prior_avg_drug.toFixed(1)}
            </span>
          )}
        </div>
        {paceCopy}
        {sparkline && (
          <div style={{ flex:1, minHeight:60, marginTop:10 }}>
            <MiniSparkline points={sparkline} accentColor={ac}
              width={230} height={68} fluid />
          </div>
        )}
        {/* Top TAs this week (by absolute count, not deviation) */}
        {ta_top?.length > 0 && (
          <div style={{ display:"flex", gap:6, flexWrap:"wrap", marginTop:10,
            borderTop:"1px solid var(--border)", paddingTop:10 }}>
            {ta_top.slice(0, 6).map(t => (
              <span key={t.label} style={{ fontFamily:"var(--fm)", fontSize:9,
                color:"var(--muted)", background:"var(--surf3)",
                border:"1px solid var(--border)", borderRadius:4, padding:"2px 7px" }}>
                {t.label} <span style={{ color:ac, fontWeight:600 }}>{t.count}</span>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Tile 2: TA % change */}
      <div style={tileStyle}>
        {tileTitle("Top / Bottom TA vs Avg")}
        <div style={{ flex:1, display:"flex", flexDirection:"column", justifyContent:"center" }}>
          {has_prior ? (
            <DivergingBars bars={ta_bars} accentColor={ac} labelFn={l => l} />
          ) : (
            <div style={{ fontFamily:"var(--fm)", fontSize:11, color:"var(--muted)" }}>
              Load prior weeks to enable comparison.
            </div>
          )}
        </div>
      </div>

      {/* Tile 3: Modality % change */}
      <div style={tileStyle}>
        {tileTitle("Top / Bottom Modality vs Avg")}
        <div style={{ flex:1, display:"flex", flexDirection:"column", justifyContent:"center" }}>
          {has_prior ? (
            <DivergingBars bars={mod_bars} accentColor={ac} labelFn={l => humanMod(l)} />
          ) : (
            <div style={{ fontFamily:"var(--fm)", fontSize:11, color:"var(--muted)" }}>
              Load prior weeks to enable comparison.
            </div>
          )}
        </div>
      </div>

      {/* Tile 4: Phase 1 intake + phase breakdown */}
      <div style={tileStyle}>
        {tileTitle("Phase 1 Intake Rate")}
        <div style={{ flex:1 }}>
          <Phase1Gauge data={phase1} accentColor={ac} />
          {!phase1?.has_prior && (
            <div style={{ fontFamily:"var(--fm)", fontSize:9, color:"var(--dim)", marginTop:6 }}>
              Avg comparison requires enriched files for prior weeks.
            </div>
          )}
        </div>
        {/* Phase breakdown mini bars */}
        {phase_breakdown?.length > 0 && (() => {
          const maxN = Math.max(...phase_breakdown.map(p => p.count), 1);
          return (
            <div style={{ borderTop:"1px solid var(--border)", paddingTop:10, marginTop:10 }}>
              <div style={{ fontFamily:"var(--fm)", fontSize:8, color:"var(--dim)",
                letterSpacing:"0.12em", marginBottom:6, textTransform:"uppercase" }}>
                All Phases This Week
              </div>
              <div style={{ display:"flex", flexDirection:"column", gap:4 }}>
                {phase_breakdown.map(p => (
                  <div key={p.phase} style={{ display:"flex", alignItems:"center", gap:6 }}>
                    <div style={{ width:72, flexShrink:0, fontFamily:"var(--fm)", fontSize:9,
                      color: p.is_p1 ? ac : "var(--muted)",
                      fontWeight: p.is_p1 ? 600 : 400,
                      textAlign:"right" }}>
                      {p.phase}
                    </div>
                    <div style={{ flex:1, height:6, background:"var(--border)", borderRadius:3 }}>
                      <div style={{ width:`${(p.count / maxN * 100)}%`, height:"100%",
                        background: p.is_p1 ? ac : "var(--muted)",
                        borderRadius:3, opacity:0.7, transition:"width 0.3s" }} />
                    </div>
                    <div style={{ width:30, flexShrink:0, fontFamily:"var(--fm)", fontSize:9,
                      color:"var(--text)", fontWeight:600, textAlign:"right" }}>
                      {p.count}
                    </div>
                    <div style={{ width:32, flexShrink:0, fontFamily:"var(--fm)", fontSize:8,
                      color:"var(--dim)", textAlign:"right" }}>
                      {p.pct}%
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })()}
      </div>

    </div>
  );
}
