/*
 * @(#)app.js, June 3, 2026.
 * <p/>
 * Copyright 2026 fenbi.com. All rights reserved.
 * FENBI.COM PROPRIETARY/CONFIDENTIAL. Use is subject to license terms.
 *
 * @Author: wukeyu
 * @Date: 2026/6/3 12:47
 */

const state = {
  stocks: [],
  allPrices: [],
  prices: [],
  bricks: [],
  brickSize: 0,
  chartGeometry: null,
  drag: null,
};

const els = {};

document.addEventListener("DOMContentLoaded", () => {
  els.stockSelect = document.getElementById("stockSelect");
  els.brickSizeInput = document.getElementById("brickSizeInput");
  els.startDateInput = document.getElementById("startDateInput");
  els.endDateInput = document.getElementById("endDateInput");
  els.reloadButton = document.getElementById("reloadButton");
  els.resetZoomButton = document.getElementById("resetZoomButton");
  els.upBrickCountInput = document.getElementById("upBrickCountInput");
  els.screenerLimitInput = document.getElementById("screenerLimitInput");
  els.runScreenerButton = document.getElementById("runScreenerButton");
  els.screenerResult = document.getElementById("screenerResult");
  els.canvas = document.getElementById("renkoCanvas");
  els.selectionBox = document.getElementById("selectionBox");
  els.emptyState = document.getElementById("emptyState");
  els.statusText = document.getElementById("statusText");
  els.dateRange = document.getElementById("dateRange");
  els.priceCount = document.getElementById("priceCount");
  els.brickCount = document.getElementById("brickCount");
  els.brickSizeText = document.getElementById("brickSizeText");

  els.stockSelect.addEventListener("change", loadSelectedPrices);
  els.reloadButton.addEventListener("click", loadSelectedPrices);
  els.resetZoomButton.addEventListener("click", resetDateRange);
  els.runScreenerButton.addEventListener("click", runRenkoUpScreener);
  els.brickSizeInput.addEventListener("input", rebuildRenko);
  els.startDateInput.addEventListener("change", rebuildRenko);
  els.endDateInput.addEventListener("change", rebuildRenko);
  els.canvas.addEventListener("pointerdown", startDragZoom);
  els.canvas.addEventListener("pointermove", updateDragZoom);
  els.canvas.addEventListener("pointerup", finishDragZoom);
  els.canvas.addEventListener("pointercancel", cancelDragZoom);
  window.addEventListener("resize", () => drawRenko(state.bricks, state.brickSize));

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

    if (state.stocks.length === 0) {
      setEmptyMessage("暂无股票数据，请先运行 python scripts/fetch_prices.py。");
      setStatus("");
      return;
    }

    await loadSelectedPrices();
  } catch (error) {
    setEmptyMessage(error.message);
    setStatus("加载失败");
  }
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

async function loadSelectedPrices() {
  const symbol = els.stockSelect.value;
  if (!symbol) {
    return;
  }

  setStatus(`正在加载 ${symbol} 收盘价...`);

  try {
    const response = await fetch(`/api/stocks/${symbol}/prices`);
    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.error || "价格接口请求失败");
    }

    const data = await response.json();
    state.allPrices = data.prices || [];
    syncDateInputs();
    rebuildRenko();
    setStatus(`已加载 ${symbol} 数据`);
  } catch (error) {
    state.allPrices = [];
    state.prices = [];
    state.bricks = [];
    updateStats();
    drawRenko([], 0);
    setEmptyMessage(error.message);
    setStatus("加载失败");
  }
}

async function runRenkoUpScreener() {
  const params = new URLSearchParams();
  const minUpBricks = Number(els.upBrickCountInput.value) || 3;
  const limit = Number(els.screenerLimitInput.value) || 50;
  const brickSize = Number(els.brickSizeInput.value);

  params.set("min_up_bricks", String(minUpBricks));
  params.set("limit", String(limit));
  if (brickSize > 0) {
    params.set("brick_size", String(brickSize));
  }
  if (els.startDateInput.value) {
    params.set("start_date", els.startDateInput.value);
  }
  if (els.endDateInput.value) {
    params.set("end_date", els.endDateInput.value);
  }

  setScreenerResultMessage("正在筛选，并刷新当前市值...");

  try {
    const response = await fetch(`/api/screener/renko-up?${params.toString()}`);
    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.error || "筛选接口请求失败");
    }

    const data = await response.json();
    renderScreenerResults(data.items || []);
  } catch (error) {
    setScreenerResultMessage(error.message);
  }
}

