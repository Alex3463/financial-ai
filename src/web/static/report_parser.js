/** 리포트 Markdown → 유저 친화적 구조로 파싱 */

function stripCitations(text) {
  return (text || "")
    .replace(/\s*\[출처:[^\]]+\]/gi, "")
    .replace(/\s*Co-authored-by:[^\n]+/gi, "")
    .trim();
}

function extractTableRows(md) {
  const rows = [];
  const lines = (md || "").split("\n");
  for (const line of lines) {
    if (!line.trim().startsWith("|")) continue;
    if (/^\|[\s\-:|]+\|$/.test(line.trim())) continue;
    const cells = line
      .split("|")
      .slice(1, -1)
      .map((c) => stripCitations(c.replace(/\*\*/g, "").trim()));
    if (cells.length >= 2 && cells.some(Boolean)) rows.push({ key: cells[0], value: cells.slice(1).join(" · ") });
  }
  return rows;
}

function extractBullets(md) {
  return (md || "")
    .split("\n")
    .filter((l) => /^[-*]\s+/.test(l.trim()))
    .map((l) => stripCitations(l.replace(/^[-*]\s+/, "").trim()))
    .filter(Boolean);
}

function parseReportSections(md) {
  if (!md) return [];
  const body = md.replace(/^#\s+.+\n+/m, "");
  const chunks = body.split(/^###\s+/m).filter((c) => c.trim());
  return chunks.map((chunk) => {
    const nl = chunk.indexOf("\n");
    const title = nl === -1 ? chunk.trim() : chunk.slice(0, nl).trim();
    const content = nl === -1 ? "" : chunk.slice(nl + 1).trim();
    return {
      title,
      rows: extractTableRows(content),
      bullets: extractBullets(content),
      raw: content,
    };
  });
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

  add(pickRow(allRows, "LLM 산정 목표가"), "LLM 목표가", "#60a5fa", 0);
  add(pickRow(allRows, "목표가"), "리포트 목표가", "#3b82f6", 0);
  add(pickRow(allRows, "손절가"), "손절가", "#ef4444", 2);
  add(pickRow(allRows, "컨센서스 평균 목표가", "컨센서스 평균"), "애널리스트 평균", "#c084fc", 2);

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

function parseHero(reportMd, data) {
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
