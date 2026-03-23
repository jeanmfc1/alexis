// ─────────────────────────────────────────────────────────────────────────
// viz/mk_wq1.jsx
// Marketing / wq1 — Social-Ready Stat Cards
//
// Data source : ALEXIS_DATA.wq4  (list of 4 card objects)
// Injected by : analytics/mk_wq1.py → wq4_social_stat_cards()
//
// Each card: { id, title, value, sub, detail:[{label,value,pct?}], note }
// Designed to be screenshot-ready: large value, clean breakdown rows.
// ─────────────────────────────────────────────────────────────────────────

function WQ4StatCards({ data, color }) {
  if (!data?.length) return (
    <div style={{ fontFamily:"var(--fm)", fontSize:12, color:"var(--muted)",
      padding:"20px 0" }}>
      No summary data available. Verify snapshot was built with summary_v2.py.
    </div>
  );

  // Card 2 (Top TA) has a long string value — shrink font for it
  const valueFontSize = c => c.id === "mk_wq1_c2" ? 18 : 32;

  return (
    <div style={{ display:"grid", gridTemplateColumns:"repeat(2,1fr)", gap:14 }}>
      {data.map(card => (
        <div key={card.id}
          style={{ background:"var(--surf2)", borderRadius:10,
            border:`1px solid ${color.accent}22`,
            padding:"20px 22px", display:"flex", flexDirection:"column", gap:12 }}>

          {/* Card header */}
          <div>
            <div style={{ fontFamily:"var(--fm)", fontSize:9,
              color:color.mid, letterSpacing:"0.16em",
              textTransform:"uppercase", marginBottom:6 }}>
              {card.title}
            </div>
            <div style={{ fontFamily:"var(--fh)", fontSize:valueFontSize(card),
              fontWeight:700, color:"var(--text)", lineHeight:1.1,
              letterSpacing:"0.01em" }}>
              {card.value}
            </div>
            <div style={{ fontFamily:"var(--fm)", fontSize:11,
              color:"var(--muted)", marginTop:4 }}>
              {card.sub}
            </div>
          </div>

          {/* Detail rows with mini bar */}
          {card.detail?.length > 0 && (
            <div style={{ borderTop:`1px solid ${color.accent}18`,
              paddingTop:10, display:"flex", flexDirection:"column", gap:6 }}>
              {card.detail.map((row, i) => {
                const maxVal = Math.max(...card.detail.map(r => r.value));
                const barPct = maxVal > 0 ? (row.value / maxVal) * 100 : 0;
                return (
                  <div key={i}>
                    <div style={{ display:"flex", justifyContent:"space-between",
                      marginBottom:3 }}>
                      <span style={{ fontFamily:"var(--fm)", fontSize:11,
                        color:"var(--text)" }}>
                        {humanMod(row.label)}
                      </span>
                      <div style={{ display:"flex", gap:8, alignItems:"center" }}>
                        <span style={{ fontFamily:"var(--fm)", fontSize:11,
                          fontWeight:600, color:"var(--text)" }}>
                          {fmt(row.value)}
                        </span>
                        {row.pct != null && (
                          <span style={{ fontFamily:"var(--fm)", fontSize:10,
                            color:"var(--muted)", minWidth:36, textAlign:"right" }}>
                            {row.pct}%
                          </span>
                        )}
                      </div>
                    </div>
                    {/* Mini bar */}
                    <div style={{ height:3, background:"var(--border)", borderRadius:2 }}>
                      <div style={{ width:`${barPct}%`, height:"100%",
                        background:color.accent, borderRadius:2, opacity:0.6 }} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Note */}
          <div style={{ fontFamily:"var(--fm)", fontSize:9,
            color:"var(--dim)", marginTop:"auto", letterSpacing:"0.06em" }}>
            {card.note}
          </div>
        </div>
      ))}
    </div>
  );
}
