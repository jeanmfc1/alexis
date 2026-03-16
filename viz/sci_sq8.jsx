// ─────────────────────────────────────────────────────────────────────────
// viz/sci_sq8.jsx
// Scientific / sq8 — Biomarker × TA Bubble Matrix
//
// Data source : ALEXIS_DATA.sq8  (matrix dict)
// Injected by : analytics/sci_biomarker.py → sq8_biomarker_ta_matrix()
// ─────────────────────────────────────────────────────────────────────────

const PHASE_ORDER = {
  "PHASE3":1, "PHASE2/PHASE3":2, "PHASE2":3, "PHASE1/PHASE2":4,
  "PHASE1":5, "EARLY_PHASE1":6, "PHASE4":7, "NA":8, "—":9,
};
function phaseSort(a, b) {
  return (PHASE_ORDER[a.phase] || 99) - (PHASE_ORDER[b.phase] || 99);
}

const PHASE_COLORS = {
  "PHASE3":"#22C55E", "PHASE2":"#38BDF8", "PHASE1":"#F59E0B",
  "PHASE1/PHASE2":"#F59E0B", "PHASE2/PHASE3":"#38BDF8",
  "EARLY_PHASE1":"#F59E0B", "PHASE4":"#8B5CF6", "NA":"#475569", "—":"#475569",
};

function abbrTA(name) {
  if (name.length <= 14) return name;
  const abbrs = {
    "Oncology":"Onc",
    "Rare Disease":"Rare",
    "Immunology":"Immuno",
    "Neurology":"Neuro",
    "Cardiology":"Cardio",
    "Infectious Disease":"InfDis",
    "Dermatology":"Derm",
    "Endocrinology":"Endo",
    "Gastroenterology":"Gastro",
    "Ophthalmology":"Ophth",
    "Hematology":"Heme",
    "Pulmonology":"Pulm",
    "Rheumatology":"Rheum",
    "Nephrology":"Neph",
    "Psychiatry":"Psych",
  };
  return abbrs[name] || name.slice(0, 12) + "…";
}

