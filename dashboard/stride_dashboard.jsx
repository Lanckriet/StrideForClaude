import { useState, useEffect, useCallback, useMemo, useRef } from "react";

// ---------------------------------------------------------------------------
// Version — keep in sync with CLI's STRIDE_VERSION and the VERSION file.
// See versioning guidelines in cctrack.py for when to bump.
// ---------------------------------------------------------------------------
const STRIDE_VERSION = "0.1.1";

const G = {
  50: "#EDFCF2", 100: "#C8F5D6", 200: "#8DEBAE", 300: "#4FD882",
  400: "#22C55E", 500: "#16A34A", 600: "#0D7A38", 700: "#065F2B",
  800: "#04472A", 900: "#022E1B",
};

const SAND = {
  50: "#FAFAF7", 100: "#F0F0EA", 200: "#E2E1D9", 300: "#C7C6BB",
  400: "#9E9D91", 500: "#75746A", 600: "#56554D", 700: "#3D3C36",
};

const TAG_COLORS = {
  apex:      { bg: G[50],     text: G[800],   accent: G[400] },
  lwc:       { bg: "#EEF4FF", text: "#1E3A6E", accent: "#5B8DEF" },
  flow:      { bg: "#FFF8EB", text: "#7A4D0B", accent: "#F0A830" },
  config:    { bg: "#FDF2F8", text: "#831843", accent: "#EC4899" },
  scripting: { bg: "#F0FDFA", text: "#134E4A", accent: "#2DD4BF" },
  docs:      { bg: "#FAF5FF", text: "#581C87", accent: "#A855F7" },
  review:    { bg: "#FFF7ED", text: "#7C2D12", accent: "#F97316" },
  other:     { bg: SAND[100], text: SAND[700], accent: SAND[400] },
  untagged:  { bg: SAND[100], text: SAND[700], accent: SAND[400] },
};

const F = "'DM Sans', var(--font-sans)";
const M = "'JetBrains Mono', var(--font-mono)";

const DATE_RANGES = [
  { label: "7d", days: 7 }, { label: "14d", days: 14 },
  { label: "30d", days: 30 }, { label: "90d", days: 90 },
  { label: "All", days: null },
];

function shortModel(n) {
  if (!n) return "unknown";
  const l = n.toLowerCase();
  if (l.includes("opus")) return "Opus";
  if (l.includes("sonnet")) return "Sonnet";
  if (l.includes("haiku")) return "Haiku";
  return n.split("-").slice(0, 2).join(" ");
}

const MC = {
  Opus:    { bg: "#FAF5FF", text: "#581C87", accent: "#A855F7" },
  Sonnet:  { bg: G[50],     text: G[800],    accent: G[500] },
  Haiku:   { bg: "#FFF7ED", text: "#7C2D12", accent: "#F97316" },
  unknown: { bg: SAND[100], text: SAND[700],  accent: SAND[400] },
};

function parseData(raw) {
  return raw.map((r) => {
    const ts = r.started_at || r.timestamp;
    const d = new Date(ts);
    const day = d.getDay();
    const diff = d.getDate() - day + (day === 0 ? -6 : 1);
    const wd = new Date(d); wd.setDate(diff);
    return { ...r, _date: d, _week: wd.toISOString().slice(0, 10) };
  });
}

function filterByRange(data, days) {
  if (!days) return data;
  const c = new Date(); c.setDate(c.getDate() - days);
  return data.filter((r) => r._date >= c);
}

function splitTags(tagStr) {
  if (!tagStr) return ["untagged"];
  const parts = tagStr.split(",").map((t) => t.trim()).filter(Boolean);
  return parts.length ? parts : ["untagged"];
}

function Empty({ msg, sub }) {
  return (
    <div style={{ padding: "2.5rem 1.5rem", textAlign: "center", borderRadius: "12px", background: "var(--color-background-secondary)" }}>
      <div style={{ fontSize: "14px", color: "var(--color-text-secondary)", fontFamily: F }}>{msg}</div>
      {sub && <div style={{ fontSize: "12px", color: "var(--color-text-tertiary)", marginTop: "6px" }}>{sub}</div>}
    </div>
  );
}

