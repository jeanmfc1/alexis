// -----------------------------------------------------------------------
// viz/bd_wq2.jsx
// BD / wq2 -- Client Trial Alert Cards
//
// Data source : ALEXIS_DATA.wq2  (from analytics/bd_wq2.py)
// Globals     : PRIORITY_CFG, modColor, humanMod
// -----------------------------------------------------------------------

const WQ2_TIER_COLOR = {
  high:   "#22C55E",   // green = high-confidence match
  medium: "#F59E0B",   // amber
  low:    "#64748B",   // slate = verify before trusting
};

function WQ2ClientAlerts({ data, color }) {
  if (!data || !data.available) {
    return (
      <div style={{ padding:"24px 16px", fontFamily:"var(--fm)",
        fontSize:12, color:"var(--muted)", textAlign:"center" }}>
        {data?.reason || "No client-list match for new trials this week."}
      </div>
    );
  }

  const [expanded, setExpanded] = useState({});
  const [confFilter, setConfFilter] = useState(null);
  const alerts = (data.alerts || []).filter(a =>
      !confFilter || a.match_confidence === confFilter);

  const toggle = (k) => setExpanded(e => ({ ...e, [k]: !e[k] }));

  const levelCounts = { HIGH: 0, MED: 0, LOW: 0 };
  (data.alerts || []).forEach(a => { levelCounts[a.alert_level]++; });

  const ModPill = ({ m }) => (
    <span style={{ fontFamily:"var(--fm)", fontSize:10, padding:"2px 6px",
      borderRadius:8, background:modColor(m)+"20", color:modColor(m),
      border:"1px solid "+modColor(m)+"30", whiteSpace:"nowrap" }}>
      {humanMod(m)}
    </span>
  );

  return (
    <div style={{ padding:"0 12px" }}>
      {/* Header strip */}
      <div style={{ display:"flex", gap:10, marginBottom:14 }}>
        {[
          {label:"NEW DRUG TRIALS", value:data.total_new_drug, tone:color.accent},
          {label:"MATCHED TO CLIENT", value:data.matched_trials, tone:"#22C55E"},
          {label:"UNMATCHED", value:data.unmatched_trials, tone:"var(--muted)"},
          {label:"CLIENT CORPUS", value:(data.meta?.client_corpus_size || 0).toLocaleString(), tone:"var(--muted)"},
        ].map((k, i) => (
          <div key={i} style={{ flex:1, background:"var(--surf2)",
            border:"1px solid "+color.accent+"22", borderRadius:8,
            padding:"12px 14px" }}>
            <div style={{ fontFamily:"var(--fm)", fontSize:9,
              color:"var(--muted)", letterSpacing:"0.14em" }}>
              {k.label}
            </div>
            <div style={{ fontFamily:"var(--fh)", fontSize:22, fontWeight:700,
              color:k.tone, marginTop:2 }}>{k.value}</div>
          </div>
        ))}
      </div>

      {/* Filter strip */}
      <div style={{ display:"flex", alignItems:"center", gap:10,
        marginBottom:10, fontFamily:"var(--fm)", fontSize:10,
        color:"var(--muted)", letterSpacing:"0.06em" }}>
        <span>PRIORITY</span>
        {["HIGH","MED","LOW"].map(l => {
          const p = PRIORITY_CFG?.[l] || {};
          return (
            <span key={l} style={{ display:"inline-flex", gap:4, alignItems:"center" }}>
              <span style={{ width:8, height:8, borderRadius:2,
                background:p.color, display:"inline-block" }}/>
              {l} ({levelCounts[l]})
            </span>
          );
        })}
        <span style={{ color:"var(--dim)" }}>|</span>
        <span>MATCH CONFIDENCE</span>
        {["high","medium","low"].map(c => {
          const active = confFilter === c;
          return (
            <span key={c} onClick={() => setConfFilter(active ? null : c)}
              style={{ cursor:"pointer", padding:"2px 8px", borderRadius:10,
                background: active ? WQ2_TIER_COLOR[c]+"30" : WQ2_TIER_COLOR[c]+"14",
                border:"1px solid "+WQ2_TIER_COLOR[c]+(active?"60":"30"),
                color: active ? "var(--text)" : WQ2_TIER_COLOR[c],
                fontWeight: active ? 600 : 500 }}>
              {c}
            </span>
          );
        })}
      </div>

      {/* Alert cards */}
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr",
        gap:12 }}>
        {alerts.map(a => {
          const p = PRIORITY_CFG?.[a.alert_level] || {};
          const tierHue = WQ2_TIER_COLOR[a.match_confidence] || "#64748B";
          const isOpen = !!expanded[a.client_name];
          return (
            <div key={a.client_name} style={{ background:"var(--surf2)",
              border:"1px solid "+p.border, borderRadius:8,
              padding:"14px 16px", display:"flex",
              flexDirection:"column", gap:8 }}>
              {/* Header row */}
              <div style={{ display:"flex", alignItems:"flex-start",
                gap:10, justifyContent:"space-between" }}>
                <div style={{ flex:1, minWidth:0 }}>
                  <div style={{ display:"flex", alignItems:"center",
                    gap:6, flexWrap:"wrap" }}>
                    <div style={{ fontFamily:"var(--fb)", fontSize:14,
                      fontWeight:600, color:"var(--text)" }}>
                      {a.client_name}
                    </div>
                    {a.client_country && (
                      <span style={{ fontFamily:"var(--fm)", fontSize:9,
                        color:"var(--muted)", padding:"1px 5px",
                        borderRadius:4, background:"var(--surf3)" }}>
                        {a.client_country}
                      </span>
                    )}
                    <span style={{ fontFamily:"var(--fm)", fontSize:9,
                      color: tierHue, padding:"1px 5px", borderRadius:4,
                      background: tierHue+"18",
                      border:"1px solid "+tierHue+"30" }}>
                      {a.match_confidence} match
                    </span>
                  </div>
                  {a.client_name_raw && a.client_name_raw !== a.client_name && (
                    <div style={{ fontFamily:"var(--fm)", fontSize:10,
                      color:"var(--muted)", marginTop:3 }}
                      title="Raw MDM entry (exact string from storage/List of MDM or Sponsor Codes.xlsx)">
                      MDM entry: <span style={{ color:"var(--text)" }}>
                        {a.client_name_raw}
                      </span>
                    </div>
                  )}
                  {a.mdm && (
                    <div style={{ fontFamily:"var(--fm)", fontSize:10,
                      color:"var(--dim)", marginTop:3 }}>
                      MDM {a.mdm}
                      {a.matched_sponsor !== a.client_name && (
                        <> · CT.gov: {a.matched_sponsor}</>
                      )}
                    </div>
                  )}
                </div>
                <span style={{ fontFamily:"var(--fm)", fontSize:10,
                  fontWeight:600, padding:"3px 10px", borderRadius:10,
                  color:p.color, background:p.bg,
                  border:"1px solid "+p.border, letterSpacing:"0.08em",
                  whiteSpace:"nowrap" }}>
                  {a.alert_level} · {a.priority_score}
                </span>
              </div>

              {/* Stat bar */}
              <div style={{ display:"flex", gap:8, alignItems:"center",
                fontFamily:"var(--fm)", fontSize:11 }}>
                <span style={{ color:"var(--text)", fontWeight:600 }}>
                  {a.new_trial_count} new trials
                </span>
                <span style={{ color:"var(--muted)" }}>·</span>
                <span style={{ color:"var(--muted)" }}>
                  top phase {a.top_phase || "-"}
                </span>
              </div>

              {/* Modality pills */}
              <div style={{ display:"flex", gap:4, flexWrap:"wrap" }}>
                {(a.top_modalities || []).slice(0, 5).map(m => (
                  <ModPill key={m} m={m}/>
                ))}
              </div>

              {/* Alert reasons */}
              {a.alert_reasons && a.alert_reasons.length > 0 && (
                <div style={{ display:"flex", gap:4, flexWrap:"wrap" }}>
                  {a.alert_reasons.map((r, i) => (
                    <span key={i} style={{ fontFamily:"var(--fm)",
                      fontSize:10, padding:"2px 7px", borderRadius:10,
                      background:"#EF444418", color:"#F87171",
                      border:"1px solid #EF444430" }}>
                      🔥 {r}
                    </span>
                  ))}
                </div>
              )}

              {/* Expand/collapse trial list */}
              <button onClick={() => toggle(a.client_name)}
                style={{ marginTop:4, background:"transparent",
                  border:"1px solid var(--border2)", color:"var(--muted)",
                  borderRadius:4, padding:"5px 10px",
                  fontFamily:"var(--fm)", fontSize:10,
                  letterSpacing:"0.10em", cursor:"pointer",
                  display:"flex", alignItems:"center",
                  justifyContent:"center", gap:6 }}>
                <span style={{ transition:"transform 0.15s",
                  display:"inline-block",
                  transform: isOpen ? "rotate(180deg)" : "none" }}>▾</span>
                {isOpen ? "HIDE" : "VIEW"} TRIALS ({a.trials.length})
              </button>

              {isOpen && (
                <div style={{ marginTop:4, display:"flex",
                  flexDirection:"column", gap:4, maxHeight:260,
                  overflowY:"auto" }}>
                  {a.trials.map(t => (
                    <a key={t.nct_id} href={t.source_url} target="_blank"
                       rel="noreferrer"
                       style={{ display:"block", padding:"6px 10px",
                         background:"var(--surf3)", borderRadius:4,
                         textDecoration:"none", borderLeft:"2px solid "+p.color }}>
                      <div style={{ display:"flex", gap:6, alignItems:"center",
                        flexWrap:"wrap" }}>
                        <span style={{ fontFamily:"var(--fm)", fontSize:10,
                          color:"var(--cyan)" }}>{t.nct_id}</span>
                        {t.modality && <ModPill m={t.modality}/>}
                        {t.phase && (
                          <span style={{ fontFamily:"var(--fm)", fontSize:9,
                            color:"var(--muted)" }}>{t.phase}</span>
                        )}
                        {t.therapeutic_area && (
                          <span style={{ fontFamily:"var(--fm)", fontSize:9,
                            color:"var(--muted)" }}>
                            · {t.therapeutic_area}
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize:11, color:"var(--text)",
                        marginTop:3, lineHeight:1.3 }}>
                        {t.title}
                      </div>
                    </a>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {alerts.length === 0 && (
        <div style={{ padding:"24px", textAlign:"center",
          fontFamily:"var(--fm)", fontSize:11, color:"var(--muted)" }}>
          No clients match the current confidence filter.
        </div>
      )}
    </div>
  );
}
