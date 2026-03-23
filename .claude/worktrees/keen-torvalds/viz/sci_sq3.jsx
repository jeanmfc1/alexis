// viz/sci_sq3.jsx
// Scientific / sq9 - Confidence Dashboard (Approach C)
//
// Data source : ALEXIS_DATA.sq9
// Injected by : analytics/sci_sq3.py

const SQ9_TIER_COLORS = {
  high:   "#22C55E",
  medium: "#F59E0B",
  low:    "#EF4444",
};

function ArcGauge({ score, size = 80, label }) {
  const r = (size - 10) / 2;
  const cx = size / 2, cy = size / 2 + 4;
  const startAngle = Math.PI;
  const sweep = Math.PI * Math.min(score, 100) / 100;
  const endAngle = startAngle + sweep;
  const x1 = cx + r * Math.cos(startAngle);
  const y1 = cy + r * Math.sin(startAngle);
  const x2 = cx + r * Math.cos(endAngle);
  const y2 = cy + r * Math.sin(endAngle);
  const large = sweep > Math.PI ? 1 : 0;
  const color = score >= 80 ? "#22C55E" : score >= 60 ? "#F59E0B" : "#EF4444";
  const bgX2 = cx + r * Math.cos(2 * Math.PI);
  const bgY2 = cy + r * Math.sin(2 * Math.PI);
  return (
    <svg width={size} height={size / 2 + 12} style={{ display: "block", margin: "0 auto" }}>
      <path d={`M ${x1} ${y1} A ${r} ${r} 0 1 1 ${bgX2} ${bgY2}`}
        fill="none" stroke="var(--border)" strokeWidth="6" strokeLinecap="round" />
      {score > 0 && (
        <path d={`M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`}
          fill="none" stroke={color} strokeWidth="6" strokeLinecap="round" />
      )}
      <text x={cx} y={cy - 4} textAnchor="middle"
        fontSize="18" fontWeight="700" fontFamily="var(--fh)" fill={color}>
        {score.toFixed(1)}%
      </text>
    </svg>
  );
}

function StackedBar({ segments, total, height = 20 }) {
  if (!total) return null;
  return (
    <div style={{ display: "flex", height, borderRadius: 4, overflow: "hidden",
      background: "var(--surf2)" }}>
      {segments.map((seg, i) => {
        const pct = (seg.value / total) * 100;
        if (pct < 0.3) return null;
        return (
          <div key={i} title={`${seg.label}: ${fmt(seg.value)} (${pct.toFixed(1)}%)`}
            style={{ width: `${pct}%`, background: seg.color, minWidth: pct > 0 ? 2 : 0,
              transition: "width 0.3s" }} />
        );
      })}
    </div>
  );
}

function StackedBarLegend({ segments, total }) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 16px", marginTop: 8 }}>
      {segments.map((seg, i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", gap: 6,
          fontFamily: "var(--fm)", fontSize: 10, color: "var(--muted)" }}>
          <span style={{ width: 8, height: 8, borderRadius: 2, background: seg.color,
            display: "inline-block", flexShrink: 0 }} />
          <span>{seg.label}</span>
          <span style={{ color: "var(--text)", fontWeight: 500 }}>{fmt(seg.value)}</span>
          <span>({(seg.value / total * 100).toFixed(1)}%)</span>
        </div>
      ))}
    </div>
  );
}

function SectionLabel({ label }) {
  return (
    <div style={{ fontFamily: "var(--fm)", fontSize: 10, letterSpacing: "0.12em",
      color: "var(--dim)", marginTop: 20, marginBottom: 8, textTransform: "uppercase" }}>
      {label}
    </div>
  );
}

