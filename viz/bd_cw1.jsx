// -----------------------------------------------------------------------
// viz/bd_cw1.jsx
// BD / cw1 (ChiCTR) -- Chinese Sponsor Action Table
//
// Data source : ALEXIS_DATA.cw1  (list of sponsor rows from
//               analytics/bd_cw1.py::cw1_china_sponsor_action_table)
// Globals used from host: PRIORITY_CFG, modColor, humanMod, fmt
// -----------------------------------------------------------------------

function CW1ChinaSponsorTable({ data, color }) {
  if (!data || data.length === 0) {
    return (
      <div style={{ padding:"28px 16px", fontFamily:"var(--fm)",
        fontSize:12, color:"var(--muted)", textAlign:"center" }}>
        No new Chinese drug trials in this window.
        <div style={{ marginTop:6, fontSize:11, color:"var(--dim)" }}>
          Run pipelines/run_diff_chictr.py to generate the enriched file.
        </div>
      </div>
    );
  }

  const [expanded, setExpanded]   = useState({});
  const [sortCol,  setSortCol]    = useState("priority_score");
  const [sortDir,  setSortDir]    = useState("desc");

  const sorted = [...data].sort((a, b) => {
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
        background:"var(--surf2)", padding:"9px 10px", textAlign: align || "left",
        cursor:"pointer", fontFamily:"var(--fm)", fontSize:10,
        letterSpacing:"0.12em", textTransform:"uppercase",
        color: active ? color.mid : "var(--muted)",
        borderBottom: `2px solid ${active ? color.accent : "var(--border)"}`,
        whiteSpace:"nowrap", userSelect:"none" }}
        onClick={() => {
          if (active) setSortDir(sortDir === "desc" ? "asc" : "desc");
          else { setSortCol(id); setSortDir("desc"); }
        }}>
        {children}{active ? (sortDir === "desc" ? " ↓" : " ↑") : ""}
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
        <span style={{ fontFamily:"var(--fm)", fontSize:10, color:"var(--muted)" }}>
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

  function exportCSV() {
    const headers = ["sponsor_name","sponsor_class","new_trial_count",
                     "top_phase","modalities","priority_score","priority_label"];
    const lines = [headers.join(",")].concat(
      sorted.map(r => [
        `"${r.sponsor_name}"`, r.sponsor_class, r.new_trial_count,
        r.top_phase || "", `"${(r.modalities||[]).join("; ")}"`,
        r.priority_score, r.priority_label,
      ].join(","))
    );
    const blob = new Blob([lines.join("\n")], { type:"text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "bd_cw1_china_sponsor_action_table.csv";
    a.click();
  }

  return (
    <div>
      {/* Legend + export */}
      <div style={{ display:"flex", alignItems:"center", gap:12,
        padding:"4px 12px 10px", fontFamily:"var(--fm)", fontSize:10,
        color:"var(--muted)", letterSpacing:"0.08em" }}>
        <span>PRIORITY</span>
        {["HIGH","MED","LOW"].map(lab => {
          const p = PRIORITY_CFG?.[lab] || {};
          return (
            <span key={lab} style={{ display:"inline-flex", gap:5, alignItems:"center" }}>
              <span style={{ width:8, height:8, borderRadius:2,
                background:p.color, display:"inline-block" }}/>
              {lab}
            </span>
          );
        })}
        <span style={{ flex:1 }}/>
        <button onClick={exportCSV}
          style={{ background:"transparent", color:"var(--muted)",
            border:"1px solid var(--border2)", borderRadius:4,
            padding:"4px 12px", fontFamily:"var(--fm)", fontSize:10,
            letterSpacing:"0.10em", cursor:"pointer" }}>
          EXPORT CSV
        </button>
      </div>

      <div style={{ maxHeight:840, overflowY:"auto",
        borderTop:"1px solid var(--border)" }}>
        <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
          <thead>
            <tr>
              <th style={{ position:"sticky", top:0, zIndex:1,
                background:"var(--surf2)", width:22 }}></th>
              <TH id="sponsor_name">Sponsor</TH>
              <TH id="sponsor_class">Class</TH>
              <TH id="new_trial_count" align="center">New</TH>
              <TH id="top_phase">Top phase</TH>
              <th style={{ position:"sticky", top:0, zIndex:1,
                background:"var(--surf2)", padding:"9px 10px",
                fontFamily:"var(--fm)", fontSize:10, letterSpacing:"0.12em",
                textTransform:"uppercase", color:"var(--muted)",
                borderBottom:"2px solid var(--border)", textAlign:"left" }}>
                Modalities
              </th>
              <TH id="priority_score">Priority</TH>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r, idx) => {
              const isOpen = !!expanded[r.sponsor_name];
              const mods   = r.modalities || [];
              return (
                <React.Fragment key={r.sponsor_name}>
                  <tr onClick={() => setExpanded(e => ({...e, [r.sponsor_name]: !e[r.sponsor_name]}))}
                    style={{ cursor:"pointer",
                      background: isOpen ? "var(--surf3)"
                                : (idx % 2 === 0 ? "var(--surf)" : "transparent"),
                      borderTop:"1px solid var(--border)" }}>
                    <td style={{ padding:"9px 8px", color:color.mid,
                      textAlign:"center", fontSize:12 }}>
                      <span style={{ display:"inline-block",
                        transition:"transform 0.15s",
                        transform: isOpen ? "rotate(180deg)" : "none" }}>▾</span>
                    </td>
                    <td style={{ padding:"9px 10px",
                      color: isOpen ? color.mid : "var(--text)",
                      fontWeight: isOpen ? 600 : 400 }}>
                      {r.sponsor_name}
                    </td>
                    <td style={{ padding:"9px 10px" }}>
                      <SponsorClassChip cls={r.sponsor_class}/>
                    </td>
                    <td style={{ padding:"9px 10px", textAlign:"center",
                      fontFamily:"var(--fm)", color:"var(--text)" }}>
                      {r.new_trial_count}
                    </td>
                    <td style={{ padding:"9px 10px", color:"var(--muted)",
                      fontFamily:"var(--fm)", fontSize:11 }}>
                      {r.top_phase || "-"}
                    </td>
                    <td style={{ padding:"9px 10px" }}>
                      <span style={{ display:"inline-flex", gap:4, flexWrap:"wrap" }}>
                        {mods.slice(0, 3).map(m => <ModPill key={m} m={m}/>)}
                        {mods.length > 3 && (
                          <span style={{ fontFamily:"var(--fm)", fontSize:10,
                            color:"var(--muted)", padding:"2px 4px" }}>
                            +{mods.length - 3}
                          </span>
                        )}
                      </span>
                    </td>
                    <td style={{ padding:"9px 10px" }}>
                      <PriorityBadge label={r.priority_label} score={r.priority_score}/>
                    </td>
                  </tr>

                  {isOpen && (
                    <tr style={{ background:"var(--surf3)" }}>
                      <td colSpan={7} style={{ padding:"10px 16px 14px 42px" }}>
                        <div style={{ maxHeight:320, overflowY:"auto",
                          border:"1px solid var(--border)", borderRadius:6 }}>
                          <table style={{ width:"100%", minWidth:900,
                            borderCollapse:"collapse", fontSize:11 }}>
                            <thead>
                              <tr style={{ background:"var(--surf2)" }}>
                                {["NCT","Title","TA","Modality","Phase","Date"].map(h => (
                                  <th key={h} style={{ padding:"6px 10px",
                                    textAlign:"left", fontFamily:"var(--fm)",
                                    fontSize:9, letterSpacing:"0.12em",
                                    textTransform:"uppercase",
                                    color:"var(--muted)",
                                    borderBottom:"1px solid var(--border)" }}>
                                    {h}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {(r.trials || []).map(t => (
                                <tr key={t.nct_id}
                                  style={{ borderBottom:"1px solid var(--border)" }}>
                                  <td style={{ padding:"5px 10px",
                                    fontFamily:"var(--fm)" }}>
                                    {t.source_url
                                      ? <a href={t.source_url} target="_blank"
                                          rel="noreferrer"
                                          style={{ color:"var(--cyan)",
                                            textDecoration:"none" }}>
                                          {t.nct_id}
                                        </a>
                                      : t.nct_id}
                                  </td>
                                  <td style={{ padding:"5px 10px", maxWidth:420,
                                    whiteSpace:"nowrap", overflow:"hidden",
                                    textOverflow:"ellipsis", color:"var(--text)" }}
                                    title={t.title}>
                                    {t.title}
                                  </td>
                                  <td style={{ padding:"5px 10px",
                                    color:"var(--muted)" }}>
                                    {t.therapeutic_area || "-"}
                                  </td>
                                  <td style={{ padding:"5px 10px" }}>
                                    {t.modality ? <ModPill m={t.modality}/> : "-"}
                                  </td>
                                  <td style={{ padding:"5px 10px",
                                    fontFamily:"var(--fm)", fontSize:10,
                                    color:"var(--muted)" }}>
                                    {t.phase || "-"}
                                  </td>
                                  <td style={{ padding:"5px 10px",
                                    fontFamily:"var(--fm)", fontSize:10,
                                    color:"var(--muted)", whiteSpace:"nowrap" }}>
                                    {t.first_posted_date || "-"}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
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
    </div>
  );
}
