import { useState } from "react";

const teams = ["BD", "Marketing", "Scientific", "Operations"];

const teamColors = {
  BD: { accent: "#3B82F6", light: "#DBEAFE", mid: "#93C5FD" },
  Marketing: { accent: "#8B5CF6", light: "#EDE9FE", mid: "#C4B5FD" },
  Scientific: { accent: "#10B981", light: "#D1FAE5", mid: "#6EE7B7" },
  Operations: { accent: "#F59E0B", light: "#FEF3C7", mid: "#FCD34D" },
};

const dashboards = {
  quarterly: {
    label: "Quarterly / Yearly",
    tag: "STRATEGIC",
    tagColor: "#3B82F6",
    icon: "📊",
    source: "Master DB (active universe) — full 39,115 drug trials",
    sourcePath: "storage/snapshots/clinical_trials_v2/active_universe/master_DB.json",
    refreshCadence: "After each AACT monthly archive update or quarterly review cycle",
    purpose: "Where is the market? How big is it? Where is it going? Where should we invest?",
    cards: {
      BD: [
        {
          id: "sq1",
          question: "How large is our total addressable market by modality and phase?",
          answer: "Group all INDUSTRY-sponsored drug trials by modality, then by phase. Each cell = a contract opportunity. Small molecule Phase 3 is high volume; cell/gene Phase 1 is high margin. Sum across the matrix to get total addressable pipeline. Compare quarter-over-quarter to show growth/contraction.",
          dataFields: ["drug_modality", "phase", "sponsor_class", "nct_id (count)"],
          filter: "sponsor_class = INDUSTRY",
          vizType: "Bubble Matrix",
          vizDesc: "Rows = modalities, Columns = phases. Bubble size = trial count. Color = growth vs. prior quarter (green ↑, red ↓). Margin totals on right and bottom. Top-right corner = total addressable number.",
          mockup: "bubble_matrix",
        },
        {
          id: "sq2",
          question: "Who are the top 25 sponsors and what do they run?",
          answer: "Filter to INDUSTRY → group by sponsor_name → rank by trial count. For each sponsor, show their modality mix and TA focus. A sponsor running 80% mAb trials in oncology is a different pitch than one running 60% small molecule across 5 TAs.",
          dataFields: ["sponsor_name", "sponsor_class", "drug_modality", "therapeutic_area", "nct_id (count)"],
          filter: "sponsor_class = INDUSTRY, top 25 by volume",
          vizType: "Ranked Bar + Stacked Modality Breakdown",
          vizDesc: "Horizontal bars ranked by trial count. Each bar is stacked by modality (color-coded). Clicking a bar opens a TA pie for that sponsor. Right column shows YoY change arrow (↑ growing sponsor, ↓ declining).",
          mockup: "ranked_bars",
        },
        {
          id: "sq3",
          question: "Which therapeutic areas are growing or shrinking year-over-year?",
          answer: "Compare master DB snapshots across quarters. Compute % share of drug trials per TA at each snapshot. Oncology at 47% — is it 47% because it grew, or because everything else shrank? Absolute counts + share % together tell the full story.",
          dataFields: ["therapeutic_area", "snapshot_date", "nct_id (count)", "% share"],
          filter: "All drug trials, multi-snapshot comparison",
          vizType: "Area Chart (stacked % or absolute toggle)",
          vizDesc: "Stacked area chart, X = quarter, Y = trial count or % share (toggle). Each color band = a TA. Hover shows exact count and % for that TA at that quarter. Oncology dominates but you can see other TAs expanding or compressing.",
          mockup: "area_chart",
        },
      ],
      Marketing: [
        {
          id: "sq4",
          question: "What is the current modality landscape for thought leadership content?",
          answer: "Master DB → group 39,115 drug trials by modality → compute percentages. This is the single chart that goes on slide 3 of every conference deck: 'X% of active clinical trials test biologics, Y% are small molecules.' Defensible, sourced from ClinicalTrials.gov, updated quarterly.",
          dataFields: ["drug_modality", "nct_id (count)", "% of total"],
          filter: "All drug trials",
          vizType: "Donut Chart with Callout Cards",
          vizDesc: "Large donut, center number = 39,115. Segments = modalities. Around the donut: callout cards for the top 4 modalities showing count, %, and a one-line insight ('mAbs now represent 1 in 6 drug trials'). Designed to be directly screenshot-able for slides.",
          mockup: "donut_callout",
        },
        {
          id: "sq5",
          question: "What TA-specific narratives can we build for targeted campaigns?",
          answer: "For each TA: total trials, modality breakdown, phase distribution, % industry-sponsored, top 5 sponsors. This creates per-TA fact sheets. 'In Rare Disease, 68% of trials are industry-sponsored, gene therapy represents 18% of modalities — 3× the overall average.'",
          dataFields: ["therapeutic_area", "drug_modality", "phase", "sponsor_class", "sponsor_name", "nct_id (count)"],
          filter: "Per therapeutic area",
          vizType: "TA Fact Sheet Grid (exportable cards)",
          vizDesc: "Grid of cards, one per TA. Each card: big trial count number, mini donut (modality), mini horizontal bars (phase distribution), sponsor type split, top 3 sponsor names. Cards exportable as individual PNGs for insertion into TA-specific pitch decks.",
          mockup: "ta_factcards",
        },
        {
          id: "sq6",
          question: "How does our capability map align with market demand?",
          answer: "Map IQVIA BioA service lines to modality categories (manual one-time mapping). Then overlay trial volume per modality against capability strength. Gaps = messaging opportunity ('we're expanding into X'). Strengths = proof points ('we support Y% of the active trial landscape').",
          dataFields: ["drug_modality", "nct_id (count)", "capability_score (manual 1-5)"],
          filter: "All drug trials + manual capability mapping",
          vizType: "Gap Analysis: Side-by-Side Bars",
          vizDesc: "Two bars per modality: left blue = market demand (trial count, normalized), right green = capability score. Visual gap between bars = opportunity or risk. Sorted by gap size descending. A 'sweet spot' highlight for modalities where both are high.",
          mockup: "gap_bars",
        },
      ],
      Scientific: [
        {
          id: "sq7",
          question: "What assay platforms should we invest in for the next 12–24 months?",
          answer: "Phase 1 trials today = Phase 2/3 demand in 1–2 years. Filter to Phase 1, group by modality. Modalities with high Phase 1 counts but low Phase 3 counts = upcoming demand wave. Gene therapy: many Phase 1s, few Phase 3s = method development window is NOW.",
          dataFields: ["drug_modality", "phase", "nct_id (count)"],
          filter: "All drug trials, phase comparison",
          vizType: "Pipeline Horizon Chart",
          vizDesc: "Each modality = a horizontal row. Phase segments fill left to right (P1 → P4). Fat P1 segment with thin P3 = 'INVEST NOW' badge. Thin P1 with fat P3 = 'MATURE, maintain.' Color intensity maps to urgency of capability gap.",
          mockup: "horizon",
        },
        {
          id: "sq8",
          question: "Which TA × modality intersections drive the most bioanalytical complexity?",
          answer: "Cross-tab TA × modality. Oncology × mAb = large-scale LBA demand. Rare Disease × gene therapy = specialized viral vector assays. The heatmap shows where trial volume concentrates, directly mapping to lab staffing and method validation priorities.",
          dataFields: ["therapeutic_area", "drug_modality", "nct_id (count)"],
          filter: "All drug trials",
          vizType: "Heatmap Matrix",
          vizDesc: "Rows = TAs (sorted by volume). Columns = modalities (sorted by volume). Cell color intensity = trial count. Row/column margin totals. Hover shows exact count. Top-left quadrant = highest demand intersections = highest priority for method readiness.",
          mockup: "heatmap",
        },
        {
          id: "sq9",
          question: "How reliable is our classification, and where should we improve?",
          answer: "The provenance field tells you: mesh = high-confidence MeSH tree mapping, text_fallback = regex pattern match, base_only = no signal. Currently 75.6% mesh for TA, 53.7% mesh for modality. Science team can spot-check the text_fallback bucket to validate quality and identify missing patterns.",
          dataFields: ["drug_modality_provenance", "ta_provenance", "drug_modality", "therapeutic_area", "nct_id (count)"],
          filter: "All drug trials",
          vizType: "Confidence Dashboard (stacked bars + KPIs)",
          vizDesc: "Top row: 3 big KPI numbers — % mesh-confirmed (TA), % mesh-confirmed (modality), % unassigned. Below: one stacked bar per modality showing green (mesh) / amber (text) / red (base_only). Sorted by % mesh descending. Trend line showing confidence improvement over time.",
          mockup: "confidence",
        },
      ],
      Operations: [
        {
          id: "sq10",
          question: "What is the total workload forecast by complexity tier?",
          answer: "Assign complexity weights: small molecule = 1×, mAb/biologic = 2×, cell/gene therapy = 3×, radiopharmaceutical = 2.5×. Multiply trial counts × weight = complexity-weighted workload units. The master DB gives the total structural demand picture for headcount and instrument planning.",
          dataFields: ["drug_modality", "nct_id (count)", "complexity_weight (manual)", "phase"],
          filter: "INDUSTRY drug trials",
          vizType: "Dual-Axis: Volume vs. Weighted Workload",
          vizDesc: "Bars = raw trial count per modality. Overlaid line + dots = complexity-weighted units. The gap between bar height and line height shows where few trials create outsized workload (cell therapy, gene therapy). Second panel: same view trended quarterly.",
          mockup: "dual_axis",
        },
        {
          id: "sq11",
          question: "How should we allocate analysts across TAs and platforms?",
          answer: "TA × modality × phase cross-tab, filtered to INDUSTRY. Oncology at 47% of trials means ~half the bioanalytical throughput. Within oncology, the modality split (SM, mAb, oligo, radiopharm) maps directly to LC-MS vs. LBA vs. qPCR vs. specialized platform headcount.",
          dataFields: ["therapeutic_area", "drug_modality", "phase", "sponsor_class", "nct_id (count)"],
          filter: "sponsor_class = INDUSTRY",
          vizType: "Sunburst Diagram",
          vizDesc: "Inner ring = TA (sized by trial volume). Middle ring = modality within each TA. Outer ring = phase. Color-coded by instrument platform (blue = LC-MS, green = LBA, purple = molecular). Click-to-drill. Directly translates to: 'We need X analysts on Y platform for Z TA.'",
          mockup: "sunburst",
        },
        {
          id: "sq12",
          question: "What is the phase transition pipeline — what's coming in 1, 2, 3 years?",
          answer: "Phase 1 today → Phase 2 in ~1-2 years → Phase 3 in ~3-4 years. Each phase brings higher sample volumes and stricter method validation. Count trials by phase and modality to model the demand wave. 130 small molecule Phase 1s today = ~80 Phase 2s needing expanded capacity in 18 months.",
          dataFields: ["drug_modality", "phase", "nct_id (count)"],
          filter: "All drug trials",
          vizType: "Demand Wave / Sankey Diagram",
          vizDesc: "Left column = Phase 1 trials (now). Middle = projected Phase 2 (1-2yr). Right = projected Phase 3 (3-4yr). Flow width = projected trial count (with historical attrition rates applied). Color = modality. Shows the wave of demand moving through the system.",
          mockup: "sankey",
        },
      ],
    },
  },
  weekly: {
    label: "Weekly Pulse",
    tag: "TACTICAL",
    tagColor: "#F59E0B",
    icon: "⚡",
    source: "Pulse snapshot — trials registered/updated this week",
    sourcePath: "storage/snapshots/clinical_trials_v2/last_update/YYYY-MM-DD_YYYY-MM-DD_v1.json",
    refreshCadence: "Every Monday (or on-demand via ALEXIS Pulse CLI)",
    purpose: "What happened THIS WEEK? What should we act on NOW? What changed?",
    cards: {
      BD: [
        {
          id: "wq1",
          question: "Which sponsors filed new trials this week that we should contact?",
          answer: "Pulse snapshot → filter sponsor_class = INDUSTRY → group by sponsor_name → list trials per sponsor with modality and phase. A sponsor filing 3 new Phase 1 mAb trials this week is actively placing bioanalytical contracts right now. This is a call list, not a market study.",
          dataFields: ["sponsor_name", "sponsor_class", "drug_modality", "phase", "nct_id", "brief_title"],
          filter: "sponsor_class = INDUSTRY, this week's pulse",
          vizType: "Action Table with Priority Score",
          vizDesc: "Table: columns = Sponsor, # New Trials, Modality Mix, Top Phase, Priority Score (computed: high-complexity modality × early phase = higher score). Sorted by priority descending. Each row expandable to show individual trial titles. Export to CSV for CRM import. Color-coded: red = act today, amber = this week, grey = monitor.",
          mockup: "action_table",
        },
        {
          id: "wq2",
          question: "Are any of our existing clients filing new trials we should know about?",
          answer: "Cross-reference pulse sponsor names against a client list (manually maintained or CRM export). Matches = upsell opportunity. 'Client X just filed 2 new gene therapy Phase 1s — they'll need bioanalytical support in 3-6 months. Reach out to your contact now.'",
          dataFields: ["sponsor_name", "drug_modality", "phase", "therapeutic_area", "nct_id", "client_flag (manual list)"],
          filter: "Pulse × client list match",
          vizType: "Client Alert Cards",
          vizDesc: "One card per matched client. Card shows: client name, new trial count this week, modality badges, phase badges, trial titles. Red border if high-complexity modality (cell/gene). 'NEW THIS WEEK' banner. Designed for email digest or Slack notification format.",
          mockup: "alert_cards",
        },
        {
          id: "wq3",
          question: "What's the competitive landscape signal this week?",
          answer: "Group this week's trials by TA and modality. If oncology mAb filings spike 40% over the 4-week average, that's a signal: either a new target is hot, or multiple sponsors are racing. BD should know which TAs are heating up before competitors do.",
          dataFields: ["therapeutic_area", "drug_modality", "nct_id (count)", "4-week rolling average"],
          filter: "Pulse vs. trailing 4-week average",
          vizType: "Deviation Bars (this week vs. average)",
          vizDesc: "Horizontal bars centered on zero. Right = above average (green), left = below average (red). One bar per TA. Length = % deviation from 4-week mean. Labels show absolute count. Instantly shows: 'Oncology is +18% this week, Rare Disease is +45%, Cardio is -30%.'",
          mockup: "deviation_bars",
        },
      ],
      Marketing: [
        {
          id: "wq4",
          question: "What's the headline stat for this week's social/newsletter content?",
          answer: "Pulse gives you ready-made stats: '644 new drug trials registered this week — 422 in oncology, 35 in oligonucleotide therapies.' Pick the most interesting number. The non-disease categories (BA/BE, PK, food effect) are great for early-phase content angles.",
          dataFields: ["drug_trials_total", "top TA by count", "notable modalities", "non_disease_categories"],
          filter: "This week's pulse, top-line numbers",
          vizType: "Social-Ready Stat Cards",
          vizDesc: "3–4 large number cards with context line. Card 1: total trials this week. Card 2: dominant TA with %. Card 3: fastest-growing modality. Card 4: interesting non-disease stat (e.g., '19 PK/BA-BE studies'). Each card designed at social media aspect ratio, branded, directly postable.",
          mockup: "stat_cards",
        },
        {
          id: "wq5",
          question: "Are there trending modalities or TAs we should write about?",
          answer: "Compare this pulse against the master DB baseline proportions. If radiopharmaceuticals are 1.9% of the pulse but only 0.8% of the master DB, that modality is over-indexing this week. That's a content signal: 'Radiopharmaceutical trials are surging — here's what bioanalytical labs need to know.'",
          dataFields: ["drug_modality", "pulse_pct", "master_db_pct", "ratio"],
          filter: "Pulse proportions vs. master DB proportions",
          vizType: "Over/Under Index Chart",
          vizDesc: "Each modality shown as a dot on a horizontal axis. Center line = 1.0 (same proportion as master). Dots right of 1.0 = over-indexing this week (hot). Dots left = under-indexing (quiet). Size of dot = absolute trial count. Labels on notable outliers. Clean enough for slide insertion.",
          mockup: "index_chart",
        },
        {
          id: "wq6",
          question: "Which conference-relevant TAs had notable activity this week?",
          answer: "If AACR is in 3 weeks, filter the pulse to oncology and show the modality breakdown. If ASH is coming, filter to hematology. Gives the marketing team ammunition for pre-conference social posts and booth talking points grounded in that week's real filing data.",
          dataFields: ["therapeutic_area", "drug_modality", "phase", "nct_id (count)"],
          filter: "Pulse filtered to conference-relevant TA",
          vizType: "Conference Prep Snapshot (single-TA deep dive)",
          vizDesc: "Single-page view for one TA: trial count this week (big number), modality donut, phase bar, notable trial titles list, comparison to 4-week average. Header shows relevant upcoming conference name and date. Print-ready for pre-conference briefing packets.",
          mockup: "conf_snapshot",
        },
      ],
      Scientific: [
        {
          id: "wq7",
          question: "What new molecule types showed up this week that we haven't seen before?",
          answer: "Compare pulse modality distribution against master DB. Any trial with a modality that's rare in the master (<0.5% of trials) but appeared this week = novel signal. Also flag any trial where text_fallback matched a recently-added pattern (validates the new regex groups are catching real trials).",
          dataFields: ["drug_modality", "drug_modality_provenance", "brief_title", "intervention_name", "nct_id"],
          filter: "Pulse trials with rare or new modality matches",
          vizType: "New Signal Feed (annotated list)",
          vizDesc: "Chronological feed of notable trials. Each entry: NCT ID, title, modality badge, provenance badge (mesh/text/base), and a one-line annotation ('First AAV9 gene therapy trial in ophthalmology this quarter'). Filterable by modality. Designed as a weekly science team email digest.",
          mockup: "signal_feed",
        },
        {
          id: "wq8",
          question: "How many trials landed in base_only this week, and why?",
          answer: "Filter pulse to drug_modality_provenance = base_only. These are trials where ALEXIS couldn't determine the modality from MeSH or text. Review the intervention names — if you see patterns (e.g., 'nanoparticle' appearing in 5 base_only trials), that's a candidate for a new text_modality_policy rule.",
          dataFields: ["nct_id", "brief_title", "intervention_name", "drug_modality_provenance", "info_flags"],
          filter: "Pulse, drug_modality_provenance = base_only",
          vizType: "Classification Gap Report (table + word cloud)",
          vizDesc: "Top: KPI bar showing this week's provenance split (% mesh / text / base_only) vs. master DB. Below: table of all base_only trials with intervention names. Right panel: word cloud of intervention terms from base_only trials — recurring words = missing patterns to add. Actionable: each word cloud term is clickable to see matching trials.",
          mockup: "gap_report",
        },
        {
          id: "wq9",
          question: "What's the MeSH coverage quality for this week's trials?",
          answer: "The pulse shows 162 mesh_available_but_not_used out of 644 drug trials. That's 25.2%. Break it down by reason: no_drug_name_match (159) vs. drug_not_in_tree (3). The 159 'no match' trials have MeSH terms for procedures or comparators, not the actual drug — that's expected but worth monitoring. If this ratio changes week-over-week, something in the source data shifted.",
          dataFields: ["info_flags", "drug_modality_provenance", "nct_id (count)", "mesh_reason breakdown"],
          filter: "Pulse trials with info_flags",
          vizType: "MeSH Quality Waterfall",
          vizDesc: "Waterfall starting from total drug trials (644). First drop: trials with full MeSH modality (346). Second drop: text_fallback (162). Third drop: base_only (136). Side annotations show info_flag reasons. Compared to prior week's waterfall as a ghost overlay. Shows whether classification quality is improving or degrading.",
          mockup: "waterfall",
        },
      ],
      Operations: [
        {
          id: "wq10",
          question: "What's the new trial velocity this week vs. recent weeks?",
          answer: "Pulse captured 644 drug trials in 2 days = ~322/day. Compare against prior pulse snapshots: is this week higher or lower than the 4-week average? Spikes in velocity = upcoming demand surges. Sustained increases = time to hire. Break down by TA and modality to see which labs get hit first.",
          dataFields: ["drug_trials_count", "date_range", "therapeutic_area", "drug_modality"],
          filter: "Pulse vs. prior 4 pulse snapshots",
          vizType: "Velocity Dashboard (sparklines + big numbers)",
          vizDesc: "Top row: 4 big-number cards — total velocity (trials/day), oncology velocity, top non-oncology TA, top complex modality. Each card has a sparkline underneath showing 8-week trend. Green arrow if accelerating, red if decelerating. Below: small multiples sparklines for each TA. Early warning system.",
          mockup: "velocity",
        },
        {
          id: "wq11",
          question: "What complexity mix is arriving this week?",
          answer: "This week's 644 drug trials: 399 small molecule (1× complexity), 106 mAb (2×), 47 biologic (2×), 35 oligo (2.5×), 12 radiopharm (2.5×), 9 cell therapy (3×), 8 gene therapy (3×). Weighted total = much higher than raw count suggests. Operations needs this to plan instrument time and analyst assignments.",
          dataFields: ["drug_modality", "nct_id (count)", "complexity_weight", "weighted_units"],
          filter: "This week's pulse",
          vizType: "Waffle Chart (100-unit grid)",
          vizDesc: "100-square waffle grid where each square = ~1% of weighted workload. Small molecule squares in light blue (many squares, low weight each). Cell/gene therapy squares in deep red (few squares, but heavy weight). Instantly visual: 'small molecule is 40% of raw trials but only 28% of actual workload.' Legend maps colors to modalities and shows the multiplier.",
          mockup: "waffle",
        },
        {
          id: "wq12",
          question: "Which Phase 1 trials arrived this week? (earliest capacity signal)",
          answer: "Phase 1 INDUSTRY trials are the earliest signal of upcoming bioanalytical demand — sponsors typically contract bioanalytical within months of Phase 1 filing. This week: 130 Phase 1 small molecules, 31 Phase 1 mAbs, 14 Phase 1 oligos, 6 Phase 1 cell therapies. Each one is a potential incoming RFP.",
          dataFields: ["phase", "drug_modality", "sponsor_name", "sponsor_class", "nct_id", "brief_title"],
          filter: "Pulse, phase = PHASE1, sponsor_class = INDUSTRY",
          vizType: "Phase 1 Intake List (sortable table + summary strip)",
          vizDesc: "Top strip: colored badges showing Phase 1 count by modality (SM: 130, mAb: 31, Oligo: 14...). Below: sortable table of all Phase 1 INDUSTRY trials — columns: NCT ID, sponsor, title, modality, TA. Sortable by any column. Each row has a 'flag for BD' button. Export to CSV. This is the weekly intake list for the ops-BD handoff meeting.",
          mockup: "intake_table",
        },
      ],
    },
  },
};

