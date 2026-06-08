const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

let pollTimer = null;
let currentData = null;
let chartRangeMonths = 6;
let _chartPrice = null;
let _chartTicker = null;
let _chartData = null;

function getDashboardToken() {
  const params = new URLSearchParams(location.search);
  const fromQuery = params.get("token");
  if (fromQuery) {
    sessionStorage.setItem("dashboard_token", fromQuery);
    return fromQuery;
  }
  return sessionStorage.getItem("dashboard_token") || "";
}

function apiHeaders(json = false) {
  const headers = {};
  if (json) headers["Content-Type"] = "application/json";
  const token = getDashboardToken();
  if (token) headers["X-Dashboard-Token"] = token;
  return headers;
}

const TABS = [
  { id: "summary", label: "요약" },
  { id: "report", label: "리포트" },
  { id: "news", label: "뉴스" },
  { id: "board", label: "종토방" },
  { id: "details", label: "상세 데이터" },
];

function fmtNum(n, digits = 2) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return Number(n).toLocaleString(undefined, { maximumFractionDigits: digits });
}

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s ?? "";
  return d.innerHTML;
}

function signalBadge(sig) {
  const s = (sig || "hold").toLowerCase();
  const label = { buy: "매수", sell: "매도", hold: "관망" }[s] || s.toUpperCase();
  return `<span class="badge ${s}">${label}</span>`;
}

function buildTabs() {
  const tabsEl = $("#tabs");
  const panelsEl = $("#panels");
  tabsEl.innerHTML = "";
  panelsEl.innerHTML = "";
  TABS.forEach((t, i) => {
    const btn = document.createElement("button");
    btn.className = "tab" + (i === 0 ? " active" : "");
    btn.dataset.tab = t.id;
    btn.textContent = t.label;
    btn.addEventListener("click", () => switchTab(t.id));
    tabsEl.appendChild(btn);

    const panel = document.createElement("div");
    panel.className = "tab-panel" + (i === 0 ? " active" : "");
    panel.id = `panel-${t.id}`;
    panelsEl.appendChild(panel);
  });
}

function switchTab(id) {
  $$(".tab").forEach((el) => el.classList.toggle("active", el.dataset.tab === id));
  $$(".tab-panel").forEach((el) => el.classList.toggle("active", el.id === `panel-${id}`));
  if (id === "details" && _chartPrice) {
    requestAnimationFrame(() => mountPriceChart(_chartTicker, _chartPrice));
  }
}

function renderSectionCard(section) {
  const rows = section.rows || [];
  const bullets = section.bullets || [];
  let inner = "";

  if (rows.length) {
    inner += `<dl class="kv-list">${rows
      .map(
        (r) =>
          `<div class="kv-row"><dt>${esc(r.key)}</dt><dd>${esc(r.value)}</dd></div>`
      )
      .join("")}</dl>`;
  }
  if (bullets.length) {
    inner += `<ul class="clean-list">${bullets.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>`;
  }
  if (!inner) return "";

  return `<article class="section-card">
    <h3 class="section-title">${esc(section.title)}</h3>
    ${inner}
  </article>`;
}

