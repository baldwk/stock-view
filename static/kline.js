/*
 * @(#)kline.js, June 13, 2026.
 * <p/>
 * Copyright 2026 fenbi.com. All rights reserved.
 * FENBI.COM PROPRIETARY/CONFIDENTIAL. Use is subject to license terms.
 *
 * @Author: wukeyu
 * @Date: 2026/6/13 20:01
 */

const state = {
  stocks: [],
  allPrices: [],
  prices: [],
  chart: null,
  candleSeries: null,
  volumeSeries: null,
  isClampingRange: false,
};

const els = {};

document.addEventListener("DOMContentLoaded", () => {
  els.stockSelect = document.getElementById("stockSelect");
  els.startDateInput = document.getElementById("startDateInput");
  els.endDateInput = document.getElementById("endDateInput");
  els.reloadButton = document.getElementById("reloadButton");
  els.resetRangeButton = document.getElementById("resetRangeButton");
  els.klineChart = document.getElementById("klineChart");
  els.klineEmptyState = document.getElementById("klineEmptyState");
  els.stockText = document.getElementById("stockText");
  els.marketCapText = document.getElementById("marketCapText");
  els.dateRangeText = document.getElementById("dateRangeText");
  els.priceCountText = document.getElementById("priceCountText");
  els.latestCloseText = document.getElementById("latestCloseText");
  els.statusText = document.getElementById("statusText");

  els.stockSelect.addEventListener("change", handleStockChange);
  els.reloadButton.addEventListener("click", loadSelectedPrices);
  els.resetRangeButton.addEventListener("click", resetDateRange);
  els.startDateInput.addEventListener("change", loadSelectedPrices);
  els.endDateInput.addEventListener("change", loadSelectedPrices);
  window.addEventListener("resize", resizeChart);

  loadStocks();
});

async function loadStocks() {
  setStatus("正在加载股票列表...");
  try {
    const response = await fetch("/api/stocks");
    if (!response.ok) {
      throw new Error("股票列表接口请求失败");
    }

    const data = await response.json();
    state.stocks = data.stocks || [];
    renderStockOptions();
    selectSymbolFromUrl();
    if (!els.stockSelect.value) {
      setEmptyMessage("暂无股票数据，请先运行数据更新脚本。");
      setStatus("");
      return;
    }
    setDateInputsForSelectedStock(true);
    await loadSelectedPrices();
  } catch (error) {
    setEmptyMessage(error.message);
    setStatus("加载失败");
  }
}

function getSelectedStock() {
  return state.stocks.find((stock) => stock.symbol === els.stockSelect.value) || null;
}

function renderStockOptions() {
  els.stockSelect.innerHTML = "";
  for (const stock of state.stocks) {
    const option = document.createElement("option");
    option.value = stock.symbol;
    option.textContent = `${stock.symbol} ${stock.name} (${stock.price_count || 0} 条)`;
    els.stockSelect.appendChild(option);
  }
}

function selectSymbolFromUrl() {
  const symbol = new URLSearchParams(window.location.search).get("symbol");
  if (!symbol) {
    return;
  }

  if (!Array.from(els.stockSelect.options).some((option) => option.value === symbol)) {
    const option = document.createElement("option");
    option.value = symbol;
    option.textContent = symbol;
    els.stockSelect.appendChild(option);
  }
  els.stockSelect.value = symbol;
}

async function handleStockChange() {
  setDateInputsForSelectedStock(true);
  await loadSelectedPrices();
}

async function loadSelectedPrices() {
  const symbol = els.stockSelect.value;
  if (!symbol) {
    return;
  }

  setStatus(`正在加载 ${symbol} 日K数据...`);
  try {
    normalizeDateInputs();
    const params = new URLSearchParams();
    if (els.startDateInput.value) {
      params.set("start_date", els.startDateInput.value);
    }
    if (els.endDateInput.value) {
      params.set("end_date", els.endDateInput.value);
    }
    const query = params.toString();
    const response = await fetch(`/api/stocks/${symbol}/prices${query ? `?${query}` : ""}`);
    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.error || "价格接口请求失败");
    }

    const data = await response.json();
    state.allPrices = data.prices || [];
    syncDateInputsFromPrices();
    rebuildChart();
    setStatus(`已加载 ${symbol} 日K数据`);
  } catch (error) {
    state.allPrices = [];
    state.prices = [];
    updateStats();
    renderChart([]);
    setEmptyMessage(error.message);
    setStatus("加载失败");
  }
}

