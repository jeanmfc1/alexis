// ─────────────────────────────────────────────────────────────────────────
// viz/sci_wq1.jsx
// Scientific / wq1 — TA × Modality Bubble Matrix
//
// Data source : ALEXIS_DATA.wq7  (matrix dict)
// Injected by : analytics/sci_wq1.py → wq7_ta_modality_matrix()
// ─────────────────────────────────────────────────────────────────────────

const MODALITY_ABBR = {
  small_molecule:"SM", biologic:"Bio", monoclonal_antibody:"mAb",
  mab:"mAb", antibody_drug_conjugate:"ADC", adc:"ADC",
  gene_therapy:"GT", cell_therapy:"CT", cell_gene_therapy:"CGT",
  radiopharmaceutical:"Radio", oligonucleotide:"Oligo", peptide:"Pep",
  vaccine:"Vax", combination:"Combo", antibody_protein:"Ab/Pr",
  fusion_protein:"Fusion", other_drug:"Other",
};

function parseMasterDbLabel(filename) {
  if (!filename) return "master DB";
  const m = filename.match(/(\d{4})[_\s]?(Q\d)/i);
  if (m) return `${m[1]} ${m[2].toUpperCase()}`;
  const m2 = filename.match(/(\d{4})/);
  return m2 ? m2[1] : filename.replace(/\.json$/, "").replace(/master_DB_?/i, "");
}

function heatToColor(heat) {
  if (heat === null || heat === undefined) {
    return { bg:"var(--surf2)", border:"var(--border)", glow:"none" };
  }
  if (heat >= 0.15) {
    const t  = Math.min(heat, 1);
    const a1 = (0.12 + t * 0.40).toFixed(2);
    const a2 = (0.40 + t * 0.45).toFixed(2);
    return { bg:`rgba(239,68,68,${a1})`, border:`rgba(239,68,68,${a2})`,
             glow:`0 0 10px rgba(239,68,68,${(t*0.5).toFixed(2)})` };
  }
  if (heat <= -0.15) {
    const t  = Math.min(Math.abs(heat), 1);
    const a1 = (0.08 + t * 0.22).toFixed(2);
    const a2 = (0.25 + t * 0.35).toFixed(2);
    return { bg:`rgba(59,130,246,${a1})`, border:`rgba(59,130,246,${a2})`,
             glow:`0 0 8px rgba(59,130,246,${(t*0.4).toFixed(2)})` };
  }
  return { bg:"rgba(200,216,238,0.07)", border:"rgba(200,216,238,0.18)", glow:"none" };
}

const PHASE_ORDER = {
  "PHASE3":1, "PHASE2/PHASE3":2, "PHASE2":3, "PHASE1/PHASE2":4,
  "PHASE1":5, "EARLY_PHASE1":6, "PHASE4":7, "NA":8, "—":9,
};
function phaseSort(a, b) {
  return (PHASE_ORDER[a.phase] || 99) - (PHASE_ORDER[b.phase] || 99);
}

const PHASE_COLORS = {
  "PHASE3":"#22C55E", "PHASE2/PHASE3":"#86EFAC", "PHASE2":"#38BDF8",
  "PHASE1/PHASE2":"#7DD3FC", "PHASE1":"#A78BFA", "EARLY_PHASE1":"#C4B5FD",
  "PHASE4":"#FB923C", "NA":"#6B7280", "—":"#4B5563",
};