function SQ8BiomarkerMatrix({ data, color }) {
  const [openCell, setOpenCell] = useState(null);

  if (!data?.available) return (
    <div style={{ fontFamily:"var(--fm)", fontSize:12, color:"var(--muted)", padding:"20px 0" }}>
      No data — biomarker enrichment not available for this quarter.
    </div>
  );

  const { rows, columns, cells, row_totals, col_totals, grand_total, meta } = data;

  const accent   = color?.accent || "#10B981";
  const maxCount = Math.max(...Object.values(cells).map(c => c.count), 1);
  const bubbleSize = n => n === 0 ? 0 : Math.max(8, Math.sqrt(n / maxCount) * 40);

  const COL_W   = 66;
  const ROW_H   = 52;
  const LABEL_W = 170;
  const fmt = n => n.toLocaleString();
  const toggle = key => setOpenCell(prev => prev === key ? null : key);

  return (
    <div style={{ fontFamily:"var(--fm)" }}>

      {/* summary strip */}
      <div style={{
        display:"flex", gap:16, alignItems:"baseline", marginBottom:14,
        fontSize:11, color:"var(--muted)", fontFamily:"var(--fb)"
      }}>
        <span><b style={{ color:"var(--text)", fontSize:13 }}>{fmt(grand_total)}</b> biomarker-tagged trials</span>
        {meta?.total_drug_trials != null &&
          <span>of <b style={{ color:"var(--text)" }}>{fmt(meta.total_drug_trials)}</b> drug trials</span>}
      </div>

      {/* matrix grid */}
      <div style={{ overflowX:"auto" }}>

        {/* column headers */}
        <div style={{ display:"flex", paddingLeft:LABEL_W }}>
          {columns.map(ta => (
            <div key={ta} style={{
              width:COL_W, textAlign:"center", fontSize:9,
              color:"var(--dim)", fontFamily:"var(--fb)",
              lineHeight:"1.15", padding:"0 2px 6px",
            }}>
              <div style={{ whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis" }}>
                {abbrTA(ta)}
              </div>
              <div style={{ fontSize:8, color:"var(--muted)", marginTop:2 }}>{fmt(col_totals[ta] || 0)}</div>
            </div>
          ))}
        </div>

        {/* rows */}
        {rows.map(bm => {
          const expanded = columns.some(ta => openCell === `${bm}||${ta}`);
          return (
            <div key={bm}>
              {/* bubble row */}
              <div style={{
                display:"flex", alignItems:"center", height:ROW_H,
                borderBottom:"1px solid var(--border)"
              }}>
                {/* row label */}
                <div style={{
                  width:LABEL_W, flexShrink:0, fontSize:11, color:"var(--text)",
                  fontFamily:"var(--fb)", paddingRight:8, overflow:"hidden",
                  textOverflow:"ellipsis", whiteSpace:"nowrap"
                }} title={bm}>{bm}</div>

                {/* cells */}
                {columns.map(ta => {
                  const cell = cells[`${bm}||${ta}`];
                  const count = cell?.count || 0;
                  const key   = `${bm}||${ta}`;
                  const sz    = bubbleSize(count);
                  const active = openCell === key;
                  return (
                    <div key={ta} style={{
                      width:COL_W, display:"flex", alignItems:"center", justifyContent:"center"
                    }}>
                      {count > 0 ? (
                        <div
                          onClick={() => toggle(key)}
                          title={`${bm} × ${ta}: ${count}`}
                          style={{
                            width:sz, height:sz, borderRadius:"50%",
                            background:accent,
                            opacity: 0.35 + 0.65 * (count / maxCount),
                            cursor:"pointer",
                            display:"flex", alignItems:"center", justifyContent:"center",
                            fontSize: sz < 18 ? 7 : 9,
                            color:"#fff", fontFamily:"var(--fb)",
                            transform: active ? "scale(1.2)" : "none",
                            transition:"transform .15s",
                          }}
                        >{count}</div>
                      ) : (
                        <div style={{ width:4, height:4, borderRadius:"50%", background:"var(--surf2)" }} />
                      )}
                    </div>
                  );
                })}

                {/* row total */}
                <div style={{
                  width:50, textAlign:"right", fontSize:10, fontFamily:"var(--fb)",
                  color:"var(--muted)", paddingLeft:4
                }}>{fmt(row_totals[bm] || 0)}</div>
              </div>

              {/* expanded panel */}
              {expanded && (() => {
                const activeTa = columns.find(ta => openCell === `${bm}||${ta}`);
                const cell = cells[`${bm}||${activeTa}`];
                if (!cell?.trials?.length) return null;
                const trials = [...cell.trials].sort(phaseSort);
                return (
                  <div style={{
                    background:"var(--surf2)", borderBottom:"1px solid var(--border)",
                    padding:"10px 12px 10px " + LABEL_W + "px",
                  }}>
                    <div style={{ fontSize:10, color:"var(--muted)", marginBottom:6, fontFamily:"var(--fb)" }}>
                      {bm} × {activeTa} — {trials.length} trial{trials.length > 1 ? "s" : ""}
                    </div>
                    <table style={{ width:"100%", borderCollapse:"collapse", fontSize:10, fontFamily:"var(--fm)" }}>
                      <tbody>
                        {trials.map(t => (
                          <tr key={t.nct_id} style={{ borderBottom:"1px solid var(--border)" }}>
                            <td style={{ padding:"3px 8px 3px 0", whiteSpace:"nowrap" }}>
                              <a href={`https://clinicaltrials.gov/study/${t.nct_id}`}
                                 target="_blank" rel="noreferrer"
                                 style={{ color:"var(--cyan)", textDecoration:"none" }}>
                                {t.nct_id}
                              </a>
                            </td>
                            <td style={{ padding:"3px 8px", color:"var(--text)", maxWidth:320,
                                         overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}
                                title={t.title}>
                              {t.title}
                            </td>
                            <td style={{ padding:"3px 0", textAlign:"right", whiteSpace:"nowrap" }}>
                              <span style={{
                                display:"inline-block", fontSize:8, fontFamily:"var(--fb)",
                                padding:"1px 6px", borderRadius:4,
                                background: PHASE_COLORS[t.phase] || "#475569",
                                color:"#fff",
                              }}>{t.phase || "—"}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                );
              })()}
            </div>
          );
        })}

        {/* column totals footer */}
        <div style={{
          display:"flex", paddingLeft:LABEL_W, borderTop:"1px solid var(--border)", paddingTop:6, marginTop:2
        }}>
          {columns.map(ta => (
            <div key={ta} style={{
              width:COL_W, textAlign:"center", fontSize:9,
              fontFamily:"var(--fb)", color:"var(--muted)"
            }}>{fmt(col_totals[ta] || 0)}</div>
          ))}
          <div style={{
            width:50, textAlign:"right", fontSize:10, fontFamily:"var(--fb)", color:"var(--text)", paddingLeft:4
          }}>{fmt(grand_total)}</div>
        </div>
      </div>

      {/* biomarker category key */}
      {meta?.categories && (
        <div style={{
          display:"flex", flexWrap:"wrap", gap:12, marginTop:14,
          fontSize:9, color:"var(--dim)", fontFamily:"var(--fb)"
        }}>
          {Object.entries(meta.categories).map(([cat, n]) => (
            <span key={cat} style={{ display:"flex", alignItems:"center", gap:4 }}>
              <span style={{
                width:6, height:6, borderRadius:"50%", background:accent, opacity:0.7,
              }} />
              {cat} ({n})
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