function renderSummary(data) {
  const o = data.overview || {};
  const hero = parseHero(data.report_md || "", data);
  const el = $("#panel-summary");

  const metrics = [
    { label: "현재가", value: hero.current },
    { label: "목표가", value: hero.target },
    { label: "손절가", value: hero.stop },
    { label: "투자 기간", value: hero.horizon },
  ].filter((m) => m.value);

  const thesis = hero.thesis.length ? hero.thesis : hero.bullets;
  const risks = hero.risks.length ? hero.risks : [];
  const sentimentBanner = renderSummarySentimentBanner(data);
  const comm = (data.community || {}).summary || {};
  const boardHint =
    comm.status === "ok" && comm.n
      ? `<div class="highlight-box board-hint ${boardMoodClass(comm.sentiment_score)}">
          <span class="highlight-label">종토방 여론 (Yahoo)</span>
          <p>긍정 ${(comm.pos_ratio * 100).toFixed(0)}% · 부정 ${(comm.neg_ratio * 100).toFixed(0)}% · ${comm.n}건
          <span class="muted-inline"> — <a href="#" class="tab-link" data-tab="board">종토방 탭</a>에서 전체 보기</span></p>
        </div>`
      : "";

  el.innerHTML = `
    <div class="hero">
      <div class="hero-top">
        <div>
          <p class="hero-ticker">${esc(data.ticker)} · ${esc(o.company_name || data.ticker)}</p>
          <p class="hero-date">${esc(data.date)}${data.cached || data.cache_hit ? ' <span class="badge cached">캐시</span>' : ""}</p>
        </div>
        <div class="hero-opinion opinion-${hero.opinionClass}">${esc(hero.opinion)}</div>
      </div>
      <div class="hero-metrics">
        ${metrics.map((m) => `<div class="metric"><span>${esc(m.label)}</span><strong>${esc(m.value)}</strong></div>`).join("")}
      </div>
      <div class="hero-footer">
        <div>시스템 신호 ${signalBadge(hero.signal)}</div>
        <div>신뢰도 ${hero.confidence != null ? (hero.confidence * 100).toFixed(0) + "%" : "—"}</div>
        <div>품질 ${esc(hero.grade || "—")} · ${fmtNum(hero.score, 0)}점</div>
      </div>
    </div>

    ${sentimentBanner}
    ${boardHint}
    ${hero.catalyst ? `<div class="highlight-box"><span class="highlight-label">핵심 쟁점</span><p>${esc(hero.catalyst)}</p></div>` : ""}
    ${hero.event ? `<div class="highlight-box warn"><span class="highlight-label">지금 봐야 할 이벤트</span><p>${esc(hero.event)}</p></div>` : ""}

    ${thesis.length ? `<section class="block"><h3>핵심 근거</h3><ul class="clean-list">${thesis.slice(0, 5).map((t) => `<li>${esc(t)}</li>`).join("")}</ul></section>` : ""}
    ${risks.length ? `<section class="block risk"><h3>리스크 트리거</h3><ul class="clean-list">${risks.slice(0, 5).map((t) => `<li>${esc(t)}</li>`).join("")}</ul></section>` : ""}
    ${hero.conclusionBullets.length ? `<section class="block"><h3>한 줄 결론</h3><ul class="clean-list">${hero.conclusionBullets.map((t) => `<li>${esc(t)}</li>`).join("")}</ul></section>` : ""}
  `;
  el.querySelectorAll(".tab-link").forEach((a) => {
    a.addEventListener("click", (e) => {
      e.preventDefault();
      switchTab(a.dataset.tab);
    });
  });
}

function renderReport(data) {
  const hero = parseHero(data.report_md || "", data);
  const el = $("#panel-report");
  const cards = (hero.sections || []).map(renderSectionCard).filter(Boolean).join("");

  el.innerHTML = cards
    ? `<div class="section-grid">${cards}</div>`
    : `<p class="muted-center">리포트 본문이 없습니다.</p>`;
}

function sentimentCssClass(label) {
  const map = { positive: "sent-pos", negative: "sent-neg", neutral: "sent-neu" };
  return map[(label || "").toLowerCase()] || "sent-neu";
}

function renderSentimentBar(s) {
  if (!s) return "";
  const p = Math.round((s.positive || 0) * 100);
  const n = Math.round((s.negative || 0) * 100);
  const u = Math.max(0, 100 - p - n);
  return `<div class="sentiment-bar" aria-label="긍정 ${p}% 중립 ${u}% 부정 ${n}%">
    <span class="sent-seg pos" style="width:${p}%"></span>
    <span class="sent-seg neu" style="width:${u}%"></span>
    <span class="sent-seg neg" style="width:${n}%"></span>
  </div>
  <div class="sentiment-legend">
    <span class="leg pos">긍정 ${p}%</span>
    <span class="leg neu">중립 ${u}%</span>
    <span class="leg neg">부정 ${n}%</span>
  </div>`;
}

function renderSentimentBadge(s) {
  if (!s) return "";
  const cls = sentimentCssClass(s.sentiment_label);
  const score = s.sentiment_score != null ? Number(s.sentiment_score).toFixed(2) : "—";
  const label = s.sentiment_label_ko || s.sentiment_label || "—";
  return `<span class="sentiment-badge ${cls}" title="sentiment_score = 긍정 − 부정">${esc(label)} <small>${score}</small></span>`;
}