function Card({ label, value, sub, accent }) {
  return (
    <div style={{
      background: accent ? G[50] : "var(--color-background-secondary)",
      borderRadius: "12px", padding: "14px 16px", minWidth: 0,
      borderLeft: accent ? `3px solid ${G[400]}` : "3px solid transparent",
    }}>
      <div style={{ fontSize: "11px", fontFamily: F, fontWeight: 500, color: "var(--color-text-secondary)", marginBottom: "6px", textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</div>
      <div style={{ fontSize: "24px", fontWeight: 500, fontFamily: M, color: accent ? G[700] : "var(--color-text-primary)", lineHeight: 1.1 }}>{value}</div>
      {sub && <div style={{ fontSize: "12px", color: "var(--color-text-tertiary)", marginTop: "4px" }}>{sub}</div>}
    </div>
  );
}

function TagPill({ tag }) {
  const c = TAG_COLORS[tag] || TAG_COLORS.other;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "4px", fontSize: "11px", fontWeight: 500, fontFamily: F, padding: "3px 10px", borderRadius: "100px", background: c.bg, color: c.text }}>
      <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: c.accent, flexShrink: 0 }}/>{tag}
    </span>
  );
}

function ModelPill({ model }) {
  const name = shortModel(model);
  const c = MC[name] || MC.unknown;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "4px", fontSize: "11px", fontWeight: 500, fontFamily: M, padding: "2px 8px", borderRadius: "100px", background: c.bg, color: c.text }}>
      <span style={{ width: "5px", height: "5px", borderRadius: "50%", background: c.accent, flexShrink: 0 }}/>{name}
    </span>
  );
}

function DistBar({ data }) {
  const total = data.reduce((s, d) => s + d.value, 0);
  if (!total) return null;
  return (
    <div>
      <div style={{ display: "flex", borderRadius: "8px", overflow: "hidden", height: "10px", background: SAND[100] }}>
        {data.map((d) => { const pct = (d.value / total) * 100; if (pct < 0.5) return null;
          return <div key={d.label} style={{ width: `${pct}%`, background: (TAG_COLORS[d.label]||TAG_COLORS.other).accent, transition: "width 0.4s ease" }}
            title={`${d.label}: ${d.value} (${pct.toFixed(0)}%)`}/>; })}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "12px", marginTop: "10px" }}>
        {data.map((d) => { const c = TAG_COLORS[d.label]||TAG_COLORS.other;
          return <span key={d.label} style={{ display: "flex", alignItems: "center", gap: "5px", fontSize: "12px", color: "var(--color-text-secondary)" }}>
            <span style={{ width: "8px", height: "8px", borderRadius: "2px", background: c.accent }}/>{d.label}
            <span style={{ fontFamily: M, fontSize: "11px", color: "var(--color-text-tertiary)" }}>{d.value}</span>
          </span>; })}
      </div>
    </div>
  );
}

function Models({ data }) {
  const stats = useMemo(() => {
    const m = {};
    data.forEach((r) => { const n = shortModel(r.model); if (!m[n]) m[n] = { count: 0, tokens: 0, cost: 0 };
      m[n].count++; m[n].tokens += (r.total_input_tokens||0) + (r.total_output_tokens||0); m[n].cost += r.estimated_cost_usd||0; });
    return Object.entries(m).map(([name, s]) => ({ name, ...s, avgTokens: Math.round(s.tokens / s.count) })).sort((a, b) => b.count - a.count);
  }, [data]);
  const total = data.length;
  return (
    <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
      {stats.map((s) => { const c = MC[s.name]||MC.unknown; const pct = Math.round((s.count / total) * 100);
        return (
          <div key={s.name} style={{ flex: "1 1 140px", minWidth: "140px", background: "var(--color-background-secondary)", borderRadius: "12px", padding: "14px 16px", borderTop: `3px solid ${c.accent}` }}>
            <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "10px" }}>
              <span style={{ width: "7px", height: "7px", borderRadius: "50%", background: c.accent }}/>
              <span style={{ fontSize: "13px", fontWeight: 500, fontFamily: M, color: c.text }}>{s.name}</span>
              <span style={{ fontSize: "11px", fontFamily: M, color: "var(--color-text-tertiary)", marginLeft: "auto" }}>{pct}%</span>
            </div>
            {[["Sessions", s.count], ["Avg tokens", s.avgTokens.toLocaleString()], ["Total cost", `$${s.cost.toFixed(2)}`]].map(([l, v]) =>
              <div key={l} style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", color: "var(--color-text-secondary)", lineHeight: 1.8 }}>
                <span>{l}</span><span style={{ fontFamily: M }}>{v}</span></div>)}
          </div>); })}
    </div>
  );
}