function setDateInputsForSelectedStock(useRecentDefault) {
  const stock = getSelectedStock();
  const startDate = stock?.start_date || "";
  const endDate = stock?.end_date || "";
  els.startDateInput.min = startDate;
  els.startDateInput.max = endDate;
  els.endDateInput.min = startDate;
  els.endDateInput.max = endDate;

  if (!startDate || !endDate) {
    els.startDateInput.value = "";
    els.endDateInput.value = "";
    return;
  }

  els.endDateInput.value = endDate;
  if (useRecentDefault) {
    els.startDateInput.value = maxDate(startDate, shiftDate(endDate, -365));
  } else {
    els.startDateInput.value = startDate;
  }
}

function syncDateInputsFromPrices() {
  const prices = state.allPrices;
  const startDate = prices[0]?.trade_date || "";
  const endDate = prices[prices.length - 1]?.trade_date || "";
  if (!els.startDateInput.min && startDate) {
    els.startDateInput.min = startDate;
  }
  if (!els.startDateInput.max && endDate) {
    els.startDateInput.max = endDate;
  }
  if (!els.endDateInput.min && startDate) {
    els.endDateInput.min = startDate;
  }
  if (!els.endDateInput.max && endDate) {
    els.endDateInput.max = endDate;
  }
  if (!els.startDateInput.value) {
    els.startDateInput.value = startDate;
  }
  if (!els.endDateInput.value) {
    els.endDateInput.value = endDate;
  }
}