function WQ7BubbleMatrix({ data, color }) {
  const [openCell, setOpenCell] = useState(null);
  const [tooltip,  setTooltip]  = useState(null);

  if (!data?.available) return (
    <div style={{ fontFamily:"var(--fm)", fontSize:12, color:"var(--muted)", padding:"20px 0" }}>
      No data — enriched file not loaded or no new drug registrations this window.
    </div>
  );

  const { rows, columns, cells, row_totals, col_totals, grand_total,
          has_heat, heat_mode, prior_weeks_used, prior_window_labels,
          week_total, db_total } = data;

  const masterLabel = parseMasterDbLabel(ALEXIS_DATA?.master_db_meta?.filename);
  const maxCount    = Math.max(...Object.values(cells).map(c => c.count), 1);
  const bubbleSize  = n => n === 0 ? 0 : Math.max(8, Math.sqrt(n / maxCount) * 40);

  const COL_W   = 66;
  const ROW_H   = 52;
  const LABEL_W = 194;

  const heatBadge = heat_mode === "rolling_avg"
    ? `✓ heat vs ${prior_weeks_used}-week rolling avg`
    : heat_mode === "master_db"
    ? `✓ heat vs ${masterLabel} baseline`
    : null;

  return (
    <div>
      {/* Summary strip */}
      <div style={{ display:"flex", gap:14, marginBottom:16,
        alignItems:"center", flexWrap:"wrap" }}>
        <div style={{ fontFamily:"var(--fm)", fontSize:12 }}>
          <span style={{ color:color.mid, fontWeight:600 }}>{fmt(grand_total)}</span>
          <span style={{ color:"var(--muted)" }}> new drug registrations this window</span>
        </div>
        <div style={{ fontFamily:"var(--fm)", fontSize:10,
          color:"var(--dim)", letterSpacing:"0.06em" }}>
          Click each bubble for more details
        </div>
        {heatBadge && (
          <div style={{ fontFamily:"var(--fm)", fontSize:10,
            color:"var(--green)", background:"rgba(34,197,94,0.08)",
            border:"1px solid rgba(34,197,94,0.3)", borderRadius:4, padding:"3px 8px" }}>
            {heatBadge}
          </div>
        )}
        {has_heat && (
          <div style={{ display:"flex", alignItems:"center", gap:8, marginLeft:"auto" }}>
            <span style={{ fontFamily:"var(--fm)", fontSize:9,
              color:"var(--dim)", letterSpacing:"0.1em" }}>HEAT</span>
            {[
              { label:"cooler",   bg:"rgba(59,130,246,0.22)",  border:"rgba(59,130,246,0.5)" },
              { label:"baseline", bg:"rgba(200,216,238,0.07)", border:"rgba(200,216,238,0.18)" },
              { label:"hotter",   bg:"rgba(239,68,68,0.38)",   border:"rgba(239,68,68,0.7)" },
            ].map(s => (
              <div key={s.label} style={{ display:"flex", alignItems:"center", gap:4 }}>
                <div style={{ width:12, height:12, borderRadius:3,
                  background:s.bg, border:`1px solid ${s.border}` }} />
                <span style={{ fontFamily:"var(--fm)", fontSize:9, color:"var(--muted)" }}>
                  {s.label}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Prior week labels */}
      {prior_window_labels?.length > 0 && (
        <div style={{ display:"flex", gap:6, marginBottom:12, flexWrap:"wrap" }}>
          <span style={{ fontFamily:"var(--fm)", fontSize:9,
            color:"var(--dim)", letterSpacing:"0.1em", alignSelf:"center" }}>
            AVG OVER:
          </span>
          {prior_window_labels.map((lbl, i) => (
            <span key={i} style={{ fontFamily:"var(--fm)", fontSize:9,
              color:"var(--muted)", background:"var(--surf2)",
              border:"1px solid var(--border)", borderRadius:4, padding:"2px 7px" }}>
              {lbl}
            </span>
          ))}
        </div>
      )}

      {/* Matrix */}
      <div style={{ overflowX:"auto" }}>
        <div style={{ display:"inline-block",
          minWidth: LABEL_W + columns.length * COL_W + 56 }}>

          {/* Column headers */}
          <div style={{ display:"flex", marginLeft:LABEL_W }}>
            {columns.map(mod => (
              <div key={mod} style={{ width:COL_W, flexShrink:0,
                textAlign:"center", paddingBottom:8 }}>
                <div style={{ fontFamily:"var(--fm)", fontSize:10,
                  color:modColor(mod), letterSpacing:"0.06em", fontWeight:600 }}>
                  {MODALITY_ABBR[mod] || mod.slice(0,6)}
                </div>
                <div style={{ fontFamily:"var(--fm)", fontSize:9,
                  color:"var(--muted)", marginTop:1 }}>
                  {fmt(col_totals[mod])}
                </div>
              </div>
            ))}
            <div style={{ width:56, flexShrink:0, textAlign:"right",
              fontFamily:"var(--fm)", fontSize:9, color:"var(--dim)",
              paddingBottom:8, paddingRight:4, alignSelf:"flex-end" }}>
              TOTAL
            </div>
          </div>

          {/* Rows + inline expanded panel */}
          {rows.map((ta, ri) => (
            <div key={ta}>
              <div style={{ display:"flex", alignItems:"center",
                borderTop:"1px solid var(--border)",
                background: ri % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)" }}>

                <div title={ta} style={{ width:LABEL_W, flexShrink:0,
                  padding:"0 10px 0 0", fontFamily:"var(--fb)", fontSize:11,
                  color:"var(--text)", overflow:"hidden", textOverflow:"ellipsis",
                  whiteSpace:"nowrap", height:ROW_H,
                  display:"flex", alignItems:"center" }}>
                  {ta}
                </div>

                {columns.map(mod => {
                  const key  = `${ta}||${mod}`;
                  const cell = cells[key] || { count:0, heat:null, trials:[] };
                  const sz   = bubbleSize(cell.count);
                  const hc   = heatToColor(cell.heat);
                  const isActive = openCell === key;
                  return (
                    <div key={mod}
                      style={{ width:COL_W, height:ROW_H, flexShrink:0,
                        display:"flex", alignItems:"center", justifyContent:"center",
                        cursor: cell.count > 0 ? "pointer" : "default" }}
                      onClick={() => {
                        if (cell.count > 0) {
                          setOpenCell(prev => prev === key ? null : key);
                          setTooltip(prev =>
                            (prev?.key === key) ? null : { cell, ta, mod, key }
                          );
                        }
                      }}>
                      {cell.count > 0 && (
                        <div style={{
                          width:sz, height:sz, borderRadius:"50%",
                          background:hc.bg, border:`1.5px solid ${hc.border}`,
                          display:"flex", alignItems:"center", justifyContent:"center",
                          transition:"all 0.15s",
                          transform: isActive ? "scale(1.2)" : "scale(1)",
                          boxShadow: isActive ? hc.glow : "none",
                          outline: isActive ? `2px solid ${hc.border}` : "none",
                          outlineOffset: 3,
                        }}>
                          {sz >= 22 && (
                            <span style={{ fontFamily:"var(--fm)",
                              fontSize: sz >= 30 ? 11 : 9, fontWeight:600,
                              color:"var(--text)", userSelect:"none" }}>
                              {cell.count}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}

                <div style={{ width:56, flexShrink:0, textAlign:"right",
                  paddingRight:4, fontFamily:"var(--fm)", fontSize:11,
                  fontWeight:600, color:color.mid }}>
                  {fmt(row_totals[ta])}
                </div>
              </div>

              {/* Inline expanded panel */}
              {columns.some(mod => openCell === `${ta}||${mod}`) && (() => {
                const activeKey  = columns.map(m => `${ta}||${m}`).find(k => openCell === k);
                const activeCell = cells[activeKey] || {};
                const activeMod  = activeKey ? activeKey.split("||")[1] : "";
                const sorted     = [...(activeCell.trials || [])].sort(phaseSort);
                return (
                  <div style={{ borderTop:"1px solid var(--border2)",
                    background:"var(--surf2)", padding:"12px 16px 16px",
                    marginLeft: LABEL_W }}>

                    <div style={{ display:"flex", alignItems:"center",
                      gap:10, marginBottom:10, flexWrap:"wrap" }}>
                      <div style={{ width:10, height:10, borderRadius:"50%",
                        background:modColor(activeMod), flexShrink:0 }} />
                      <span style={{ fontFamily:"var(--fb)", fontSize:12,
                        color:"var(--text)" }}>
                        {ta} — {humanMod(activeMod)}
                      </span>
                      <span style={{ fontFamily:"var(--fm)", fontSize:11,
                        color:color.mid }}>
                        {activeCell.count} trial{activeCell.count !== 1 ? "s" : ""} this week
                      </span>
                      {activeCell.prior_avg_count != null && (
                        <span style={{ fontFamily:"var(--fm)", fontSize:10,
                          color:"var(--muted)" }}>
                          · {prior_weeks_used}-week avg: {activeCell.prior_avg_count.toFixed(1)}
                        </span>
                      )}
                      {activeCell.baseline_n != null && (
                        <span style={{ fontFamily:"var(--fm)", fontSize:10,
                          color:"var(--dim)" }}>
                          · {masterLabel} total: {fmt(activeCell.baseline_n)}
                        </span>
                      )}
                      {activeCell.heat_label && (
                        <span style={{ fontFamily:"var(--fm)", fontSize:10, fontWeight:600,
                          color: activeCell.heat >= 0.15 ? "#EF4444"
                               : activeCell.heat <= -0.15 ? "#60A5FA"
                               : "var(--muted)" }}>
                          {activeCell.heat_label}
                        </span>
                      )}
                      <button onClick={() => setOpenCell(null)}
                        style={{ marginLeft:"auto", fontFamily:"var(--fm)",
                          fontSize:10, color:"var(--muted)", background:"transparent",
                          border:"none", cursor:"pointer", padding:"2px 6px" }}>
                        ✕ close
                      </button>
                    </div>

                    <div style={{ maxHeight:260, overflowY:"auto",
                      border:"1px solid var(--border)", borderRadius:6 }}>
                      <table style={{ width:"100%", borderCollapse:"collapse" }}>
                        <thead style={{ position:"sticky", top:0,
                          background:"var(--surf3)", zIndex:1 }}>
                          <tr>
                            {["NCT ID","TITLE","PHASE"].map(h => (
                              <th key={h} style={{ padding:"6px 10px",
                                fontFamily:"var(--fm)", fontSize:9,
                                color:"var(--dim)", letterSpacing:"0.12em",
                                textAlign:"left", fontWeight:500,
                                borderBottom:"1px solid var(--border)" }}>
                                {h}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {sorted.map((t, ti) => {
                            const pc = PHASE_COLORS[t.phase] || "#6B7280";
                            return (
                              <tr key={t.nct_id || ti}
                                style={{ borderTop: ti > 0 ? "1px solid var(--border)" : "none",
                                  background: ti % 2 === 0 ? "transparent" : "rgba(255,255,255,0.01)" }}>
                                <td style={{ padding:"5px 10px", whiteSpace:"nowrap" }}>
                                  <a href={`https://clinicaltrials.gov/expert-search?term=${t.nct_id}`}
                                     target="_blank" rel="noopener noreferrer"
                                     style={{ fontFamily:"var(--fm)", fontSize:11,
                                       color:"var(--cyan)", textDecoration:"none" }}
                                     onMouseOver={e => e.target.style.textDecoration="underline"}
                                     onMouseOut={e  => e.target.style.textDecoration="none"}>
                                    {t.nct_id}
                                  </a>
                                </td>
                                <td style={{ padding:"5px 10px", fontSize:11,
                                  color:"var(--text)", maxWidth:480,
                                  overflowX:"auto", whiteSpace:"nowrap" }}>
                                  {t.title}
                                </td>
                                <td style={{ padding:"5px 10px", whiteSpace:"nowrap" }}>
                                  <span style={{ fontFamily:"var(--fm)", fontSize:10,
                                    padding:"2px 7px", borderRadius:8,
                                    background:(PHASE_COLORS[t.phase]||"#6B7280")+"18",
                                    color:pc, border:`1px solid ${pc}30` }}>
                                    {t.phase}
                                  </span>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                );
              })()}
            </div>
          ))}

          {/* Column totals footer */}
          <div style={{ display:"flex", borderTop:"1px solid var(--border2)", marginTop:2 }}>
            <div style={{ width:LABEL_W, flexShrink:0, fontFamily:"var(--fm)",
              fontSize:9, color:"var(--dim)", padding:"6px 10px 0 0",
              textAlign:"right", letterSpacing:"0.1em" }}>
              TOTAL
            </div>
            {columns.map(mod => (
              <div key={mod} style={{ width:COL_W, flexShrink:0, textAlign:"center",
                fontFamily:"var(--fm)", fontSize:11, fontWeight:600,
                color:modColor(mod), paddingTop:6 }}>
                {fmt(col_totals[mod])}
              </div>
            ))}
            <div style={{ width:56, flexShrink:0, textAlign:"right",
              paddingRight:4, fontFamily:"var(--fm)", fontSize:12,
              fontWeight:700, color:"var(--cyan)", paddingTop:6 }}>
              {fmt(grand_total)}
            </div>
          </div>
        </div>
      </div>

      {/* Modality key */}
      <div style={{ display:"flex", gap:10, flexWrap:"wrap", marginTop:14 }}>
        {columns.map(mod => (
          <div key={mod} style={{ display:"flex", alignItems:"center", gap:5 }}>
            <div style={{ width:8, height:8, borderRadius:"50%", background:modColor(mod) }} />
            <span style={{ fontFamily:"var(--fm)", fontSize:9, color:"var(--muted)" }}>
              {MODALITY_ABBR[mod] || mod} = {humanMod(mod)}
            </span>
          </div>
        ))}
      </div>

      {/* Click-triggered sidebar panel */}
      {tooltip && (
        <div style={{ marginTop:14, borderRadius:10,
          background:"var(--surf2)", border:`1px solid ${heatToColor(tooltip.cell.heat).border}`,
          padding:"14px 16px" }}>
          <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:10 }}>
            <div style={{ width:9, height:9, borderRadius:"50%",
              background:modColor(tooltip.mod), flexShrink:0 }} />
            <span style={{ fontFamily:"var(--fb)", fontSize:12, color:"var(--text)" }}>
              {humanMod(tooltip.mod)}
            </span>
            <span style={{ fontFamily:"var(--fm)", fontSize:11, color:"var(--muted)" }}>·</span>
            <span style={{ fontFamily:"var(--fm)", fontSize:11,
              color:"var(--muted)", overflow:"hidden", textOverflow:"ellipsis",
              whiteSpace:"nowrap" }}>
              {tooltip.ta}
            </span>
            <button onClick={() => { setTooltip(null); setOpenCell(null); }}
              style={{ marginLeft:"auto", fontFamily:"var(--fm)", fontSize:10,
                color:"var(--muted)", background:"transparent",
                border:"none", cursor:"pointer", padding:"2px 6px", flexShrink:0 }}>
              ✕
            </button>
          </div>
          <div style={{ display:"flex", gap:20, flexWrap:"wrap", marginBottom:10 }}>
            <div>
              <div style={{ fontFamily:"var(--fm)", fontSize:9,
                color:"var(--dim)", letterSpacing:"0.1em", marginBottom:2 }}>
                THIS WEEK
              </div>
              <div style={{ fontFamily:"var(--fm)", fontSize:22,
                fontWeight:700, color:"var(--cyan)", lineHeight:1 }}>
                {tooltip.cell.count}
              </div>
              <div style={{ fontFamily:"var(--fm)", fontSize:9, color:"var(--muted)" }}>
                new trials
              </div>
            </div>
            {tooltip.cell.prior_avg_count != null && (
              <div>
                <div style={{ fontFamily:"var(--fm)", fontSize:9,
                  color:"var(--dim)", letterSpacing:"0.1em", marginBottom:2 }}>
                  {prior_weeks_used}-WK AVG
                </div>
                <div style={{ fontFamily:"var(--fm)", fontSize:22,
                  fontWeight:700, color:"var(--muted)", lineHeight:1 }}>
                  {tooltip.cell.prior_avg_count.toFixed(1)}
                </div>
              </div>
            )}
            {tooltip.cell.baseline_n != null && (
              <div>
                <div style={{ fontFamily:"var(--fm)", fontSize:9,
                  color:"var(--dim)", letterSpacing:"0.1em", marginBottom:2 }}>
                  {masterLabel}
                </div>
                <div style={{ fontFamily:"var(--fm)", fontSize:22,
                  fontWeight:700, color:"var(--muted)", lineHeight:1 }}>
                  {fmt(tooltip.cell.baseline_n)}
                </div>
              </div>
            )}
          </div>
          {tooltip.cell.heat_label && (
            <div style={{ fontFamily:"var(--fm)", fontSize:11, fontWeight:600,
              marginBottom:10,
              color: tooltip.cell.heat >= 0.15 ? "#EF4444"
                   : tooltip.cell.heat <= -0.15 ? "#60A5FA"
                   : "var(--muted)" }}>
              {tooltip.cell.heat_label}
            </div>
          )}
          {/* Trial list — only when bubble is also selected */}
          {openCell === tooltip.key && (() => {
            const sorted = [...(tooltip.cell.trials || [])].sort(phaseSort);
            return (
              <div style={{ maxHeight:220, overflowY:"auto",
                border:"1px solid var(--border)", borderRadius:6 }}>
                <table style={{ width:"100%", borderCollapse:"collapse" }}>
                  <thead style={{ position:"sticky", top:0,
                    background:"var(--surf3)", zIndex:1 }}>
                    <tr>
                      {["NCT ID","TITLE","PHASE"].map(h => (
                        <th key={h} style={{ padding:"5px 8px",
                          fontFamily:"var(--fm)", fontSize:9, color:"var(--dim)",
                          letterSpacing:"0.1em", textAlign:"left", fontWeight:500,
                          borderBottom:"1px solid var(--border)" }}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {sorted.map((t, ti) => {
                      const pc = PHASE_COLORS[t.phase] || "#6B7280";
                      return (
                        <tr key={t.nct_id || ti}
                          style={{ borderTop: ti > 0 ? "1px solid var(--border)" : "none",
                            background: ti%2===0 ? "transparent" : "rgba(255,255,255,0.01)" }}>
                          <td style={{ padding:"4px 8px", whiteSpace:"nowrap" }}>
                            <a href={`https://clinicaltrials.gov/expert-search?term=${t.nct_id}`}
                               target="_blank" rel="noopener noreferrer"
                               style={{ fontFamily:"var(--fm)", fontSize:10,
                                 color:"var(--cyan)", textDecoration:"none" }}
                               onMouseOver={e => e.target.style.textDecoration="underline"}
                               onMouseOut={e  => e.target.style.textDecoration="none"}>
                              {t.nct_id}
                            </a>
                          </td>
                          <td style={{ padding:"4px 8px", fontSize:10,
                            color:"var(--text)", maxWidth:380,
                            overflowX:"auto", whiteSpace:"nowrap" }}>
                            {t.title}
                          </td>
                          <td style={{ padding:"4px 8px", whiteSpace:"nowrap" }}>
                            <span style={{ fontFamily:"var(--fm)", fontSize:9,
                              padding:"2px 6px", borderRadius:6,
                              background:pc+"18", color:pc,
                              border:`1px solid ${pc}30` }}>
                              {t.phase}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            );
          })()}
          {openCell !== tooltip.key && tooltip.cell.count > 0 && (
            <div style={{ fontFamily:"var(--fm)", fontSize:9,
              color:"var(--dim)", marginTop:4 }}>
              click the bubble again to show trials ↑
            </div>
          )}
        </div>
      )}
    </div>
  );
}
