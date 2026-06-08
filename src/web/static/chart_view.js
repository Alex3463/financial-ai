/** snapshot.price → TradingView Lightweight Charts (심플 캔들) */

let _activeChart = null;
let _activeResizeObserver = null;

function destroyPriceChart() {
  if (_activeResizeObserver) {
    _activeResizeObserver.disconnect();
    _activeResizeObserver = null;
  }
  if (_activeChart) {
    _activeChart.remove();
    _activeChart = null;
  }
}

function buildCandles(price, months) {
  const close = price?.daily_close || {};
  const high = price?.daily_high || {};
  const low = price?.daily_low || {};
  const volume = price?.daily_volume || {};

  let dates = Object.keys(close).sort();
  if (months && months > 0) {
    const cutoff = new Date();
    cutoff.setMonth(cutoff.getMonth() - months);
    const cut = cutoff.toISOString().slice(0, 10);
    dates = dates.filter((d) => d >= cut);
  }

  let prevClose = null;
  const candles = [];
  const vols = [];

  for (const d of dates) {
    const c = close[d];
    if (c == null || Number.isNaN(Number(c))) continue;
    const o = prevClose ?? c;
    prevClose = c;
    candles.push({
      time: d,
      open: o,
      high: high[d] ?? Math.max(o, c),
      low: low[d] ?? Math.min(o, c),
      close: c,
    });
    if (volume[d] != null) {
      vols.push({ time: d, value: volume[d], color: c >= o ? "#22c55e88" : "#ef444488" });
    }
  }
  return { candles, vols };
}

function calcChange(candles) {
  if (!candles.length) return null;
  const first = candles[0].close;
  const last = candles[candles.length - 1].close;
  if (!first) return null;
  return ((last - first) / first) * 100;
}

function renderPriceChart(containerEl, price, ticker, rangeMonths, levels) {
  destroyPriceChart();
  if (!containerEl || !price?.daily_close) return false;
  if (typeof LightweightCharts === "undefined") return false;

  const { candles, vols } = buildCandles(price, rangeMonths);
  if (!candles.length) return false;

  const minP = Math.min(...candles.map((c) => c.low));
  const maxP = Math.max(...candles.map((c) => c.high));
  const pad = (maxP - minP) * 0.08 || maxP * 0.05;

  const chart = LightweightCharts.createChart(containerEl, {
    layout: {
      background: { color: "#1a2332" },
      textColor: "#8b9cb3",
      fontSize: 11,
      padding: { left: 8, right: 24 },
    },
    grid: {
      vertLines: { color: "#2d3f5644" },
      horzLines: { color: "#2d3f5644" },
    },
    rightPriceScale: {
      borderColor: "#2d3f56",
      minimumWidth: 96,
      scaleMargins: { top: 0.06, bottom: 0.14 },
    },
    leftPriceScale: { visible: false },
    timeScale: {
      borderColor: "#2d3f56",
      timeVisible: false,
      rightOffset: 16,
      fixLeftEdge: true,
    },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    width: containerEl.clientWidth,
    height: 320,
  });

  const candleSeries = chart.addCandlestickSeries({
    upColor: "#22c55e",
    downColor: "#ef4444",
    borderUpColor: "#22c55e",
    borderDownColor: "#ef4444",
    wickUpColor: "#22c55e",
    wickDownColor: "#ef4444",
  });
  candleSeries.setData(candles);

  const appliedLevels = [];
  for (const lv of levels || []) {
    if (lv.price < minP - pad || lv.price > maxP + pad) continue;
    const shortTitle =
      lv.label.length > 8 ? `${lv.label.slice(0, 7)}…` : lv.label;
    candleSeries.createPriceLine({
      price: lv.price,
      color: lv.color,
      lineWidth: lv.lineStyle === 3 ? 1 : 2,
      lineStyle: lv.lineStyle ?? 2,
      axisLabelVisible: true,
      title: shortTitle,
    });
    appliedLevels.push(lv);
  }

  if (vols.length) {
    const volSeries = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
    });
    chart.priceScale("vol").applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });
    volSeries.setData(vols);
  }

  chart.timeScale().fitContent();
  chart.timeScale().applyOptions({ rightOffset: 20 });
  chart.priceScale("right").applyOptions({
    minimumWidth: 100,
    scaleMargins: { top: 0.06, bottom: 0.14 },
  });
  _activeChart = chart;

  _activeResizeObserver = new ResizeObserver(() => {
    if (containerEl && _activeChart) {
      _activeChart.applyOptions({ width: containerEl.clientWidth });
    }
  });
  _activeResizeObserver.observe(containerEl);

  return {
    changePct: calcChange(candles),
    last: candles[candles.length - 1].close,
    levels: appliedLevels,
  };
}
