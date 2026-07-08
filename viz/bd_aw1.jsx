// -----------------------------------------------------------------------
// viz/bd_aw1.jsx
// BD / aw1 (ANZCTR) -- Foreign Sponsor FIH Trial Table
//
// Data source : ALEXIS_DATA.aw1  (list of trial rows from
//               analytics/bd_aw1.py::aw1_foreign_sponsor_fih_table)
// Globals used from host: PRIORITY_CFG, modColor, humanMod, fmt
// -----------------------------------------------------------------------

function AW1ForeignSponsorFIH({ data, color }) {
  if (!data || data.available === false) {
    return (
      <div style={{ padding:"28px 24px", fontFamily:"var(--fm)",
        fontSize:12, color:"var(--muted)", textAlign:"left",
        maxWidth:640, margin:"0 auto", lineHeight:1.5 }}>
        <div style={{ color:"#F59E0B", fontWeight:600, fontSize:11,
          letterSpacing:"0.14em", marginBottom:8 }}>
          BASELINE UNAVAILABLE
        </div>
        {data?.reason || "No ANZCTR FIH data available."}
      </div>
    );
  }

  const rows = data.rows || [];
  const newCount = rows.filter(r => r.is_new).length;

  const [expanded, setExpanded]   = useState({});
  const [sortCol,  setSortCol]    = useState("priority_score");
  const [sortDir,  setSortDir]    = useState("desc");
  const [newOnly,  setNewOnly]    = useState(false);

  const visible = newOnly ? rows.filter(r => r.is_new) : rows;

  const sorted = [...visible].sort((a, b) => {
    const av = a[sortCol]; const bv = b[sortCol];
    let cmp = 0;
    if (typeof av === "number" && typeof bv === "number") cmp = av - bv;
    else cmp = String(av || "").localeCompare(String(bv || ""));
    return sortDir === "desc" ? -cmp : cmp;
  });

  const TH = ({ id, children, align }) => {
    const active = sortCol === id;
    return (
      <th style={{ position:"sticky", top:0, zIndex:1,
        background:"var(--surf2)", padding:"9px 10px",
        textAlign: align || "left", cursor:"pointer",
        fontFamily:"var(--fm)", fontSize:10,
        letterSpacing:"0.12em", textTransform:"uppercase",
        color: active ? color.mid : "var(--muted)",
        borderBottom: `2px solid ${active ? color.accent : "var(--border)"}`,
        whiteSpace:"nowrap", userSelect:"none" }}
        onClick={() => {
          if (active) setSortDir(sortDir === "desc" ? "asc" : "desc");
          else { setSortCol(id); setSortDir("desc"); }
        }}>
        {children}{active ? (sortDir === "desc" ? " \u2193" : " \u2191") : ""}
      </th>
    );
  };

  const ModPill = ({ m }) => (
    <span style={{ fontFamily:"var(--fm)", fontSize:10, padding:"2px 6px",
      borderRadius:8, background:modColor(m)+"20", color:modColor(m),
      border:`1px solid ${modColor(m)}30`, whiteSpace:"nowrap" }}>
      {humanMod(m)}
    </span>
  );

  const PriorityBadge = ({ label, score }) => {
    const pri = PRIORITY_CFG?.[label] || PRIORITY_CFG?.LOW
             || { color:"#4A5E78", bg:"rgba(74,94,120,0.08)", border:"#4A5E7830" };
    return (
      <span style={{ display:"inline-flex", alignItems:"center", gap:6 }}>
        <span style={{ fontFamily:"var(--fm)", fontSize:10, fontWeight:600,
          padding:"3px 10px", borderRadius:10, color:pri.color,
          background:pri.bg, border:`1px solid ${pri.border}`,
          letterSpacing:"0.08em" }}>
          {label}
        </span>
        <span style={{ fontFamily:"var(--fm)", fontSize:10,
          color:"var(--muted)" }}>
          {score}
        </span>
      </span>
    );
  };

  const SponsorClassChip = ({ cls }) => {
    const up = (cls || "UNKNOWN").toUpperCase();
    const hue = up === "INDUSTRY" ? "#F59E0B"
              : up === "NIH"      ? "#22C55E"
              : up === "OTHER"    ? "#A78BFA"
              : "#4A5E78";
    return (
      <span style={{ fontFamily:"var(--fm)", fontSize:9,
        letterSpacing:"0.10em", padding:"2px 6px", borderRadius:6,
        color:hue, background:hue+"18", border:`1px solid ${hue}30` }}>
        {up}
      </span>
    );
  };

  const StatusChip = ({ status }) => {
    const s = (status || "").toUpperCase();
    const col = s.includes("RECRUIT") ? "#22C55E"
              : s.includes("NOT_YET") || s.includes("NOT YET") ? "#F59E0B"
              : s.includes("ACTIVE")  ? "#00CFFF"
              : "#4A5E78";
    return (
      <span style={{ fontFamily:"var(--fm)", fontSize:10,
        padding:"2px 7px", borderRadius:6,
        color:col, background:col+"18",
        border:`1px solid ${col}30`,
        whiteSpace:"nowrap" }}>
        {status || "-"}
      </span>
    );
  };

  function exportCSV() {
    const headers = ["actrn","title","phase","overall_status","modality",
                     "therapeutic_area","sponsor_name","sponsor_class",
                     "primary_sponsor_country","start_date","first_posted_date",
                     "priority_score","priority_label","is_new"];
    const lines = [headers.join(",")].concat(
      sorted.map(r => [
        `"${r.nct_id || ""}"`,
        `"${(r.title || "").replace(/"/g, "'")}"`,
        r.phase || "",
        r.overall_status || "",
        r.modality || "",
        `"${r.therapeutic_area || ""}"`,
        `"${r.sponsor_name || ""}"`,
        r.sponsor_class || "",
        r.primary_sponsor_country || "",
        r.start_date || "",
        r.first_posted_date || "",
        r.priority_score,
        r.priority_label || "",
        r.is_new ? "true" : "false",
      ].join(","))
    );
    const blob = new Blob([lines.join("\n")], { type:"text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "bd_aw1_foreign_sponsor_fih.csv";
    a.click();
  }

  return (
    <div>
      {/* Summary bar */}
      <div style={{ display:"flex", alignItems:"center", gap:20,
        padding:"6px 12px 10px", fontFamily:"var(--fm)", fontSize:11,
        color:"var(--muted)", flexWrap:"wrap" }}>
        <span>
          <span style={{ color:color.mid, fontWeight:700, fontSize:16,
            fontFamily:"var(--fh)" }}>
            {data.total_fih ?? 0}
          </span>
          &nbsp;FIH-stage foreign drug
        </span>
        <span style={{ color:"var(--dim)" }}>|</span>
        <span>
          <span style={{ color:"var(--text)", fontWeight:600 }}>
            {data.total_foreign_drug ?? 0}
          </span>
          &nbsp;total foreign drug
        </span>
        <span style={{ color:"var(--dim)" }}>|</span>
        <span>
          <span style={{ color:"var(--text)", fontWeight:600 }}>
            {data.total_drug ?? 0}
          </span>
          &nbsp;all drug trials
        </span>
        <span style={{ flex:1 }}/>
        {newCount > 0 && (
          <button onClick={() => setNewOnly(n => !n)}
            style={{ background: newOnly ? color.accent+"22" : "transparent",
              color: newOnly ? color.mid : "var(--muted)",
              border:`1px solid ${newOnly ? color.accent : "var(--border2)"}`,
              borderRadius:4, padding:"4px 12px",
              fontFamily:"var(--fm)", fontSize:10,
              letterSpacing:"0.10em", cursor:"pointer" }}>
            NEW ONLY ({newCount})
          </button>
        )}
        <button onClick={exportCSV}
          style={{ background:"transparent", color:"var(--muted)",
            border:"1px solid var(--border2)", borderRadius:4,
            padding:"4px 12px", fontFamily:"var(--fm)", fontSize:10,
            letterSpacing:"0.10em", cursor:"pointer" }}>
          EXPORT CSV
        </button>
      </div>

      {sorted.length === 0 ? (
        <div style={{ padding:"28px 16px", fontFamily:"var(--fm)",
          fontSize:12, color:"var(--muted)", textAlign:"center" }}>
          No matching trials.
        </div>
      ) : (
        <div style={{ maxHeight:840, overflowY:"auto",
          borderTop:"1px solid var(--border)" }}>
          <table style={{ width:"100%", borderCollapse:"collapse",
            fontSize:12 }}>
            <thead>
              <tr>
                <th style={{ position:"sticky", top:0, zIndex:1,
                  background:"var(--surf2)", width:22 }}/>
                <TH id="nct_id">ACTRN</TH>
                <TH id="sponsor_name">Sponsor</TH>
                <TH id="primary_sponsor_country">Country</TH>
                <TH id="phase">Phase</TH>
                <TH id="overall_status">Status</TH>
                <TH id="therapeutic_area">TA</TH>
                <TH id="modality">Modality</TH>
                <TH id="priority_score">Priority</TH>
              </tr>
            </thead>
            <tbody>
              {sorted.map((r, idx) => {
                const key = r.nct_id || String(idx);
                const isOpen = !!expanded[key];
                return (
                  <React.Fragment key={key}>
                    <tr onClick={() => setExpanded(e => ({...e, [key]: !e[key]}))}
                      style={{ cursor:"pointer",
                        background: isOpen ? "var(--surf3)"
                                  : (idx % 2 === 0 ? "var(--surf)" : "transparent"),
                        borderTop:"1px solid var(--border)" }}>
                      <td style={{ padding:"9px 8px", color:color.mid,
                        textAlign:"center", fontSize:12 }}>
                        <span style={{ display:"inline-block",
                          transition:"transform 0.15s",
                          transform: isOpen ? "rotate(180deg)" : "none" }}>&#9662;</span>
                      </td>
                      <td style={{ padding:"9px 10px", whiteSpace:"nowrap" }}>
                        {r.source_url
                          ? <a href={r.source_url} target="_blank" rel="noreferrer"
                              style={{ color:"var(--cyan)", textDecoration:"none",
                                fontFamily:"var(--fm)", fontSize:11 }}
                              onClick={e => e.stopPropagation()}>
                              {r.nct_id}
                            </a>
                          : <span style={{ fontFamily:"var(--fm)", fontSize:11 }}>
                              {r.nct_id}
                            </span>}
                        {r.is_new && (
                          <span style={{ marginLeft:6, fontFamily:"var(--fm)",
                            fontSize:8, letterSpacing:"0.10em",
                            padding:"1px 5px", borderRadius:4,
                            color:"#22C55E", background:"#22C55E18",
                            border:"1px solid #22C55E30",
                            verticalAlign:"middle" }}>
                            NEW
                          </span>
                        )}
                      </td>
                      <td style={{ padding:"9px 10px" }}>
                        <div style={{ color: isOpen ? color.mid : "var(--text)",
                          fontWeight: isOpen ? 600 : 400,
                          maxWidth:200, whiteSpace:"nowrap",
                          overflow:"hidden", textOverflow:"ellipsis" }}
                          title={r.sponsor_name}>
                          {r.sponsor_name || "-"}
                        </div>
                        {r.sponsor_class && (
                          <div style={{ marginTop:3 }}>
                            <SponsorClassChip cls={r.sponsor_class}/>
                          </div>
                        )}
                      </td>
                      <td style={{ padding:"9px 10px" }}>
                        {r.primary_sponsor_country ? (
                          <span style={{ fontFamily:"var(--fm)", fontSize:10,
                            padding:"2px 7px", borderRadius:6,
                            color:color.mid, background:color.mid+"18",
                            border:`1px solid ${color.mid}30`,
                            whiteSpace:"nowrap" }}>
                            {r.primary_sponsor_country}
                          </span>
                        ) : <span style={{ color:"var(--muted)" }}>-</span>}
                      </td>
                      <td style={{ padding:"9px 10px", fontFamily:"var(--fm)",
                        fontSize:11, color:"var(--muted)",
                        whiteSpace:"nowrap" }}>
                        {r.phase || "-"}
                      </td>
                      <td style={{ padding:"9px 10px" }}>
                        <StatusChip status={r.recruitment_status || r.overall_status}/>
                      </td>
                      <td style={{ padding:"9px 10px", color:"var(--muted)",
                        fontFamily:"var(--fm)", fontSize:11,
                        maxWidth:160, whiteSpace:"nowrap",
                        overflow:"hidden", textOverflow:"ellipsis" }}
                        title={r.therapeutic_area}>
                        {r.therapeutic_area || "-"}
                      </td>
                      <td style={{ padding:"9px 10px" }}>
                        {r.modality
                          ? <ModPill m={r.modality}/>
                          : <span style={{ color:"var(--muted)" }}>-</span>}
                      </td>
                      <td style={{ padding:"9px 10px" }}>
                        <PriorityBadge label={r.priority_label}
                          score={r.priority_score}/>
                      </td>
                    </tr>

                    {isOpen && (
                      <tr style={{ background:"var(--surf3)" }}>
                        <td colSpan={9} style={{ padding:"12px 16px 16px 42px" }}>
                          <div style={{ display:"grid",
                            gridTemplateColumns:"1fr 1fr", gap:16 }}>
                            <div>
                              <div style={{ fontFamily:"var(--fm)", fontSize:9,
                                letterSpacing:"0.12em", color:"var(--muted)",
                                textTransform:"uppercase", marginBottom:4 }}>
                                Title
                              </div>
                              <div style={{ fontSize:12, color:"var(--text)",
                                lineHeight:1.4 }}>
                                {r.title || "-"}
                              </div>
                              <div style={{ marginTop:10, fontFamily:"var(--fm)",
                                fontSize:9, letterSpacing:"0.12em",
                                color:"var(--muted)", textTransform:"uppercase",
                                marginBottom:4 }}>
                                Conditions
                              </div>
                              <div style={{ fontSize:12, color:"var(--text)",
                                lineHeight:1.4 }}>
                                {r.conditions || "-"}
                              </div>
                              <div style={{ marginTop:10, fontFamily:"var(--fm)",
                                fontSize:9, letterSpacing:"0.12em",
                                color:"var(--muted)", textTransform:"uppercase",
                                marginBottom:4 }}>
                                Interventions
                              </div>
                              <div style={{ fontSize:12, color:"var(--text)",
                                lineHeight:1.4 }}>
                                {r.interventions_text
                                  ? r.interventions_text.slice(0, 300) +
                                    (r.interventions_text.length > 300 ? "..." : "")
                                  : "-"}
                              </div>
                            </div>
                            <div>
                              <div style={{ fontFamily:"var(--fm)", fontSize:9,
                                letterSpacing:"0.12em", color:"var(--muted)",
                                textTransform:"uppercase", marginBottom:4 }}>
                                Dates
                              </div>
                              <div style={{ display:"flex",
                                flexDirection:"column", gap:6 }}>
                                <div style={{ fontSize:12, color:"var(--muted)" }}>
                                  <span style={{ color:"var(--dim)",
                                    fontSize:10 }}>First posted: </span>
                                  {r.first_posted_date || "-"}
                                </div>
                                <div style={{ fontSize:12, color:"var(--muted)" }}>
                                  <span style={{ color:"var(--dim)",
                                    fontSize:10 }}>Start date: </span>
                                  {r.start_date || "-"}
                                </div>
                              </div>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div style={{ padding:"8px 12px", fontFamily:"var(--fm)", fontSize:9,
        color:"var(--dim)", letterSpacing:"0.06em" }}>
        Showing foreign-sponsored drug trials registered on ANZCTR.
        FIH = Phase 1 or Early Phase 1 with no prior AU registration found.
        {data.fih_phases && data.fih_phases.length > 0 && (
          <React.Fragment> FIH phases: {data.fih_phases.join(", ")}.</React.Fragment>
        )}
      </div>
    </div>
  );
}