function renderSentimentHero(sa) {
  if (!sa || sa.skipped || sa.error) return "";
  const agg = sa.aggregate || {};
  if (!agg.article_count) return "";
  const cls = sentimentCssClass(agg.sentiment_label);
  const avg = agg.avg_score != null ? Number(agg.avg_score).toFixed(3) : "—";
  return `<section class="sentiment-hero ${cls}">
    <div class="sentiment-hero-top">
      <span class="sentiment-model">FinBERT</span>
      <span class="sentiment-hero-label">종합 뉴스 감성</span>
    </div>
    <div class="sentiment-hero-value">${esc(agg.sentiment_label_ko || agg.sentiment_label)}</div>
    <div class="sentiment-hero-score">평균 ${avg} <span class="muted-inline">· ${agg.article_count}건 · +1 긍정 / −1 부정</span></div>
  </section>`;
}

function averageArticleScores(articles) {
  if (!articles?.length) return null;
  const n = articles.length;
  return {
    positive: articles.reduce((s, a) => s + (a.positive || 0), 0) / n,
    negative: articles.reduce((s, a) => s + (a.negative || 0), 0) / n,
    neutral: articles.reduce((s, a) => s + (a.neutral || 0), 0) / n,
  };
}

function needsSentimentLoad(data) {
  const n = data.news_enrichment || {};
  const sa = n.sentiment_analysis;
  if (sa?.articles?.length || sa?.skipped) return false;
  return !!((n.deep_read_articles || []).length || (n.company_relevant_articles || []).length);
}

function renderSummarySentimentBanner(data) {
  const sa = (data.news_enrichment || {}).sentiment_analysis || {};
  if (sa.skipped) return "";
  if (sa.error) {
    return `<section class="summary-sentiment-banner sent-neu"><p class="sentiment-error">뉴스 감성분석 오류: ${esc(sa.error)}</p></section>`;
  }
  const agg = sa.aggregate || {};
  const articles = sa.articles || [];
  if (!agg.article_count && !articles.length) return "";

  const cls = sentimentCssClass(agg.sentiment_label);
  const avg = agg.avg_score != null ? Number(agg.avg_score).toFixed(3) : "—";
  const avgBar = averageArticleScores(articles);

  const listItems = articles.slice(0, 6).map((a) => {
    const title = (a.title || "").trim();
    const short = title.length > 72 ? `${title.slice(0, 70)}…` : title;
    return `<li class="summary-sent-item ${sentimentCssClass(a.sentiment_label)}">
      ${renderSentimentBadge(a)}
      <span class="summary-sent-title">${esc(short)}</span>
    </li>`;
  }).join("");

  return `<section class="summary-sentiment-banner ${cls}">
    <div class="summary-sent-head">
      <div class="summary-sent-head-left">
        <span class="sentiment-model">FinBERT</span>
        <h3 class="summary-sent-heading">최근 뉴스 감성 요약</h3>
      </div>
      <div class="summary-sent-aggregate">
        <span class="summary-sent-label">${esc(agg.sentiment_label_ko || agg.sentiment_label)}</span>
        <span class="summary-sent-avg">평균 ${avg}</span>
        <span class="muted-inline">${agg.article_count}건</span>
      </div>
    </div>
    ${avgBar ? renderSentimentBar(avgBar) : ""}
    ${listItems ? `<ul class="summary-sent-list">${listItems}</ul>` : ""}
    <p class="summary-sent-hint muted-inline">뉴스 탭에서 기사별 상세 감성을 확인할 수 있습니다.</p>
  </section>`;
}

function lookupSentiment(article, sa) {
  if (article.sentiment) return article.sentiment;
  const url = (article.url || article.link || "").replace(/\/$/, "");
  const title = (article.title || article.headline || "").trim().toLowerCase();
  const rows = sa?.articles || [];
  return rows.find((r) => {
    const ru = (r.url || "").replace(/\/$/, "");
    if (url && ru && url === ru) return true;
    return title && (r.title || "").trim().toLowerCase() === title;
  });
}

