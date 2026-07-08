// -----------------------------------------------------------------------
// viz/ops_aw1.jsx
// Operations / aw4 (ANZCTR) -- Pipeline Health & Classifier Confidence
//
// Data source : ALEXIS_DATA.aw4  (dict from analytics/ops_aw1.py)
// Globals used from host: modColor, humanMod
// Extra keys vs cw4: counts.foreign_drug, counts.fih_active,
//                    foreign_country_distribution
// -----------------------------------------------------------------------

function AW4AnzctrPipelineHealth({ data, color }) {
  if (!data || data.available === false) {
    return (
      <div style={{ padding:"24px 16px", fontFamily:"var(--fm)",
        fontSize:12, color:"var(--muted)", textAlign:"center" }}>
        No ANZCTR pipeline data available.
      </div>
    );
  }

  const { freshness, counts, classifier_overrides,
          modality_distribution, ta_distribution,
          sample_low_confidence, foreign_country_distribution } = data;

  const freshTone = (days) =>
      days == null ? "var(--muted)"
    : days <=  7 ? "#22C55E"
    : days <= 14 ? "#F59E0B"
    : "#EF4444";

  const Tile = ({ title, value, sub, subTone }) => (
    <div style={{ background:"var(--surf2)",
      border:`1px solid ${color.accent}22`, borderRadius:10,
      padding:"16px 18px", display:"flex", flexDirection:"column",
      minHeight:96 }}>
      <div style={{ fontFamily:"var(--fm)", fontSize:9,
        letterSpacing:"0.14em", color:color.mid,
        textTransform:"uppercase", marginBottom:8 }}>
        {title}
      </div>
      <div style={{ fontFamily:"var(--fh)", fontSize:26,
        fontWeight:700, color:"var(--text)", lineHeight:1.05 }}>
        {value}
      </div>
      {sub && (
        <div style={{ fontFamily:"var(--fm)", fontSize:11,
          color: subTone || "var(--muted)", marginTop:4 }}>
          {sub}
        </div>
      )}
    </div>
  );

  const modTotal = Object.values(modality_distribution || {})
    .reduce((a, b) => a + b, 0) || 1;
  const taTotal  = Object.values(ta_distribution || {})
    .reduce((a, b) => a + b, 0) || 1;
  const ctryTotal = (foreign_country_distribution || [])
    .reduce((a, r) => a + (r.count || 0), 0) || 1;

  const ModRow = ({ name, n, total }) => {
    const pct = (n / total) * 100;
    const hue = modColor(name);
    return (
      <div style={{ display:"flex", alignItems:"center", gap:10,
        padding:"5px 0" }}>
        <div style={{ width:140, display:"flex", alignItems:"center", gap:6 }}>
          <span style={{ width:8, height:8, borderRadius:2,
            background:hue, display:"inline-block" }}/>
          <span style={{ fontFamily:"var(--fb)", fontSize:12,
            color:"var(--text)" }}>{humanMod(name)}</span>
        </div>
        <div style={{ flex:1, height:4, background:"var(--border)",
          borderRadius:2 }}>
          <div style={{ width:`${Math.min(100, pct)}%`, height:"100%",
            background:hue, borderRadius:2, opacity:0.7 }}/>
        </div>
        <div style={{ fontFamily:"var(--fm)", fontSize:11,
          color:"var(--muted)", minWidth:36, textAlign:"right" }}>
          {pct < 1 ? "<1%" : `${pct.toFixed(0)}%`}
        </div>
        <div style={{ fontFamily:"var(--fm)", fontSize:12,
          color:"var(--text)", minWidth:48, textAlign:"right" }}>
          {n.toLocaleString()}
        </div>
      </div>
    );
  };

  const TaRow = ({ name, n, total }) => {
    const pct = (n / total) * 100;
    return (
      <div style={{ display:"flex", alignItems:"center", gap:10,
        padding:"5px 0" }}>
        <div style={{ width:200, fontFamily:"var(--fb)", fontSize:12,
          color:"var(--text)", whiteSpace:"nowrap",
          overflow:"hidden", textOverflow:"ellipsis" }} title={name}>
          {name}
        </div>
        <div style={{ flex:1, height:4, background:"var(--border)",
          borderRadius:2 }}>
          <div style={{ width:`${Math.min(100, pct)}%`, height:"100%",
            background:color.accent, borderRadius:2, opacity:0.65 }}/>
        </div>
        <div style={{ fontFamily:"var(--fm)", fontSize:11,
          color:"var(--muted)", minWidth:36, textAlign:"right" }}>
          {pct < 1 ? "<1%" : `${pct.toFixed(0)}%`}
        </div>
        <div style={{ fontFamily:"var(--fm)", fontSize:12,
          color:"var(--text)", minWidth:48, textAlign:"right" }}>
          {n.toLocaleString()}
        </div>
      </div>
    );
  };

  const CtryRow = ({ name, n, total }) => {
    const pct = (n / total) * 100;
    return (
      <div style={{ display:"flex", alignItems:"center", gap:10,
        padding:"5px 0" }}>
        <div style={{ width:160, fontFamily:"var(--fb)", fontSize:12,
          color:"var(--text)", whiteSpace:"nowrap",
          overflow:"hidden", textOverflow:"ellipsis" }} title={name}>
          {name}
        </div>
        <div style={{ flex:1, height:4, background:"var(--border)",
          borderRadius:2 }}>
          <div style={{ width:`${Math.min(100, pct)}%`, height:"100%",
            background:color.mid, borderRadius:2, opacity:0.6 }}/>
        </div>
        <div style={{ fontFamily:"var(--fm)", fontSize:11,
          color:"var(--muted)", minWidth:36, textAlign:"right" }}>
          {pct < 1 ? "<1%" : `${pct.toFixed(0)}%`}
        </div>
        <div style={{ fontFamily:"var(--fm)", fontSize:12,
          color:"var(--text)", minWidth:48, textAlign:"right" }}>
          {n.toLocaleString()}
        </div>
      </div>
    );
  };

  return (
    <div>
      {/* KPI tiles - base counts */}
      <div style={{ display:"grid",
        gridTemplateColumns:"repeat(6, minmax(130px, 1fr))",
        gap:12, padding:"0 12px 14px" }}>
        <Tile title="SNAPSHOT AS_OF" value={freshness.current_as_of || "-"}
          sub={freshness.days_since != null ? `${freshness.days_since}d ago` : null}
          subTone={freshTone(freshness.days_since)}/>
        <Tile title="SCRAPE LAST RUN"
          value={freshness.scrape_mtime ? freshness.scrape_mtime.slice(0,10) : "-"}
          sub={freshness.scrape_age_days != null ? `${freshness.scrape_age_days}d ago` : null}
          subTone={freshTone(freshness.scrape_age_days)}/>
        <Tile title="CORPUS SIZE" value={counts.current_total.toLocaleString()}
          sub={`${counts.current_drug.toLocaleString()} drug (${(counts.drug_share*100).toFixed(1)}%)`}/>
        <Tile title="LOW-CONF BIO"
          value={classifier_overrides.low_confidence_biologic}
          sub="flagged for review"
          subTone={classifier_overrides.low_confidence_biologic > 50
                   ? "#F59E0B" : "var(--muted)"}/>
        <Tile title="GT REGEX OVERRIDE"
          value={classifier_overrides.gene_therapy_override}
          sub="regex upgraded to gene_therapy"/>
        <Tile title="RADIO REJECTED"
          value={classifier_overrides.radiopharma_rejected}
          sub="downgraded to non_drug"/>
      </div>

      {/* Extra ANZCTR-specific count tiles */}
      <div style={{ display:"grid",
        gridTemplateColumns:"repeat(2, minmax(130px, 220px))",
        gap:12, padding:"0 12px 14px" }}>
        <Tile title="FOREIGN DRUG TRIALS"
          value={(counts.foreign_drug ?? 0).toLocaleString()}
          sub="drug trials with non-AU sponsor"/>
        <Tile title="FIH ACTIVE"
          value={(counts.fih_active ?? 0).toLocaleString()}
          sub="Phase 1 foreign trials recruiting"/>
      </div>

      {/* Two-column distribution tables */}
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr",
        gap:14, padding:"0 12px" }}>
        <div style={{ background:"var(--surf2)",
          border:"1px solid var(--border)", borderRadius:10,
          padding:"14px 16px" }}>
          <div style={{ fontFamily:"var(--fm)", fontSize:9,
            letterSpacing:"0.14em", color:color.mid,
            textTransform:"uppercase", marginBottom:10 }}>
            Drug modality distribution
          </div>
          {Object.entries(modality_distribution || {}).slice(0, 12).map(([m, n]) => (
            <ModRow key={m} name={m} n={n} total={modTotal}/>
          ))}
        </div>
        <div style={{ background:"var(--surf2)",
          border:"1px solid var(--border)", borderRadius:10,
          padding:"14px 16px" }}>
          <div style={{ fontFamily:"var(--fm)", fontSize:9,
            letterSpacing:"0.14em", color:color.mid,
            textTransform:"uppercase", marginBottom:10 }}>
            Therapeutic area distribution (top 12)
          </div>
          {Object.entries(ta_distribution || {}).slice(0, 12).map(([ta, n]) => (
            <TaRow key={ta} name={ta} n={n} total={taTotal}/>
          ))}
        </div>
      </div>

      {/* Top foreign sponsor countries */}
      {foreign_country_distribution && foreign_country_distribution.length > 0 && (
        <div style={{ margin:"14px 12px 0", padding:"14px 16px",
          background:"var(--surf2)", border:"1px solid var(--border)",
          borderRadius:10 }}>
          <div style={{ fontFamily:"var(--fm)", fontSize:9,
            letterSpacing:"0.14em", color:color.mid,
            textTransform:"uppercase", marginBottom:10 }}>
            Top foreign sponsor countries
          </div>
          {foreign_country_distribution.slice(0, 15).map(row => (
            <CtryRow key={row.country} name={row.country}
              n={row.count} total={ctryTotal}/>
          ))}
        </div>
      )}

      {/* Sample low-confidence biologic trials */}
      {sample_low_confidence && sample_low_confidence.length > 0 && (
        <div style={{ margin:"14px 12px 0", padding:"14px 16px",
          background:"var(--surf2)", border:"1px solid var(--border)",
          borderRadius:10 }}>
          <div style={{ fontFamily:"var(--fm)", fontSize:9,
            letterSpacing:"0.14em", color:color.mid,
            textTransform:"uppercase", marginBottom:10 }}>
            Low-confidence biologic trials ({sample_low_confidence.length} shown)
          </div>
          <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
            {sample_low_confidence.map(t => (
              <div key={t.nct_id} style={{ padding:"8px 10px",
                background:"var(--surf3)", borderRadius:6,
                border:"1px solid var(--border)" }}>
                <div style={{ display:"flex", alignItems:"center",
                  gap:8, marginBottom:3 }}>
                  {t.source_url
                    ? <a href={t.source_url} target="_blank" rel="noreferrer"
                        style={{ color:"var(--cyan)", fontFamily:"var(--fm)",
                          fontSize:11, textDecoration:"none" }}>
                        {t.nct_id}
                      </a>
                    : <span style={{ fontFamily:"var(--fm)",
                        fontSize:11 }}>{t.nct_id}</span>}
                  {t.modality && (
                    <span style={{ fontFamily:"var(--fm)", fontSize:10,
                      padding:"1px 6px", borderRadius:8,
                      background:modColor(t.modality)+"20",
                      color:modColor(t.modality),
                      border:`1px solid ${modColor(t.modality)}30` }}>
                      {humanMod(t.modality)}
                    </span>
                  )}
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
            ))}
          </div>
        </div>
      )}

      <div style={{ margin:"14px 12px 0", fontFamily:"var(--fm)", fontSize:9,
        color:"var(--dim)", letterSpacing:"0.06em" }}>
        All ANZCTR classifications are ML-derived. Thresholds: biologic
        confidence {"<"} 0.75 is flagged; gene_therapy regex overrides ML
        label; radiopharmaceutical reverts to non_drug when intervention
        text lacks isotope markers.
      </div>
    </div>
  );
}
