// -----------------------------------------------------------------------
// viz/mk_wq2.jsx
// Marketing / wq5 -- Modality & TA Over/Under Index
//
// Data source : ALEXIS_DATA.wq5  (from analytics/mk_wq2.py)
// Globals     : modColor, humanMod
// -----------------------------------------------------------------------

const WQ5_TREND_COLOR = {
  hot:     "#EF4444",
  rising:  "#F59E0B",
  steady:  "#64748B",
  cold:    "#3B82F6",
  new:     "#00CFFF",
};
const WQ5_TREND_LABEL = {
  hot: "HOT",     rising: "rising",  steady: "steady",
  cold: "cold",   new: "NEW",
};

function WQ5ModalityIndex({ data, color }) {
  if (!data || !data.available) {
    return (
      <div style={{ padding:"24px 16px", fontFamily:"var(--fm)",
        fontSize:12, color:"var(--muted)", textAlign:"center" }}>
        Over/Under index needs prior-week snapshots to compute a baseline.
        <div style={{ marginTop:6, fontSize:11, color:"var(--dim)" }}>
          Load at least one prior week when generating the dashboard.
        </div>
      </div>
    );
  }

  const [openKey, setOpenKey] = useState(null);

  const mods = data.modalities || [];
  const tas  = data.tas        || [];
  const th   = data.meta?.thresholds || {};

  // Shared scale for the diverging bars: clamp to [0, 3]
  const MAX_IDX = 3;

  // Diverging bar: center at 1.0, left=cold (width proportional to 1-idx),
  // right=hot (width proportional to idx-1)
  const DivergingBar = ({ row, side }) => {
    // side = "mod" or "ta" -- determines the key + color
    const idx     = row.index;
    const trend   = row.trend;
    const hueBar  = WQ5_TREND_COLOR[trend] || "#64748B";
    const hueLab  = side === "mod" ? modColor(row.name) : color.accent;

    const leftPct  = idx == null ? 0 : Math.min(1, Math.max(0, (1 - idx))) * 50;
    const rightPct = idx == null ? 0 : Math.min(1, Math.max(0, idx - 1) / (MAX_IDX - 1)) * 50;
    const zero     = idx == null;

    const key = `${side}:${row.name}`;
    const opened = openKey === key;

    return (
      <React.Fragment>
        <div onClick={() => setOpenKey(opened ? null : key)}
          style={{ display:"flex", alignItems:"center", gap:8,
            padding:"6px 10px", cursor:"pointer",
            background: opened ? "var(--surf3)" : "transparent",
            borderRadius:4, transition:"background 0.15s" }}>
          {/* Label */}
          <div style={{ width:160, flexShrink:0 }}>
            {side === "mod" ? (
              <span style={{ fontFamily:"var(--fm)", fontSize:11,
                padding:"2px 6px", borderRadius:8,
                background:modColor(row.name)+"20",
                color:modColor(row.name),
                border:"1px solid "+modColor(row.name)+"30" }}>
                {humanMod(row.name)}
              </span>
            ) : (
              <span style={{ fontFamily:"var(--fb)", fontSize:12,
                color:"var(--text)" }}>{row.name}</span>
            )}
          </div>
          {/* Diverging bar */}
          <div style={{ flex:1, position:"relative", height:16,
            background:"var(--surf2)", borderRadius:3, overflow:"hidden" }}>
            {/* Cold (left of center) */}
            <div style={{ position:"absolute", top:0, bottom:0,
              right:"50%", width:`${leftPct}%`,
              background:"rgba(59,130,246,0.85)",
              borderRadius:"3px 0 0 3px",
              transition:"width 0.3s ease" }}/>
            {/* Hot (right of center) */}
            <div style={{ position:"absolute", top:0, bottom:0,
              left:"50%", width:`${rightPct}%`,
              background:"rgba(239,68,68,0.85)",
              borderRadius:"0 3px 3px 0",
              transition:"width 0.3s ease" }}/>
            {/* Center line */}
            <div style={{ position:"absolute", top:0, bottom:0,
              left:"50%", width:2, background:"rgba(255,255,255,0.2)" }}/>
          </div>
          {/* Numeric */}
          <div style={{ width:50, textAlign:"right",
            fontFamily:"var(--fm)", fontSize:11,
            color: zero ? "var(--cyan)" : "var(--text)",
            fontWeight:600 }}>
            {zero ? "NEW" : `${idx}×`}
          </div>
          {/* This / baseline */}
          <div style={{ width:78, textAlign:"right",
            fontFamily:"var(--fm)", fontSize:10, color:"var(--muted)" }}>
            {row.this_week} / {row.baseline || "—"}
          </div>
          {/* Trend tag */}
          <div style={{ width:60, textAlign:"right" }}>
            <span style={{ fontFamily:"var(--fm)", fontSize:10,
              fontWeight: trend === "hot" || trend === "new" ? 600 : 500,
              color:hueBar, letterSpacing:"0.08em",
              textTransform:"uppercase" }}>
              {WQ5_TREND_LABEL[trend] || trend}
            </span>
          </div>
        </div>

        {opened && (row.samples || []).length > 0 && (
          <div style={{ padding:"4px 12px 10px 172px" }}>
            <div style={{ fontFamily:"var(--fm)", fontSize:9,
              letterSpacing:"0.12em", color:"var(--dim)",
              textTransform:"uppercase", marginBottom:4 }}>
              Story seeds
            </div>
            {row.samples.map((s, i) => (
              <a key={i} href={s.source_url} target="_blank" rel="noreferrer"
                 style={{ display:"block", padding:"5px 8px",
                   background:"var(--surf2)", borderRadius:4,
                   textDecoration:"none", marginBottom:3,
                   borderLeft:"2px solid "+hueBar }}>
                <span style={{ fontFamily:"var(--fm)", fontSize:10,
                  color:"var(--cyan)" }}>{s.nct_id}</span>
                <span style={{ marginLeft:6, color:"var(--text)",
                  fontSize:11 }}>{s.title}</span>
                {s.sponsor && (
                  <span style={{ marginLeft:6, color:"var(--muted)",
                    fontSize:10 }}>· {s.sponsor}</span>
                )}
              </a>
            ))}
          </div>
        )}
      </React.Fragment>
    );
  };

  const Panel = ({ title, rows, side }) => (
    <div style={{ flex:1, background:"var(--surf2)",
      borderRadius:8, border:"1px solid var(--border)",
      padding:"14px 16px" }}>
      <div style={{ fontFamily:"var(--fm)", fontSize:9,
        letterSpacing:"0.14em", color:color.mid,
        textTransform:"uppercase", marginBottom:10 }}>
        {title}
      </div>
      {/* Header row */}
      <div style={{ display:"flex", alignItems:"center", gap:8,
        padding:"4px 10px", fontFamily:"var(--fm)", fontSize:9,
        letterSpacing:"0.10em", color:"var(--dim)",
        textTransform:"uppercase", marginBottom:4 }}>
        <div style={{ width:160 }}>{side === "mod" ? "Modality" : "Therapeutic area"}</div>
        <div style={{ flex:1, position:"relative" }}>
          <span style={{ position:"absolute", left:0 }}>cold</span>
          <span style={{ position:"absolute", left:"50%",
            transform:"translateX(-50%)" }}>baseline 1×</span>
          <span style={{ position:"absolute", right:0 }}>hot</span>
        </div>
        <div style={{ width:50, textAlign:"right" }}>index</div>
        <div style={{ width:78, textAlign:"right" }}>this / base</div>
        <div style={{ width:60, textAlign:"right" }}>trend</div>
      </div>
      {rows.map(r => <DivergingBar key={r.name} row={r} side={side}/>)}
      {rows.length === 0 && (
        <div style={{ padding:"14px", textAlign:"center",
          color:"var(--muted)", fontSize:11 }}>
          no data in this bucket
        </div>
      )}
    </div>
  );

  return (
    <div style={{ padding:"0 12px" }}>
      <div style={{ display:"flex", alignItems:"center", gap:10,
        marginBottom:10, fontFamily:"var(--fm)", fontSize:10,
        color:"var(--muted)", letterSpacing:"0.06em" }}>
        <span><b style={{ color:"var(--text)" }}>{data.meta?.total_new || 0}</b> new drug trials this week</span>
        <span style={{ color:"var(--dim)" }}>|</span>
        <span>baseline from <b style={{ color:"var(--text)" }}>{data.meta?.prior_weeks_used || 0}</b> prior weeks</span>
        <span style={{ color:"var(--dim)" }}>|</span>
        <span>
          <b style={{ color:"#EF4444" }}>hot</b> {">="} {th.hot}x +
          {" "}{th.hot_min_count} trials ·
          {" "}<b style={{ color:"#3B82F6" }}>cold</b> {"<="} {th.cold}x with baseline {">="} {th.cold_min_base}
        </span>
      </div>

      <div style={{ display:"flex", gap:14 }}>
        <Panel title="Modalities" rows={mods} side="mod"/>
        <Panel title="Therapeutic areas" rows={tas} side="ta"/>
      </div>
    </div>
  );
}