function Spark({ points, width = 100, height = 24, color = G[500] }) {
  if (!points || points.length < 2) return <span style={{ color: "var(--color-text-tertiary)", fontSize: "11px" }}>--</span>;
  const mn = Math.min(...points), mx = Math.max(...points), rng = mx - mn || 1, p = 2;
  const pts = points.map((v, i) => `${(p + (i / (points.length-1)) * (width-p*2)).toFixed(1)},${(p + (1-(v-mn)/rng)*(height-p*2)).toFixed(1)}`);
  return <svg width={width} height={height} style={{ display: "block" }}><polyline points={pts.join(" ")} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>;
}

function useDarkMode() {
  const [dark, setDark] = useState(() =>
    typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches
  );
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (e) => setDark(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);
  return dark;
}

function useChart(ref, cfg, ready) {
  const inst = useRef(null);
  useEffect(() => { if (!ref.current||!ready||!window.Chart) return; if (inst.current) inst.current.destroy();
    inst.current = new window.Chart(ref.current, cfg); return () => { if (inst.current) inst.current.destroy(); }; }, [cfg, ready]);
}

function Trends({ data, chartReady }) {
  const ref = useRef(null);
  const isDark = useDarkMode();
  const gc = isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.04)";
  const tc = isDark ? "#888" : SAND[400];
  const wm = useMemo(() => { const m = {}; data.forEach((r) => { if (!m[r._week]) m[r._week] = { count: 0, cost: 0 };
    m[r._week].count++; m[r._week].cost += r.estimated_cost_usd||0; }); return m; }, [data]);
  const weeks = Object.keys(wm).sort();
  const cfg = useMemo(() => ({
    type: "line",
    data: { labels: weeks.map((w) => new Date(w+"T00:00:00").toLocaleDateString("en",{month:"short",day:"numeric"})),
      datasets: [
        { label: "Sessions", data: weeks.map((w) => wm[w].count), borderColor: G[500],
          backgroundColor: isDark?"rgba(34,197,94,0.1)":"rgba(34,197,94,0.06)", fill: true, tension: 0.35,
          pointRadius: 3, pointBackgroundColor: G[500], borderWidth: 2, yAxisID: "y" },
        { label: "Cost ($)", data: weeks.map((w) => Math.round(wm[w].cost*100)/100), borderColor: "#F0A830",
          backgroundColor: "transparent", borderDash: [5,3], tension: 0.35, pointRadius: 3,
          pointBackgroundColor: "#F0A830", borderWidth: 1.5, yAxisID: "y1" },
      ] },
    options: { responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: { legend: { display: false }, tooltip: { backgroundColor: isDark?"#1a1a1a":"#fff",
        titleColor: isDark?"#eee":"#333", bodyColor: isDark?"#aaa":"#666",
        borderColor: isDark?"rgba(255,255,255,0.1)":"rgba(0,0,0,0.08)", borderWidth: 1, cornerRadius: 8, padding: 10,
        titleFont: { family: F }, bodyFont: { family: M, size: 12 },
        callbacks: { label: (ctx) => ctx.dataset.yAxisID==="y1"?`Cost: $${ctx.parsed.y.toFixed(2)}`:`Sessions: ${ctx.parsed.y}` } } },
      scales: { x: { grid: { display: false }, ticks: { color: tc, font: { size: 11 } } },
        y: { position: "left", grid: { color: gc }, ticks: { color: tc, font: { size: 11, family: M } },
          title: { display: true, text: "Sessions", color: G[600], font: { size: 11, family: F } } },
        y1: { position: "right", grid: { display: false }, ticks: { color: tc, font: { size: 11, family: M }, callback: (v) => `$${v}` },
          title: { display: true, text: "Cost", color: "#F0A830", font: { size: 11, family: F } } } } },
  }), [weeks, wm, isDark]);
  useChart(ref, cfg, chartReady);
  if (!chartReady || weeks.length < 2) return <Empty msg="Not enough data for trend chart" sub="Need at least 2 weeks of sessions"/>;
  return (<div>
    <div style={{ display: "flex", gap: "16px", marginBottom: "10px", fontSize: "12px", color: "var(--color-text-secondary)" }}>
      <span style={{ display: "flex", alignItems: "center", gap: "5px" }}><span style={{ width: 10, height: 10, borderRadius: 2, background: G[500] }}/>Sessions</span>
      <span style={{ display: "flex", alignItems: "center", gap: "5px" }}><span style={{ width: 10, height: 2, borderTop: "2px dashed #F0A830" }}/>Cost</span>
    </div>
    <div style={{ position: "relative", height: "240px" }}><canvas ref={ref}/></div>
  </div>);
}