/* ── Viz Mockups ── */
const VizMockup = ({ type, color }) => {
  const a = color.accent;
  const m = color.mid;

  const mockups = {
    bubble_matrix: (
      <svg viewBox="0 0 320 160" className="w-full">
        <text x="160" y="12" fill="#64748B" fontSize="7" textAnchor="middle" fontStyle="italic">Modality × Phase — bubble size = trial count</text>
        {["P1","P2","P3","P4"].map((p,j)=><text key={p} x={100+j*55} y="28" fill="#94A3B8" fontSize="7" textAnchor="middle">{p}</text>)}
        {[
          {label:"SM",sizes:[28,33,18,6]},
          {label:"mAb",sizes:[18,22,14,4]},
          {label:"Bio",sizes:[12,10,8,2]},
          {label:"Oligo",sizes:[10,10,5,0]},
          {label:"Cell/Gene",sizes:[8,3,1,0]},
        ].map((row,i)=>(
          <g key={row.label}>
            <text x="55" y={52+i*24} fill="#94A3B8" fontSize="7" textAnchor="end">{row.label}</text>
            {row.sizes.map((s,j)=>s>0&&(
              <circle key={j} cx={100+j*55} cy={48+i*24} r={Math.max(s/3.5,2)} fill={a} opacity={0.15+s/40} />
            ))}
          </g>
        ))}
        <circle cx={265} cy={140} r={4} fill="#10B981" opacity={0.6}/><text x={273} y={143} fill="#64748B" fontSize="6">Growing</text>
        <circle cx={265} cy={150} r={4} fill="#EF4444" opacity={0.6}/><text x={273} y={153} fill="#64748B" fontSize="6">Declining</text>
      </svg>
    ),
    ranked_bars: (
      <svg viewBox="0 0 320 160" className="w-full">
        {[
          {name:"Pfizer",w:180,sm:80,mab:60,bio:25,other:15},
          {name:"Novartis",w:145,sm:65,mab:45,bio:20,other:15},
          {name:"Roche",w:120,sm:40,mab:55,bio:15,other:10},
          {name:"AstraZeneca",w:100,sm:30,mab:40,bio:20,other:10},
          {name:"Merck",w:90,sm:50,mab:20,bio:10,other:10},
          {name:"BMS",w:75,sm:20,mab:35,bio:12,other:8},
        ].map((s,i)=>(
          <g key={s.name}>
            <text x="62" y={18+i*24} fill="#CBD5E1" fontSize="7" textAnchor="end">{s.name}</text>
            <rect x="66" y={10+i*24} width={s.sm/2} height="12" fill={a} opacity={0.5} rx="1"/>
            <rect x={66+s.sm/2} y={10+i*24} width={s.mab/2} height="12" fill={m} opacity={0.7} rx="1"/>
            <rect x={66+s.sm/2+s.mab/2} y={10+i*24} width={s.bio/2} height="12" fill="#10B981" opacity={0.6} rx="1"/>
            <rect x={66+s.sm/2+s.mab/2+s.bio/2} y={10+i*24} width={s.other/2} height="12" fill="#64748B" opacity={0.4} rx="1"/>
            <text x={70+s.w/2} y={18+i*24} fill="#64748B" fontSize="6">{s.w} trials</text>
          </g>
        ))}
        {[{c:a,l:"SM"},{c:m,l:"mAb"},{c:"#10B981",l:"Bio"},{c:"#64748B",l:"Other"}].map((x,i)=>(
          <g key={x.l}><rect x={70+i*45} y={155} width={8} height={5} fill={x.c} opacity={0.6} rx={1}/><text x={81+i*45} y={160} fill="#64748B" fontSize="6">{x.l}</text></g>
        ))}
      </svg>
    ),
    area_chart: (
      <svg viewBox="0 0 320 150" className="w-full">
        <line x1="40" y1="125" x2="300" y2="125" stroke="#334155" strokeWidth="0.5"/>
        {["Q1'25","Q2'25","Q3'25","Q4'25","Q1'26"].map((q,i)=><text key={q} x={55+i*60} y="138" fill="#64748B" fontSize="7" textAnchor="middle">{q}</text>)}
        <polygon points="40,125 55,50 115,48 175,45 235,42 295,38 295,70 235,72 175,75 115,78 55,80 40,125" fill={a} opacity="0.3"/>
        <polygon points="40,125 55,80 115,78 175,75 235,72 295,70 295,90 235,92 175,93 115,94 55,96 40,125" fill="#10B981" opacity="0.3"/>
        <polygon points="40,125 55,96 115,94 175,93 235,92 295,90 295,110 235,110 175,112 115,113 55,115 40,125" fill="#F59E0B" opacity="0.3"/>
        <text x="300" y="52" fill={a} fontSize="6">Oncology</text>
        <text x="300" y="82" fill="#10B981" fontSize="6">Immuno</text>
        <text x="300" y="102" fill="#F59E0B" fontSize="6">Neuro</text>
      </svg>
    ),
    donut_callout: (
      <svg viewBox="0 0 320 160" className="w-full">
        <circle cx="110" cy="80" r="55" fill="none" stroke={a} strokeWidth="22" strokeDasharray="200 145" opacity="0.85"/>
        <circle cx="110" cy="80" r="55" fill="none" stroke={m} strokeWidth="22" strokeDasharray="65 280" strokeDashoffset="-200" opacity="0.7"/>
        <circle cx="110" cy="80" r="55" fill="none" stroke="#10B981" strokeWidth="22" strokeDasharray="40 305" strokeDashoffset="-265"/>
        <circle cx="110" cy="80" r="55" fill="none" stroke="#F59E0B" strokeWidth="22" strokeDasharray="30 315" strokeDashoffset="-305"/>
        <text x="110" y="76" fill="white" fontSize="15" textAnchor="middle" fontWeight="bold">39,115</text>
        <text x="110" y="90" fill="#94A3B8" fontSize="7" textAnchor="middle">Drug Trials</text>
        {[
          {y:25,c:a,t:"Small Molecule",n:"62%",sub:"24,251 trials"},
          {y:55,c:m,t:"Monoclonal Ab",n:"16%",sub:"6,258 — 1 in 6 trials"},
          {y:85,c:"#10B981",t:"Biologic",n:"7%",sub:"2,738 trials"},
          {y:115,c:"#F59E0B",t:"Oligo / Gene / Cell",n:"5%",sub:"Growing +18% YoY"},
        ].map((item,i)=>(
          <g key={i}>
            <rect x="195" y={item.y} width="120" height="24" fill="#1E293B" rx="4" stroke="#334155" strokeWidth="0.5"/>
            <rect x="195" y={item.y} width="3" height="24" fill={item.c} rx="1"/>
            <text x="205" y={item.y+10} fill="white" fontSize="7" fontWeight="bold">{item.t}</text>
            <text x="205" y={item.y+19} fill="#94A3B8" fontSize="6">{item.n} — {item.sub}</text>
          </g>
        ))}
      </svg>
    ),
    ta_factcards: (
      <svg viewBox="0 0 320 160" className="w-full">
        {[
          {name:"Oncology",n:"18,554",pct:"47%",ind:"55%"},
          {name:"Immunology",n:"3,210",pct:"8%",ind:"76%"},
          {name:"Neurology",n:"2,870",pct:"7%",ind:"52%"},
        ].map((ta,i)=>(
          <g key={ta.name}>
            <rect x={5+i*106} y="3" width="100" height="153" fill="#1E293B" rx="6" stroke="#334155" strokeWidth="0.5"/>
            <text x={55+i*106} y="20" fill={a} fontSize="8" textAnchor="middle" fontWeight="bold">{ta.name}</text>
            <text x={55+i*106} y="44" fill="white" fontSize="16" textAnchor="middle" fontWeight="bold">{ta.n}</text>
            <text x={55+i*106} y="56" fill="#94A3B8" fontSize="7" textAnchor="middle">{ta.pct} of all drug trials</text>
            <circle cx={30+i*106} cy={88} r={16} fill="none" stroke={m} strokeWidth="5" strokeDasharray="62 38"/>
            <circle cx={30+i*106} cy={88} r={16} fill="none" stroke="#10B981" strokeWidth="5" strokeDasharray="20 80" strokeDashoffset="-62"/>
            <text x={30+i*106} y={91} fill="white" fontSize="6" textAnchor="middle">mod</text>
            <rect x={55+i*106} y={76} width="35" height="5" fill={a} rx="1" opacity="0.9"/>
            <rect x={55+i*106} y={84} width="26" height="5" fill={a} rx="1" opacity="0.6"/>
            <rect x={55+i*106} y={92} width="16" height="5" fill={a} rx="1" opacity="0.4"/>
            <text x={55+i*106} y={115} fill="#94A3B8" fontSize="6" textAnchor="middle">Industry: {ta.ind}</text>
            <text x={55+i*106} y={130} fill="#64748B" fontSize="5.5" textAnchor="middle">Top: Pfizer, Novartis, Roche</text>
            <text x={55+i*106} y={145} fill="#64748B" fontSize="5.5" textAnchor="middle">P1:412 P2:380 P3:195</text>
          </g>
        ))}
      </svg>
    ),
    gap_bars: (
      <svg viewBox="0 0 320 150" className="w-full">
        {[
          {label:"SM",demand:95,cap:90},{label:"mAb",demand:55,cap:70},{label:"Bio",demand:35,cap:40},
          {label:"Oligo",demand:30,cap:15},{label:"Cell",demand:12,cap:8},{label:"Gene",demand:10,cap:5},{label:"Vacc",demand:15,cap:20},
        ].map((r,i)=>(
          <g key={r.label}>
            <text x="35" y={20+i*18} fill="#94A3B8" fontSize="7" textAnchor="end">{r.label}</text>
            <rect x="42" y={12+i*18} width={r.demand*1.6} height="6" fill={a} rx="2" opacity="0.7"/>
            <rect x="42" y={20+i*18} width={r.cap*1.6} height="6" fill="#10B981" rx="2" opacity="0.7"/>
            {r.demand>r.cap+10&&<text x={44+Math.max(r.demand,r.cap)*1.6} y={20+i*18} fill="#EF4444" fontSize="6" fontWeight="bold">GAP</text>}
            {Math.abs(r.demand-r.cap)<=10&&<text x={44+Math.max(r.demand,r.cap)*1.6} y={20+i*18} fill="#10B981" fontSize="6">✓</text>}
          </g>
        ))}
        <rect x="42" y="142" width="10" height="5" fill={a} rx="1" opacity="0.7"/><text x="56" y="147" fill="#64748B" fontSize="6">Market demand</text>
        <rect x="120" y="142" width="10" height="5" fill="#10B981" rx="1" opacity="0.7"/><text x="134" y="147" fill="#64748B" fontSize="6">Our capability</text>
      </svg>
    ),
    horizon: (
      <svg viewBox="0 0 320 150" className="w-full">
        {[
          {label:"SM",p1:130,p2:155,p3:69,badge:null},
          {label:"mAb",p1:31,p2:47,p3:23,badge:null},
          {label:"Oligo",p1:14,p2:15,p3:6,badge:"INVEST"},
          {label:"Gene",p1:5,p2:0,p3:1,badge:"INVEST NOW"},
          {label:"Cell",p1:6,p2:2,p3:0,badge:"INVEST NOW"},
        ].map((r,i)=>{
          const s=0.5;
          return(
            <g key={r.label}>
              <text x="38" y={26+i*26} fill="#94A3B8" fontSize="7" textAnchor="end">{r.label}</text>
              <rect x="44" y={16+i*26} width={r.p1*s} height="16" fill="#10B981" rx="2"/>
              <rect x={44+r.p1*s} y={16+i*26} width={Math.max(r.p2*s,1)} height="16" fill={a} rx="2" opacity="0.7"/>
              <rect x={44+r.p1*s+r.p2*s} y={16+i*26} width={Math.max(r.p3*s,1)} height="16" fill={m} rx="2" opacity="0.4"/>
              {r.badge&&<g><rect x={44+(r.p1+r.p2+r.p3)*s+6} y={17+i*26} width={r.badge.length*4.5+6} height="14" fill="#F59E0B" rx="3" opacity="0.2"/><text x={44+(r.p1+r.p2+r.p3)*s+9} y={27+i*26} fill="#F59E0B" fontSize="6.5" fontWeight="bold">{r.badge}</text></g>}
            </g>
          );
        })}
        {[{c:"#10B981",l:"P1 (now)"},{c:a,l:"P2 (1-2yr)"},{c:m,l:"P3 (2-4yr)"}].map((x,i)=>(
          <g key={x.l}><rect x={44+i*70} y="145" width="10" height="5" fill={x.c} rx="1" opacity="0.7"/><text x={58+i*70} y="150" fill="#64748B" fontSize="6">{x.l}</text></g>
        ))}
      </svg>
    ),
    heatmap: (
      <svg viewBox="0 0 320 160" className="w-full">
        {["SM","mAb","Bio","Oligo","Cell","Gene","Vacc"].map((m2,j)=><text key={m2} x={78+j*32} y="14" fill="#94A3B8" fontSize="6.5" textAnchor="middle">{m2}</text>)}
        {[
          {ta:"Oncology",vals:[0.95,0.75,0.3,0.5,0.15,0.1,0.15]},
          {ta:"Immuno",vals:[0.6,0.35,0.4,0.1,0.05,0.0,0.05]},
          {ta:"Neuro",vals:[0.7,0.1,0.15,0.08,0.0,0.12,0.0]},
          {ta:"Infect",vals:[0.5,0.1,0.15,0.1,0.1,0.0,0.35]},
          {ta:"Rare",vals:[0.4,0.05,0.15,0.2,0.0,0.25,0.0]},
          {ta:"GI",vals:[0.5,0.15,0.1,0.0,0.0,0.0,0.0]},
        ].map((row,i)=>(
          <g key={row.ta}>
            <text x="42" y={32+i*22} fill="#94A3B8" fontSize="7" textAnchor="end">{row.ta}</text>
            {row.vals.map((v,j)=><rect key={j} x={62+j*32} y={20+i*22} width="28" height="18" fill={a} opacity={Math.max(v,0.04)} rx="3"/>)}
          </g>
        ))}
      </svg>
    ),
    confidence: (
      <svg viewBox="0 0 320 150" className="w-full">
        {[{l:"TA Classification",v:75.6},{l:"Modality Classification",v:53.7},{l:"Assigned (non-unassigned)",v:98.4}].map((kpi,i)=>(
          <g key={kpi.l}>
            <rect x={5+i*106} y="5" width="100" height="42" fill="#1E293B" rx="5" stroke="#334155" strokeWidth="0.5"/>
            <text x={55+i*106} y="22" fill="#94A3B8" fontSize="6" textAnchor="middle">{kpi.l}</text>
            <text x={55+i*106} y="40" fill={kpi.v>70?"#10B981":"#F59E0B"} fontSize="14" textAnchor="middle" fontWeight="bold">{kpi.v}%</text>
          </g>
        ))}
        {[
          {label:"SM",mesh:70,text:20,base:10},{label:"mAb",mesh:85,text:10,base:5},{label:"Bio",mesh:40,text:45,base:15},
          {label:"Oligo",mesh:30,text:55,base:15},{label:"Cell",mesh:10,text:70,base:20},{label:"Gene",mesh:15,text:60,base:25},
        ].map((r,i)=>(
          <g key={r.label}>
            <text x="35" y={72+i*13} fill="#94A3B8" fontSize="7" textAnchor="end">{r.label}</text>
            <rect x="40" y={65+i*13} width={r.mesh*1.5} height="9" fill="#10B981" rx="1.5"/>
            <rect x={40+r.mesh*1.5} y={65+i*13} width={r.text*1.5} height="9" fill="#F59E0B" rx="1.5"/>
            <rect x={40+(r.mesh+r.text)*1.5} y={65+i*13} width={r.base*1.5} height="9" fill="#EF4444" rx="1.5" opacity="0.7"/>
          </g>
        ))}
        {[{c:"#10B981",l:"MeSH"},{c:"#F59E0B",l:"Text"},{c:"#EF4444",l:"Base only"}].map((x,i)=>(
          <g key={x.l}><rect x={40+i*60} y="145" width="8" height="5" fill={x.c} rx="1" opacity="0.7"/><text x={51+i*60} y="150" fill="#64748B" fontSize="6">{x.l}</text></g>
        ))}
      </svg>
    ),
    dual_axis: (
      <svg viewBox="0 0 320 150" className="w-full">
        <line x1="50" y1="120" x2="290" y2="120" stroke="#334155" strokeWidth="0.5"/>
        {[{l:"SM",h:95,w:95},{l:"mAb",h:45,w:90},{l:"Bio",h:30,w:60},{l:"Oligo",h:20,w:50},{l:"Cell",h:12,w:36},{l:"Gene",h:10,w:30}].map((r,i)=>(
          <g key={r.l}>
            <rect x={60+i*38} y={120-r.h} width="30" height={r.h} fill={a} rx="3" opacity="0.6"/>
            <circle cx={75+i*38} cy={120-r.w} r="4" fill="#F59E0B"/>
            <text x={75+i*38} y="133" fill="#94A3B8" fontSize="7" textAnchor="middle">{r.l}</text>
          </g>
        ))}
        <polyline points="75,25 113,30 151,60 189,70 227,84 265,90" fill="none" stroke="#F59E0B" strokeWidth="1.5" strokeDasharray="3"/>
        <rect x="60" y="6" width="8" height="5" fill={a} rx="1" opacity="0.6"/><text x="72" y="11" fill="#64748B" fontSize="6">Raw count</text>
        <circle cx="140" cy="8" r="3" fill="#F59E0B"/><text x="147" y="11" fill="#64748B" fontSize="6">Weighted workload</text>
      </svg>
    ),
    sunburst: (
      <svg viewBox="0 0 320 160" className="w-full">
        <circle cx="130" cy="80" r="28" fill={a} opacity="0.85"/>
        <text x="130" y="78" fill="white" fontSize="7" textAnchor="middle" fontWeight="bold">All</text>
        <text x="130" y="88" fill="white" fontSize="6" textAnchor="middle">Trials</text>
        <path d="M130 80 m0-42 a42 42 0 0 1 36 21 L130 80Z" fill={a} opacity="0.6"/>
        <path d="M130 80 l36-21 a42 42 0 0 1 0 42 L130 80Z" fill={m} opacity="0.7"/>
        <path d="M130 80 l36 21 a42 42 0 0 1-36 21 L130 80Z" fill="#10B981" opacity="0.6"/>
        <path d="M130 80 l0 42 a42 42 0 0 1-42 0 L130 80Z" fill="#F59E0B" opacity="0.6"/>
        <path d="M130 80 l-42 0 a42 42 0 0 1 6-42 L130 80Z" fill="#EF4444" opacity="0.4"/>
        <circle cx="130" cy="80" r="56" fill="none" stroke="#334155" strokeWidth="14" opacity="0.25"/>
        <text x="230" y="40" fill="#94A3B8" fontSize="7">Inner: TA</text>
        <text x="230" y="52" fill="#94A3B8" fontSize="7">Middle: Modality</text>
        <text x="230" y="64" fill="#94A3B8" fontSize="7">Outer: Phase</text>
        {[{c:a,l:"LC-MS"},{c:"#10B981",l:"LBA"},{c:"#F59E0B",l:"Molecular"},{c:"#EF4444",l:"Specialized"}].map((x,i)=>(
          <g key={x.l}><rect x="230" y={78+i*14} width="8" height="8" fill={x.c} rx="1" opacity="0.7"/><text x="242" y={86+i*14} fill="#94A3B8" fontSize="6.5">{x.l}</text></g>
        ))}
      </svg>
    ),
    sankey: (
      <svg viewBox="0 0 320 150" className="w-full">
        <text x="45" y="12" fill="#94A3B8" fontSize="7" textAnchor="middle">Phase 1</text>
        <text x="160" y="12" fill="#94A3B8" fontSize="7" textAnchor="middle">→ Phase 2</text>
        <text x="275" y="12" fill="#94A3B8" fontSize="7" textAnchor="middle">→ Phase 3</text>
        {[
          {label:"SM",c:a,y1:20,h1:50,y2:25,h2:35,y3:30,h3:22},
          {label:"mAb",c:m,y1:75,h1:25,y2:65,h2:18,y3:56,h3:12},
          {label:"Oligo",c:"#10B981",y1:105,h1:12,y2:88,h2:9,y3:72,h3:5},
          {label:"Gene",c:"#F59E0B",y1:122,h1:8,y2:102,h2:5,y3:82,h3:2},
        ].map((r)=>(
          <g key={r.label}>
            <rect x="20" y={r.y1} width="50" height={r.h1} fill={r.c} opacity="0.7" rx="3"/>
            <rect x="135" y={r.y2} width="50" height={r.h2} fill={r.c} opacity="0.5" rx="3"/>
            <rect x="250" y={r.y3} width="50" height={r.h3} fill={r.c} opacity="0.35" rx="3"/>
            <path d={`M70 ${r.y1+r.h1/2} C100 ${r.y1+r.h1/2} 105 ${r.y2+r.h2/2} 135 ${r.y2+r.h2/2}`} fill="none" stroke={r.c} strokeWidth={Math.max(r.h2/2,1)} opacity="0.2"/>
            <path d={`M185 ${r.y2+r.h2/2} C215 ${r.y2+r.h2/2} 220 ${r.y3+r.h3/2} 250 ${r.y3+r.h3/2}`} fill="none" stroke={r.c} strokeWidth={Math.max(r.h3/2,1)} opacity="0.15"/>
            <text x="10" y={r.y1+r.h1/2+3} fill="#94A3B8" fontSize="6">{r.label}</text>
          </g>
        ))}
        <text x="160" y="140" fill="#475569" fontSize="6" textAnchor="middle" fontStyle="italic">Width = projected trial volume (with historical attrition)</text>
      </svg>
    ),
    action_table: (
      <svg viewBox="0 0 320 150" className="w-full">
        <rect x="5" y="5" width="310" height="20" fill="#1E293B" rx="3"/>
        <text x="12" y="18" fill="#94A3B8" fontSize="6.5" fontWeight="bold">SPONSOR</text>
        <text x="100" y="18" fill="#94A3B8" fontSize="6.5" fontWeight="bold">NEW</text>
        <text x="130" y="18" fill="#94A3B8" fontSize="6.5" fontWeight="bold">MODALITY MIX</text>
        <text x="230" y="18" fill="#94A3B8" fontSize="6.5" fontWeight="bold">PHASE</text>
        <text x="275" y="18" fill="#94A3B8" fontSize="6.5" fontWeight="bold">PRIORITY</text>
        {[
          {name:"GeneTx Corp",n:3,mods:["gene","cell"],phase:"P1",pri:"HIGH",priColor:"#EF4444"},
          {name:"OncoPharma",n:5,mods:["mAb","SM"],phase:"P1/P2",pri:"HIGH",priColor:"#EF4444"},
          {name:"NovaBio",n:2,mods:["oligo"],phase:"P1",pri:"MED",priColor:"#F59E0B"},
          {name:"CardioRx",n:4,mods:["SM","SM"],phase:"P2/P3",pri:"MED",priColor:"#F59E0B"},
          {name:"ImmunoLabs",n:1,mods:["bio"],phase:"P2",pri:"LOW",priColor:"#64748B"},
        ].map((r,i)=>(
          <g key={r.name}>
            <rect x="5" y={28+i*22} width="310" height="20" fill={i%2===0?"#0F172A":"transparent"} rx="2"/>
            <text x="12" y={41+i*22} fill="#E2E8F0" fontSize="7">{r.name}</text>
            <text x="107" y={41+i*22} fill="white" fontSize="8" fontWeight="bold">{r.n}</text>
            {r.mods.map((mod,j)=>(
              <g key={j}><rect x={130+j*28} y={33+i*22} width="24" height="12" fill={a} opacity="0.2" rx="6"/><text x={142+j*28} y={42+i*22} fill={m} fontSize="5.5" textAnchor="middle">{mod}</text></g>
            ))}
            <text x="235" y={41+i*22} fill="#94A3B8" fontSize="7">{r.phase}</text>
            <rect x="270" y={33+i*22} width="30" height="12" fill={r.priColor} opacity="0.2" rx="6"/>
            <text x="285" y={42+i*22} fill={r.priColor} fontSize="6" textAnchor="middle" fontWeight="bold">{r.pri}</text>
          </g>
        ))}
      </svg>
    ),
    alert_cards: (
      <svg viewBox="0 0 320 150" className="w-full">
        {[
          {name:"Pfizer",n:4,mods:"mAb, SM",hl:false},
          {name:"GeneTx Corp",n:2,mods:"gene therapy",hl:true},
          {name:"NovaBio",n:1,mods:"oligonucleotide",hl:false},
        ].map((c,i)=>(
          <g key={c.name}>
            <rect x={5+i*106} y="5" width="100" height="140" fill="#1E293B" rx="6" stroke={c.hl?"#EF4444":"#334155"} strokeWidth={c.hl?1.5:0.5}/>
            <rect x={5+i*106} y="5" width="100" height="18" fill={c.hl?"#EF444420":a+"15"} rx="6"/>
            <rect x={5+i*106} y="17" width="100" height="6" fill="#1E293B"/>
            <text x={55+i*106} y="16" fill={c.hl?"#EF4444":m} fontSize="6" textAnchor="middle" fontWeight="bold">🔔 NEW THIS WEEK</text>
            <text x={55+i*106} y="38" fill="white" fontSize="9" textAnchor="middle" fontWeight="bold">{c.name}</text>
            <text x={55+i*106} y="56" fill={a} fontSize="18" textAnchor="middle" fontWeight="bold">{c.n}</text>
            <text x={55+i*106} y="68" fill="#94A3B8" fontSize="7" textAnchor="middle">new trials</text>
            <rect x={20+i*106} y="78" width="70" height="14" fill={a} opacity="0.15" rx="7"/>
            <text x={55+i*106} y="88" fill={m} fontSize="6" textAnchor="middle">{c.mods}</text>
            <line x1={15+i*106} y1="100" x2={95+i*106} y2="100" stroke="#334155" strokeWidth="0.5"/>
            <text x={55+i*106} y="115" fill="#64748B" fontSize="5.5" textAnchor="middle">NCT09182736 — Phase 1</text>
            <text x={55+i*106} y="126" fill="#64748B" fontSize="5.5" textAnchor="middle">NCT09182737 — Phase 2</text>
          </g>
        ))}
      </svg>
    ),
    deviation_bars: (
      <svg viewBox="0 0 320 150" className="w-full">
        <line x1="160" y1="10" x2="160" y2="135" stroke="#475569" strokeWidth="0.5" strokeDasharray="3"/>
        <text x="160" y="8" fill="#64748B" fontSize="6" textAnchor="middle">4-week avg</text>
        {[
          {ta:"Rare Disease",dev:45,dir:1},{ta:"Oncology",dev:18,dir:1},{ta:"Infectious",dev:12,dir:1},
          {ta:"Neuro",dev:5,dir:1},{ta:"Immuno",dev:-8,dir:-1},{ta:"Cardio",dev:-30,dir:-1},
        ].map((r,i)=>{
          const w=Math.abs(r.dev)*1.8;
          return(
            <g key={r.ta}>
              <text x={r.dir>0?155:165} y={25+i*20} fill="#94A3B8" fontSize="7" textAnchor={r.dir>0?"end":"start"}>{r.ta}</text>
              <rect x={r.dir>0?160-w:160} y={17+i*20} width={w} height="12" fill={r.dir>0?"#10B981":"#EF4444"} rx="2" opacity="0.6"/>
              <text x={r.dir>0?160-w-4:160+w+4} y={26+i*20} fill={r.dir>0?"#10B981":"#EF4444"} fontSize="7" textAnchor={r.dir>0?"end":"start"} fontWeight="bold">{r.dir>0?"+":""}{r.dev}%</text>
            </g>
          );
        })}
      </svg>
    ),
    stat_cards: (
      <svg viewBox="0 0 320 150" className="w-full">
        {[
          {n:"644",sub:"drug trials this week",c:a},
          {n:"65%",sub:"Oncology (422 trials)",c:"#EF4444"},
          {n:"17%",sub:"mAb — 1 in 6 trials",c:m},
          {n:"19",sub:"PK / BA-BE studies",c:"#10B981"},
        ].map((card,i)=>(
          <g key={i}>
            <rect x={5+i*79} y="10" width="73" height="130" fill="#1E293B" rx="8" stroke="#334155" strokeWidth="0.5"/>
            <rect x={5+i*79} y="10" width="73" height="4" fill={card.c} rx="8" opacity="0.6"/>
            <text x={41+i*79} y="65" fill="white" fontSize="22" textAnchor="middle" fontWeight="bold">{card.n}</text>
            <text x={41+i*79} y="85" fill="#94A3B8" fontSize="6" textAnchor="middle">{card.sub}</text>
            <text x={41+i*79} y="125" fill="#475569" fontSize="5" textAnchor="middle">Week of Feb 22</text>
          </g>
        ))}
      </svg>
    ),
    index_chart: (
      <svg viewBox="0 0 320 150" className="w-full">
        <line x1="160" y1="15" x2="160" y2="130" stroke="#475569" strokeWidth="0.5"/>
        <text x="160" y="12" fill="#64748B" fontSize="6" textAnchor="middle">1.0× (same as master DB)</text>
        <text x="80" y="140" fill="#64748B" fontSize="6" textAnchor="middle">← Under-indexing (quiet)</text>
        <text x="240" y="140" fill="#64748B" fontSize="6" textAnchor="middle">Over-indexing (hot) →</text>
        {[
          {label:"Radiopharm",x:245,y:40,r:7,hot:true},{label:"Gene Tx",x:220,y:65,r:6,hot:true},
          {label:"mAb",x:185,y:50,r:14,hot:true},{label:"SM",x:150,y:80,r:18,hot:false},
          {label:"Vaccine",x:130,y:55,r:8,hot:false},{label:"Bio",x:100,y:70,r:9,hot:false},
        ].map((d)=>(
          <g key={d.label}>
            <circle cx={d.x} cy={d.y} r={d.r} fill={d.hot?"#10B981":a} opacity={0.4}/>
            <text x={d.x} y={d.y+d.r+10} fill="#94A3B8" fontSize="6" textAnchor="middle">{d.label}</text>
          </g>
        ))}
      </svg>
    ),
    conf_snapshot: (
      <svg viewBox="0 0 320 150" className="w-full">
        <rect x="5" y="5" width="310" height="140" fill="#1E293B" rx="8" stroke="#334155" strokeWidth="0.5"/>
        <rect x="5" y="5" width="310" height="24" fill={a} opacity="0.15" rx="8"/>
        <rect x="5" y="23" width="310" height="6" fill="#1E293B"/>
        <text x="15" y="20" fill={m} fontSize="8" fontWeight="bold">🎯 AACR 2026 Prep — Oncology This Week</text>
        <text x="280" y="20" fill="#64748B" fontSize="6">Mar 28-Apr 2</text>
        <text x="55" y="55" fill="white" fontSize="22" fontWeight="bold">422</text>
        <text x="55" y="68" fill="#94A3B8" fontSize="7">oncology drug trials</text>
        <circle cx="55" cy="105" r="22" fill="none" stroke={m} strokeWidth="6" strokeDasharray="80 58"/>
        <circle cx="55" cy="105" r="22" fill="none" stroke="#10B981" strokeWidth="6" strokeDasharray="25 113" strokeDashoffset="-80"/>
        <circle cx="55" cy="105" r="22" fill="none" stroke="#F59E0B" strokeWidth="6" strokeDasharray="18 120" strokeDashoffset="-105"/>
        <text x="55" y="108" fill="white" fontSize="6" textAnchor="middle">mod</text>
        {[{l:"SM: 235",y:48},{l:"mAb: 97",y:60},{l:"Oligo: 32",y:72},{l:"Radioph: 10",y:84},{l:"Cell: 7",y:96},{l:"Gene: 2",y:108}].map((r)=>(
          <text key={r.l} x="120" y={r.y} fill="#94A3B8" fontSize="7">{r.l}</text>
        ))}
        <text x="220" y="48" fill="#94A3B8" fontSize="6.5" fontWeight="bold">vs. 4-wk avg:</text>
        <text x="220" y="62" fill="#10B981" fontSize="7" fontWeight="bold">+18% total volume</text>
        <text x="220" y="76" fill="#10B981" fontSize="7">+24% mAb</text>
        <text x="220" y="90" fill="#F59E0B" fontSize="7">+8% SM (flat)</text>
        <text x="220" y="108" fill="#64748B" fontSize="6">Top 3: P1 (170) P2 (176) P3 (61)</text>
      </svg>
    ),
    signal_feed: (
      <svg viewBox="0 0 320 150" className="w-full">
        {[
          {nct:"NCT09182001",title:"AAV9 gene therapy for retinitis pigmentosa",mod:"gene_therapy",prov:"text",note:"First ophtho gene therapy this quarter"},
          {nct:"NCT09182045",title:"[177Lu]-PSMA radioligand therapy in mCRPC",mod:"radiopharm",prov:"text",note:"New isotope notation matched"},
          {nct:"NCT09182102",title:"Neoantigen vaccine + pembrolizumab",mod:"vaccine",prov:"text",note:"Neoantigen pattern (new rule) confirmed"},
        ].map((r,i)=>(
          <g key={r.nct}>
            <rect x="5" y={5+i*48} width="310" height="42" fill="#1E293B" rx="5" stroke="#334155" strokeWidth="0.5"/>
            <text x="12" y={20+i*48} fill="#94A3B8" fontSize="6" fontFamily="monospace">{r.nct}</text>
            <rect x="90" y={12+i*48} width={r.mod.length*4.5+8} height="12" fill={a} opacity="0.2" rx="6"/>
            <text x={94+r.mod.length*2.25} y={21+i*48} fill={m} fontSize="5.5" textAnchor="middle">{r.mod}</text>
            <rect x={100+r.mod.length*4.5+12} y={12+i*48} width="24" height="12" fill={r.prov==="mesh"?"#10B98130":"#F59E0B30"} rx="6"/>
            <text x={112+r.mod.length*4.5+12} y={21+i*48} fill={r.prov==="mesh"?"#10B981":"#F59E0B"} fontSize="5.5" textAnchor="middle">{r.prov}</text>
            <text x="12" y={33+i*48} fill="#E2E8F0" fontSize="6.5">{r.title}</text>
            <text x="12" y={43+i*48} fill="#F59E0B" fontSize="5.5" fontStyle="italic">💡 {r.note}</text>
          </g>
        ))}
      </svg>
    ),
    gap_report: (
      <svg viewBox="0 0 320 150" className="w-full">
        {[{l:"MeSH",v:"53.7%",c:"#10B981"},{l:"Text",v:"25.2%",c:"#F59E0B"},{l:"Base only",v:"21.1%",c:"#EF4444"}].map((kpi,i)=>(
          <g key={kpi.l}>
            <rect x={5+i*106} y="5" width="100" height="35" fill="#1E293B" rx="5" stroke="#334155" strokeWidth="0.5"/>
            <text x={55+i*106} y="18" fill="#94A3B8" fontSize="6" textAnchor="middle">{kpi.l}</text>
            <text x={55+i*106} y="34" fill={kpi.c} fontSize="13" textAnchor="middle" fontWeight="bold">{kpi.v}</text>
          </g>
        ))}
        <text x="160" y="55" fill="#64748B" fontSize="6" textAnchor="middle" fontStyle="italic">Word cloud of intervention terms in base_only trials:</text>
        {[
          {t:"nanoparticle",x:80,y:80,s:13},{t:"extract",x:170,y:75,s:11},{t:"herbal",x:250,y:82,s:10},
          {t:"compound",x:120,y:100,s:12},{t:"formulation",x:210,y:98,s:9},{t:"cream",x:60,y:115,s:8},
          {t:"topical",x:150,y:118,s:10},{t:"probiotic",x:250,y:112,s:9},{t:"suspension",x:100,y:130,s:7},
        ].map((w)=>(
          <text key={w.t} x={w.x} y={w.y} fill={a} fontSize={w.s} textAnchor="middle" opacity={0.4+w.s/20} fontWeight="bold">{w.t}</text>
        ))}
      </svg>
    ),
    waterfall: (
      <svg viewBox="0 0 320 150" className="w-full">
        <rect x="25" y="20" width="260" height="18" fill={a} rx="3" opacity="0.3"/>
        <text x="155" y="32" fill="white" fontSize="7" textAnchor="middle">644 total drug trials</text>
        <rect x="25" y="44" width="140" height="18" fill="#10B981" rx="3" opacity="0.6"/>
        <text x="95" y="56" fill="white" fontSize="7" textAnchor="middle">346 MeSH classified ✓</text>
        <line x1="165" y1="44" x2="165" y2="68" stroke="#475569" strokeWidth="0.5" strokeDasharray="2"/>
        <rect x="25" y="68" width="65" height="18" fill="#F59E0B" rx="3" opacity="0.6"/>
        <text x="57" y="80" fill="white" fontSize="7" textAnchor="middle">162 text</text>
        <line x1="90" y1="68" x2="90" y2="92" stroke="#475569" strokeWidth="0.5" strokeDasharray="2"/>
        <rect x="25" y="92" width="55" height="18" fill="#EF4444" rx="3" opacity="0.5"/>
        <text x="52" y="104" fill="white" fontSize="7" textAnchor="middle">136 base_only</text>
        <rect x="25" y="120" width="260" height="18" fill="#0F172A" rx="3" stroke="#475569" strokeWidth="0.5" strokeDasharray="3"/>
        <text x="155" y="132" fill="#64748B" fontSize="6.5" textAnchor="middle" fontStyle="italic">Ghost: prior week comparison (dashed outline)</text>
      </svg>
    ),
    velocity: (
      <svg viewBox="0 0 320 160" className="w-full">
        {[
          {label:"ALL DRUG",rate:"322/d",trend:"↑8%",c:a,pts:"0,20 18,22 36,18 54,15 72,12 90,10"},
          {label:"ONCOLOGY",rate:"148/d",trend:"↑12%",c:"#EF4444",pts:"0,20 18,18 36,20 54,16 72,12 90,8"},
          {label:"mAb",rate:"44/d",trend:"↑15%",c:m,pts:"0,22 18,20 36,18 54,14 72,10 90,6"},
          {label:"GENE TX",rate:"4/d",trend:"↑40%",c:"#F59E0B",pts:"0,22 18,24 36,20 54,16 72,14 90,8"},
        ].map((r,i)=>(
          <g key={r.label} transform={`translate(${(i%2)*160},${Math.floor(i/2)*80})`}>
            <rect x="5" y="5" width="148" height="72" fill="#1E293B" rx="6" stroke="#334155" strokeWidth="0.5"/>
            <text x="14" y="20" fill="#94A3B8" fontSize="7" fontWeight="bold">{r.label}</text>
            <text x="14" y="40" fill="white" fontSize="15" fontWeight="bold">{r.rate}</text>
            <text x="80" y="40" fill={r.trend.includes("↑")?"#10B981":"#94A3B8"} fontSize="9" fontWeight="bold">{r.trend}</text>
            <g transform="translate(14,48)"><polyline points={r.pts} fill="none" stroke={r.c} strokeWidth="2"/></g>
          </g>
        ))}
      </svg>
    ),
    waffle: (
      <svg viewBox="0 0 320 150" className="w-full">
        <text x="160" y="12" fill="#64748B" fontSize="7" textAnchor="middle">Each square ≈ 1% of complexity-weighted workload</text>
        {Array.from({length:100}).map((_,i)=>{
          const x=15+(i%14)*21;
          const y=20+Math.floor(i/14)*17;
          let fill=a, op=0.4, label="SM";
          if(i>=40&&i<58){fill=m;op=0.6;label="mAb";}
          else if(i>=58&&i<72){fill="#10B981";op=0.6;label="Bio";}
          else if(i>=72&&i<82){fill="#F59E0B";op=0.7;label="Oligo";}
          else if(i>=82&&i<92){fill="#EF4444";op=0.8;label="Cell/Gene";}
          else if(i>=92){fill="#64748B";op=0.5;label="Other";}
          return <rect key={i} x={x} y={y} width="18" height="14" fill={fill} opacity={op} rx="2"/>;
        })}
        {[{c:a,l:"SM (1×)"},{c:m,l:"mAb (2×)"},{c:"#10B981",l:"Bio (2×)"},{c:"#F59E0B",l:"Oligo (2.5×)"},{c:"#EF4444",l:"Cell/Gene (3×)"}].map((x,i)=>(
          <g key={x.l}><rect x={15+i*58} y="142" width="8" height="6" fill={x.c} rx="1" opacity="0.7"/><text x={26+i*58} y="148" fill="#64748B" fontSize="5.5">{x.l}</text></g>
        ))}
      </svg>
    ),
    intake_table: (
      <svg viewBox="0 0 320 150" className="w-full">
        <rect x="5" y="5" width="310" height="16" fill={a} opacity="0.15" rx="3"/>
        {[{l:"SM",n:82,c:a},{l:"mAb",n:19,c:m},{l:"Oligo",n:9,c:"#10B981"},{l:"Cell",n:4,c:"#EF4444"},{l:"Gene",n:3,c:"#F59E0B"}].map((b,i)=>(
          <g key={b.l}>
            <rect x={10+i*60} y="7" width="52" height="12" fill={b.c} opacity="0.2" rx="6"/>
            <text x={36+i*60} y="16" fill={b.c} fontSize="6.5" textAnchor="middle" fontWeight="bold">{b.l}: {b.n}</text>
          </g>
        ))}
        <rect x="5" y="25" width="310" height="16" fill="#1E293B" rx="2"/>
        <text x="12" y="36" fill="#94A3B8" fontSize="6" fontWeight="bold">NCT ID</text>
        <text x="75" y="36" fill="#94A3B8" fontSize="6" fontWeight="bold">SPONSOR</text>
        <text x="155" y="36" fill="#94A3B8" fontSize="6" fontWeight="bold">TITLE</text>
        <text x="270" y="36" fill="#94A3B8" fontSize="6" fontWeight="bold">MODALITY</text>
        {[
          {nct:"NCT09182001",sp:"GeneTx",title:"AAV9 for retinitis pigm...",mod:"gene"},
          {nct:"NCT09182045",sp:"OncoPharma",title:"Anti-CD38 mAb in r/r MM...",mod:"mAb"},
          {nct:"NCT09182102",sp:"NovaBio",title:"ASO for spinal muscular...",mod:"oligo"},
          {nct:"NCT09182199",sp:"ImmuCore",title:"CAR-T anti-BCMA in ALL...",mod:"cell"},
          {nct:"NCT09182250",sp:"CardioRx",title:"SGLT2 inhibitor in HFpEF...",mod:"SM"},
        ].map((r,i)=>(
          <g key={r.nct}>
            <rect x="5" y={43+i*18} width="310" height="16" fill={i%2===0?"#0F172A":"transparent"} rx="1"/>
            <text x="12" y={54+i*18} fill="#94A3B8" fontSize="6" fontFamily="monospace">{r.nct}</text>
            <text x="75" y={54+i*18} fill="#E2E8F0" fontSize="6">{r.sp}</text>
            <text x="155" y={54+i*18} fill="#CBD5E1" fontSize="6">{r.title}</text>
            <rect x="268" y={46+i*18} width="28" height="11" fill={a} opacity="0.15" rx="5"/>
            <text x="282" y={54+i*18} fill={m} fontSize="5.5" textAnchor="middle">{r.mod}</text>
          </g>
        ))}
      </svg>
    ),
  };
  return (
    <div className="bg-slate-900/50 rounded-lg p-3 border border-slate-700/50">
      <div className="text-xs text-slate-500 mb-1 font-mono">VIZ MOCKUP</div>
      {mockups[type] || <div className="text-slate-500 text-sm">Preview not available</div>}
    </div>
  );
};

