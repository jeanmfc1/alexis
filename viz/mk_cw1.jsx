// -----------------------------------------------------------------------
// viz/mk_cw1.jsx
// Marketing / cw2 (ChiCTR) -- TA Momentum Stat Cards
//
// Data source : ALEXIS_DATA.cw2  (cards + items from
//               analytics/mk_cw1.py::cw2_china_ta_momentum)
// Globals used from host: modColor, humanMod
// -----------------------------------------------------------------------

function CW2ChinaTAMomentum({ data, color }) {
  if (!data || data.available === false) {
    return (
      <div style={{ padding:"24px 16px", fontFamily:"var(--fm)",
        fontSize:12, color:"var(--muted)", textAlign:"center" }}>
        No ChiCTR momentum data yet. Run pipelines/run_diff_chictr.py.
      </div>
    );
  }

  const cards = data.cards || [];
  const items = data.items || [];
  const th    = data.thresholds || {};

  const trendColor = (t) =>
      t === "accelerating" ? "#22C55E"
    : t === "new"          ? "#00CFFF"
    : t === "slowing"      ? "#EF4444"
    : "var(--muted)";

  const StatCard = ({ c }) => {
    const maxDetail = Math.max(1, ...((c.detail || []).map(d => d.value || 0)));
    return (
      <div style={{ background:"var(--surf2)", borderRadius:10,
        border:`1px solid ${color.accent}22`, padding:"20px 22px",
        display:"flex", flexDirection:"column", gap:12 }}>
        <div style={{ fontFamily:"var(--fm)", fontSize:9,
          color:color.mid, letterSpacing:"0.16em",
          textTransform:"uppercase" }}>
          {c.title}
        </div>
        <div style={{ fontFamily:"var(--fh)",
          fontSize: String(c.value).length > 6 ? 22 : 32,
          fontWeight:700, color:"var(--text)", lineHeight:1.1 }}>
          {c.value}
        </div>
        {c.sub && (
          <div style={{ fontFamily:"var(--fm)", fontSize:11,
            color:"var(--muted)" }}>{c.sub}</div>
        )}
        <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
          {(c.detail || []).map((d, i) => {
            const barPct = d.value ? (d.value / maxDetail) * 100 : 0;
            return (
              <div key={i} style={{ display:"flex", alignItems:"center",
                gap:10 }}>
                <div style={{ flex:1, fontFamily:"var(--fb)", fontSize:12,
                  color:"var(--text)",
                  overflow:"hidden", textOverflow:"ellipsis",
                  whiteSpace:"nowrap" }}>
                  {d.ta}
                  {d.modality && (
                    <span style={{ marginLeft:6, fontFamily:"var(--fm)",
                      fontSize:10, padding:"1px 5px", borderRadius:6,
                      background:modColor(d.modality)+"20",
                      color:modColor(d.modality),
                      border:`1px solid ${modColor(d.modality)}30` }}>
                      {humanMod(d.modality)}
                    </span>
                  )}
                </div>
                <div style={{ fontFamily:"var(--fm)", fontSize:11,
                  color:"var(--muted)", minWidth:40, textAlign:"right" }}>
                  {d.ratio != null ? `${d.ratio}x` : "new"}
                </div>
                <div style={{ width:80, height:3,
                  background:"var(--border)", borderRadius:2 }}>
                  <div style={{ width:`${Math.min(100, barPct)}%`,
                    height:"100%", background:color.accent,
                    borderRadius:2, opacity:0.6 }}/>
                </div>
                <div style={{ fontFamily:"var(--fm)", fontSize:12,
                  color:"var(--text)", minWidth:26, textAlign:"right" }}>
                  {d.value}
                </div>
              </div>
            );
          })}
        </div>
        {c.note && (
          <div style={{ fontFamily:"var(--fm)", fontSize:9,
            color:"var(--dim)", letterSpacing:"0.06em",
            marginTop:"auto" }}>{c.note}</div>
        )}
      </div>
    );
  };

  return (
    <div>
      {/* Trend-threshold explanation strip */}
      <div style={{ padding:"6px 12px 10px", fontFamily:"var(--fm)",
        fontSize:10, color:"var(--muted)", letterSpacing:"0.06em" }}>
        Trend thresholds:&nbsp;
        <span style={{ color:trendColor("accelerating"), fontWeight:600 }}>
          accelerating
        </span>
        &nbsp;= this week {">="} {th.accelerating_ratio}x baseline AND {">="} {th.accelerating_min} trials&nbsp;
        <span style={{ color:"var(--dim)" }}>|</span>&nbsp;
        <span style={{ color:trendColor("slowing"), fontWeight:600 }}>
          slowing
        </span>
        &nbsp;= {"<="} {th.slowing_ratio}x baseline AND baseline {">="} {th.slowing_min_base}&nbsp;
        <span style={{ color:"var(--dim)" }}>|</span>&nbsp;
        <span style={{ color:trendColor("new"), fontWeight:600 }}>
          new
        </span>
        &nbsp;= no prior activity
      </div>

      {/* 2x2 stat-card grid */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(2, 1fr)",
        gap:14, padding:"0 12px" }}>
        {cards.map((c, i) => <StatCard key={i} c={c}/>)}
      </div>

      {/* Full ranked table below */}
      <div style={{ marginTop:18, padding:"0 12px" }}>
        <div style={{ fontFamily:"var(--fm)", fontSize:9,
          letterSpacing:"0.12em", color:"var(--muted)",
          textTransform:"uppercase", marginBottom:8 }}>
          All TAs -- this week vs baseline
        </div>
        <div style={{ border:"1px solid var(--border)", borderRadius:8,
          overflow:"hidden" }}>
          <table style={{ width:"100%", borderCollapse:"collapse",
            fontSize:12 }}>
            <thead>
              <tr style={{ background:"var(--surf2)" }}>
                {["TA","This week","Baseline","Ratio","Trend","Top modality"]
                  .map(h => (
                  <th key={h} style={{ padding:"8px 10px",
                    textAlign:"left", fontFamily:"var(--fm)",
                    fontSize:9, letterSpacing:"0.12em",
                    textTransform:"uppercase", color:"var(--muted)",
                    borderBottom:"2px solid var(--border)" }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {items.slice(0, 25).map((r, i) => {
                const maxRatio = Math.max(2, ...items
                  .filter(x => x.ratio != null).map(x => x.ratio));
                const pct = r.ratio != null
                  ? Math.min(100, (r.ratio / maxRatio) * 100) : 100;
                return (
                  <tr key={i} style={{
                    background: i%2===0 ? "var(--surf)" : "transparent",
                    borderTop:"1px solid var(--border)" }}>
                    <td style={{ padding:"8px 10px", color:"var(--text)" }}>
                      {r.ta}
                    </td>
                    <td style={{ padding:"8px 10px",
                      fontFamily:"var(--fm)", color:"var(--text)" }}>
                      {r.this_week}
                    </td>
                    <td style={{ padding:"8px 10px",
                      fontFamily:"var(--fm)", color:"var(--muted)" }}>
                      {r.baseline}
                    </td>
                    <td style={{ padding:"8px 10px" }}>
                      <div style={{ display:"flex", alignItems:"center", gap:8 }}>
                        <div style={{ width:90, height:4,
                          background:"var(--border)", borderRadius:2 }}>
                          <div style={{ width:`${pct}%`, height:"100%",
                            background:trendColor(r.trend),
                            borderRadius:2, opacity:0.65 }}/>
                        </div>
                        <span style={{ fontFamily:"var(--fm)", fontSize:11,
                          color:"var(--muted)", minWidth:40, textAlign:"right" }}>
                          {r.ratio != null ? `${r.ratio}x` : "new"}
                        </span>
                      </div>
                    </td>
                    <td style={{ padding:"8px 10px",
                      color:trendColor(r.trend), fontWeight:600,
                      fontFamily:"var(--fm)", fontSize:11 }}>
                      {r.trend}
                    </td>
                    <td style={{ padding:"8px 10px" }}>
                      {r.top_modality ? (
                        <span style={{ fontFamily:"var(--fm)", fontSize:10,
                          padding:"2px 6px", borderRadius:8,
                          background:modColor(r.top_modality)+"20",
                          color:modColor(r.top_modality),
                          border:`1px solid ${modColor(r.top_modality)}30` }}>
                          {humanMod(r.top_modality)}
                        </span>
                      ) : <span style={{ color:"var(--muted)" }}>-</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div style={{ marginTop:8, fontFamily:"var(--fm)", fontSize:9,
          color:"var(--dim)", letterSpacing:"0.06em" }}>
          Baseline = mean weekly additions computed from{" "}
          {data.pair_windows || 0} consecutive prior-snapshot deltas.
          Snapshots used: {data.snapshots_used}.
        </div>
      </div>
    </div>
  );
}