async function ensureSentiment(data) {
  const n = data.news_enrichment || {};
  const sa = n.sentiment_analysis;
  if (sa?.articles?.length || sa?.skipped) return data;
  if (!data.ticker || !data.date) return data;
  const deep = n.deep_read_articles || [];
  const fallback = n.company_relevant_articles || [];
  if (!deep.length && !fallback.length) return data;
  try {
    const res = await fetch(
      `/api/sentiment/${encodeURIComponent(data.ticker)}/${encodeURIComponent(data.date)}`,
      { method: "POST", headers: apiHeaders() }
    );
    if (res.ok) {
      const body = await res.json();
      data.news_enrichment = { ...n, sentiment_analysis: body.sentiment_analysis };
      currentData = data;
    }
  } catch (_) {}
  return data;
}

function renderNews(data) {
  const n = data.news_enrichment || {};
  const sa = n.sentiment_analysis || {};
  const deep = n.deep_read_articles || [];
  const articles = deep.length ? deep : n.company_relevant_articles || [];
  const el = $("#panel-news");

  if (!articles.length) {
    el.innerHTML = `<p class="muted-center">관련 뉴스가 없습니다.</p>`;
    return;
  }

  if (sa.error) {
    el.innerHTML = `${renderSentimentHero(sa)}
      <p class="sentiment-error">감성분석 오류: ${esc(sa.error)}</p>`;
    return;
  }

  const hero = renderSentimentHero(sa);
  const cards = articles.slice(0, 10).map((a) => {
    const title = a.title || a.headline || "(제목 없음)";
    const bullets = a.summary_bullets;
    const sum = Array.isArray(bullets) && bullets.length
      ? bullets.map((b) => esc(b)).join(" ")
      : esc((a.summary || a.digest || "").slice(0, 200));
    const url = a.url || a.link || "";
    const sent = lookupSentiment(a, sa);
    return `<article class="news-card ${sent ? sentimentCssClass(sent.sentiment_label) : ""}">
      <div class="news-card-head">
        <h3>${esc(title)}</h3>
        ${sent ? renderSentimentBadge(sent) : ""}
      </div>
      ${sent ? renderSentimentBar(sent) : ""}
      ${sum ? `<p>${sum}</p>` : ""}
      ${url ? `<a href="${esc(url)}" target="_blank" rel="noopener">원문 보기 →</a>` : ""}
    </article>`;
  }).join("");

  el.innerHTML = `${hero}<div class="news-grid">${cards}</div>`;
}

