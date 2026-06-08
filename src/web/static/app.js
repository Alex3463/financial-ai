const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

let pollTimer = null;
let currentData = null;

const TABS = [
  { id: "overview", label: "개요" },
  { id: "data", label: "1/5 데이터" },
  { id: "news", label: "뉴스" },
  { id: "context", label: "2/5 컨텍스트" },
  { id: "report", label: "3/5 리포트" },
  { id: "eval", label: "4/5 평가" },
  { id: "signal", label: "5/5 신호" },
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

function renderMarkdown(md) {
  if (typeof marked !== "undefined") {
    return marked.parse(md || "");
  }
  return `<pre>${esc(md)}</pre>`;
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
}

function signalBadge(sig) {
  const s = (sig || "hold").toLowerCase();
  return `<span class="badge ${s}">${s.toUpperCase()}</span>`;
}

function renderOverview(data) {
  const o = data.overview || {};
  const el = $("#panel-overview");
  el.innerHTML = `
    <div class="cards">
      <div class="card"><div class="label">티커</div><div class="value">${esc(data.ticker)}</div></div>
      <div class="card"><div class="label">회사</div><div class="value">${esc(o.company_name)}</div></div>
      <div class="card"><div class="label">섹터</div><div class="value">${esc(o.sector || "—")}</div></div>
      <div class="card"><div class="label">현재가</div><div class="value">${fmtNum(o.current_price)}</div></div>
      <div class="card"><div class="label">신호</div><div class="value">${signalBadge(o.signal)}</div></div>
      <div class="card"><div class="label">신뢰도</div><div class="value">${o.confidence != null ? (o.confidence * 100).toFixed(0) + "%" : "—"}</div></div>
      <div class="card"><div class="label">등급</div><div class="value" style="font-size:0.85rem">${esc(o.grade || "—")}</div></div>
      <div class="card"><div class="label">점수(100)</div><div class="value">${fmtNum(o.score_normalized_100, 1)}</div></div>
    </div>
    <p style="color:var(--muted);font-size:0.85rem">
      기준일: ${esc(data.date)}
      ${data.cached || data.cache_hit ? ' · <span class="badge cached">캐시 사용</span>' : ""}
      · 산출 경로: <code>${esc(data.paths?.artifacts_dir || "")}</code>
    </p>
  `;
}

function renderData(data) {
  const s = data.snapshot_summary || {};
  const price = s.price || {};
  const info = s.info || {};
  const el = $("#panel-data");
  el.innerHTML = `
    <div class="cards">
      <div class="card"><div class="label">수집 시각</div><div class="value" style="font-size:0.8rem">${esc(s.fetched_at)}</div></div>
      <div class="card"><div class="label">52주 고/저</div><div class="value" style="font-size:0.85rem">${fmtNum(price["52w_high"])} / ${fmtNum(price["52w_low"])}</div></div>
      <div class="card"><div class="label">PER</div><div class="value">${fmtNum(info.trailingPE)}</div></div>
      <div class="card"><div class="label">Forward PER</div><div class="value">${fmtNum(info.forwardPE)}</div></div>
      <div class="card"><div class="label">시가총액</div><div class="value" style="font-size:0.85rem">${info.marketCap ? (info.marketCap / 1e9).toFixed(1) + "B" : "—"}</div></div>
      <div class="card"><div class="label">뉴스 후보</div><div class="value">${s.news_count ?? 0}건</div></div>
    </div>
    <h3 style="font-size:0.9rem;color:var(--muted)">snapshot 요약 (JSON)</h3>
    <pre class="json-block">${esc(JSON.stringify(s, null, 2))}</pre>
  `;
}

function formatArticleSummary(a) {
  const bullets = a.summary_bullets;
  if (Array.isArray(bullets) && bullets.length) {
    return bullets.map((b) => esc(b)).join(" · ");
  }
  const sum = a.summary || a.digest || "";
  return sum ? esc(sum.slice(0, 280)) : "";
}

function renderNews(data) {
  const n = data.news_enrichment || {};
  const status = n.status || {};
  const deep = n.deep_read_articles || [];
  const articles = deep.length ? deep : n.company_relevant_articles || [];
  const failures = n.failures || [];
  const el = $("#panel-news");
  let list = "";
  if (articles.length) {
    list = "<ul class='bullets'>" + articles.slice(0, 8).map((a) => {
      const title = a.title || a.headline || "(제목 없음)";
      const sum = formatArticleSummary(a);
      const url = a.url || a.link || "";
      const link = url ? ` <a href="${esc(url)}" target="_blank" rel="noopener" style="color:#93c5fd;font-size:0.8rem">원문</a>` : "";
      return `<li><strong>${esc(title)}</strong>${link}${sum ? "<br><span style='color:var(--muted)'>" + sum + "</span>" : ""}</li>`;
    }).join("") + "</ul>";
  } else {
    list = "<p style='color:var(--muted)'>심층 읽기 기사가 없거나 수집되지 않았습니다.</p>";
  }
  if (failures.length) {
    list += `<h3 style="font-size:0.9rem;color:var(--danger);margin-top:1rem">실패 ${failures.length}건</h3><ul class="bullets">${failures.slice(0, 5).map((f) => `<li>${esc(f.title || f.url)} — <span style="color:var(--muted)">${esc((f.error || "").slice(0, 120))}</span></li>`).join("")}</ul>`;
  }
  el.innerHTML = `
    <div class="cards">
      <div class="card"><div class="label">선택</div><div class="value">${status.selected_count ?? 0}</div></div>
      <div class="card"><div class="label">심층 읽기 성공</div><div class="value">${status.deep_read_count ?? 0}</div></div>
      <div class="card"><div class="label">실패</div><div class="value">${status.failed_count ?? 0}</div></div>
    </div>
    ${list}
    <h3 style="font-size:0.9rem;color:var(--muted);margin-top:1rem">enrichment (JSON)</h3>
    <pre class="json-block">${esc(JSON.stringify(n, null, 2))}</pre>
  `;
}

function renderContext(data) {
  const ctx = data.context || {};
  const ps = ctx.price_summary || {};
  const val = ctx.valuation || {};
  const fin = ctx.financials || {};
  const tok = data.token_check || ctx._token_check || {};
  const el = $("#panel-context");
  el.innerHTML = `
    <div class="cards">
      <div class="card"><div class="label">1M 수익률</div><div class="value">${fmtNum(ps.returns?.return_1m)}%</div></div>
      <div class="card"><div class="label">12M 수익률</div><div class="value">${fmtNum(ps.returns?.return_12m)}%</div></div>
      <div class="card"><div class="label">변동성(연)</div><div class="value">${fmtNum(ps.vol_annual, 4)}</div></div>
      <div class="card"><div class="label">EV/EBITDA</div><div class="value">${fmtNum(val.EV_EBITDA)}</div></div>
      <div class="card"><div class="label">컨텍스트 토큰</div><div class="value">${tok.context_tokens ?? "—"}</div></div>
      <div class="card"><div class="label">예산 내</div><div class="value">${tok.within_budget ? "✓" : "✗"}</div></div>
    </div>
    <h3 style="font-size:0.9rem;color:var(--muted)">분기 실적 추이</h3>
    <pre class="json-block">${esc(JSON.stringify(fin.quarterly_trend || [], null, 2))}</pre>
    <h3 style="font-size:0.9rem;color:var(--muted)">전체 context (JSON)</h3>
    <pre class="json-block">${esc(JSON.stringify(ctx, null, 2))}</pre>
  `;
}

function renderReport(data) {
  const el = $("#panel-report");
  el.innerHTML = `<div class="report-md">${renderMarkdown(data.report_md || "")}</div>`;
}

function renderEval(data) {
  const ev = data.eval || {};
  const bd = ev.breakdown || {};
  const flags = ev.flags || [];
  const items = Object.entries(bd).map(([k, v]) => `<div class="score-item"><span>${esc(k)}</span><strong>${v}</strong></div>`).join("");
  const el = $("#panel-eval");
  el.innerHTML = `
    <div class="cards">
      <div class="card"><div class="label">총점</div><div class="value">${fmtNum(ev.total_score, 1)}</div></div>
      <div class="card"><div class="label">100점 환산</div><div class="value">${fmtNum(ev.score_normalized_100, 1)}</div></div>
      <div class="card"><div class="label">모드</div><div class="value" style="font-size:0.8rem">${esc(ev.rubric_mode)}</div></div>
      <div class="card"><div class="label">등급</div><div class="value" style="font-size:0.8rem">${esc(ev.grade)}</div></div>
    </div>
    <h3 style="font-size:0.9rem;color:var(--muted)">항목별 breakdown</h3>
    <div class="score-grid">${items || "<p>—</p>"}</div>
    ${flags.length ? `<h3 style="font-size:0.9rem;color:var(--muted)">플래그</h3><ul class="bullets">${flags.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>` : ""}
    <p style="color:var(--muted);font-size:0.8rem;margin-top:0.75rem">${esc(ev.grade_note || "")}</p>
  `;
}

function renderSignal(data) {
  const sig = data.signal || {};
  const thesis = sig.thesis_bullets || [];
  const risks = sig.risk_triggers || [];
  const el = $("#panel-signal");
  el.innerHTML = `
    <div class="cards">
      <div class="card"><div class="label">신호</div><div class="value">${signalBadge(sig.signal)}</div></div>
      <div class="card"><div class="label">신뢰도</div><div class="value">${sig.confidence != null ? (sig.confidence * 100).toFixed(0) + "%" : "—"}</div></div>
      <div class="card"><div class="label">기간</div><div class="value">${esc(sig.time_horizon)}</div></div>
    </div>
    <h3 style="font-size:0.9rem;color:var(--muted)">투자 논거 (thesis)</h3>
    ${thesis.length ? `<ul class="bullets">${thesis.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>` : "<p style='color:var(--muted)'>—</p>"}
    <h3 style="font-size:0.9rem;color:var(--muted)">리스크 트리거</h3>
    ${risks.length ? `<ul class="bullets">${risks.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>` : "<p style='color:var(--muted)'>—</p>"}
    <pre class="json-block">${esc(JSON.stringify(sig, null, 2))}</pre>
  `;
}

function renderAll(data) {
  currentData = data;
  if (data.ticker && data.date) {
    history.replaceState(null, "", `#${data.ticker}/${data.date}`);
  }
  $("#empty").style.display = "none";
  $("#results").style.display = "block";
  renderOverview(data);
  renderData(data);
  renderNews(data);
  renderContext(data);
  renderReport(data);
  renderEval(data);
  renderSignal(data);
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
    : "<p style='color:var(--muted);font-size:0.85rem'>저장된 실행 이력 없음</p>";
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
    renderAll(job.result);
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
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    setRunning(false);
    return alert("요청 실패");
  }
  const { job_id } = await res.json();
  pollJob(job_id);
});

async function loadInfo() {
  try {
    const res = await fetch("/api/info");
    const info = await res.json();
    if (info.disclaimer) $("#disclaimer").textContent = info.disclaimer;
    if (info.public_url) {
      const box = $("#share-box");
      const link = $("#public-url");
      link.href = info.public_url;
      link.textContent = info.public_url;
      box.hidden = false;
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

// URL hash로 티커/날짜 공유: #AAPL/2026-06-08
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
      hint.textContent = `${data.ticker} · ${data.date}: 저장된 리포트가 있습니다. 재생성 없이 바로 불러옵니다.`;
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

buildTabs();
loadHistory();
loadInfo();
loadFromHash();
