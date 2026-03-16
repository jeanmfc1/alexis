// ─────────────────────────────────────────────────────────────────────────
// viz/bd_sq2.jsx
// BD / sq2 — Top 25 Sponsors and What They Run
//
// Data source : ALEXIS_DATA.sq2  (dict from bd_sq2.py)
// Injected by : analytics/bd_sq2.py → sq2_top_sponsors()
// ─────────────────────────────────────────────────────────────────────────

function exportSQ2CSV(sponsors) {
  const headers = ["rank","sponsor_name","total_trials","top_modality","top_ta","complexity_score"];
  const lines = [
    headers.join(","),
    ...sponsors.map((r, i) => [
      i + 1,
      `"${r.sponsor_name}"`,
      r.total_trials,
      r.top_modality || "",
      `"${r.top_ta || ""}"`,
      r.complexity_score,
    ].join(","))
  ];
  const blob = new Blob([lines.join("\n")], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "bd_sq2_top_sponsors.csv";
  a.click();
}


// ── Sponsor Profile Panel ─────────────────────────────────────────
function SponsorProfile({ sponsor, color, PHASE_COLORS }) {
  if (!sponsor) return null;

  const { sponsor_name, total_trials, phase_breakdown, ta_breakdown, modality_breakdown, trials } = sponsor;

  const phaseDist = phase_breakdown || {};
  const phaseTotal = Object.values(phaseDist).reduce((s, n) => s + n, 0) || 1;
  const buckets = [
    { key:"PHASE1", label:"P1", count: (phaseDist["PHASE1"]||0)+(phaseDist["EARLY_PHASE1"]||0)+(phaseDist["PHASE1/PHASE2"]||0) },
    { key:"PHASE2", label:"P2", count: (phaseDist["PHASE2"]||0)+(phaseDist["PHASE2/PHASE3"]||0) },
    { key:"PHASE3", label:"P3", count: phaseDist["PHASE3"]||0 },
    { key:"PHASE4", label:"P4", count: phaseDist["PHASE4"]||0 },
    { key:"NA", label:"Other", count: phaseTotal - ((phaseDist["PHASE1"]||0)+(phaseDist["EARLY_PHASE1"]||0)+(phaseDist["PHASE1/PHASE2"]||0)+(phaseDist["PHASE2"]||0)+(phaseDist["PHASE2/PHASE3"]||0)+(phaseDist["PHASE3"]||0)+(phaseDist["PHASE4"]||0)) },
  ].filter(b => b.count > 0);

  const R = 36, r = 22, cx = 44, cy = 44;
  let cumAngle = -90;
  const toRad = a => (a * Math.PI) / 180;
  const arcs = buckets.map(b => {
    const angle = (b.count / phaseTotal) * 360;
    const startAngle = cumAngle; cumAngle += angle; const endAngle = cumAngle;
    const largeArc = angle > 180 ? 1 : 0;
    const x1 = cx + R * Math.cos(toRad(startAngle));
    const y1 = cy + R * Math.sin(toRad(startAngle));
    const x2 = cx + R * Math.cos(toRad(endAngle));
    const y2 = cy + R * Math.sin(toRad(endAngle));
    const ix1 = cx + r * Math.cos(toRad(endAngle));
    const iy1 = cy + r * Math.sin(toRad(endAngle));
    const ix2 = cx + r * Math.cos(toRad(startAngle));
    const iy2 = cy + r * Math.sin(toRad(startAngle));
    if (buckets.length === 1) { return (<circle key={b.key} cx={cx} cy={cy} r={(R+r)/2} fill="none" stroke={PHASE_COLORS[b.key]||"#475569"} strokeWidth={R-r} opacity={0.85} />); }
    const d = [
      `M ${x1} ${y1}`,
      `A ${R} ${R} 0 ${largeArc} 1 ${x2} ${y2}`,
      `L ${ix1} ${iy1}`,
      `A ${r} ${r} 0 ${largeArc} 0 ${ix2} ${iy2}`,
      `Z`
    ].join(" ");
    return <path key={b.key} d={d} fill={PHASE_COLORS[b.key]||"#475569"} opacity={0.85} />;
  });

  const taEntries = Object.entries(ta_breakdown || {}).sort((a, b) => b[1] - a[1]).slice(0, 8);
  const taMax = taEntries[0]?.[1] || 1;
  const modEntries = Object.entries(modality_breakdown || {}).sort((a, b) => b[1] - a[1]).slice(0, 5);
  const modMax = modEntries[0]?.[1] || 1;
  const trialList = trials || [];
  const phaseBadgeColor = (phase) => { if (!phase) return "#475569"; return PHASE_COLORS[phase] || "#475569"; };

  return (
    <div style={{ background:"var(--surf2)", borderRadius:10,
      border:"1px solid var(--border)", padding:"18px 20px", marginTop:12 }}>
      {/* Header */}
      <div style={{ display:"flex", alignItems:"baseline", gap:10, marginBottom:14 }}>
        <span style={{ fontFamily:"var(--fm)", fontSize:14, fontWeight:600, color:"var(--text)" }}>{sponsor_name}</span>
        <span style={{ fontFamily:"var(--fm)", fontSize:11, color:color.mid, fontWeight:600 }}>{total_trials} trials</span>
      </div>

      {/* Phase donut + TA bars + Modality bars */}
      <div style={{ display:"flex", gap:20, marginBottom:16, flexWrap:"wrap" }}>
        {/* Phase donut */}
        <div style={{ display:"flex", flexDirection:"column", alignItems:"center", gap:6 }}>
          <svg width={88} height={88} viewBox="0 0 88 88">{arcs}</svg>
          <div style={{ display:"flex", gap:8, flexWrap:"wrap", justifyContent:"center" }}>
            {buckets.map(b => (
              <div key={b.key} style={{ display:"flex", alignItems:"center", gap:3 }}>
                <div style={{ width:7, height:7, borderRadius:2, background:PHASE_COLORS[b.key]||"#475569" }} />
                <span style={{ fontFamily:"var(--fm)", fontSize:8, color:"var(--muted)" }}>{b.label} {b.count}</span>
              </div>
            ))}
          </div>
        </div>

        {/* TA horizontal bars (top 8) */}
        <div style={{ flex:1, minWidth:200 }}>
          <div style={{ fontFamily:"var(--fm)", fontSize:9, color:"var(--dim)", letterSpacing:"0.08em", marginBottom:6 }}>THERAPEUTIC AREAS</div>
          {taEntries.map(([ta, count]) => (
            <div key={ta} style={{ display:"flex", alignItems:"center", gap:6, marginBottom:3 }}>
              <div style={{ width:120, fontFamily:"var(--fm)", fontSize:9, color:"var(--muted)", overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap", flexShrink:0 }} title={ta}>{ta}</div>
              <div style={{ flex:1, height:12, borderRadius:2, background:"var(--surf3)", overflow:"hidden" }}>
                <div style={{ width:`${(count/taMax)*100}%`, height:"100%", background:color.accent, opacity:0.7, borderRadius:2 }} />
              </div>
              <span style={{ fontFamily:"var(--fm)", fontSize:9, color:"var(--dim)", width:28, textAlign:"right", flexShrink:0 }}>{count}</span>
            </div>
          ))}
        </div>

        {/* Modality horizontal bars (top 5) */}
        <div style={{ flex:1, minWidth:180 }}>
          <div style={{ fontFamily:"var(--fm)", fontSize:9, color:"var(--dim)", letterSpacing:"0.08em", marginBottom:6 }}>MODALITIES</div>
          {modEntries.map(([mod, count]) => (
            <div key={mod} style={{ display:"flex", alignItems:"center", gap:6, marginBottom:3 }}>
              <div style={{ width:100, fontFamily:"var(--fm)", fontSize:9, color:"var(--muted)", overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap", flexShrink:0 }} title={mod}>{humanMod(mod)}</div>
              <div style={{ flex:1, height:12, borderRadius:2, background:"var(--surf3)", overflow:"hidden" }}>
                <div style={{ width:`${(count/modMax)*100}%`, height:"100%", background:modColor(mod), opacity:0.7, borderRadius:2 }} />
              </div>
              <span style={{ fontFamily:"var(--fm)", fontSize:9, color:"var(--dim)", width:28, textAlign:"right", flexShrink:0 }}>{count}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Trial table */}
      <div style={{ fontFamily:"var(--fm)", fontSize:9, color:"var(--dim)", letterSpacing:"0.08em", marginBottom:6 }}>TRIALS ({trialList.length})</div>
      <div style={{ maxHeight:220, overflowY:"auto", border:"1px solid var(--border)", borderRadius:6, background:"var(--surf3)" }}>
        <table style={{ width:"100%", borderCollapse:"collapse", fontFamily:"var(--fm)", fontSize:10 }}>
          <thead>
            <tr style={{ borderBottom:"1px solid var(--border)", position:"sticky", top:0, background:"var(--surf3)", zIndex:1 }}>
              <th style={{ textAlign:"left", padding:"6px 8px", color:"var(--muted)", fontSize:9, letterSpacing:"0.06em", fontWeight:500 }}>NCT ID</th>
              <th style={{ textAlign:"left", padding:"6px 8px", color:"var(--muted)", fontSize:9, letterSpacing:"0.06em", fontWeight:500 }}>TITLE</th>
              <th style={{ textAlign:"center", padding:"6px 8px", color:"var(--muted)", fontSize:9, letterSpacing:"0.06em", fontWeight:500 }}>PHASE</th>
              <th style={{ textAlign:"left", padding:"6px 8px", color:"var(--muted)", fontSize:9, letterSpacing:"0.06em", fontWeight:500 }}>TA</th>
              <th style={{ textAlign:"left", padding:"6px 8px", color:"var(--muted)", fontSize:9, letterSpacing:"0.06em", fontWeight:500 }}>STATUS</th>
            </tr>
          </thead>
          <tbody>
            {trialList.map(t => (
              <tr key={t.nct_id} style={{ borderBottom:"1px solid var(--border)" }}>
                <td style={{ padding:"5px 8px", whiteSpace:"nowrap" }}>
                  <a href={`https://clinicaltrials.gov/study/${t.nct_id}`}
                    target="_blank" rel="noopener noreferrer"
                    style={{ color:color.accent, textDecoration:"none" }}>
                    {t.nct_id}
                  </a>
                </td>
                <td style={{ padding:"5px 8px", color:"var(--text)", maxWidth:260, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}
                  title={t.title}>{t.title}</td>
                <td style={{ padding:"5px 8px", textAlign:"center" }}>
                  <span style={{ display:"inline-block", padding:"1px 6px", borderRadius:3, fontSize:8, fontWeight:600, background:phaseBadgeColor(t.phase)+"22", color:phaseBadgeColor(t.phase) }}>
                    {t.phase ? t.phase.replace("PHASE","P") : "—"}
                  </span>
                </td>
                <td style={{ padding:"5px 8px", color:"var(--muted)", maxWidth:140, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}
                  title={t.therapeutic_area}>{t.therapeutic_area}</td>
                <td style={{ padding:"5px 8px", color:"var(--dim)" }}>{t.overall_status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SQ2TopSponsors({ data, color }) {
  const [hoveredSeg, setHoveredSeg] = useState(null); // {sponsor, mod, count, x, y}
  const [showZoom, setShowZoom] = useState(false);
  const [hoveredPhase, setHoveredPhase] = useState(null); // {ta, label, count, pct, color, x, y}
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedSponsor, setSelectedSponsor] = useState(null);

  if (!data?.available) return (
    <div style={{ fontFamily:"var(--fm)", fontSize:12, color:"var(--muted)", padding:"20px 0" }}>
      No quarterly sponsor data available.<br />
      <span style={{ color:"var(--dim)", fontSize:11 }}>
        Run the quarterly pipeline with a master DB to generate this view.
      </span>
    </div>
  );

  const { top_sponsors, modality_leaders, ta_leaders, meta, all_sponsors } = data;
  const maxTrials = top_sponsors[0]?.total_trials || 1;

  // Zoomed view: sponsors 13-25 rescaled so small bars are readable
  const zoomCutoff = 12;
  const tailSponsors = top_sponsors.slice(zoomCutoff);
  const tailMax = tailSponsors[0]?.total_trials || 1;

  // Consistent modality ordering across all bars (most common first)
  const allMods = useMemo(() => {
    const counts = {};
    for (const s of top_sponsors) {
      for (const [mod, n] of Object.entries(s.modality_breakdown || {})) {
        counts[mod] = (counts[mod] || 0) + n;
      }
    }
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .map(([mod]) => mod);
  }, [top_sponsors]);

  // Filter modality leaders to those with >=10 trials
  const modLeaderEntries = useMemo(() => {
    return Object.entries(modality_leaders || {})
      .map(([mod, leaders]) => {
        const total = leaders.reduce((s, l) => s + l.count, 0);
        return { mod, leaders, total };
      })
      .filter(e => e.total >= 10)
      .sort((a, b) => b.total - a.total);
  }, [modality_leaders]);

  // Filter TA leaders — exclude Unassigned, sort by total desc
  const taLeaderEntries = useMemo(() => {
    return Object.entries(ta_leaders || {})
      .filter(([ta, info]) => info.total >= 50
        && !ta.toLowerCase().includes("unassigned") && !ta.toLowerCase().includes("non-disease"))
      .sort((a, b) => b[1].total - a[1].total);
  }, [ta_leaders]);

  // Phase color palette for donut charts
  const PHASE_COLORS = {
    PHASE1: "#3B82F6", "PHASE1/PHASE2": "#6366F1",
    PHASE2: "#8B5CF6", "PHASE2/PHASE3": "#A78BFA",
    PHASE3: "#22C55E", PHASE4: "#F59E0B",
    NA: "#475569", EARLY_PHASE1: "#60A5FA",
  };
  // Sponsor Lookup: filtered matches
  const sponsorMatches = useMemo(() => {
    if (!searchQuery || searchQuery.length < 2 || !all_sponsors) return [];
    const q = searchQuery.toLowerCase();
    return all_sponsors
      .filter(s => s.sponsor_name.toLowerCase().includes(q))
      .slice(0, 20);
  }, [searchQuery, all_sponsors]);

  return (
    <div>
      {/* Summary line + export */}
      <div style={{ display:"flex", alignItems:"center", gap:12, marginBottom:14 }}>
        <MonoLabel style={{ marginBottom:0 }}>
          {fmt(meta?.total_industry_drug)} industry drug trials · {fmt(meta?.unique_sponsors)} sponsors · {meta?.master_db_file}
        </MonoLabel>
        <div style={{ flex:1 }} />
        <button onClick={() => exportSQ2CSV(top_sponsors)}
          style={{ fontFamily:"var(--fm)", fontSize:10, padding:"4px 12px",
            background:"transparent", border:"1px solid var(--border2)",
            borderRadius:4, color:"var(--muted)", cursor:"pointer",
            letterSpacing:"0.1em" }}>
          EXPORT CSV
        </button>
      </div>

      {/* ── Section 1: The Big 25 ─────────────────────────────────── */}
      <MonoLabel color={color.mid}>The Big 25</MonoLabel>

      {/* Modality legend */}
      <div style={{ display:"flex", gap:10, flexWrap:"wrap", marginBottom:14 }}>
        {allMods.map(mod => (
          <div key={mod} style={{ display:"flex", alignItems:"center", gap:4 }}>
            <div style={{ width:8, height:8, borderRadius:2,
              background:modColor(mod) }} />
            <span style={{ fontFamily:"var(--fm)", fontSize:9,
              color:"var(--muted)", letterSpacing:"0.06em" }}>
              {humanMod(mod)}
            </span>
          </div>
        ))}
      </div>

      <div style={{ position:"relative", marginBottom:8 }}>
        {top_sponsors.map((row, i) => {
          const barPct = (row.total_trials / maxTrials) * 100;
          return (
            <div key={row.sponsor_name}
              style={{ display:"flex", alignItems:"center", gap:0,
                marginBottom:2, height:24 }}>

              {/* Rank */}
              <div style={{ width:28, fontFamily:"var(--fm)", fontSize:10,
                color:"var(--dim)", textAlign:"right", flexShrink:0,
                paddingRight:8 }}>
                {i + 1}
              </div>

              {/* Sponsor name */}
              <div style={{ width:220, fontFamily:"var(--fm)", fontSize:11,
                color:"var(--text)", overflow:"hidden",
                textOverflow:"ellipsis", whiteSpace:"nowrap", flexShrink:0,
                paddingRight:12 }}
                title={row.sponsor_name}>
                {row.sponsor_name}
              </div>

              {/* Count — left of bar */}
              <div style={{ width:44, fontFamily:"var(--fm)", fontSize:12,
                fontWeight:600, color:color.mid, textAlign:"right",
                flexShrink:0, paddingRight:10 }}>
                {row.total_trials}
              </div>

              {/* Stacked bar */}
              <div style={{ flex:1, display:"flex", height:18,
                borderRadius:3, overflow:"hidden" }}>
                {allMods.map(mod => {
                  const count = (row.modality_breakdown || {})[mod] || 0;
                  if (count === 0) return null;
                  const segPct = (count / maxTrials) * 100;
                  return (
                    <div key={mod}
                      style={{ width:`${segPct}%`, minWidth: count > 0 ? 2 : 0,
                        background:modColor(mod), opacity:0.85,
                        cursor:"pointer", transition:"opacity 0.15s" }}
                      onMouseEnter={e => {
                        e.target.style.opacity = "1";
                        const rect = e.target.getBoundingClientRect();
                        setHoveredSeg({
                          sponsor:row.sponsor_name, mod,
                          count, total:row.total_trials,
                          x:rect.left + rect.width/2, y:rect.top - 4
                        });
                      }}
                      onMouseLeave={e => {
                        e.target.style.opacity = "0.85";
                        setHoveredSeg(null);
                      }}
                    />
                  );
                })}
              </div>
            </div>
          );
        })}

        {/* Tooltip */}
        {hoveredSeg && (
          <div style={{ position:"fixed", zIndex:999,
            left:hoveredSeg.x, top:hoveredSeg.y,
            transform:"translate(-50%, -100%)",
            background:"var(--surf2)", border:"1px solid var(--border2)",
            borderRadius:6, padding:"6px 10px", pointerEvents:"none",
            boxShadow:"0 4px 12px rgba(0,0,0,0.4)" }}>
            <div style={{ fontFamily:"var(--fm)", fontSize:10, color:modColor(hoveredSeg.mod),
              marginBottom:2 }}>
              {humanMod(hoveredSeg.mod)}
            </div>
            <div style={{ fontFamily:"var(--fm)", fontSize:12, color:"var(--text)" }}>
              {hoveredSeg.count} trials
              <span style={{ color:"var(--muted)", fontSize:10, marginLeft:6 }}>
                ({Math.round(100 * hoveredSeg.count / hoveredSeg.total)}%)
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Tail zoom toggle */}
      <div style={{ marginBottom:28 }}>
        <button onClick={() => setShowZoom(z => !z)}
          style={{ fontFamily:"var(--fm)", fontSize:9, padding:"3px 10px",
            background:showZoom ? color.accent+"18" : "transparent",
            border:`1px solid ${showZoom ? color.accent+"40" : "var(--border)"}`,
            borderRadius:4, color:showZoom ? color.mid : "var(--muted)",
            cursor:"pointer", letterSpacing:"0.08em" }}>
          {showZoom ? "HIDE" : "SHOW"} TAIL ZOOM (#{zoomCutoff + 1}–25)
        </button>
        {showZoom && (
          <div style={{ marginTop:12, padding:"12px 16px",
            background:"var(--surf2)", borderRadius:8,
            border:"1px solid var(--border)" }}>
            <MonoLabel color="var(--muted)" style={{ marginBottom:10 }}>
              Rescaled — #{zoomCutoff + 1} ({tailSponsors[0]?.sponsor_name}) = 100%
            </MonoLabel>
            {tailSponsors.map((row, ti) => {
              const idx = zoomCutoff + ti;
              return (
                <div key={row.sponsor_name}
                  style={{ display:"flex", alignItems:"center", gap:0,
                    marginBottom:2, height:24 }}>
                  <div style={{ width:28, fontFamily:"var(--fm)", fontSize:10,
                    color:"var(--dim)", textAlign:"right", flexShrink:0,
                    paddingRight:8 }}>
                    {idx + 1}
                  </div>
                  <div style={{ width:220, fontFamily:"var(--fm)", fontSize:11,
                    color:"var(--text)", overflow:"hidden",
                    textOverflow:"ellipsis", whiteSpace:"nowrap", flexShrink:0,
                    paddingRight:12 }}
                    title={row.sponsor_name}>
                    {row.sponsor_name}
                  </div>
                  <div style={{ width:44, fontFamily:"var(--fm)", fontSize:12,
                    fontWeight:600, color:color.mid, textAlign:"right",
                    flexShrink:0, paddingRight:10 }}>
                    {row.total_trials}
                  </div>
                  <div style={{ flex:1, display:"flex", height:18,
                    borderRadius:3, overflow:"hidden" }}>
                    {allMods.map(mod => {
                      const count = (row.modality_breakdown || {})[mod] || 0;
                      if (count === 0) return null;
                      const segPct = (count / tailMax) * 100;
                      return (
                        <div key={mod}
                          style={{ width:`${segPct}%`, minWidth: count > 0 ? 2 : 0,
                            background:modColor(mod), opacity:0.85 }}
                        />
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Section 2: Modality Champions ─────────────────────────── */}
      <MonoLabel color={color.mid}>Modality Champions</MonoLabel>

      <div style={{ display:"flex", gap:10, overflowX:"auto",
        paddingBottom:8, marginBottom:28 }}>
        {modLeaderEntries.map(({ mod, leaders, total }) => (
          <div key={mod}
            style={{ minWidth:190, flexShrink:0,
              background:"var(--surf2)", borderRadius:8,
              border:"1px solid var(--border)",
              overflow:"hidden" }}>

            {/* Color stripe */}
            <div style={{ height:4, background:modColor(mod) }} />

            <div style={{ padding:"12px 14px" }}>
              {/* Modality name + total */}
              <div style={{ fontFamily:"var(--fm)", fontSize:11, fontWeight:600,
                color:modColor(mod), marginBottom:2 }}>
                {humanMod(mod)}
              </div>
              <div style={{ fontFamily:"var(--fm)", fontSize:9,
                color:"var(--dim)", marginBottom:10, letterSpacing:"0.06em" }}>
                {fmt(total)} industry trials
              </div>

              {/* Podium */}
              {leaders.map((l, li) => (
                <div key={l.sponsor}
                  style={{ display:"flex", alignItems:"center", gap:6,
                    marginBottom:li < leaders.length - 1 ? 6 : 0 }}>
                  <span style={{ fontFamily:"var(--fm)", fontSize:10, fontWeight:600,
                    color: li === 0 ? color.mid : "var(--muted)",
                    width:14, flexShrink:0 }}>
                    {li === 0 ? "\u2660" : `#${li+1}`}
                  </span>
                  <span style={{ fontFamily:"var(--fm)",
                    fontSize: li === 0 ? 11 : 10,
                    color: li === 0 ? "var(--text)" : "var(--muted)",
                    fontWeight: li === 0 ? 600 : 400,
                    overflow:"hidden", textOverflow:"ellipsis",
                    whiteSpace:"nowrap", flex:1 }}
                    title={l.sponsor}>
                    {l.sponsor}
                  </span>
                  <span style={{ fontFamily:"var(--fm)", fontSize:10, flexShrink:0,
                    color: li === 0 ? color.mid : "var(--dim)" }}>
                    {l.count}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* ── Section 3: TA Territory ───────────────────────────────── */}
      <MonoLabel color={color.mid}>TA Territory</MonoLabel>

      {/* Phase donut legend */}
      <div style={{ display:"flex", gap:12, flexWrap:"wrap", marginBottom:14 }}>
        {["PHASE1","PHASE2","PHASE3","PHASE4","NA"].map(p => (
          <div key={p} style={{ display:"flex", alignItems:"center", gap:4 }}>
            <div style={{ width:8, height:8, borderRadius:2,
              background:PHASE_COLORS[p] || "#475569" }} />
            <span style={{ fontFamily:"var(--fm)", fontSize:9,
              color:"var(--muted)", letterSpacing:"0.06em" }}>
              {p === "NA" ? "Other" : p.replace("PHASE","P")}
            </span>
          </div>
        ))}
      </div>

      <div style={{ display:"grid",
        gridTemplateColumns:"repeat(4, minmax(0, 1fr))", gap:10 }}>
        {taLeaderEntries.map(([ta, info]) => {
          const heat = info.share_pct >= 30 ? "var(--red)"
            : info.share_pct >= 20 ? "var(--amber)"
            : info.share_pct >= 12 ? color.mid
            : "var(--muted)";

          // Build donut arcs from phase_dist
          const phaseDist = info.phase_dist || {};
          const phaseTotal = Object.values(phaseDist).reduce((s, n) => s + n, 0) || 1;
          // Bucket phases: P1 (incl early/P1P2), P2 (incl P2P3), P3, P4, Other
          const buckets = [
            { key:"PHASE1", label:"P1", count:
              (phaseDist["PHASE1"]||0)+(phaseDist["EARLY_PHASE1"]||0)+(phaseDist["PHASE1/PHASE2"]||0) },
            { key:"PHASE2", label:"P2", count:
              (phaseDist["PHASE2"]||0)+(phaseDist["PHASE2/PHASE3"]||0) },
            { key:"PHASE3", label:"P3", count: phaseDist["PHASE3"]||0 },
            { key:"PHASE4", label:"P4", count: phaseDist["PHASE4"]||0 },
            { key:"NA", label:"Other", count:
              phaseTotal - ((phaseDist["PHASE1"]||0)+(phaseDist["EARLY_PHASE1"]||0)+
              (phaseDist["PHASE1/PHASE2"]||0)+(phaseDist["PHASE2"]||0)+
              (phaseDist["PHASE2/PHASE3"]||0)+(phaseDist["PHASE3"]||0)+
              (phaseDist["PHASE4"]||0)) },
          ].filter(b => b.count > 0);

          // SVG donut arcs
          const R = 22, r = 14, cx = 26, cy = 26;
          let cumAngle = -90; // start at top
          const arcs = buckets.map(b => {
            const angle = (b.count / phaseTotal) * 360;
            const startAngle = cumAngle;
            cumAngle += angle;
            const endAngle = cumAngle;
            const largeArc = angle > 180 ? 1 : 0;
            const toRad = a => (a * Math.PI) / 180;
            const x1 = cx + R * Math.cos(toRad(startAngle));
            const y1 = cy + R * Math.sin(toRad(startAngle));
            const x2 = cx + R * Math.cos(toRad(endAngle));
            const y2 = cy + R * Math.sin(toRad(endAngle));
            const ix1 = cx + r * Math.cos(toRad(endAngle));
            const iy1 = cy + r * Math.sin(toRad(endAngle));
            const ix2 = cx + r * Math.cos(toRad(startAngle));
            const iy2 = cy + r * Math.sin(toRad(startAngle));
            // Full circle case
            if (buckets.length === 1) {
              return (
                <circle key={b.key} cx={cx} cy={cy} r={(R+r)/2}
                  fill="none" stroke={PHASE_COLORS[b.key]||"#475569"}
                  strokeWidth={R-r} opacity={0.85}
                  style={{ cursor:"pointer" }}
                  onMouseEnter={e => {
                    const rect = e.target.getBoundingClientRect();
                    setHoveredPhase({ ta, label:b.key==="NA"?"Other":b.key.replace("PHASE","P"), count:b.count, pct:Math.round(100*b.count/phaseTotal), color:PHASE_COLORS[b.key]||"#475569", x:rect.left+rect.width/2, y:rect.top-4 });
                  }}
                  onMouseLeave={() => setHoveredPhase(null)} />
              );
            }
            const d = [
              `M ${x1} ${y1}`,
              `A ${R} ${R} 0 ${largeArc} 1 ${x2} ${y2}`,
              `L ${ix1} ${iy1}`,
              `A ${r} ${r} 0 ${largeArc} 0 ${ix2} ${iy2}`,
              `Z`
            ].join(" ");
            return <path key={b.key} d={d}
              fill={PHASE_COLORS[b.key]||"#475569"} opacity={0.85}
              style={{ cursor:"pointer" }}
              onMouseEnter={e => {
                const rect = e.target.getBoundingClientRect();
                setHoveredPhase({ ta, label:b.key==="NA"?"Other":b.key.replace("PHASE","P"), count:b.count, pct:Math.round(100*b.count/phaseTotal), color:PHASE_COLORS[b.key]||"#475569", x:rect.left+rect.width/2, y:rect.top-4 });
              }}
              onMouseLeave={() => setHoveredPhase(null)} />;
          });

          return (
            <div key={ta}
              style={{ background:"var(--surf2)", borderRadius:8,
                border:"1px solid var(--border)", padding:"12px",
                borderLeft:`3px solid ${heat}`,
                display:"flex", gap:10, alignItems:"center" }}>

              {/* Left: text info */}
              <div style={{ flex:1, minWidth:0 }}>
                {/* TA name */}
                <div style={{ fontFamily:"var(--fm)", fontSize:9,
                  color:"var(--muted)", letterSpacing:"0.08em",
                  marginBottom:5, overflow:"hidden",
                  textOverflow:"ellipsis", whiteSpace:"nowrap" }}
                  title={ta}>
                  {ta.toUpperCase()}
                </div>

                {/* Dominant sponsor */}
                <div style={{ fontFamily:"var(--fm)", fontSize:10,
                  color:"var(--text)", fontWeight:500,
                  overflow:"hidden", textOverflow:"ellipsis",
                  whiteSpace:"nowrap", marginBottom:4 }}
                  title={info.sponsor}>
                  {info.sponsor}
                </div>

                {/* Count + share */}
                <div style={{ display:"flex", alignItems:"baseline", gap:4 }}>
                  <span style={{ fontFamily:"var(--fm)", fontSize:13,
                    fontWeight:600, color:heat }}>
                    {info.count}
                  </span>
                  <span style={{ fontFamily:"var(--fm)", fontSize:8,
                    color:"var(--dim)" }}>
                    / {fmt(info.total)} ({info.share_pct}%)
                  </span>
                </div>
              </div>

              {/* Right: phase donut */}
              <div style={{ flexShrink:0, position:"relative",
                width:52, height:52 }}>
                <svg width={52} height={52} viewBox="0 0 52 52">
                  {arcs}
                </svg>
                {/* Center label: total */}
                <div style={{ position:"absolute", top:0, left:0,
                  width:52, height:52, display:"flex",
                  alignItems:"center", justifyContent:"center",
                  pointerEvents:"none" }}>
                  <span style={{ fontFamily:"var(--fm)", fontSize:9,
                    fontWeight:600, color:"var(--text)" }}>
                    {info.count}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Phase donut tooltip */}
      {hoveredPhase && (
        <div style={{ position:"fixed", zIndex:999,
          left:hoveredPhase.x, top:hoveredPhase.y,
          transform:"translate(-50%, -100%)",
          background:"var(--surf2)", border:"1px solid var(--border2)",
          borderRadius:6, padding:"6px 10px", pointerEvents:"none",
          boxShadow:"0 4px 12px rgba(0,0,0,0.4)" }}>
          <div style={{ fontFamily:"var(--fm)", fontSize:10, color:hoveredPhase.color,
            marginBottom:2 }}>
            {hoveredPhase.label}
          </div>
          <div style={{ fontFamily:"var(--fm)", fontSize:12, color:"var(--text)" }}>
            {hoveredPhase.count} trials
            <span style={{ color:"var(--muted)", fontSize:10, marginLeft:6 }}>
              ({hoveredPhase.pct}%)
            </span>
          </div>
        </div>
      )}


      {/* ── Section 4: Sponsor Lookup ─────────────────────────────────────── */}
      <div style={{ marginTop:28, marginBottom:20 }}>
        <MonoLabel color={color.mid}>Sponsor Lookup</MonoLabel>
        <div style={{ display:"flex", gap:10, alignItems:"flex-start", marginBottom:8 }}>
          <div style={{ position:"relative", flex:"0 0 320px" }}>
            <input
              type="text"
              value={searchQuery}
              onChange={e => { setSearchQuery(e.target.value); setSelectedSponsor(null); }}
              placeholder="Search sponsor name…"
              style={{ width:"100%", fontFamily:"var(--fm)", fontSize:11,
                padding:"7px 12px", background:"var(--surf3)",
                border:"1px solid var(--border2)", borderRadius:6,
                color:"var(--text)", outline:"none", boxSizing:"border-box" }}
            />
            {sponsorMatches.length > 0 && !selectedSponsor && (
              <div style={{ position:"absolute", top:"100%", left:0, right:0,
                zIndex:50, background:"var(--surf2)", border:"1px solid var(--border2)",
                borderRadius:6, marginTop:2, maxHeight:220, overflowY:"auto",
                boxShadow:"0 4px 16px rgba(0,0,0,0.4)" }}>
                {sponsorMatches.map(s => (
                  <div key={s.sponsor_name}
                    onClick={() => { setSelectedSponsor(s); setSearchQuery(s.sponsor_name); }}
                    style={{ padding:"7px 12px", fontFamily:"var(--fm)", fontSize:11,
                      color:"var(--text)", cursor:"pointer",
                      borderBottom:"1px solid var(--border)",
                      display:"flex", justifyContent:"space-between",
                      alignItems:"center" }}
                    onMouseEnter={e => e.currentTarget.style.background="var(--surf3)"}
                    onMouseLeave={e => e.currentTarget.style.background="transparent"}>
                    <span style={{ overflow:"hidden", textOverflow:"ellipsis",
                      whiteSpace:"nowrap" }}>{s.sponsor_name}</span>
                    <span style={{ fontFamily:"var(--fm)", fontSize:9,
                      color:"var(--dim)", flexShrink:0, marginLeft:8 }}>
                      {s.total_trials} trials
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
          {selectedSponsor && (
            <button onClick={() => { setSelectedSponsor(null); setSearchQuery(""); }}
              style={{ fontFamily:"var(--fm)", fontSize:9, padding:"6px 12px",
                background:"transparent", border:"1px solid var(--border2)",
                borderRadius:4, color:"var(--muted)", cursor:"pointer",
                letterSpacing:"0.08em" }}>
              CLEAR
            </button>
          )}
        </div>
        {selectedSponsor && (
          <SponsorProfile sponsor={selectedSponsor} color={color}
            PHASE_COLORS={PHASE_COLORS} />
        )}
      </div>

      {/* Footer */}
      <div style={{ fontFamily:"var(--fm)", fontSize:9, color:"var(--dim)",
        marginTop:16, letterSpacing:"0.06em" }}>
        Source: {meta?.master_db_file} · {fmt(meta?.total_industry_drug)} industry drug trials · {fmt(meta?.unique_sponsors)} unique sponsors
      </div>
    </div>
  );
}