function Tokens({ data, chartReady }) {
  const ref = useRef(null);
  const isDark = useDarkMode();
  const ts = useMemo(() => { const m = {}; data.forEach((r) => { splitTags(r.tags).forEach((t) => {
    if (!m[t]) m[t] = { i: 0, o: 0, c: 0 }; m[t].i += r.total_input_tokens||0; m[t].o += r.total_output_tokens||0; m[t].c++; }); });
    return Object.entries(m).map(([tag, s]) => ({ tag, avgIn: Math.round(s.i/s.c), avgOut: Math.round(s.o/s.c) }))
      .sort((a, b) => (b.avgIn+b.avgOut)-(a.avgIn+a.avgOut)); }, [data]);
  const cfg = useMemo(() => ({
    type: "bar", data: { labels: ts.map((s)=>s.tag), datasets: [
      { label: "Avg input", data: ts.map((s)=>s.avgIn), backgroundColor: G[200], borderRadius: 4, barPercentage: 0.65 },
      { label: "Avg output", data: ts.map((s)=>s.avgOut), backgroundColor: G[500], borderRadius: 4, barPercentage: 0.65 }]},
    options: { responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { backgroundColor: isDark?"#1a1a1a":"#fff", titleColor: isDark?"#eee":"#333",
        bodyColor: isDark?"#aaa":"#666", borderColor: isDark?"rgba(255,255,255,0.1)":"rgba(0,0,0,0.08)", borderWidth: 1, cornerRadius: 8,
        bodyFont: { family: M, size: 12 } } },
      scales: { x: { grid: { display: false }, ticks: { color: isDark?"#888":SAND[400], font: { size: 11 }, autoSkip: false } },
        y: { grid: { color: isDark?"rgba(255,255,255,0.06)":"rgba(0,0,0,0.04)" },
          ticks: { color: isDark?"#888":SAND[400], font: { size: 11, family: M } } } } },
  }), [ts, isDark]);
  useChart(ref, cfg, chartReady);
  if (!chartReady) return null;
  return (<div>
    <div style={{ display: "flex", gap: "16px", marginBottom: "10px", fontSize: "12px", color: "var(--color-text-secondary)" }}>
      <span style={{ display: "flex", alignItems: "center", gap: "5px" }}><span style={{ width: 10, height: 10, borderRadius: 2, background: G[200] }}/>Avg input</span>
      <span style={{ display: "flex", alignItems: "center", gap: "5px" }}><span style={{ width: 10, height: 10, borderRadius: 2, background: G[500] }}/>Avg output</span>
    </div>
    <div style={{ position: "relative", height: "220px" }}><canvas ref={ref}/></div>
  </div>);
}

function Tags({ data }) {
  const stats = useMemo(() => { const m = {};
    data.forEach((r) => { splitTags(r.tags).forEach((t) => { if (!m[t]) m[t] = { count: 0, lat: [], tok: [], cost: 0, wk: {} };
      m[t].count++; if (r.duration_ms) m[t].lat.push(r.duration_ms);
      m[t].tok.push((r.total_input_tokens||0)+(r.total_output_tokens||0)); m[t].cost += r.estimated_cost_usd||0;
      if (!m[t].wk[r._week]) m[t].wk[r._week] = 0; m[t].wk[r._week]++; }); });
    return Object.entries(m).map(([tag, s]) => {
      const avgD = s.lat.length ? s.lat.reduce((a,b)=>a+b,0)/s.lat.length : 0;
      const avgT = s.tok.length ? s.tok.reduce((a,b)=>a+b,0)/s.tok.length : 0;
      const wks = Object.keys(s.wk).sort();
      return { tag, count: s.count, avgD, avgT, cost: s.cost, cps: s.count?s.cost/s.count:0, spark: wks.map((w)=>s.wk[w]) };
    }).sort((a,b)=>b.count-a.count); }, [data]);
  const th = { textAlign: "left", padding: "10px 12px", fontWeight: 500, fontSize: "11px", color: "var(--color-text-secondary)",
    textTransform: "uppercase", letterSpacing: "0.04em", fontFamily: F, borderBottom: `1px solid ${SAND[200]}` };
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
        <thead><tr>
          <th style={th}>Tag</th><th style={{...th,textAlign:"right"}}>Sessions</th>
          <th style={{...th,textAlign:"center"}}>Activity</th><th style={{...th,textAlign:"right"}}>Avg duration</th>
          <th style={{...th,textAlign:"right"}}>Avg tokens</th><th style={{...th,textAlign:"right"}}>Cost/session</th>
          <th style={{...th,textAlign:"right"}}>Total cost</th>
        </tr></thead>
        <tbody>{stats.map((s,i) => (
          <tr key={s.tag} style={{ borderBottom: i<stats.length-1?"0.5px solid var(--color-border-tertiary)":"none" }}>
            <td style={{ padding: "12px 12px 12px 0" }}><TagPill tag={s.tag}/></td>
            <td style={{ textAlign: "right", padding: "12px", fontFamily: M, fontWeight: 500 }}>{s.count}</td>
            <td style={{ textAlign: "center", padding: "12px" }}><Spark points={s.spark} color={(TAG_COLORS[s.tag]||TAG_COLORS.other).accent}/></td>
            <td style={{ textAlign: "right", padding: "12px", fontFamily: M, color: "var(--color-text-secondary)" }}>{s.avgD?`${(s.avgD/1000/60).toFixed(1)}m`:"--"}</td>
            <td style={{ textAlign: "right", padding: "12px", fontFamily: M, color: "var(--color-text-secondary)" }}>{Math.round(s.avgT).toLocaleString()}</td>
            <td style={{ textAlign: "right", padding: "12px", fontFamily: M, color: "var(--color-text-secondary)" }}>${s.cps.toFixed(2)}</td>
            <td style={{ textAlign: "right", padding: "12px", fontFamily: M, color: "var(--color-text-secondary)" }}>${s.cost.toFixed(2)}</td>
          </tr>))}</tbody>
      </table>
    </div>
  );
}

