/** 리포트 Markdown → 유저 친화적 구조로 파싱 */

function stripCitations(text) {
  return (text || "")
    .replace(/\s*\[출처:[^\]]+\]/gi, "")
    .replace(/\s*Co-authored-by:[^\n]+/gi, "")
    .trim();
}

function parseTableCells(line) {
  return line
    .split("|")
    .slice(1, -1)
    .map((c) => stripCitations(c.replace(/`/g, "").replace(/\*\*/g, "").trim()));
}

function extractMarkdownTables(md) {
  const tables = [];
  const lines = (md || "").split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i].trim();
    if (!line.startsWith("|")) {
      i++;
      continue;
    }
    const headers = parseTableCells(line);
    i++;
    if (i >= lines.length || !/^\|[\s\-:|]+\|$/.test(lines[i].trim())) continue;
    i++;
    const rows = [];
    while (i < lines.length && lines[i].trim().startsWith("|")) {
      if (/^\|[\s\-:|]+\|$/.test(lines[i].trim())) {
        i++;
        continue;
      }
      rows.push(parseTableCells(lines[i]));
      i++;
    }
    if (headers.length >= 2 && rows.length) tables.push({ headers, rows });
  }
  return tables;
}

function extractTableRows(md) {
  const kv = extractMarkdownTables(md).find((t) => t.headers.length === 2);
  if (!kv) return [];
  return kv.rows
    .filter((cells) => cells.some(Boolean))
    .map((cells) => ({ key: cells[0], value: cells[1] }));
}

function extractBullets(md) {
  return (md || "")
    .split("\n")
    .filter((l) => /^[-*]\s+/.test(l.trim()))
    .map((l) => stripCitations(l.replace(/^[-*]\s+/, "").trim()))
    .filter(Boolean);
}

function proseBlockKind(text) {
  const t = (text || "").trim();
  if (!t) return "skip";
  if (t.length < 90 && !/[.。\]%]$/.test(t)) return "heading";
  return "paragraph";
}

function extractProseBlocks(md) {
  const blocks = [];
  const lines = (md || "").split("\n");
  let buf = [];
  const flush = () => {
    if (!buf.length) return;
    const text = stripCitations(buf.join(" ").trim());
    buf = [];
    const kind = proseBlockKind(text);
    if (kind !== "skip") blocks.push({ kind, text });
  };
  for (const line of lines) {
    const t = line.trim();
    if (!t) {
      flush();
      continue;
    }
    if (t.startsWith("|") || /^[-*]\s+/.test(t) || t.startsWith("####")) {
      flush();
      continue;
    }
    buf.push(t);
  }
  flush();
  return blocks;
}

function extractSubsections(md) {
  const parts = (md || "").split(/^####\s+/m);
  if (parts.length <= 1) return [];
  return parts.slice(1).map((chunk) => {
    const nl = chunk.indexOf("\n");
    const title = nl === -1 ? chunk.trim() : chunk.slice(0, nl).trim();
    const content = nl === -1 ? "" : chunk.slice(nl + 1).trim();
    return {
      title,
      bullets: extractBullets(content),
      prose: extractProseBlocks(content),
    };
  });
}

function parseReportTitle(md) {
  const m = (md || "").match(/^#\s+(.+)$/m);
  return m ? stripCitations(m[1].trim()) : "";
}

function parseReportSections(md) {
  if (!md) return [];
  const body = md.replace(/^#\s+.+\n+/m, "");
  const chunks = body.split(/^###\s+/m).filter((c) => c.trim());
  return chunks.map((chunk) => {
    const nl = chunk.indexOf("\n");
    const title = nl === -1 ? chunk.trim() : chunk.slice(0, nl).trim();
    const content = nl === -1 ? "" : chunk.slice(nl + 1).trim();
    const main = content.split(/^####\s+/m)[0].trim();
    return {
      title,
      rows: extractTableRows(main),
      tables: extractMarkdownTables(content),
      bullets: extractBullets(main),
      subsections: extractSubsections(content),
      prose: extractProseBlocks(main),
      raw: content,
    };
  });
}

function etfSectionKind(title) {
  const t = title || "";
  if (/요약/.test(t)) return "summary";
  if (/보유|구성/.test(t)) return "holdings";
  if (/운용|비용/.test(t)) return "operations";
  if (/리스크/.test(t)) return "risk";
  if (/모멘텀|시장/.test(t)) return "momentum";
  if (/전략/.test(t)) return "strategy";
  return "generic";
}

function etfSectionNumber(title) {
  const m = (title || "").match(/^(\d+)\./);
  return m ? m[1] : null;
}

function pickRow(rows, ...keys) {
  for (const k of keys) {
    const row = rows.find((r) => r.key.includes(k));
    if (row) return row.value;
  }
  return null;
}

/** "307.50달러", "310.51" 등에서 숫자 추출 */
function parsePriceNumber(text) {
  if (text == null || text === "") return null;
  if (typeof text === "number") return Number.isFinite(text) ? text : null;
  const s = String(text).replace(/,/g, "");
  const m = s.match(/([\d]+(?:\.\d+)?)/);
  if (!m) return null;
  const n = parseFloat(m[1]);
  return Number.isFinite(n) && n > 0 ? n : null;
}

/** 차트 참고선: 리포트·컨센서스·기술적 가격 */
function extractChartLevels(data) {
  const levels = [];
  const seen = new Set();
  const etf = isEtfReport(data);

  const add = (price, label, color, lineStyle = 2) => {
    const p = parsePriceNumber(price);
    if (p == null) return;
    const key = Math.round(p * 100);
    if (seen.has(key)) return;
    seen.add(key);
    levels.push({ price: p, label, color, lineStyle });
  };

  const snapPrice = data?.snapshot_summary?.price || {};
  const ctx = data?.context || {};
  const consensus = ctx.consensus_summary || {};
  const tech = ctx.price_technicals || {};
  const info = data?.snapshot_summary?.info || ctx?.metadata || {};

  const sections = parseReportSections(data?.report_md || "");
  const allRows = sections.flatMap((s) => s.rows);

  if (!etf) {
    add(pickRow(allRows, "LLM 산정 목표가"), "LLM 목표가", "#60a5fa", 0);
    add(pickRow(allRows, "목표가"), "리포트 목표가", "#3b82f6", 0);
    add(pickRow(allRows, "손절가"), "손절가", "#ef4444", 2);
    add(pickRow(allRows, "컨센서스 평균 목표가", "컨센서스 평균"), "애널리스트 평균", "#c084fc", 2);
  }

  const rangeText = pickRow(allRows, "컨센서스 목표가 범위");
  if (rangeText) {
    const parts = String(rangeText).match(/([\d.,]+)\s*[~\-–]\s*([\d.,]+)/);
    if (parts) {
      add(parts[1], "컨센서스 하단", "#94a3b8", 3);
      add(parts[2], "컨센서스 상단", "#94a3b8", 3);
    }
  }

  add(consensus.target_mean_price ?? info.targetMeanPrice, "애널리스트 평균", "#c084fc", 2);
  add(consensus.target_low_price ?? info.targetLowPrice, "애널리스트 하단", "#94a3b8", 3);
  add(consensus.target_high_price ?? info.targetHighPrice, "애널리스트 상단", "#94a3b8", 3);
  add(tech.atr_stop_loss_candidate, "ATR 손절", "#f87171", 2);
  add(tech.support_stop_loss_candidate, "지지 손절", "#fb923c", 2);
  add(snapPrice.current, "현재가", "#fbbf24", 0);
  add(snapPrice["52w_high"], "52주 고가", "#4ade8066", 3);
  add(snapPrice["52w_low"], "52주 저가", "#f8717166", 3);

  return levels.slice(0, 10);
}

function parseOpinion(text) {
  const t = stripCitations(text || "");
  const m = t.match(/(강력\s*매수|매수|중립|보유|관망|매도|강력\s*매도)/);
  return m ? m[1] : t.slice(0, 12) || "—";
}

function opinionClass(opinion) {
  const o = opinion || "";
  if (/매수/.test(o) && !/매도/.test(o)) return "buy";
  if (/매도/.test(o)) return "sell";
  return "hold";
}

const ETF_ASSET_TYPES = new Set(["ETF", "FUND", "MUTUALFUND", "ETN"]);

function isEtfReport(data) {
  const at = String(data?.context?.metadata?.asset_type || data?.overview?.asset_type || "")
    .trim()
    .toUpperCase();
  if (ETF_ASSET_TYPES.has(at)) return true;
  const md = data?.report_md || "";
  return /ETF\s*분석\s*리포트/i.test(md);
}

function fundProfileFromData(data) {
  return data?.context?.fund_profile || data?.snapshot_summary?.fund || {};
}

function formatPct(value, digits = 2) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  const pct = n <= 1 && n > 0 ? n * 100 : n;
  return `${pct.toFixed(digits)}%`;
}

function formatAum(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  return fmtNum(n, 0);
}

const SECTOR_LABELS = {
  technology: "기술",
  financial_services: "금융",
  communication_services: "통신",
  healthcare: "헬스케어",
  consumer_cyclical: "경기소비재",
  consumer_defensive: "필수소비재",
  industrials: "산업",
  energy: "에너지",
  utilities: "유틸리티",
  basic_materials: "소재",
  realestate: "부동산",
};

function sectorEntries(sectorWeightings) {
  if (!sectorWeightings || typeof sectorWeightings !== "object") return [];
  return Object.entries(sectorWeightings)
    .map(([k, v]) => ({
      key: k,
      label: SECTOR_LABELS[k] || k.replace(/_/g, " "),
      weight: Number(v),
    }))
    .filter((e) => Number.isFinite(e.weight) && e.weight > 0)
    .sort((a, b) => b.weight - a.weight);
}

function parseEtfHero(reportMd, data) {
  const sections = parseReportSections(reportMd);
  const summary = sections.find((s) => /ETF\s*요약|요약/.test(s.title)) || sections[0];
  const strategy = sections.find((s) => /투자\s*전략/.test(s.title));
  const riskSec = sections.find((s) => /리스크/.test(s.title));
  const rows = summary?.rows || [];
  const o = data.overview || {};
  const sig = data.signal || {};
  const ev = data.eval || {};
  const fund = fundProfileFromData(data);
  const ops = fund.fund_operations || {};

  const opinionRaw = pickRow(rows, "투자 의견") || sig.signal || "—";
  const opinion = parseOpinion(String(opinionRaw).replace(/\(조건부\)/g, "").trim());

  return {
    isEtf: true,
    opinion,
    opinionClass: opinionClass(opinion),
    etfNature: pickRow(rows, "ETF 성격"),
    theme: pickRow(rows, "핵심 테마"),
    current: pickRow(rows, "현재가") || (o.current_price != null ? `${fmtNum(o.current_price)}` : null),
    horizon: pickRow(rows, "투자 기간") || sig.time_horizon,
    dataAvailability: pickRow(rows, "데이터 가용성"),
    event: pickRow(rows, "지금 봐야"),
    community: pickRow(rows, "커뮤니티"),
    expenseRatio: ops.expense_ratio != null ? formatPct(ops.expense_ratio, 3) : null,
    turnover: ops.holdings_turnover != null ? formatPct(ops.holdings_turnover, 2) : null,
    aum: ops.total_net_assets != null ? formatAum(ops.total_net_assets) : null,
    topHoldings: (fund.top_holdings || []).slice(0, 10),
    sectors: sectorEntries(fund.sector_weightings).slice(0, 8),
    assetClasses: fund.asset_classes || {},
    grade: ev.grade || o.grade,
    score: ev.score_normalized_100 ?? o.score_normalized_100,
    confidence: sig.confidence ?? o.confidence,
    signal: sig.signal,
    sections,
    strategyBullets: (strategy?.bullets || []).slice(0, 4),
    riskBullets: (riskSec?.bullets || []).slice(0, 5),
    thesis: sig.thesis_bullets || [],
    risks: sig.risk_triggers || [],
  };
}

function parseHero(reportMd, data) {
  if (isEtfReport(data)) return parseEtfHero(reportMd, data);
  const sections = parseReportSections(reportMd);
  const summary = sections.find((s) => /투자 요약|요약/.test(s.title)) || sections[0];
  const conclusion = sections.find((s) => /결론/.test(s.title));
  const valuation = sections.find((s) => /밸류|valuation/i.test(s.title));

  const rows = summary?.rows || [];
  const o = data.overview || {};
  const sig = data.signal || {};
  const ev = data.eval || {};

  const opinion = pickRow(rows, "투자 의견") || sig.signal || "—";
  const current = pickRow(rows, "현재가") || (o.current_price != null ? `${fmtNum(o.current_price)}` : null);
  const target = pickRow(rows, "목표가");
  const stop = pickRow(rows, "손절가");
  const horizon = pickRow(rows, "투자 기간") || sig.time_horizon;
  const catalyst = pickRow(rows, "핵심 쟁점");
  const event = pickRow(rows, "지금 봐야");

  return {
    opinion: parseOpinion(opinion),
    opinionClass: opinionClass(parseOpinion(opinion)),
    current,
    target,
    stop,
    horizon,
    catalyst,
    event,
    bullets: (summary?.bullets || []).slice(0, 4),
    conclusionBullets: (conclusion?.bullets || []).slice(0, 3),
    thesis: sig.thesis_bullets || [],
    risks: sig.risk_triggers || [],
    grade: ev.grade || o.grade,
    score: ev.score_normalized_100 ?? o.score_normalized_100,
    confidence: sig.confidence ?? o.confidence,
    signal: sig.signal,
    sections,
  };
}

// fmtNum from app.js scope when bundled in browser - duplicate minimal version
function fmtNum(n, digits = 2) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return Number(n).toLocaleString(undefined, { maximumFractionDigits: digits });
}
