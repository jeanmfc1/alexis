// -----------------------------------------------------------------------
// viz/sci_wq2.jsx
// Scientific / wq8 -- Status-Change Spotlight (why_stopped focus)
//
// Data source : ALEXIS_DATA.wq8  (from analytics/sci_wq2.py)
// Globals     : modColor, humanMod
// -----------------------------------------------------------------------

const WQ8_BUCKET_COLORS = {
  safety:     "#EF4444",   // red
  efficacy:   "#F97316",   // orange
  enrollment: "#3B82F6",   // blue
  funding:    "#A78BFA",   // purple
  business:   "#64748B",   // slate
  regulatory: "#F59E0B",   // amber
  covid:      "#06B6D4",   // cyan
  logistics:  "#14B8A6",   // teal
  other:      "#4B5563",   // grey
  unstated:   "#374151",   // dark grey
};

const WQ8_BUCKET_LABEL = {
  safety: "Safety", efficacy: "Efficacy / futility",
  enrollment: "Enrollment issues", funding: "Funding",
  business: "Business / strategic", regulatory: "Regulatory",
  covid: "COVID-related", logistics: "Logistics / supply",
  other: "Other (specified)", unstated: "Not stated",
};

const WQ8_PHASE_COLORS = {
  "PHASE3":"#22C55E","PHASE2/PHASE3":"#86EFAC",
  "PHASE2":"#38BDF8","PHASE1/PHASE2":"#7DD3FC",
  "PHASE1":"#A78BFA","EARLY_PHASE1":"#C4B5FD",
  "PHASE4":"#FB923C","NA":"#6B7280","-":"#4B5563",
};