function Ratings({ data }) {
  const rated = useMemo(() => data.filter((r) => r.rating), [data]);
  if (!rated.length) return <Empty msg="No rated sessions in this period" sub="Use stride rate to add ratings after sessions"/>;
  const avg = rated.reduce((s,r)=>s+r.rating,0)/rated.length;
  const dist = useMemo(() => { const d=[0,0,0,0,0]; rated.forEach((r)=>d[r.rating-1]++); return d; }, [rated]);
  const mx = Math.max(...dist, 1);
  const byTag = useMemo(() => { const m = {};
    rated.forEach((r) => { splitTags(r.tags).forEach((t) => { if (!m[t]) m[t] = { r: [], wr: {} };
      m[t].r.push(r.rating); if (!m[t].wr[r._week]) m[t].wr[r._week]=[]; m[t].wr[r._week].push(r.rating); }); });
    return Object.entries(m).map(([tag, s]) => {
      const a = s.r.reduce((x,y)=>x+y,0)/s.r.length;
      const wks = Object.keys(s.wr).sort();
      return { tag, count: s.r.length, avg: a, spark: wks.map((w)=>s.wr[w].reduce((x,y)=>x+y,0)/s.wr[w].length) };
    }).sort((a,b)=>b.avg-a.avg); }, [rated]);
  return (<div>
    <div style={{ display: "flex", gap: "16px", marginBottom: "2rem", flexWrap: "wrap" }}>
      <div style={{ background: "var(--color-background-secondary)", borderRadius: "12px", padding: "16px 20px", minWidth: "160px" }}>
        <div style={{ fontSize: "11px", fontFamily: F, fontWeight: 500, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "6px" }}>Avg rating</div>
        <div style={{ fontFamily: M, fontSize: "28px", fontWeight: 500, color: G[700] }}>{avg.toFixed(1)}<span style={{ fontSize: "14px", color: "var(--color-text-tertiary)", fontWeight: 400 }}>/5</span></div>
        <div style={{ fontSize: "12px", color: "var(--color-text-tertiary)", marginTop: "4px" }}>{rated.length} of {data.length} rated ({Math.round(rated.length/data.length*100)}%)</div>
      </div>
      <div style={{ flex: 1, minWidth: "200px" }}>
        <div style={{ fontSize: "11px", fontFamily: F, fontWeight: 500, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "10px" }}>Distribution</div>
        {[5,4,3,2,1].map((n)=>(<div key={n} style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
          <span style={{ fontSize: "12px", fontFamily: M, width: "14px", textAlign: "right", color: "var(--color-text-secondary)" }}>{n}</span>
          <div style={{ flex: 1, height: "14px", background: SAND[100], borderRadius: "4px", overflow: "hidden" }}>
            <div style={{ width: `${(dist[n-1]/mx)*100}%`, height: "100%", background: n>=4?G[400]:n===3?"#F0A830":"#ef4444", borderRadius: "4px", transition: "width 0.3s ease" }}/></div>
          <span style={{ fontSize: "11px", fontFamily: M, width: "28px", color: "var(--color-text-tertiary)" }}>{dist[n-1]}</span>
        </div>))}
      </div>
    </div>
    {byTag.length > 0 && (<div>
      <div style={{ fontSize: "11px", fontFamily: F, fontWeight: 500, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "12px" }}>By tag</div>
      <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
        {byTag.map((s)=>(
          <div key={s.tag} style={{ display: "flex", alignItems: "center", gap: "12px", padding: "10px 12px", borderRadius: "8px", background: "var(--color-background-secondary)" }}>
            <TagPill tag={s.tag}/>
            <span style={{ fontFamily: M, fontSize: "14px", fontWeight: 500, color: G[700] }}>{s.avg.toFixed(1)}</span>
            <span style={{ fontSize: "11px", color: "var(--color-text-tertiary)", fontFamily: M }}>({s.count} rated)</span>
            <div style={{ marginLeft: "auto" }}><Spark points={s.spark} color={(TAG_COLORS[s.tag]||TAG_COLORS.other).accent} width={80}/></div>
          </div>))}
      </div>
    </div>)}
  </div>);
}