function shiftDate(value, days) {
  const date = new Date(`${value}T00:00:00`);
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

function maxDate(left, right) {
  if (!left) {
    return right;
  }
  if (!right) {
    return left;
  }
  return left > right ? left : right;
}

function syncDateInputs() {
  const prices = state.allPrices;
  const startDate = prices[0]?.trade_date || "";
  const endDate = prices[prices.length - 1]?.trade_date || "";
  els.startDateInput.min = startDate;
  els.startDateInput.max = endDate;
  els.endDateInput.min = startDate;
  els.endDateInput.max = endDate;
  els.startDateInput.value = startDate;
  els.endDateInput.value = endDate;
}

async function resetDateRange() {
  setDateInputsForSelectedStock(false);
  await loadSelectedPrices();
}

function rebuildChart() {
  normalizeDateInputs();
  state.prices = filterPricesByDateRange(state.allPrices);
  updateStats();
  renderChart(state.prices);
  if (state.prices.length === 0) {
    setEmptyMessage("当前日期范围内没有日K数据。");
  } else {
    els.klineEmptyState.hidden = true;
  }
}

function normalizeDateInputs() {
  if (els.startDateInput.value && els.endDateInput.value && els.startDateInput.value > els.endDateInput.value) {
    const endDate = els.endDateInput.value;
    els.endDateInput.value = els.startDateInput.value;
    els.startDateInput.value = endDate;
  }
}

function filterPricesByDateRange(prices) {
  const startDate = els.startDateInput.value;
  const endDate = els.endDateInput.value;
  return prices.filter((item) => {
    if (startDate && item.trade_date < startDate) {
      return false;
    }
    if (endDate && item.trade_date > endDate) {
      return false;
    }
    return true;
  });
}

function renderChart(prices) {
  if (!window.LightweightCharts) {
    setEmptyMessage("K线图库加载失败，请检查服务器网络或改为本地静态资源。");
    return;
  }

  ensureChart();
  state.candleSeries.setData(buildCandles(prices));
  state.volumeSeries.setData(buildVolumes(prices));
  state.chart.timeScale().fitContent();
  clampVisibleLogicalRange();
}

function ensureChart() {
  if (state.chart) {
    resizeChart();
    return;
  }

  state.chart = LightweightCharts.createChart(els.klineChart, {
    layout: {
      background: { color: "#ffffff" },
      textColor: "#334155",
    },
    grid: {
      vertLines: { color: "#e2e8f0" },
      horzLines: { color: "#e2e8f0" },
    },
    rightPriceScale: {
      borderColor: "#cbd5e1",
    },
    timeScale: {
      borderColor: "#cbd5e1",
      fixLeftEdge: true,
      fixRightEdge: true,
      rightOffset: 0,
    },
    width: els.klineChart.clientWidth,
    height: els.klineChart.clientHeight,
  });
  state.candleSeries = state.chart.addCandlestickSeries({
    upColor: "#ef4444",
    downColor: "#16a34a",
    borderUpColor: "#ef4444",
    borderDownColor: "#16a34a",
    wickUpColor: "#ef4444",
    wickDownColor: "#16a34a",
  });
  state.candleSeries.priceScale().applyOptions({
    scaleMargins: {
      top: 0.05,
      bottom: 0.25,
    },
  });
  state.volumeSeries = state.chart.addHistogramSeries({
    priceFormat: { type: "volume" },
    priceScaleId: "",
  });
  state.volumeSeries.priceScale().applyOptions({
    scaleMargins: {
      top: 0.78,
      bottom: 0,
    },
  });
  state.chart.timeScale().subscribeVisibleLogicalRangeChange(clampVisibleLogicalRange);
}

function clampVisibleLogicalRange() {
  if (!state.chart || state.isClampingRange || state.prices.length === 0) {
    return;
  }

  const range = state.chart.timeScale().getVisibleLogicalRange();
  if (!range) {
    return;
  }

  const minIndex = 0;
  const maxIndex = state.prices.length - 1;
  let from = range.from;
  let to = range.to;
  const span = to - from;

  if (span >= maxIndex - minIndex) {
    from = minIndex;
    to = maxIndex;
  } else {
    if (from < minIndex) {
      to += minIndex - from;
      from = minIndex;
    }
    if (to > maxIndex) {
      from -= to - maxIndex;
      to = maxIndex;
    }
  }

  from = Math.max(minIndex, from);
  to = Math.min(maxIndex, to);
  if (from === range.from && to === range.to) {
    return;
  }

  state.isClampingRange = true;
  state.chart.timeScale().setVisibleLogicalRange({ from, to });
  state.isClampingRange = false;
}

function resizeChart() {
  if (!state.chart) {
    return;
  }
  state.chart.applyOptions({
    width: els.klineChart.clientWidth,
    height: els.klineChart.clientHeight,
  });
}

function buildCandles(prices) {
  return prices
    .filter((item) => item.high_price != null && item.low_price != null && item.close_price != null)
    .map((item) => {
      const close = Number(item.close_price);
      return {
        time: item.trade_date,
        open: Number(item.open_price ?? close),
        high: Number(item.high_price),
        low: Number(item.low_price),
        close,
      };
    });
}

function buildVolumes(prices) {
  return prices
    .filter((item) => item.volume != null)
    .map((item) => {
      const close = Number(item.close_price);
      const open = Number(item.open_price ?? close);
      return {
        time: item.trade_date,
        value: Number(item.volume),
        color: close >= open ? "rgba(239, 68, 68, 0.45)" : "rgba(22, 163, 74, 0.45)",
      };
    });
}

function updateStats() {
  const selectedOption = els.stockSelect.selectedOptions[0];
  const selectedStock = getSelectedStock();
  const latest = state.prices[state.prices.length - 1];
  const startDate = state.prices[0]?.trade_date || "-";
  const endDate = latest?.trade_date || "-";
  els.stockText.textContent = selectedOption?.textContent || "-";
  els.marketCapText.textContent = formatMarketCap(selectedStock?.market_cap);
  els.dateRangeText.textContent = startDate === "-" ? "-" : `${startDate} 至 ${endDate}`;
  els.priceCountText.textContent = String(state.prices.length);
  els.latestCloseText.textContent = latest ? formatNumber(latest.close_price) : "-";
}

function setEmptyMessage(message) {
  els.klineEmptyState.textContent = message;
  els.klineEmptyState.hidden = false;
}

function setStatus(message) {
  els.statusText.textContent = message;
}

function formatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "-";
  }
  return number.toFixed(3);
}

function formatMarketCap(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) {
    return "-";
  }
  if (number >= 100000000) {
    return `${(number / 100000000).toFixed(2)} 亿`;
  }
  if (number >= 10000) {
    return `${(number / 10000).toFixed(2)} 万`;
  }
  return number.toFixed(0);
}
