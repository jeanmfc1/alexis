// -----------------------------------------------------------------------
// viz/sci_aw1.jsx
// Scientific / aw3 (ANZCTR) -- TA x Modality Bubble Matrix
//
// Mirrors sci_cw1.jsx interactivity: heat-coloured bubbles sized by count,
// click to drill into trials, phase chips, row/column totals.
//
// Data source : ALEXIS_DATA.aw3  (matrix from analytics/sci_aw1.py)
// Globals used from host: modColor, humanMod
// -----------------------------------------------------------------------

const AW3_MOD_ABBR = {
  small_molecule:"SM", biologic:"Bio", monoclonal_antibody:"mAb", mab:"mAb",
  antibody_drug_conjugate:"ADC", adc:"ADC", gene_therapy:"GT",
  cell_therapy:"CT", cell_gene_therapy:"CGT", radiopharmaceutical:"Radio",
  oligonucleotide:"Oligo", peptide:"Pep", vaccine:"Vax", combination:"Combo",
  antibody_protein:"Ab/Pr", fusion_protein:"Fusion", other_drug:"Other",
  bispecific_antibody:"BsAb", Unknown:"?",
};

function aw3HeatToColor(heat) {
  if (heat === null || heat === undefined) {
    return { bg:"rgba(200,216,238,0.05)", border:"rgba(200,216,238,0.15)",
             glow:"none" };
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
  return { bg:"rgba(200,216,238,0.07)", border:"rgba(200,216,238,0.18)",
           glow:"none" };
}

const AW3_PHASE_COLORS = {
  "PHASE3":"#22C55E", "PHASE2/PHASE3":"#86EFAC",
  "PHASE2":"#38BDF8", "PHASE1/PHASE2":"#7DD3FC",
  "PHASE1":"#A78BFA", "EARLY_PHASE1":"#C4B5FD",
  "PHASE4":"#FB923C", "NA":"#6B7280", "-":"#4B5563",
};

function AW3AnzctrTAModalityMatrix({ data, color }) {
  if (!data || !data.available) {
    return (
      <div style={{ padding:"24px 16px", fontFamily:"var(--fm)",
        fontSize:12, color:"var(--muted)", textAlign:"center" }}>
        No new ANZCTR drug trials this period.
      </div>
    );
  }

  const [openCell, setOpenCell] = useState(null);

  const rows = data.rows || [];
  const cols = data.columns || [];
  const cells = data.cells || {};
  const rowTot = data.row_totals || {};
  const colTot = data.col_totals || {};

  const maxCount = Math.max(1, ...rows.flatMap(r =>
    cols.map(c => (cells[`${r}||${c}`]?.count || 0))));

  const bubbleSize = (n) => n === 0 ? 0
    : Math.max(10, Math.sqrt(n / maxCount) * 44);

  const COL_W = 66, ROW_H = 54, LABEL_W = 180;

  const activeCell = openCell ? cells[openCell] : null;

  const header = (
    <div style={{ padding:"2px 14px 10px", display:"flex",
      alignItems:"center", gap:14, fontFamily:"var(--fm)", fontSize:10,
      color:"var(--muted)", letterSpacing:"0.06em" }}>
      <span>
        <span style={{ color:"var(--text)", fontSize:12, fontWeight:600 }}>
          {data.grand_total}
        </span>
        &nbsp;new drug trials (ANZCTR)
      </span>
      {data.has_heat && (
        <React.Fragment>
          <span style={{ color:"var(--dim)" }}>|</span>
          <span>
            heat vs {data.prior_weeks_used}-period avg:
          </span>
          <span style={{ display:"inline-flex", gap:5, alignItems:"center" }}>
            <span style={{ width:10, height:10, borderRadius:2,
              background:"rgba(239,68,68,0.50)" }}/>above
          </span>
          <span style={{ display:"inline-flex", gap:5, alignItems:"center" }}>
            <span style={{ width:10, height:10, borderRadius:2,
              background:"rgba(59,130,246,0.50)" }}/>below
          </span>
        </React.Fragment>
      )}
      {!data.has_heat && (
        <React.Fragment>
          <span style={{ color:"var(--dim)" }}>|</span>
          <span>no heat (need {">="}2 prior snapshots)</span>
        </React.Fragment>
      )}
      <span style={{ flex:1 }}/>
      <span style={{ color:"var(--dim)" }}>
        click a bubble to inspect trials
      </span>
    </div>
  );

  return (
    <div>
      {header}
      <div style={{ display:"flex", gap:12, padding:"0 12px",
        alignItems:"flex-start" }}>
        {/* Left: matrix */}
        <div style={{ flex:1, minWidth:0, overflowX:"auto" }}>
          <div style={{ display:"inline-block" }}>
            {/* Header row: modality columns */}
            <div style={{ display:"flex", paddingLeft:LABEL_W }}>
              {cols.map(m => (
                <div key={m} style={{ width:COL_W, textAlign:"center",
                  fontFamily:"var(--fm)", fontSize:10,
                  color:"var(--muted)", padding:"4px 0",
                  borderBottom:"1px solid var(--border)" }} title={m}>
                  {AW3_MOD_ABBR[m] || humanMod(m).slice(0, 5)}
                </div>
              ))}
              <div style={{ width:50, textAlign:"center",
                fontFamily:"var(--fm)", fontSize:10, color:color.mid,
                fontWeight:600, padding:"4px 0",
                borderBottom:"1px solid var(--border)" }}>
                &#931;
              </div>
            </div>
            {/* Data rows */}
            {rows.map((ta, ri) => (
              <div key={ta} style={{
                display:"flex", alignItems:"center", height:ROW_H,
                background: ri % 2 === 0
                          ? "transparent" : "rgba(255,255,255,0.02)" }}>
                <div style={{ width:LABEL_W, padding:"0 14px 0 2px",
                  fontFamily:"var(--fb)", fontSize:12, color:"var(--text)",
                  whiteSpace:"nowrap", overflow:"hidden",
                  textOverflow:"ellipsis" }} title={ta}>
                  {ta}
                </div>
                {cols.map(m => {
                  const key    = `${ta}||${m}`;
                  const cell   = cells[key] || { count:0, heat:null };
                  const active = openCell === key;
                  const sz     = bubbleSize(cell.count);
                  const hc     = aw3HeatToColor(cell.heat);
                  return (
                    <div key={m} style={{ width:COL_W, height:ROW_H,
                      display:"flex", alignItems:"center",
                      justifyContent:"center", position:"relative" }}>
                      {cell.count > 0 && (
                        <div onClick={() => setOpenCell(active ? null : key)}
                          style={{ width:sz, height:sz, borderRadius:"50%",
                            cursor:"pointer",
                            background: hc.bg,
                            border: `2px solid ${hc.border}`,
                            outline: active ? `2px solid ${color.accent}` : "none",
                            outlineOffset: 3,
                            boxShadow: active ? hc.glow : "none",
                            transition:"all 0.15s",
                            transform: active ? "scale(1.15)" : "scale(1)",
                            display:"flex", alignItems:"center",
                            justifyContent:"center",
                            color:"var(--text)", fontFamily:"var(--fm)",
                            fontSize: sz >= 22 ? 11 : 0, fontWeight:600 }}
                          title={`${ta} x ${humanMod(m)}: ${cell.count}`
                                 + (cell.heat_label ? "  (" + cell.heat_label + ")" : "")}>
                          {sz >= 22 ? cell.count : ""}
                        </div>
                      )}
                    </div>
                  );
                })}
                <div style={{ width:50, textAlign:"center",
                  fontFamily:"var(--fm)", fontSize:12, fontWeight:600,
                  color: rowTot[ta] > 0 ? color.mid : "var(--dim)" }}>
                  {rowTot[ta] || ""}
                </div>
              </div>
            ))}
            {/* Column totals */}
            <div style={{ display:"flex", paddingLeft:LABEL_W,
              borderTop:"1px solid var(--border)" }}>
              {cols.map(m => (
                <div key={m} style={{ width:COL_W, textAlign:"center",
                  fontFamily:"var(--fm)", fontSize:11, color:color.mid,
                  padding:"6px 0" }}>
                  {colTot[m] || ""}
                </div>
              ))}
              <div style={{ width:50, textAlign:"center",
                fontFamily:"var(--fm)", fontSize:12, color:"var(--text)",
                fontWeight:700, padding:"6px 0" }}>
                {data.grand_total}
              </div>
            </div>
          </div>
        </div>

        {/* Right: detail pane */}
        {activeCell && (
          <div style={{ width:360, maxHeight:580, overflowY:"auto",
            background:"var(--surf2)", border:"1px solid var(--border)",
            borderRadius:10, padding:"14px 16px", flexShrink:0 }}>
            <div style={{ display:"flex", alignItems:"center",
              justifyContent:"space-between", marginBottom:8 }}>
              <div>
                <div style={{ fontFamily:"var(--fm)", fontSize:9,
                  letterSpacing:"0.14em", color:"var(--muted)",
                  textTransform:"uppercase" }}>
                  Cell detail
                </div>
                <div style={{ fontFamily:"var(--fb)", fontSize:14,
                  color:"var(--text)", fontWeight:600, marginTop:2 }}>
                  {activeCell.ta}
                </div>
                <div style={{ marginTop:4 }}>
                  <span style={{ fontFamily:"var(--fm)", fontSize:11,
                    padding:"2px 6px", borderRadius:8,
                    background:modColor(activeCell.mod)+"20",
                    color:modColor(activeCell.mod),
                    border:`1px solid ${modColor(activeCell.mod)}30` }}>
                    {humanMod(activeCell.mod)}
                  </span>
                </div>
              </div>
              <button onClick={() => setOpenCell(null)}
                style={{ background:"transparent", color:"var(--muted)",
                  border:"none", cursor:"pointer", fontFamily:"var(--fm)",
                  fontSize:11 }}>
                &#10005; close
              </button>
            </div>
            <div style={{ display:"flex", gap:12, margin:"12px 0 14px" }}>
              <div>
                <div style={{ fontFamily:"var(--fm)", fontSize:9,
                  letterSpacing:"0.10em", color:"var(--muted)" }}>
                  THIS PERIOD
                </div>
                <div style={{ fontFamily:"var(--fm)", fontSize:22,
                  fontWeight:700, color:"var(--cyan)" }}>
                  {activeCell.count}
                </div>
              </div>
              {activeCell.prior_avg_count !== null &&
               activeCell.prior_avg_count !== undefined && (
                <div>
                  <div style={{ fontFamily:"var(--fm)", fontSize:9,
                    letterSpacing:"0.10em", color:"var(--muted)" }}>
                    PRIOR AVG
                  </div>
                  <div style={{ fontFamily:"var(--fm)", fontSize:22,
                    fontWeight:700, color:"var(--text)" }}>
                    {activeCell.prior_avg_count}
                  </div>
                </div>
              )}
            </div>
            {activeCell.heat_label && (
              <div style={{ fontFamily:"var(--fm)", fontSize:11,
                color: activeCell.heat >= 0.15 ? "#EF4444"
                     : activeCell.heat <= -0.15 ? "#3B82F6"
                     : "var(--muted)",
                marginBottom:12 }}>
                {activeCell.heat_label}
              </div>
            )}
            <div style={{ fontFamily:"var(--fm)", fontSize:9,
              letterSpacing:"0.10em", color:"var(--muted)",
              marginBottom:6 }}>
              TRIALS ({activeCell.trials?.length || 0})
            </div>
            <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
              {(activeCell.trials || []).map(t => {
                const phase = (t.phase || "-").toString();
                const pc    = AW3_PHASE_COLORS[phase] || "#4B5563";
                return (
                  <div key={t.nct_id} style={{ padding:"8px 10px",
                    background:"var(--surf3)", borderRadius:6,
                    border:"1px solid var(--border)" }}>
                    <div style={{ display:"flex", alignItems:"center",
                      gap:8, marginBottom:4 }}>
                      {t.source_url
                        ? <a href={t.source_url} target="_blank" rel="noreferrer"
                            style={{ color:"var(--cyan)",
                              fontFamily:"var(--fm)", fontSize:11,
                              textDecoration:"none" }}>
                            {t.nct_id}
                          </a>
                        : <span style={{ fontFamily:"var(--fm)",
                            fontSize:11 }}>{t.nct_id}</span>}
                      <span style={{ fontFamily:"var(--fm)", fontSize:10,
                        padding:"1px 6px", borderRadius:6,
                        color:pc, background:pc+"18",
                        border:`1px solid ${pc}30` }}>
                        {phase}
                      </span>
                    </div>
                    <div style={{ fontSize:12, color:"var(--text)",
                      lineHeight:1.3 }}>
                      {t.title}
                    </div>
                    {t.sponsor && (
                      <div style={{ fontFamily:"var(--fm)", fontSize:10,
                        color:"var(--muted)", marginTop:3 }}>
                        {t.sponsor}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