function Issues({ data }) {
  const fails = useMemo(() =>
    data.filter((r) => r.exit_status==="error"||(r.rating&&r.rating<=2))
      .sort((a,b)=>new Date(b.started_at||b.timestamp)-new Date(a.started_at||a.timestamp)).slice(0,30), [data]);
  if (!fails.length) return <Empty msg="No failures or low-rated sessions" sub="Keep it up."/>;
  return (<div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
    {fails.map((f,i)=>(
      <div key={i} style={{ display: "flex", alignItems: "center", gap: "8px", padding: "10px 12px", borderRadius: "8px",
        background: i%2===0?"transparent":"var(--color-background-secondary)", fontSize: "13px" }}>
        <span style={{ fontSize: "11px", color: "var(--color-text-tertiary)", minWidth: "55px", fontFamily: M }}>
          {new Date(f.started_at||f.timestamp).toLocaleDateString("en",{month:"short",day:"numeric"})}</span>
        {f.model && <ModelPill model={f.model}/>}
        {f.tags && splitTags(f.tags).filter((t)=>t!=="untagged").map((t)=><TagPill key={t} tag={t}/>)}
        <span style={{ flex: 1, color: "var(--color-text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {f.prompt_summary||"(no summary)"}</span>
        <span style={{ flexShrink: 0, display: "flex", gap: "6px", alignItems: "center" }}>
          {f.exit_status==="error" && <span style={{ fontSize: "10px", fontWeight: 500, fontFamily: M, padding: "2px 7px", borderRadius: "100px", background: "#fef2f2", color: "#dc2626" }}>error</span>}
          {f.rating && <span style={{ fontFamily: M, fontSize: "12px", fontWeight: 500, color: "#F0A830" }}>{f.rating}/5</span>}
          {f.note && <span title={f.note} style={{ fontSize: "11px", color: "var(--color-text-tertiary)", cursor: "help", borderBottom: "1px dotted var(--color-border-secondary)" }}>note</span>}
        </span>
      </div>))}
  </div>);
}

function Upload({ onData }) {
  const [drag, setDrag] = useState(false);
  const ref = useRef(null);
  const handle = useCallback((file) => {
    const r = new FileReader();
    r.onload = (e) => { try { const j = JSON.parse(e.target.result); if (Array.isArray(j)) onData(j); else alert("Expected JSON array."); } catch { alert("Could not parse JSON."); } };
    r.readAsText(file);
  }, [onData]);
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "3rem 2rem", minHeight: "360px" }}>
      <div style={{ marginBottom: "2rem", textAlign: "center" }}>
        <div style={{ marginBottom: "4px" }}>
          <span style={{ fontFamily: F, fontSize: "28px", fontWeight: 500, color: G[700], letterSpacing: "-0.02em" }}>Stride</span>
          <span style={{ fontFamily: F, fontSize: "15px", fontWeight: 400, color: "var(--color-text-tertiary)", marginLeft: "8px" }}>for Claude</span>
        </div>
        <div style={{ fontSize: "14px", color: "var(--color-text-secondary)", fontFamily: F }}>Claude Code performance insights</div>
      </div>
      <div onDragOver={(e)=>{e.preventDefault();setDrag(true);}} onDragLeave={()=>setDrag(false)}
        onDrop={(e)=>{e.preventDefault();setDrag(false);if(e.dataTransfer.files[0])handle(e.dataTransfer.files[0]);}}
        onClick={()=>ref.current?.click()}
        style={{ border: `2px dashed ${drag?G[400]:SAND[200]}`, borderRadius: "16px", padding: "2.5rem 2rem",
          textAlign: "center", cursor: "pointer", transition: "all 0.2s", width: "100%", maxWidth: "400px", background: drag?G[50]:"transparent" }}>
        <div style={{ width: "48px", height: "48px", borderRadius: "12px", background: G[50], display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 12px" }}>
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M10 3v10M6 7l4-4 4 4M3 14v1a2 2 0 002 2h10a2 2 0 002-2v-1" stroke={G[500]} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
        </div>
        <div style={{ fontSize: "14px", fontWeight: 500, color: "var(--color-text-primary)", fontFamily: F, marginBottom: "6px" }}>Load your export</div>
        <div style={{ fontSize: "12px", color: "var(--color-text-secondary)", lineHeight: 1.6 }}>
          Drop <code style={{ fontSize: "11px", fontFamily: M, background: SAND[100], padding: "1px 5px", borderRadius: "4px" }}>export.json</code> here or click to browse</div>
        <div style={{ fontSize: "11px", color: "var(--color-text-tertiary)", marginTop: "8px", fontFamily: M }}>stride export</div>
        <input ref={ref} type="file" accept=".json" style={{ display: "none" }} onChange={(e)=>{if(e.target.files[0])handle(e.target.files[0]);}}/>
      </div>
    </div>
  );
}

function Sec({ title, children }) {
  return <div style={{ marginBottom: "2rem" }}>
    <h3 style={{ fontSize: "11px", fontWeight: 500, fontFamily: F, color: "var(--color-text-secondary)", marginBottom: "12px", textTransform: "uppercase", letterSpacing: "0.06em" }}>{title}</h3>
    {children}</div>;
}

function Pills({ options, value, onChange, mono }) {
  return (
    <div style={{ display: "inline-flex", gap: "2px", background: "var(--color-background-secondary)", borderRadius: "8px", padding: "2px" }}>
      {options.map((o)=>(<button key={o.value} onClick={()=>onChange(o.value)} style={{
        padding: "4px 10px", fontSize: "11px", fontFamily: mono?M:F,
        fontWeight: value===o.value?500:400, color: value===o.value?"#fff":"var(--color-text-secondary)",
        background: value===o.value?G[500]:"transparent", border: "none", borderRadius: "6px",
        cursor: "pointer", transition: "all 0.15s", whiteSpace: "nowrap",
      }}>{o.label}</button>))}
    </div>
  );
}

export default function StrideDashboard() {
  const [raw, setRaw] = useState(null);
  const [tab, setTab] = useState("overview");
  const [cr, setCr] = useState(false);
  const [rd, setRd] = useState(null);
  const [proj, setProj] = useState("all");

  useEffect(() => {
    const l = document.createElement("link");
    l.href = "https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500&family=JetBrains+Mono:wght@400;500&display=swap";
    l.rel = "stylesheet"; document.head.appendChild(l);
    const s = document.createElement("script");
    s.src = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js";
    s.onload = () => setCr(true); document.head.appendChild(s);
  }, []);

  useEffect(() => {
    (async () => { try { const r = await window.storage.get("stride-data");
      if (r?.value) { const p = JSON.parse(r.value); if (Array.isArray(p)&&p.length) setRaw(parseData(p)); }
    } catch {} })();
  }, []);

  const handleData = useCallback(async (r) => {
    setRaw(parseData(r)); try { await window.storage.set("stride-data", JSON.stringify(r)); } catch {}
  }, []);

  const projects = useMemo(() => {
    if (!raw) return []; return [...new Set(raw.map((r)=>r.project_name).filter(Boolean))].sort();
  }, [raw]);

  const data = useMemo(() => {
    if (!raw) return null;
    let d = filterByRange(raw, rd);
    if (proj !== "all") d = d.filter((r) => r.project_name === proj);
    return d;
  }, [raw, rd, proj]);

  const sum = useMemo(() => {
    if (!data||!data.length) return null;
    const n = data.length;
    const fc = data.filter((r)=>r.exit_status==="error").length;
    const cost = data.reduce((s,r)=>s+(r.estimated_cost_usd||0),0);
    const tok = data.reduce((s,r)=>s+(r.total_input_tokens||0)+(r.total_output_tokens||0),0);
    const dur = data.reduce((s,r)=>s+(r.duration_ms||0),0)/n;
    const code = data.filter((r)=>r.code_generated).length;
    const td = {}; data.forEach((r)=>{splitTags(r.tags).forEach((t)=>{td[t]=(td[t]||0)+1;});});
    return { n, fc, fr: (fc/n)*100, cost, tok, dur, code, td };
  }, [data]);

  if (!raw) return <Upload onData={handleData}/>;

  const tabs = [
    { id: "overview", label: "Overview" }, { id: "tags", label: "By tag" },
    { id: "tokens", label: "Tokens" }, { id: "ratings", label: "Ratings" },
    { id: "failures", label: "Issues" },
  ];

  return (
    <div style={{ fontFamily: F }}>
      <div style={{ background: "#6B7F4E", borderRadius: "0 0 14px 14px", padding: "14px 1.25rem", marginBottom: "1rem",
        display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "8px" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: "6px" }}>
          <span style={{ fontSize: "16px", fontWeight: 500, color: "#E8EDDF", letterSpacing: "-0.01em" }}>Stride</span>
          <span style={{ fontSize: "11px", fontWeight: 400, color: "#A4B494" }}>for Claude</span>
          <span style={{ fontSize: "11px", color: "#A4B494", fontFamily: M, marginLeft: "4px",
            borderLeft: "0.5px solid rgba(255,255,255,0.15)", paddingLeft: "8px" }}>{data?data.length:0} sessions</span>
          <span style={{ fontSize: "10px", color: "rgba(164,180,148,0.6)", fontFamily: M }}>v{STRIDE_VERSION}</span>
        </div>
        <button onClick={()=>{setRaw(null);window.storage.delete("stride-data").catch(()=>{});}}
          style={{ fontSize: "11px", color: "#A4B494", background: "none", border: "none", cursor: "pointer",
            fontFamily: F, textDecoration: "underline", textUnderlineOffset: "3px" }}>Reset data</button>
      </div>

      <div style={{ padding: "0 1.25rem 1rem" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "8px", marginBottom: "1rem" }}>
          <Pills mono options={DATE_RANGES.map((r)=>({label:r.label,value:r.days}))} value={rd} onChange={setRd}/>
          {projects.length > 1 && <Pills options={[{label:"All projects",value:"all"},...projects.map((p)=>({label:p,value:p}))]} value={proj} onChange={setProj}/>}
        </div>

        <div style={{ display: "flex", gap: "2px", marginBottom: "1.5rem", borderBottom: "1px solid var(--color-border-tertiary)" }}>
          {tabs.map((t)=>(<button key={t.id} onClick={()=>setTab(t.id)} style={{
            padding: "8px 16px", fontSize: "13px", fontFamily: F, fontWeight: tab===t.id?500:400,
            color: tab===t.id?G[700]:"var(--color-text-secondary)", background: "transparent", border: "none", cursor: "pointer",
            borderBottom: tab===t.id?`2px solid ${G[500]}`:"2px solid transparent", marginBottom: "-1px", transition: "all 0.15s",
          }}>{t.label}</button>))}
        </div>

        {(!data||!data.length) && <Empty msg="No sessions match these filters" sub="Try a wider date range or different project"/>}

        {tab==="overview"&&sum&&(<>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: "10px", marginBottom: "2rem" }}>
            <Card label="Sessions" value={sum.n} accent/>
            <Card label="Est. cost" value={`$${sum.cost.toFixed(2)}`} accent/>
            <Card label="Total tokens" value={sum.tok>1e6?`${(sum.tok/1e6).toFixed(1)}M`:`${Math.round(sum.tok/1000)}K`}/>
            <Card label="Avg duration" value={`${(sum.dur/1000/60).toFixed(1)}m`}/>
            <Card label="Failure rate" value={`${sum.fr.toFixed(0)}%`} sub={`${sum.fc} failed`}/>
            <Card label="Code generated" value={`${Math.round((sum.code/sum.n)*100)}%`} sub={`${sum.code} of ${sum.n}`}/>
          </div>
          <Sec title="Task distribution"><DistBar data={Object.entries(sum.td).map(([l,v])=>({label:l,value:v})).sort((a,b)=>b.value-a.value)}/></Sec>
          <Sec title="Model usage"><Models data={data}/></Sec>
          <Sec title="Weekly trends"><Trends data={data} chartReady={cr}/></Sec>
        </>)}

        {tab==="tags"&&data&&data.length>0&&<Sec title="Performance by tag"><Tags data={data}/></Sec>}
        {tab==="tokens"&&data&&data.length>0&&<Sec title="Token usage by tag"><Tokens data={data} chartReady={cr}/></Sec>}
        {tab==="ratings"&&data&&<Sec title="Quality ratings"><Ratings data={data}/></Sec>}
        {tab==="failures"&&data&&<Sec title="Failures and low-rated sessions"><Issues data={data}/></Sec>}
      </div>
    </div>
  );
}