function formatBoardTime(raw) {
  if (!raw) return "";
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return String(raw).slice(0, 16);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 3600) return `${Math.max(1, Math.floor(diff / 60))}분 전`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}시간 전`;
  return d.toLocaleDateString("ko-KR", { month: "short", day: "numeric" });
}

function boardMoodClass(score) {
  if (score == null || Number.isNaN(Number(score))) return "sent-neu";
  const s = Number(score);
  if (s > 0.1) return "sent-pos";
  if (s < -0.1) return "sent-neg";
  return "sent-neu";
}

function renderBoardSummaryBar(summary) {
  if (!summary || summary.status !== "ok") return "";
  const score = summary.sentiment_score;
  const cls = boardMoodClass(score);
  const pos = summary.pos_ratio != null ? `${(summary.pos_ratio * 100).toFixed(0)}%` : "—";
  const neg = summary.neg_ratio != null ? `${(summary.neg_ratio * 100).toFixed(0)}%` : "—";
  const terms = (summary.top_terms || []).slice(0, 6);
  const moodLabel = score > 0.1 ? "긍정 우세" : score < -0.1 ? "부정 우세" : "중립";
  return `<div class="board-summary ${cls}">
    <div class="board-summary-row">
      <span class="board-mood">${esc(moodLabel)}</span>
      <span class="muted-inline">긍정 ${pos} · 부정 ${neg} · 점수 ${Number(score).toFixed(2)}</span>
    </div>
    ${terms.length ? `<div class="board-keywords">${terms.map((t) => `<span class="kw-tag">#${esc(t)}</span>`).join("")}</div>` : ""}
    <p class="board-disclaimer muted-inline">${esc(summary.note || "리테일 커뮤니티 여론(참고).")}</p>
  </div>`;
}

function renderCommunityBoard(data) {
  const el = $("#panel-board");
  const pack = data.community || {};
  const raw = pack.raw || {};
  const summary = pack.summary || {};
  const posts = raw.conversations || [];
  const source = raw.source_url || summary.source_url || "";

  if (!posts.length && (raw.status === "error" || summary.status !== "ok")) {
    const err = raw.error || summary.note || "커뮤니티 글을 가져오지 못했습니다.";
    el.innerHTML = `<section class="board-empty">
      <h3>Yahoo Finance 종토방</h3>
      <p>${esc(err)}</p>
      <p class="muted-inline">일시적 네트워크 오류·티커 미지원 시 실패할 수 있습니다. (수집: Yahoo GraphQL community API)</p>
      <div class="board-actions">
        <button type="button" class="secondary-btn" id="board-refresh">다시 수집</button>
        ${source ? `<a class="secondary-btn link-btn" href="${esc(source)}" target="_blank" rel="noopener">Yahoo 원문</a>` : ""}
      </div>
    </section>`;
    $("#board-refresh")?.addEventListener("click", () => refreshCommunity(data));
    return;
  }

  if (!posts.length) {
    el.innerHTML = `<section class="board-empty">
      <h3>종토방</h3>
      <p class="muted-center">표시할 게시글이 없습니다.</p>
      <button type="button" class="secondary-btn" id="board-refresh">다시 수집</button>
    </section>`;
    $("#board-refresh")?.addEventListener("click", () => refreshCommunity(data));
    return;
  }

  const summaryBar = renderBoardSummaryBar(summary);
  const list = posts
    .map((p) => {
      const author = p.author || "익명";
      const body = p.text || "";
      const votes = p.upvotes != null ? `👍 ${p.upvotes}` : "";
      const mood = boardMoodClass(
        /매수|buy|bull|상승|moon/i.test(body) && !/매도|sell|bear|하락/i.test(body)
          ? 0.2
          : /매도|sell|bear|하락|dump|crash/i.test(body)
            ? -0.2
            : 0
      );
      return `<li class="board-post ${mood}">
        <div class="post-meta">
          <span class="post-author">${esc(author)}</span>
          <span class="post-time">${esc(formatBoardTime(p.created_at))}</span>
          ${votes ? `<span class="post-votes">${votes}</span>` : ""}
        </div>
        <p class="post-body">${esc(body)}</p>
      </li>`;
    })
    .join("");

  el.innerHTML = `
    <section class="board-panel">
      <div class="board-head">
        <div>
          <h3 class="board-title">Yahoo Finance · 종목 토론방</h3>
          <p class="muted-inline">${posts.length}건 · 참고용 리테일 여론</p>
        </div>
        <div class="board-actions">
          <button type="button" class="secondary-btn" id="board-refresh">새로고침</button>
          ${source ? `<a class="secondary-btn link-btn" href="${esc(source)}" target="_blank" rel="noopener">Yahoo</a>` : ""}
        </div>
      </div>
      ${summaryBar}
      <ul class="board-posts">${list}</ul>
    </section>`;
  $("#board-refresh")?.addEventListener("click", () => refreshCommunity(data));
}

async function refreshCommunity(data) {
  if (!data.ticker || !data.date) return;
  const el = $("#panel-board");
  el.innerHTML = `<p class="muted-center">Yahoo 종토방 수집 중…</p>`;
  try {
    const res = await fetch(
      `/api/community/${encodeURIComponent(data.ticker)}/${encodeURIComponent(data.date)}`,
      { method: "POST", headers: apiHeaders() }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(err.detail || "수집 실패");
      renderCommunityBoard(data);
      return;
    }
    const body = await res.json();
    data.community = body.community;
    currentData = data;
    renderCommunityBoard(data);
  } catch (_) {
    alert("수집 요청 실패");
    renderCommunityBoard(data);
  }
}

function renderDetailsAccordion(title, contentHtml, open = false) {
  return `<details class="accordion" ${open ? "open" : ""}>
    <summary>${esc(title)}</summary>
    <div class="accordion-body">${contentHtml}</div>
  </details>`;
}

function renderDetails(data) {
  const s = data.snapshot_summary || {};
  const price = s.price || {};
  const ctx = data.context || {};
  const ev = data.eval || {};
  const sig = data.signal || {};
  const bd = ev.breakdown || {};
  const scoreItems = Object.entries(bd)
    .map(([k, v]) => `<div class="score-item"><span>${esc(k)}</span><strong>${v}</strong></div>`)
    .join("");

  const hasChart = price.daily_close && Object.keys(price.daily_close).length > 1;
  const rangeBtns = [3, 6, 12]
    .map(
      (m) =>
        `<button type="button" class="range-btn${chartRangeMonths === m ? " active" : ""}" data-months="${m}">${m}M</button>`
    )
    .join("");

  const el = $("#panel-details");
  el.innerHTML = `
    ${
      hasChart
        ? `<section class="chart-panel">
      <div class="chart-header">
        <div>
          <h3 class="chart-title">${esc(data.ticker)} 주가</h3>
          <p class="chart-sub" id="chart-stats">—</p>
        </div>
        <div class="range-group">${rangeBtns}</div>
      </div>
      <div id="price-chart" class="price-chart"></div>
      <div id="chart-legend" class="chart-legend"></div>
      <p class="chart-note">일봉 캔들 · 목표가·손절·컨센서스는 리포트·context 기준 참고선</p>
    </section>`
        : `<p class="muted-center">차트용 일봉 데이터가 없습니다.</p>`
    }
    ${renderDetailsAccordion(
      "시장 데이터",
      `<div class="mini-cards">
        <div><span>52주</span><strong>${fmtNum(s.price?.["52w_low"])} – ${fmtNum(s.price?.["52w_high"])}</strong></div>
        <div><span>PER</span><strong>${fmtNum(s.info?.trailingPE)}</strong></div>
        <div><span>시총</span><strong>${s.info?.marketCap ? (s.info.marketCap / 1e9).toFixed(1) + "B" : "—"}</strong></div>
      </div>`
    )}
    ${renderDetailsAccordion(
      "평가 점수",
      `<div class="score-grid">${scoreItems || "<p>—</p>"}</div>
       <p class="grade-note">${esc(ev.grade_note || "")}</p>`
    )}
    ${renderDetailsAccordion("원본 JSON (snapshot)", `<pre class="json-block">${esc(JSON.stringify(s, null, 2))}</pre>`)}
    ${renderDetailsAccordion("원본 JSON (context)", `<pre class="json-block">${esc(JSON.stringify(ctx, null, 2))}</pre>`)}
    ${renderDetailsAccordion("원본 JSON (signal)", `<pre class="json-block">${esc(JSON.stringify(sig, null, 2))}</pre>`)}
  `;

  _chartTicker = data.ticker;
  _chartPrice = hasChart ? price : null;
  _chartData = hasChart ? data : null;

  if (hasChart) {
    el.querySelectorAll(".range-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        chartRangeMonths = Number(btn.dataset.months);
        el.querySelectorAll(".range-btn").forEach((b) => b.classList.toggle("active", b === btn));
        mountPriceChart(_chartTicker, _chartPrice);
      });
    });
    if ($("#panel-details")?.classList.contains("active")) {
      requestAnimationFrame(() => mountPriceChart(_chartTicker, _chartPrice));
    }
  }
}

function mountPriceChart(ticker, price) {
  const container = $("#price-chart");
  const stats = $("#chart-stats");
  const legend = $("#chart-legend");
  if (!container) return;

  const levels = _chartData ? extractChartLevels(_chartData) : [];
  const result = renderPriceChart(container, price, ticker, chartRangeMonths, levels);
  if (!result || !stats) return;

  const chg = result.changePct;
  const chgClass = chg >= 0 ? "up" : "down";
  const chgSign = chg >= 0 ? "+" : "";
  stats.innerHTML = `
    <strong>${fmtNum(result.last)}</strong>
    <span class="chg ${chgClass}">${chgSign}${chg?.toFixed(2) ?? "—"}%</span>
    <span class="muted-inline">· 52주 ${fmtNum(price["52w_low"])} – ${fmtNum(price["52w_high"])}</span>
  `;

  if (legend) {
    const shown = result.levels || [];
    legend.innerHTML = shown.length
      ? shown
          .map(
            (lv) =>
              `<span class="legend-item"><i style="background:${lv.color}"></i>${esc(lv.label)} <strong>${fmtNum(lv.price)}</strong></span>`
          )
          .join("")
      : `<span class="muted-inline">참고선 데이터 없음 (리포트·context 확인)</span>`;
  }
}

async function renderAll(data) {
  currentData = data;
  destroyPriceChart();
  if (data.ticker && data.date) {
    history.replaceState(null, "", `#${data.ticker}/${data.date}`);
  }
  $("#empty").style.display = "none";
  $("#results").style.display = "block";

  if (needsSentimentLoad(data)) {
    $("#panel-summary").innerHTML =
      `<p class="muted-center sentiment-loading">FinBERT 뉴스 감성분석 중…<br><span class="muted-inline">첫 실행은 모델 로딩으로 수십 초 걸릴 수 있습니다</span></p>`;
    data = await ensureSentiment(data);
    currentData = data;
  }

  renderReport(data);
  renderSummary(currentData);
  renderNews(currentData);
  renderCommunityBoard(currentData);
  renderDetails(currentData);
  switchTab("summary");
}