function WQ8StatusSpotlight({ data, color }) {
  if (!data || !data.available) {
    return (
      <div style={{ padding:"28px 16px", fontFamily:"var(--fm)",
        fontSize:12, color:"var(--muted)", textAlign:"center" }}>
        No status changes detected in this window.
        <div style={{ marginTop:6, fontSize:11, color:"var(--dim)" }}>
          Run analytics/run_update_categorizer.py to generate the enriched file.
        </div>
      </div>
    );
  }

  const [bucketFilter, setBucketFilter] = useState(null);
  const [expandedNct, setExpandedNct]   = useState(null);

  const buckets = data.why_stopped_buckets || {};
  const events  = data.why_stopped_events  || [];
  const newly   = data.newly_recruiting    || [];
  const cats    = data.category_counts     || {};
  const transitions = data.status_transitions || [];

  const totalStops = Object.values(buckets).reduce((a, b) => a + b, 0);

  // ── SVG donut for why_stopped buckets ────────────────────────────────
  const Donut = ({ size = 190, stroke = 32 }) => {
    const entries = Object.entries(buckets);
    if (totalStops === 0 || entries.length === 0) {
      return (
        <div style={{ width:size, height:size, display:"flex",
          alignItems:"center", justifyContent:"center",
          color:"var(--muted)", fontFamily:"var(--fm)", fontSize:11 }}>
          no stop events
        </div>
      );
    }
    const r = (size - stroke) / 2;
    const C = 2 * Math.PI * r;
    let offset = 0;
    const arcs = entries.map(([bucket, count]) => {
      const pct  = count / totalStops;
      const dash = pct * C;
      const arc = {
        bucket, count,
        color: WQ8_BUCKET_COLORS[bucket] || "#475569",
        dash, dashArray: `${dash} ${C - dash}`,
        dashOffset: -offset,
        active: bucketFilter === bucket,
      };
      offset += dash;
      return arc;
    });
    return (
      <svg width={size} height={size} style={{ display:"block" }}>
        <defs>
          <filter id="wq8-glow" x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="3"/>
          </filter>
        </defs>
        <circle cx={size/2} cy={size/2} r={r} fill="none"
          stroke="var(--border)" strokeWidth={stroke} opacity={0.3}/>
        {arcs.map((a, i) => (
          <circle key={i} cx={size/2} cy={size/2} r={r} fill="none"
            stroke={a.color} strokeWidth={stroke}
            strokeDasharray={a.dashArray}
            strokeDashoffset={a.dashOffset}
            transform={`rotate(-90 ${size/2} ${size/2})`}
            onClick={() => setBucketFilter(a.active ? null : a.bucket)}
            style={{ cursor:"pointer", opacity: bucketFilter && !a.active ? 0.25 : 1,
              transition:"opacity 0.2s, stroke-width 0.2s",
              filter: a.active ? "url(#wq8-glow)" : "none" }}/>
        ))}
        <text x={size/2} y={size/2 - 6} textAnchor="middle"
          style={{ fontFamily:"var(--fh)", fontSize:30, fontWeight:700,
            fill:"var(--text)" }}>
          {totalStops}
        </text>
        <text x={size/2} y={size/2 + 14} textAnchor="middle"
          style={{ fontFamily:"var(--fm)", fontSize:9, letterSpacing:"0.14em",
            fill:"var(--muted)" }}>
          STOPPED
        </text>
      </svg>
    );
  };

  // ── Visible event rows (with bucket filter) ──────────────────────────
  const visibleEvents = bucketFilter
    ? events.filter(e => e.bucket === bucketFilter)
    : events;

  return (
    <div style={{ padding:"2px 12px" }}>
      {/* Header KPIs */}
      <div style={{ display:"flex", gap:10, marginBottom:14 }}>
        {[
          { label:"EXISTING-TRIAL CHANGES",  value:data.total_existing_changes },
          { label:"STATUS TRANSITIONS",      value:data.total_status_changes },
          { label:"TRIALS STOPPED / COMPLETED", value:events.length },
          { label:"NEWLY ACTIVE",            value:newly.length,
            tone:"#22C55E" },
        ].map((k, i) => (
          <div key={i} style={{ flex:1,
            background:"var(--surf2)", borderRadius:8,
            border:`1px solid ${color.accent}22`, padding:"12px 14px" }}>
            <div style={{ fontFamily:"var(--fm)", fontSize:9,
              color:"var(--muted)", letterSpacing:"0.14em" }}>
              {k.label}
            </div>
            <div style={{ fontFamily:"var(--fh)", fontSize:24, fontWeight:700,
              color: k.tone || "var(--text)", marginTop:2 }}>
              {k.value.toLocaleString()}
            </div>
          </div>
        ))}
      </div>

      {/* ── Category summary (horizontal bars) ──────────────────────── */}
      <div style={{ marginBottom:18, padding:"12px 14px",
        background:"var(--surf2)", borderRadius:8,
        border:"1px solid var(--border)" }}>
        <div style={{ fontFamily:"var(--fm)", fontSize:9,
          letterSpacing:"0.14em", color:color.mid,
          textTransform:"uppercase", marginBottom:10 }}>
          Updates by category
        </div>
        {(() => {
          const entries = Object.entries(cats).sort((a,b)=>b[1]-a[1]).slice(0,8);
          if (!entries.length) return <div style={{ color:"var(--muted)",
            fontSize:11 }}>no categories</div>;
          const max = Math.max(...entries.map(e=>e[1]));
          return entries.map(([cat, n]) => {
            const pct = (n / max) * 100;
            const isStatus = cat.startsWith("status_");
            const tone = isStatus ? "#EF4444" : color.accent;
            return (
              <div key={cat} style={{ display:"flex",
                alignItems:"center", gap:10, padding:"4px 0" }}>
                <div style={{ width:200, fontFamily:"var(--fm)", fontSize:11,
                  color:"var(--text)" }}>
                  {cat}
                </div>
                <div style={{ flex:1, height:6, background:"var(--border)",
                  borderRadius:3 }}>
                  <div style={{ width:`${pct}%`, height:"100%",
                    background:tone, borderRadius:3,
                    transition:"width 0.3s ease", opacity:0.8 }}/>
                </div>
                <div style={{ fontFamily:"var(--fm)", fontSize:12,
                  color:"var(--text)", minWidth:40, textAlign:"right" }}>
                  {n}
                </div>
              </div>
            );
          });
        })()}
      </div>

      {/* Why-stopped spotlight header */}
      <div style={{ marginBottom:18, padding:"14px 16px",
        background:"var(--surf2)", borderRadius:8,
        border:"1px solid var(--border)" }}>
        <div style={{ display:"flex", alignItems:"center",
          justifyContent:"space-between", marginBottom:12 }}>
          <div style={{ fontFamily:"var(--fm)", fontSize:9,
            letterSpacing:"0.14em", color:color.mid,
            textTransform:"uppercase" }}>
            Why did trials stop? (click a slice or chip to filter)
          </div>
          {bucketFilter && (
            <button onClick={() => setBucketFilter(null)}
              style={{ background:"transparent", border:"1px solid var(--border2)",
                color:"var(--muted)", borderRadius:4, padding:"3px 10px",
                fontFamily:"var(--fm)", fontSize:10, cursor:"pointer" }}>
              clear filter
            </button>
          )}
        </div>

        <div style={{ display:"flex", gap:20, alignItems:"flex-start" }}>
          <div style={{ flexShrink:0 }}><Donut/></div>

          <div style={{ flex:1, minWidth:0 }}>
            <div style={{ display:"flex", flexWrap:"wrap", gap:6,
              marginBottom:12 }}>
              {Object.entries(buckets).map(([b, n]) => {
                const hue = WQ8_BUCKET_COLORS[b] || "#475569";
                const active = bucketFilter === b;
                return (
                  <div key={b} onClick={() => setBucketFilter(active ? null : b)}
                    style={{ cursor:"pointer", padding:"4px 10px",
                      borderRadius:14,
                      background: active ? hue+"30" : hue+"14",
                      border: "1px solid " + hue + (active ? "60" : "30"),
                      fontFamily:"var(--fm)", fontSize:11,
                      color: active ? "var(--text)" : hue,
                      fontWeight: active ? 600 : 500,
                      transition:"all 0.15s" }}>
                    {WQ8_BUCKET_LABEL[b] || b}  ·  {n}
                  </div>
                );
              })}
            </div>

            <div style={{ maxHeight:360, overflowY:"auto",
              border:"1px solid var(--border)", borderRadius:6 }}>
              <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
                <thead>
                  <tr style={{ background:"var(--surf3)" }}>
                    {["NCT","Phase","Modality","TA","Sponsor","Bucket","Reason"].map(h => (
                      <th key={h} style={{ padding:"7px 10px", textAlign:"left",
                        fontFamily:"var(--fm)", fontSize:9,
                        letterSpacing:"0.12em", color:"var(--muted)",
                        textTransform:"uppercase", position:"sticky", top:0,
                        background:"var(--surf3)",
                        borderBottom:"1px solid var(--border)" }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {visibleEvents.slice(0, 60).map((e, i) => {
                    const hue   = WQ8_BUCKET_COLORS[e.bucket] || "#475569";
                    const phase = e.phase || "-";
                    const pc    = WQ8_PHASE_COLORS[phase] || "#4B5563";
                    const opened = expandedNct === e.nct_id;
                    return (
                      <React.Fragment key={i}>
                        <tr onClick={() => setExpandedNct(opened ? null : e.nct_id)}
                          style={{ borderTop:"1px solid var(--border)",
                            cursor:"pointer",
                            background: opened ? "var(--surf3)"
                              : (i%2===0 ? "transparent" : "rgba(255,255,255,0.015)") }}>
                          <td style={{ padding:"6px 10px", whiteSpace:"nowrap" }}>
                            <a href={e.source_url} target="_blank" rel="noreferrer"
                               style={{ color:"var(--cyan)", fontFamily:"var(--fm)",
                                 fontSize:11, textDecoration:"none" }}
                               onClick={ev => ev.stopPropagation()}>
                              {e.nct_id}
                            </a>
                          </td>
                          <td style={{ padding:"6px 10px" }}>
                            <span style={{ fontFamily:"var(--fm)", fontSize:10,
                              padding:"1px 6px", borderRadius:6, color:pc,
                              background:pc+"18",
                              border:"1px solid "+pc+"30" }}>{phase}</span>
                          </td>
                          <td style={{ padding:"6px 10px" }}>
                            {e.modality
                              ? <span style={{ fontFamily:"var(--fm)", fontSize:10,
                                  padding:"1px 6px", borderRadius:6,
                                  background:modColor(e.modality)+"20",
                                  color:modColor(e.modality),
                                  border:"1px solid "+modColor(e.modality)+"30" }}>
                                  {humanMod(e.modality)}
                                </span>
                              : <span style={{ color:"var(--muted)" }}>-</span>}
                          </td>
                          <td style={{ padding:"6px 10px",
                            color:"var(--muted)", maxWidth:120,
                            overflow:"hidden", textOverflow:"ellipsis",
                            whiteSpace:"nowrap" }} title={e.ta || ""}>
                            {e.ta || "-"}
                          </td>
                          <td style={{ padding:"6px 10px", maxWidth:200,
                            overflow:"hidden", textOverflow:"ellipsis",
                            whiteSpace:"nowrap" }} title={e.sponsor || ""}>
                            {e.sponsor || "-"}
                          </td>
                          <td style={{ padding:"6px 10px" }}>
                            <span style={{ display:"inline-block", width:8,
                              height:8, borderRadius:"50%", background:hue,
                              marginRight:6, verticalAlign:"middle" }}/>
                            <span style={{ color:hue, fontSize:11 }}>
                              {WQ8_BUCKET_LABEL[e.bucket] || e.bucket}
                            </span>
                          </td>
                          <td style={{ padding:"6px 10px", color:"var(--text)",
                            fontSize:11, maxWidth:320, overflow:"hidden",
                            textOverflow:"ellipsis", whiteSpace:"nowrap" }}
                            title={e.reason_text}>
                            {e.reason_text || "(not stated)"}
                          </td>
                        </tr>
                        {opened && (
                          <tr style={{ background:"var(--surf3)" }}>
                            <td colSpan={7} style={{ padding:"8px 14px 14px 14px" }}>
                              <div style={{ fontFamily:"var(--fb)", fontSize:13,
                                color:"var(--text)", marginBottom:6 }}>
                                {e.title}
                              </div>
                              <div style={{ fontFamily:"var(--fm)", fontSize:11,
                                color:"var(--muted)" }}>
                                {e.from_status} to <b style={{color:hue}}>{e.to_status}</b>
                                {e.sponsor_class && " · " + e.sponsor_class}
                              </div>
                              {e.reason_text && (
                                <div style={{ marginTop:8, padding:"8px 10px",
                                  background:"var(--surf2)", borderRadius:4,
                                  borderLeft:"3px solid "+hue,
                                  fontSize:12, color:"var(--text)",
                                  lineHeight:1.45 }}>
                                  {e.reason_text}
                                </div>
                              )}
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                  {visibleEvents.length === 0 && (
                    <tr><td colSpan={7} style={{ padding:"14px",
                      textAlign:"center", color:"var(--muted)",
                      fontSize:11 }}>no events in this bucket</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      {/* Newly recruiting strip */}
      {newly.length > 0 && (
        <div style={{ marginBottom:4, padding:"14px 16px",
          background:"var(--surf2)", borderRadius:8,
          border:"1px solid var(--border)" }}>
          <div style={{ display:"flex", alignItems:"center", gap:10,
            marginBottom:10 }}>
            <div style={{ fontFamily:"var(--fm)", fontSize:9,
              letterSpacing:"0.14em", color:"#22C55E",
              textTransform:"uppercase" }}>
              Newly active ({newly.length})
            </div>
            <div style={{ fontFamily:"var(--fm)", fontSize:10,
              color:"var(--muted)" }}>
              Trials that flipped into RECRUITING / ACTIVE this week
            </div>
          </div>
          <div style={{ display:"flex", gap:10, overflowX:"auto",
            paddingBottom:4 }}>
            {newly.slice(0, 24).map((t, i) => {
              const phase = t.phase || "-";
              const pc = WQ8_PHASE_COLORS[phase] || "#4B5563";
              return (
                <a key={i} href={t.source_url} target="_blank" rel="noreferrer"
                  style={{ flexShrink:0, width:240, padding:"10px 12px",
                    background:"var(--surf3)",
                    border:"1px solid #22C55E30",
                    borderRadius:6, textDecoration:"none",
                    cursor:"pointer", transition:"all 0.15s" }}>
                  <div style={{ display:"flex", gap:6, marginBottom:4 }}>
                    <span style={{ fontFamily:"var(--fm)", fontSize:10,
                      color:"var(--cyan)" }}>{t.nct_id}</span>
                    <span style={{ fontFamily:"var(--fm)", fontSize:9,
                      padding:"1px 5px", borderRadius:5, color:pc,
                      background:pc+"18",
                      border:"1px solid "+pc+"30" }}>{phase}</span>
                    {t.modality && (
                      <span style={{ fontFamily:"var(--fm)", fontSize:9,
                        padding:"1px 5px", borderRadius:5,
                        background:modColor(t.modality)+"20",
                        color:modColor(t.modality),
                        border:"1px solid "+modColor(t.modality)+"30" }}>
                        {humanMod(t.modality)}
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize:12, color:"var(--text)",
                    lineHeight:1.3,
                    display:"-webkit-box", WebkitLineClamp:2,
                    WebkitBoxOrient:"vertical", overflow:"hidden" }}>
                    {t.title}
                  </div>
                  <div style={{ fontFamily:"var(--fm)", fontSize:10,
                    color:"var(--muted)", marginTop:4 }}>
                    {t.sponsor || "-"}
                  </div>
                </a>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
