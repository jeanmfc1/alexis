// ─────────────────────────────────────────────────────────────────────────
// viz/bd_wq1.jsx
// BD / wq1 — Sponsor Action Table with Priority Score
//
// Data source : ALEXIS_DATA.wq1  (list of sponsor row dicts)
// Injected by : analytics/bd_wq1.py → wq1_sponsor_action_table()
// ─────────────────────────────────────────────────────────────────────────

function exportCSV(rows) {
  const headers = ["sponsor_name","new_trial_count","modalities","top_phase","priority_score","priority_label"];
  const lines = [
    headers.join(","),
    ...rows.map(r => [
      `"${r.sponsor_name}"`,
      r.new_trial_count,
      `"${(r.modalities||[]).join("; ")}"`,
      r.top_phase || "",
      r.priority_score,
      r.priority_label,
    ].join(","))
  ];
  const blob = new Blob([lines.join("\n")], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "bd_wq1_sponsor_action_table.csv";
  a.click();
}

function WQ1ActionTable({ data, color }) {
  const [expanded, setExpanded] = useState({});
  const [sortCol, setSortCol]   = useState("priority_score");
  const [sortDir, setSortDir]   = useState(-1);  // -1 desc, +1 asc

  const rows = useMemo(() => {
    if (!data?.length) return [];
    return [...data].sort((a, b) => {
      const av = a[sortCol] ?? 0;
      const bv = b[sortCol] ?? 0;
      if (typeof av === "string") return sortDir * av.localeCompare(bv);
      return sortDir * (av - bv);
    });
  }, [data, sortCol, sortDir]);

  if (!data?.length) return (
    <div style={{ fontFamily:"var(--fm)", fontSize:12, color:"var(--muted)", padding:"20px 0" }}>
      No INDUSTRY drug trial new registrations found in this window.<br />
      <span style={{ color:"var(--dim)", fontSize:11 }}>
        Verify that the enriched file was loaded and matches this snapshot window.
      </span>
    </div>
  );

  const toggleSort = col => {
    if (sortCol === col) setSortDir(d => d * -1);
    else { setSortCol(col); setSortDir(-1); }
  };

  const TH = ({ col, label, align = "left", width }) => {
    const active = sortCol === col;
    return (
      <th onClick={() => toggleSort(col)}
        style={{ padding:"8px 12px", textAlign:align,
          fontFamily:"var(--fm)", fontSize:10, letterSpacing:"0.12em",
          color: active ? color.mid : "var(--muted)",
          cursor:"pointer", whiteSpace:"nowrap", userSelect:"none",
          width: width || "auto",
          borderBottom:`2px solid ${active ? color.accent : "var(--border)"}` }}>
        {label}{active ? (sortDir === -1 ? " ↓" : " ↑") : ""}
      </th>
    );
  };

  const totalNew = rows.reduce((s, r) => s + r.new_trial_count, 0);

  return (
    <div>
      {/* Summary line + export */}
      <div style={{ display:"flex", alignItems:"center", gap:12, marginBottom:14 }}>
        <MonoLabel style={{ marginBottom:0 }}>
          {rows.length} sponsors · {totalNew} new trials this window
        </MonoLabel>
        <div style={{ flex:1 }} />
        <button onClick={() => exportCSV(rows)}
          style={{ fontFamily:"var(--fm)", fontSize:10, padding:"4px 12px",
            background:"transparent", border:"1px solid var(--border2)",
            borderRadius:4, color:"var(--muted)", cursor:"pointer",
            letterSpacing:"0.1em" }}>
          EXPORT CSV
        </button>
      </div>

      {/* Priority legend */}
      <div style={{ display:"flex", gap:14, marginBottom:14, alignItems:"center" }}>
        {Object.entries(PRIORITY_CFG).map(([lbl, cfg]) => (
          <div key={lbl} style={{ display:"flex", alignItems:"center", gap:5 }}>
            <div style={{ width:8, height:8, borderRadius:2,
              background:cfg.color, opacity:0.8 }} />
            <span style={{ fontFamily:"var(--fm)", fontSize:10,
              color:cfg.color, letterSpacing:"0.08em" }}>
              {lbl}
            </span>
          </div>
        ))}
        <span style={{ fontFamily:"var(--fm)", fontSize:10, color:"var(--dim)" }}>
          score = Σ modality_weight × phase_weight per trial
        </span>
      </div>

      {/* Table */}
      <div style={{ overflowX:"auto", maxHeight:840, overflowY:"auto" }}>
        <table style={{ width:"100%", borderCollapse:"collapse" }}>
          <thead style={{ position:"sticky", top:0, zIndex:1 }}>
            <tr style={{ background:"var(--surf2)" }}>
              <TH col="sponsor_name"    label="SPONSOR" />
              <TH col="new_trial_count" label="NEW"    align="right" width={56} />
              <th style={{ padding:"8px 12px", fontFamily:"var(--fm)", fontSize:10,
                letterSpacing:"0.12em", color:"var(--muted)", textAlign:"left",
                borderBottom:"2px solid var(--border)" }}>
                MODALITY MIX
              </th>
              <TH col="top_phase"      label="TOP PHASE" width={100} />
              <TH col="priority_score" label="SCORE"   align="right" width={72} />
              <th style={{ padding:"8px 12px", fontFamily:"var(--fm)", fontSize:10,
                letterSpacing:"0.12em", color:"var(--muted)",
                borderBottom:"2px solid var(--border)", width:90 }}>
                PRIORITY
              </th>
              <th style={{ width:28, borderBottom:"2px solid var(--border)" }} />
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const isOpen = !!expanded[row.sponsor_name];
              const pri    = PRIORITY_CFG[row.priority_label] || PRIORITY_CFG.LOW;
              return (
                <React.Fragment key={row.sponsor_name}>

                  {/* Main row */}
                  <tr onClick={() => setExpanded(e => ({
                        ...e, [row.sponsor_name]: !isOpen }))}
                    style={{ cursor:"pointer",
                      background: isOpen ? "var(--surf3)"
                        : i % 2 === 0 ? "var(--surf)" : "transparent",
                      borderTop:"1px solid var(--border)" }}>

                    <td style={{ padding:"10px 12px", fontFamily:"var(--fm)",
                      fontSize:12, color:"var(--text)",
                      maxWidth:260, overflow:"hidden",
                      textOverflow:"ellipsis", whiteSpace:"nowrap" }}>
                      {row.sponsor_name}
                    </td>

                    <td style={{ padding:"10px 12px", textAlign:"right",
                      fontFamily:"var(--fm)", fontSize:15, fontWeight:600,
                      color:color.mid }}>
                      {row.new_trial_count}
                    </td>

                    <td style={{ padding:"10px 12px" }}>
                      <div style={{ display:"flex", gap:4, flexWrap:"wrap" }}>
                        {(row.modalities||[]).slice(0,3).map(mod => (
                          <span key={mod} style={{ fontFamily:"var(--fm)", fontSize:10,
                            padding:"2px 6px", borderRadius:8,
                            background:modColor(mod)+"20", color:modColor(mod),
                            border:`1px solid ${modColor(mod)}30` }}>
                            {humanMod(mod)}
                          </span>
                        ))}
                        {(row.modalities||[]).length > 3 && (
                          <span style={{ fontFamily:"var(--fm)", fontSize:10,
                            color:"var(--muted)" }}>
                            +{row.modalities.length - 3}
                          </span>
                        )}
                      </div>
                    </td>

                    <td style={{ padding:"10px 12px", fontFamily:"var(--fm)",
                      fontSize:12, color:"var(--muted)" }}>
                      {row.top_phase || "—"}
                    </td>

                    <td style={{ padding:"10px 12px", textAlign:"right",
                      fontFamily:"var(--fm)", fontSize:12, color:"var(--text)" }}>
                      {row.priority_score}
                    </td>

                    <td style={{ padding:"10px 12px" }}>
                      <span style={{ fontFamily:"var(--fm)", fontSize:10,
                        fontWeight:600, padding:"3px 10px", borderRadius:10,
                        color:pri.color, background:pri.bg,
                        border:`1px solid ${pri.border}` }}>
                        {row.priority_label}
                      </span>
                    </td>

                    <td style={{ padding:"10px 8px", color:"var(--muted)",
                      fontSize:12, textAlign:"center",
                      transition:"transform 0.15s",
                      transform: isOpen ? "rotate(180deg)" : "none" }}>
                      ▾
                    </td>
                  </tr>

                  {/* Expanded trial list */}
                  {isOpen && (
                    <tr style={{ background:"var(--surf3)" }}>
                      <td colSpan={7} style={{ padding:"0 12px 14px 36px" }}>
                        <table style={{ width:"100%", borderCollapse:"collapse" }}>
                          <thead>
                            <tr>
                              {["NCT ID","TITLE","MODALITY","PHASE"].map(h => (
                                <th key={h} style={{ padding:"6px 8px", textAlign:"left",
                                  fontFamily:"var(--fm)", fontSize:9,
                                  color:"var(--dim)", letterSpacing:"0.12em",
                                  borderBottom:"1px solid var(--border)" }}>
                                  {h}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {(row.trials||[]).map((t, ti) => (
                              <tr key={t.nct_id || ti}
                                style={{ borderTop:"1px solid var(--border)" }}>
                                <td style={{ padding:"5px 8px",
                                  fontFamily:"var(--fm)", fontSize:11,
                                  color:"var(--cyan)", whiteSpace:"nowrap" }}>
                                  <a href={`https://clinicaltrials.gov/expert-search?term=${t.nct_id}`}
                                     target="_blank" rel="noopener noreferrer"
                                     style={{ color:"var(--cyan)", textDecoration:"none" }}
                                     onMouseOver={e => e.target.style.textDecoration="underline"}
                                     onMouseOut={e  => e.target.style.textDecoration="none"}>
                                    {t.nct_id}
                                  </a>
                                </td>
                                <td style={{ padding:"5px 8px", fontSize:12,
                                  color:"var(--text)", maxWidth:420,
                                  overflowX:"auto", whiteSpace:"nowrap" }}>
                                  {t.title}
                                </td>
                                <td style={{ padding:"5px 8px" }}>
                                  <span style={{ fontFamily:"var(--fm)", fontSize:10,
                                    padding:"2px 6px", borderRadius:8,
                                    background:modColor(t.modality)+"20",
                                    color:modColor(t.modality) }}>
                                    {humanMod(t.modality)}
                                  </span>
                                </td>
                                <td style={{ padding:"5px 8px",
                                  fontFamily:"var(--fm)", fontSize:11,
                                  color:"var(--muted)" }}>
                                  {t.phase || "—"}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
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