function appendProgress(lines) {
  const box = $("#progress");
  box.classList.add("active");
  box.textContent = lines.join("\n");
  box.scrollTop = box.scrollHeight;
}

async function loadHistory() {
  const res = await fetch("/api/history");
  const { items } = await res.json();
  const list = $("#history");
  list.innerHTML = items.length
    ? items.map((it) => `<button type="button" class="history-item" data-ticker="${esc(it.ticker)}" data-date="${esc(it.date)}">${esc(it.ticker)} · ${esc(it.date)}</button>`).join("")
    : "<p class='muted-small'>저장된 실행 이력 없음</p>";
  list.querySelectorAll(".history-item").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const res = await fetch(`/api/runs/${btn.dataset.ticker}/${btn.dataset.date}`);
      if (!res.ok) return alert("불러오기 실패");
      renderAll(await res.json());
    });
  });
}

function setRunning(running) {
  $("#submit").disabled = running;
  $("#submit-spinner").hidden = !running;
  $("#submit-label").textContent = running ? "분석 중…" : "리포트 생성";
}

async function pollJob(jobId) {
  const res = await fetch(`/api/jobs/${jobId}`);
  const job = await res.json();
  appendProgress(job.progress || []);
  if (job.status === "running" || job.status === "pending") {
    pollTimer = setTimeout(() => pollJob(jobId), 1500);
    return;
  }
  setRunning(false);
  if (job.status === "done" && job.result) {
    await renderAll(job.result);
    loadHistory();
  } else if (job.status === "error") {
    alert("실행 실패: " + (job.error || "unknown"));
  }
}