function renderScreenerResults(items) {
  els.screenerResult.innerHTML = "";

  if (items.length === 0) {
    setScreenerResultMessage("暂无符合条件的公司。");
    return;
  }

  for (const item of items) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "result-card";
    card.innerHTML = `
      <div class="result-main">
        <span>${item.symbol}</span>
        <strong>${item.name}</strong>
      </div>
      <div class="result-metric">
        <span>当前市值</span>
        <strong>${formatMarketCap(item.market_cap)}</strong>
      </div>
      <div class="result-metric">
        <span>连续上涨砖块</span>
        <strong>${item.latest_up_bricks}</strong>
      </div>
      <div class="result-metric">
        <span>砖块大小</span>
        <strong>${formatNumber(item.brick_size)}</strong>
      </div>
      <div class="result-metric">
        <span>最新收盘</span>
        <strong>${formatNumber(item.latest_close)}</strong>
      </div>
      <div class="result-metric">
        <span>最新交易日</span>
        <strong>${item.latest_trade_date}</strong>
      </div>
    `;
    card.addEventListener("click", () => selectScreenerStock(item.symbol));
    els.screenerResult.appendChild(card);
  }
}

async function selectScreenerStock(symbol) {
  if (!Array.from(els.stockSelect.options).some((option) => option.value === symbol)) {
    const option = document.createElement("option");
    option.value = symbol;
    option.textContent = symbol;
    els.stockSelect.appendChild(option);
  }

  els.stockSelect.value = symbol;
  await loadSelectedPrices();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function setScreenerResultMessage(message) {
  els.screenerResult.innerHTML = `<div class="empty-result">${message}</div>`;
}

function rebuildRenko() {
  normalizeDateInputs();
  state.prices = filterPricesByDateRange(state.allPrices);
  state.brickSize = resolveBrickSize(state.prices);
  state.bricks = buildRenko(state.prices, state.brickSize);
  updateStats();
  drawRenko(state.bricks, state.brickSize);

  if (state.allPrices.length === 0) {
    setEmptyMessage("暂无收盘价数据，请先运行数据脚本。");
  } else if (state.prices.length === 0) {
    setEmptyMessage("当前日期范围内没有收盘价数据，请调整日期。");
  } else if (state.bricks.length === 0) {
    setEmptyMessage("当前价格波动不足以生成砖块，请调小砖块大小。");
  } else {
    els.emptyState.hidden = true;
  }
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

function resetDateRange() {
  syncDateInputs();
  rebuildRenko();
}

function normalizeDateInputs() {
  const startDate = els.startDateInput.value;
  const endDate = els.endDateInput.value;

  if (startDate && endDate && startDate > endDate) {
    els.startDateInput.value = endDate;
    els.endDateInput.value = startDate;
  }
}

function filterPricesByDateRange(prices) {
  const startDate = els.startDateInput.value;
  const endDate = els.endDateInput.value;

  return prices.filter((price) => {
    if (startDate && price.trade_date < startDate) {
      return false;
    }
    if (endDate && price.trade_date > endDate) {
      return false;
    }
    return true;
  });
}

function resolveBrickSize(prices) {
  const inputValue = Number(els.brickSizeInput.value);
  if (inputValue > 0) {
    return inputValue;
  }

  if (prices.length === 0) {
    return 0;
  }

  const closes = prices.map((item) => Number(item.close_price));
  const high = Math.max(...closes);
  const low = Math.min(...closes);
  const latest = closes[closes.length - 1];
  const rawSize = high > low ? (high - low) / 40 : latest * 0.01;
  return roundBrickSize(Math.max(rawSize, 0.01));
}

function roundBrickSize(value) {
  const power = Math.pow(10, Math.floor(Math.log10(value)));
  const normalized = value / power;
  let step = 1;

  if (normalized >= 5) {
    step = 5;
  } else if (normalized >= 2) {
    step = 2;
  }

  return Number((step * power).toFixed(4));
}

function buildRenko(prices, brickSize) {
  if (prices.length === 0 || brickSize <= 0) {
    return [];
  }

  const sortedPrices = [...prices].sort((a, b) => a.trade_date.localeCompare(b.trade_date));
  let lastBrickClose = Number(sortedPrices[0].close_price);
  const bricks = [];

  for (const price of sortedPrices.slice(1)) {
    const close = Number(price.close_price);
    let diff = close - lastBrickClose;

    while (Math.abs(diff) >= brickSize) {
      const direction = diff > 0 ? 1 : -1;
      const open = lastBrickClose;
      const brickClose = open + direction * brickSize;
      bricks.push({
        date: price.trade_date,
        open,
        close: brickClose,
        direction,
      });
      lastBrickClose = brickClose;
      diff = close - lastBrickClose;
    }
  }

  return bricks;
}

function updateStats() {
  const prices = state.prices;
  const startDate = prices[0]?.trade_date || "-";
  const endDate = prices[prices.length - 1]?.trade_date || "-";

  els.dateRange.textContent = prices.length > 0 ? `${startDate} 至 ${endDate}` : "-";
  els.priceCount.textContent = String(prices.length || "-");
  els.brickCount.textContent = String(state.bricks.length || "-");
  els.brickSizeText.textContent = state.brickSize > 0 ? formatNumber(state.brickSize) : "-";
}

function drawRenko(bricks, brickSize) {
  const canvas = els.canvas;
  const ctx = canvas.getContext("2d");
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const width = Math.max(1, rect.width);
  const height = Math.max(1, rect.height);

  canvas.width = Math.floor(width * dpr);
  canvas.height = Math.floor(height * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);

  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);

  if (bricks.length === 0) {
    state.chartGeometry = null;
    return;
  }

  const padding = { top: 24, right: 74, bottom: 44, left: 24 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const values = bricks.flatMap((brick) => [brick.open, brick.close]);
  let minValue = Math.min(...values);
  let maxValue = Math.max(...values);
  const valuePadding = Math.max(brickSize * 2, (maxValue - minValue) * 0.08);

  minValue -= valuePadding;
  maxValue += valuePadding;

  const yOf = (value) => {
    const rate = (value - minValue) / (maxValue - minValue || 1);
    return padding.top + chartHeight - rate * chartHeight;
  };

  drawGrid(ctx, padding, width, chartWidth, chartHeight, minValue, maxValue, yOf);
  state.chartGeometry = {
    left: padding.left,
    right: padding.left + chartWidth,
    top: padding.top,
    bottom: padding.top + chartHeight,
    bricks,
  };

  const slotWidth = chartWidth / bricks.length;
  const gap = Math.min(4, Math.max(1, slotWidth * 0.18));
  const brickWidth = Math.max(2, slotWidth - gap);

  bricks.forEach((brick, index) => {
    const x = padding.left + index * slotWidth + gap / 2;
    const top = yOf(Math.max(brick.open, brick.close));
    const bottom = yOf(Math.min(brick.open, brick.close));

    ctx.fillStyle = brick.direction > 0 ? "#16a34a" : "#dc2626";
    ctx.fillRect(x, top, brickWidth, Math.max(2, bottom - top));
  });

  drawDateLabels(ctx, bricks, padding, width, height);
}

function drawGrid(ctx, padding, width, chartWidth, chartHeight, minValue, maxValue, yOf) {
  ctx.save();
  ctx.strokeStyle = "#e2e8f0";
  ctx.fillStyle = "#64748b";
  ctx.font = "12px Inter, Arial, sans-serif";
  ctx.lineWidth = 1;

  for (let index = 0; index <= 4; index += 1) {
    const value = maxValue - ((maxValue - minValue) * index) / 4;
    const y = yOf(value);
    ctx.beginPath();
    ctx.moveTo(padding.left, y);
    ctx.lineTo(padding.left + chartWidth, y);
    ctx.stroke();
    ctx.fillText(formatNumber(value), width - padding.right + 12, y + 4);
  }

  ctx.strokeStyle = "#cbd5e1";
  ctx.strokeRect(padding.left, padding.top, chartWidth, chartHeight);
  ctx.restore();
}

function drawDateLabels(ctx, bricks, padding, width, height) {
  ctx.save();
  ctx.fillStyle = "#64748b";
  ctx.font = "12px Inter, Arial, sans-serif";
  ctx.textBaseline = "top";
  ctx.fillText(bricks[0].date, padding.left, height - padding.bottom + 16);

  const lastDate = bricks[bricks.length - 1].date;
  const textWidth = ctx.measureText(lastDate).width;
  ctx.fillText(lastDate, width - padding.right - textWidth, height - padding.bottom + 16);
  ctx.restore();
}

function startDragZoom(event) {
  if (!state.chartGeometry || state.chartGeometry.bricks.length < 2) {
    return;
  }

  const x = getCanvasX(event);
  if (x < state.chartGeometry.left || x > state.chartGeometry.right) {
    return;
  }

  state.drag = {
    pointerId: event.pointerId,
    startX: x,
    currentX: x,
  };
  els.canvas.setPointerCapture(event.pointerId);
  positionSelectionBox(x, x);
  event.preventDefault();
}

function updateDragZoom(event) {
  if (!state.drag || state.drag.pointerId !== event.pointerId) {
    return;
  }

  const x = clamp(getCanvasX(event), state.chartGeometry.left, state.chartGeometry.right);
  state.drag.currentX = x;
  positionSelectionBox(state.drag.startX, state.drag.currentX);
}

function finishDragZoom(event) {
  if (!state.drag || state.drag.pointerId !== event.pointerId) {
    return;
  }

  const startX = state.drag.startX;
  const endX = state.drag.currentX;
  state.drag = null;
  els.selectionBox.hidden = true;
  els.canvas.releasePointerCapture(event.pointerId);

  if (Math.abs(endX - startX) < 12) {
    return;
  }

  const startDate = dateFromCanvasX(Math.min(startX, endX));
  const endDate = dateFromCanvasX(Math.max(startX, endX));
  if (!startDate || !endDate) {
    return;
  }

  els.startDateInput.value = startDate;
  els.endDateInput.value = endDate;
  rebuildRenko();
}

function cancelDragZoom(event) {
  if (state.drag && state.drag.pointerId === event.pointerId) {
    state.drag = null;
    els.selectionBox.hidden = true;
  }
}

function getCanvasX(event) {
  const rect = els.canvas.getBoundingClientRect();
  return event.clientX - rect.left;
}

function positionSelectionBox(startX, endX) {
  const canvasRect = els.canvas.getBoundingClientRect();
  const panelRect = els.canvas.parentElement.getBoundingClientRect();
  const left = Math.min(startX, endX) + canvasRect.left - panelRect.left;
  const width = Math.abs(endX - startX);

  els.selectionBox.style.left = `${left}px`;
  els.selectionBox.style.width = `${width}px`;
  els.selectionBox.hidden = false;
}

function dateFromCanvasX(x) {
  const geometry = state.chartGeometry;
  if (!geometry) {
    return "";
  }

  const chartWidth = geometry.right - geometry.left;
  const rate = (clamp(x, geometry.left, geometry.right) - geometry.left) / chartWidth;
  const index = Math.round(rate * (geometry.bricks.length - 1));
  return geometry.bricks[index]?.date || "";
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function formatNumber(value) {
  return Number(value).toLocaleString("zh-CN", {
    minimumFractionDigits: value >= 10 ? 2 : 3,
    maximumFractionDigits: value >= 10 ? 2 : 3,
  });
}

function formatMarketCap(value) {
  const marketCap = Number(value);
  if (!Number.isFinite(marketCap) || marketCap <= 0) {
    return "-";
  }

  if (marketCap >= 1000000000000) {
    return `${(marketCap / 1000000000000).toFixed(2)} 万亿`;
  }
  return `${(marketCap / 100000000).toFixed(2)} 亿`;
}

function setEmptyMessage(message) {
  els.emptyState.textContent = message;
  els.emptyState.hidden = false;
}

function setStatus(message) {
  els.statusText.textContent = message;
}