/* ── Card Component ── */
const Card = ({ item, color }) => {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-slate-700/60 bg-slate-800/80 overflow-hidden cursor-pointer transition-all hover:border-slate-600" onClick={() => setOpen(!open)}>
      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <h3 className="text-white font-semibold text-sm leading-snug flex-1">{item.question}</h3>
          <span className="text-slate-400 text-base mt-0.5 transition-transform duration-200 flex-shrink-0" style={{ transform: open ? "rotate(180deg)" : "rotate(0deg)" }}>▾</span>
        </div>
        <div className="mt-2 flex items-center gap-2 flex-wrap">
          <span className="text-xs font-mono px-2 py-0.5 rounded-full" style={{ backgroundColor: color.accent + "25", color: color.mid }}>{item.vizType}</span>
        </div>
      </div>
      {open && (
        <div className="px-4 pb-4 space-y-3 border-t border-slate-700/40 pt-3">
          <div>
            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">How the data answers it</div>
            <p className="text-sm text-slate-300 leading-relaxed">{item.answer}</p>
          </div>
          <div>
            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Data fields</div>
            <div className="flex flex-wrap gap-1.5">
              {item.dataFields.map((f) => <code key={f} className="text-xs px-1.5 py-0.5 bg-slate-700/60 rounded text-slate-300 font-mono">{f}</code>)}
            </div>
          </div>
          <div>
            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Visualization</div>
            <p className="text-sm text-slate-300 leading-relaxed">{item.vizDesc}</p>
          </div>
          <VizMockup type={item.mockup} color={color} />
        </div>
      )}
    </div>
  );
};