$("#form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (pollTimer) clearTimeout(pollTimer);
  const ticker = $("#ticker").value.trim();
  if (!ticker) return;

  setRunning(true);
  $("#progress").textContent = "";
  $("#progress").classList.add("active");

  const dateVal = $("#date").value.trim();
  const body = {
    ticker,
    date: dateVal || null,
    skip_llm: $("#skip_llm").checked,
    no_judge: $("#no_judge").checked,
    judge: $("#judge").checked,
    force_refresh: $("#force_refresh").checked,
  };

  const res = await fetch("/api/analyze", {
    method: "POST",
    headers: apiHeaders(true),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    setRunning(false);
    const err = await res.json().catch(() => ({}));
    const msg = err.detail || (res.status === 401 ? "API 토큰이 필요합니다. URL에 ?token= 을 확인하세요." : "요청 실패");
    return alert(msg);
  }
  const { job_id } = await res.json();
  pollJob(job_id);
});

async function loadInfo() {
  try {
    const res = await fetch("/api/info");
    const info = await res.json();
    if (info.disclaimer) $("#disclaimer").textContent = info.disclaimer;
    const gh = $("#github-banner");
    if (gh && info.github_url) {
      gh.href = info.github_url;
      const slug = info.github_url.replace(/\/$/, "").split("/").slice(-2).join("/");
      if (slug) gh.querySelector("span").textContent = slug;
    }
    if (info.public_url) {
      const box = $("#share-box");
      const link = $("#public-url");
      const token = getDashboardToken();
      const share = token ? `${info.public_url}?token=${encodeURIComponent(token)}` : info.public_url;
      link.href = share;
      link.textContent = share;
      box.hidden = false;
    }
    if (info.auth_required_for_analyze && !getDashboardToken()) {
      $("#disclaimer").textContent +=
        " · 분석 실행에는 URL의 ?token= 파라미터가 필요합니다.";
    }
  } catch (_) {}
}