function SQ9ConfidenceDashboard({ data, color }) {
  const [sortCol, setSortCol] = React.useState("impact_score");
  const [sortDir, setSortDir] = React.useState(-1);

  if (!data?.available) {
    return (
      <div style={{ fontFamily: "var(--fm)", fontSize: 11, color: "var(--muted)",
        padding: "20px 0" }}>
        No data — master DB not loaded or contains no drug trials.
      </div>
    );
  }

  const { modality_confidence: mc, ta_confidence: tc,
          data_coverage: dc, flag_breakdown: flags,
          per_ta: perTa, improvement_priorities: priorities } = data;

  const sortedPriorities = [...priorities].sort((a, b) => {
    const va = a[sortCol], vb = b[sortCol];
    if (typeof va === "number") return (va - vb) * sortDir;
    return String(va).localeCompare(String(vb)) * sortDir;
  });

  const toggleSort = col => {
    if (sortCol === col) setSortDir(d => d * -1);
    else { setSortCol(col); setSortDir(-1); }
  };

  const thStyle = { cursor: "pointer", padding: "6px 8px", textAlign: "right",
    fontFamily: "var(--fm)", fontSize: 9, letterSpacing: "0.1em",
    color: "var(--muted)", borderBottom: "1px solid var(--border)",
    userSelect: "none", whiteSpace: "nowrap" };

  const tdStyle = { padding: "6px 8px", textAlign: "right",
    fontFamily: "var(--fm)", fontSize: 11, color: "var(--text)",
    borderBottom: "1px solid var(--border)" };

  const flagEntries = Object.entries(flags || {}).sort((a, b) => b[1] - a[1]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>

      {/* Section 1: Confidence Gauges + Total */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
        <div style={{ background: "var(--surf2)", borderRadius: 8, padding: "16px 12px", textAlign: "center" }}>
          <div style={{ fontFamily: "var(--fm)", fontSize: 9, letterSpacing: "0.12em", color: "var(--dim)", marginBottom: 8, textTransform: "uppercase" }}>Modality Confidence</div>
          <ArcGauge score={mc.score} />
          <div style={{ fontFamily: "var(--fm)", fontSize: 9, color: "var(--muted)", marginTop: 4 }}>
            {fmt(mc.high_count)} high / {fmt(mc.medium_count)} med of {fmt(mc.denominator)}
          </div>
        </div>
        <div style={{ background: "var(--surf2)", borderRadius: 8, padding: "16px 12px", textAlign: "center" }}>
          <div style={{ fontFamily: "var(--fm)", fontSize: 9, letterSpacing: "0.12em", color: "var(--dim)", marginBottom: 8, textTransform: "uppercase" }}>TA Confidence</div>
          <ArcGauge score={tc.score} />
          <div style={{ fontFamily: "var(--fm)", fontSize: 9, color: "var(--muted)", marginTop: 4 }}>
            {fmt(tc.high_count)} high / {fmt(tc.low_count)} low of {fmt(tc.denominator)}
          </div>
        </div>
        <div style={{ background: "var(--surf2)", borderRadius: 8, padding: "16px 12px", textAlign: "center", display: "flex", flexDirection: "column", justifyContent: "center" }}>
          <div style={{ fontFamily: "var(--fm)", fontSize: 9, letterSpacing: "0.12em", color: "var(--dim)", marginBottom: 8, textTransform: "uppercase" }}>Total Drug Trials</div>
          <div style={{ fontFamily: "var(--fh)", fontSize: 28, fontWeight: 700, color: color.accent }}>{fmt(dc.total_drug_trials)}</div>
          <div style={{ fontFamily: "var(--fm)", fontSize: 9, color: "var(--muted)", marginTop: 4 }}>in master DB</div>
        </div>
      </div>

      {/* Section 2: Data Coverage */}
      <SectionLabel label="MeSH Data Coverage" />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <div>
          <div style={{ fontFamily: "var(--fm)", fontSize: 9, color: "var(--muted)", marginBottom: 4 }}>MODALITY — INTERVENTION MeSH</div>
          <StackedBar height={16} total={dc.total_drug_trials} segments={[
            { label: "MeSH available", value: dc.modality_mesh_available, color: SQ9_TIER_COLORS.high },
            { label: "No MeSH", value: dc.total_drug_trials - dc.modality_mesh_available, color: "var(--surf3)" },
          ]} />
          <div style={{ fontFamily: "var(--fm)", fontSize: 10, color: "var(--muted)", marginTop: 4 }}>
            {dc.modality_mesh_coverage_pct}% of drug trials have intervention MeSH terms
          </div>
        </div>
        <div>
          <div style={{ fontFamily: "var(--fm)", fontSize: 9, color: "var(--muted)", marginBottom: 4 }}>TA — CONDITION MeSH</div>
          <StackedBar height={16} total={dc.total_drug_trials} segments={[
            { label: "MeSH available", value: dc.ta_mesh_available, color: SQ9_TIER_COLORS.high },
            { label: "No MeSH", value: dc.total_drug_trials - dc.ta_mesh_available, color: "var(--surf3)" },
          ]} />
          <div style={{ fontFamily: "var(--fm)", fontSize: 10, color: "var(--muted)", marginTop: 4 }}>
            {dc.ta_mesh_coverage_pct}% of drug trials have condition MeSH terms
          </div>
        </div>
      </div>

      {/* Section 3: Modality Confidence Breakdown */}
      <SectionLabel label="Modality Confidence Breakdown" />
      <StackedBar height={22} total={mc.denominator} segments={[
        { label: "High (MeSH tree)", value: mc.high_count, color: SQ9_TIER_COLORS.high },
        { label: "Medium (text / type)", value: mc.medium_count, color: SQ9_TIER_COLORS.medium },
      ]} />
      <StackedBarLegend total={mc.denominator} segments={[
        { label: "High (MeSH tree)", value: mc.high_count, color: SQ9_TIER_COLORS.high },
        { label: "Medium (text / type)", value: mc.medium_count, color: SQ9_TIER_COLORS.medium },
      ]} />

      {/* Section 4: TA Confidence Breakdown */}
      <SectionLabel label="TA Confidence Breakdown" />
      <StackedBar height={22} total={tc.denominator} segments={[
        { label: "High (MeSH evidence)", value: tc.high_count, color: SQ9_TIER_COLORS.high },
        { label: "Low (text / fallback)", value: tc.low_count, color: SQ9_TIER_COLORS.low },
      ]} />
      <StackedBarLegend total={tc.denominator} segments={[
        { label: "High (MeSH evidence)", value: tc.high_count, color: SQ9_TIER_COLORS.high },
        { label: "Low (text / fallback)", value: tc.low_count, color: SQ9_TIER_COLORS.low },
      ]} />

      {/* Section 5: Flag Breakdown (why MeSH failed) */}
      {flagEntries.length > 0 && (
        <>
          <SectionLabel label="MeSH Non-Resolution Reasons" />
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {flagEntries.map(([flag, count]) => {
              const label = flag.replace("mesh_reason:", "").replace(/_/g, " ")
                .replace(/\b\w/g, c => c.toUpperCase());
              return (
                <div key={flag} style={{ display: "grid", gridTemplateColumns: "1fr 80px",
                  alignItems: "center", gap: 8, padding: "3px 0" }}>
                  <div style={{ fontFamily: "var(--fm)", fontSize: 11, color: "var(--text)" }}>{label}</div>
                  <div style={{ fontFamily: "var(--fm)", fontSize: 11, fontWeight: 600,
                    color: SQ9_TIER_COLORS.medium, textAlign: "right" }}>{fmt(count)}</div>
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* Section 6: Per-TA Confidence */}
      <SectionLabel label="Confidence by Therapeutic Area" />
      <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
        <div style={{ display: "grid", gridTemplateColumns: "180px 1fr 52px 52px",
          gap: 8, padding: "3px 0" }}>
          <div style={{ fontFamily: "var(--fm)", fontSize: 9, color: "var(--dim)", letterSpacing: "0.1em" }}>TA</div>
          <div style={{ fontFamily: "var(--fm)", fontSize: 9, color: "var(--dim)", letterSpacing: "0.1em" }}>MeSH DATA</div>
          <div style={{ fontFamily: "var(--fm)", fontSize: 9, color: "var(--dim)", letterSpacing: "0.1em", textAlign: "right" }}>MOD</div>
          <div style={{ fontFamily: "var(--fm)", fontSize: 9, color: "var(--dim)", letterSpacing: "0.1em", textAlign: "right" }}>TA</div>
        </div>
        {perTa.map(row => {
          const modColor_ = row.mod_high_pct >= 80 ? SQ9_TIER_COLORS.high
            : row.mod_high_pct >= 60 ? SQ9_TIER_COLORS.medium : SQ9_TIER_COLORS.low;
          const taColor = row.ta_high_pct >= 80 ? SQ9_TIER_COLORS.high
            : row.ta_high_pct >= 60 ? SQ9_TIER_COLORS.medium : SQ9_TIER_COLORS.low;
          return (
            <div key={row.ta} style={{ display: "grid",
              gridTemplateColumns: "180px 1fr 52px 52px", alignItems: "center", gap: 8,
              padding: "3px 0" }}>
              <div style={{ fontFamily: "var(--fb)", fontSize: 11, color: "var(--text)",
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                title={row.ta}>
                {row.ta}
              </div>
              <div style={{ display: "flex", height: 12, borderRadius: 3, overflow: "hidden",
                background: "var(--surf2)" }}>
                <div style={{ width: `${row.mod_mesh_pct}%`, background: SQ9_TIER_COLORS.high, opacity: 0.5 }} />
              </div>
              <div style={{ fontFamily: "var(--fm)", fontSize: 10, fontWeight: 600,
                color: modColor_, textAlign: "right" }}>
                {row.mod_high_pct}%
              </div>
              <div style={{ fontFamily: "var(--fm)", fontSize: 10, fontWeight: 600,
                color: taColor, textAlign: "right" }}>
                {row.ta_high_pct}%
              </div>
            </div>
          );
        })}
      </div>

      {/* Section 7: Improvement Priority Table */}
      <SectionLabel label="Improvement Priorities" />
      <div style={{ overflowX: "auto", maxHeight: 420, overflowY: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", tableLayout: "fixed" }}>
          <thead>
            <tr>
              {[
                { key: "ta",       label: "TA",       align: "left",  w: "22%" },
                { key: "modality", label: "MODALITY", align: "left",  w: "18%" },
                { key: "total",    label: "TOTAL",    align: "right", w: "10%" },
                { key: "low_count", label: "LOW",     align: "right", w: "10%" },
                { key: "pct_low",  label: "% LOW",    align: "right", w: "10%" },
                { key: "impact_score", label: "IMPACT", align: "right", w: "12%" },
                { key: "dominant_issue", label: "ISSUE", align: "left", w: "18%" },
              ].map(col => (
                <th key={col.key} onClick={() => toggleSort(col.key)}
                  style={{ ...thStyle, textAlign: col.align, width: col.w }}>
                  {col.label}
                  {sortCol === col.key ? (sortDir > 0 ? " ▲" : " ▼") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sortedPriorities.map((row, i) => (
              <tr key={i} style={{ background: i % 2 === 0 ? "transparent" : "var(--surf2)" }}>
                <td style={{ ...tdStyle, textAlign: "left", overflow: "hidden",
                  textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={row.ta}>
                  {row.ta}
                </td>
                <td style={{ ...tdStyle, textAlign: "left" }}>
                  <span style={{ display: "inline-block", padding: "1px 6px", borderRadius: 3,
                    fontSize: 10, fontFamily: "var(--fm)",
                    background: modColor(row.modality) + "22",
                    color: modColor(row.modality), border: `1px solid ${modColor(row.modality)}33` }}>
                    {humanMod(row.modality)}
                  </span>
                </td>
                <td style={tdStyle}>{fmt(row.total)}</td>
                <td style={{ ...tdStyle, color: SQ9_TIER_COLORS.low }}>{fmt(row.low_count)}</td>
                <td style={tdStyle}>
                  <span style={{ background: SQ9_TIER_COLORS.low + (Math.round(row.pct_low / 100 * 40 + 10).toString(16).padStart(2, "0")),
                    padding: "1px 4px", borderRadius: 3 }}>
                    {row.pct_low}%
                  </span>
                </td>
                <td style={{ ...tdStyle, fontWeight: 600, color: color.accent }}>
                  {row.impact_score.toFixed(2)}
                </td>
                <td style={{ ...tdStyle, textAlign: "left", fontSize: 10, color: "var(--muted)",
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                  title={row.dominant_issue}>
                  {row.dominant_issue}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