/* ── Main ── */
export default function App() {
  const [view, setView] = useState("quarterly");
  const [team, setTeam] = useState("BD");
  const db = dashboards[view];
  const color = teamColors[team];

  return (
    <div className="min-h-screen bg-slate-900 text-white">
      <div className="max-w-3xl mx-auto px-4 py-6">
        {/* Header */}
        <div className="mb-6">
          <div className="text-xs font-mono text-slate-500 tracking-widest mb-1">ALEXIS → BUSINESS INTELLIGENCE</div>
          <h1 className="text-xl font-bold text-white mb-1">Dashboard Spec: Two Views</h1>
          <p className="text-sm text-slate-400">24 business questions. Each mapped to exact data fields, query logic, and visualization.</p>
        </div>

        {/* Dashboard Toggle */}
        <div className="flex gap-2 mb-5">
          {Object.entries(dashboards).map(([key, d]) => (
            <button key={key} onClick={() => setView(key)}
              className="flex-1 rounded-lg p-3 text-left transition-all border"
              style={{
                backgroundColor: view === key ? "#1E293B" : "transparent",
                borderColor: view === key ? d.tagColor + "60" : "#334155",
              }}>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-base">{d.icon}</span>
                <span className="text-xs font-mono px-1.5 py-0.5 rounded" style={{ backgroundColor: d.tagColor + "20", color: d.tagColor }}>{d.tag}</span>
              </div>
              <div className="text-sm font-semibold text-white">{d.label}</div>
              <div className="text-xs text-slate-500 mt-0.5">{d.purpose}</div>
            </button>
          ))}
        </div>

        {/* Source Info */}
        <div className="mb-4 p-3 rounded-lg bg-slate-800/40 border border-slate-700/30 text-xs text-slate-400">
          <span className="text-slate-500">Source:</span> {db.source} &nbsp;|&nbsp;
          <span className="text-slate-500">Refresh:</span> {db.refreshCadence} &nbsp;|&nbsp;
          <span className="text-slate-500">Path:</span> <code className="bg-slate-700/40 px-1 rounded">{db.sourcePath}</code>
        </div>

        {/* Team Tabs */}
        <div className="flex gap-1 mb-5 bg-slate-800/50 rounded-lg p-1">
          {teams.map((t) => {
            const tc = teamColors[t];
            const active = team === t;
            return (
              <button key={t} onClick={() => setTeam(t)}
                className="flex-1 py-2 px-3 rounded-md text-sm font-semibold transition-all"
                style={{
                  backgroundColor: active ? tc.accent + "20" : "transparent",
                  color: active ? tc.mid : "#64748B",
                  borderBottom: active ? `2px solid ${tc.accent}` : "2px solid transparent",
                }}>
                {t}
              </button>
            );
          })}
        </div>

        {/* Cards */}
        <div className="space-y-3">
          {db.cards[team].map((item) => <Card key={item.id} item={item} color={color} />)}
        </div>

        {/* Footer */}
        <div className="mt-6 p-3 rounded-lg bg-slate-800/30 border border-slate-700/30">
          <div className="text-xs text-slate-500 space-y-1">
            <div><span className="font-semibold">Quarterly data:</span> Full master DB snapshot. Requires ≥2 snapshots for trend charts.</div>
            <div><span className="font-semibold">Weekly data:</span> Pulse CLI output. Requires ≥4 pulses for rolling average comparisons.</div>
            <div><span className="font-semibold">Manual inputs needed:</span> capability_score (Marketing Q2), complexity_weight (Operations Q1/Q2), client_list (BD Q2).</div>
          </div>
        </div>
      </div>
    </div>
  );
}