$("#copy-url")?.addEventListener("click", async () => {
  const url = $("#public-url")?.href;
  if (!url) return;
  try {
    await navigator.clipboard.writeText(url);
    $("#copy-url").textContent = "복사됨!";
    setTimeout(() => { $("#copy-url").textContent = "복사"; }, 2000);
  } catch (_) {
    prompt("링크를 복사하세요:", url);
  }
});

async function loadFromHash() {
  const hash = location.hash.replace(/^#/, "").trim();
  if (!hash) return;
  const [ticker, date] = hash.split("/");
  if (!ticker) return;
  if (date) {
    const res = await fetch(`/api/runs/${encodeURIComponent(ticker)}/${encodeURIComponent(date)}`);
    if (res.ok) renderAll(await res.json());
  } else {
    $("#ticker").value = ticker.toUpperCase();
  }
}

async function updateCacheHint() {
  const ticker = $("#ticker").value.trim().toUpperCase();
  const dateVal = $("#date").value.trim();
  const hint = $("#cache-hint");
  if (!ticker || $("#force_refresh").checked) {
    hint.hidden = true;
    return;
  }
  try {
    const url = dateVal
      ? `/api/cache/${encodeURIComponent(ticker)}?date=${encodeURIComponent(dateVal)}`
      : `/api/cache/${encodeURIComponent(ticker)}`;
    const res = await fetch(url);
    const data = await res.json();
    if (data.complete) {
      hint.textContent = `${data.ticker} · ${data.date}: 저장된 리포트가 있습니다.`;
      hint.hidden = false;
    } else {
      hint.hidden = true;
    }
  } catch (_) {
    hint.hidden = true;
  }
}

$("#ticker")?.addEventListener("input", () => setTimeout(updateCacheHint, 300));
$("#date")?.addEventListener("change", updateCacheHint);
$("#force_refresh")?.addEventListener("change", updateCacheHint);

async function loadVisitors() {
  const box = $("#visitors");
  if (!box) return;
  try {
    const res = await fetch("/api/visitors", { headers: apiHeaders() });
    const data = await res.json();
    if (data.detail_requires_auth) {
      box.innerHTML = `<p class="muted-small">접속 약 ${data.active_count}명 · IP 상세는 토큰 인증 후 표시</p>`;
      return;
    }
    const active = data.active || [];
    if (!active.length) {
      box.innerHTML = `<p class="muted-small">현재 접속자 없음 <span style="opacity:0.7">(최근 ${data.active_window_sec / 60}분 기준)</span></p>`;
      return;
    }
    box.innerHTML = `
      <p class="count">접속 중 약 ${data.active_count}명</p>
      ${active
        .map(
          (v) =>
            `<div class="visitor-row"><strong>${esc(v.ip)}</strong> · ${esc(v.user_agent)}<br><span>${v.seconds_ago}초 전 · ${esc(v.last_path)}</span></div>`
        )
        .join("")}
      <p class="muted-small" style="margin-top:0.4rem">IP는 터널/프록시 기준일 수 있습니다.</p>
    `;
  } catch (_) {
    box.innerHTML = `<p class="muted-small">접속 정보를 불러올 수 없습니다.</p>`;
  }
}

setInterval(loadVisitors, 12000);
buildTabs();
loadHistory();
loadInfo();
loadFromHash();
loadVisitors();
