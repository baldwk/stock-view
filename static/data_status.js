/*
 * @(#)data_status.js, June 13, 2026.
 * <p/>
 * Copyright 2026 fenbi.com. All rights reserved.
 * FENBI.COM PROPRIETARY/CONFIDENTIAL. Use is subject to license terms.
 *
 * @Author: wukeyu
 * @Date: 2026/6/13 20:47
 */

const els = {};
let autoRefresh = true;
let refreshTimer = null;

document.addEventListener("DOMContentLoaded", () => {
  els.updateDateInput = document.getElementById("updateDateInput");
  els.reloadButton = document.getElementById("reloadButton");
  els.autoRefreshButton = document.getElementById("autoRefreshButton");
  els.statusText = document.getElementById("statusText");
  els.totalStocksText = document.getElementById("totalStocksText");
  els.stocksWithPricesText = document.getElementById("stocksWithPricesText");
  els.dailyPriceRowsText = document.getElementById("dailyPriceRowsText");
  els.dateRangeText = document.getElementById("dateRangeText");
  els.updateDateText = document.getElementById("updateDateText");
  els.updatedStocksText = document.getElementById("updatedStocksText");
  els.updatedRowsText = document.getElementById("updatedRowsText");
  els.lastUpdatedAtText = document.getElementById("lastUpdatedAtText");
  els.progressText = document.getElementById("progressText");
  els.progressBar = document.getElementById("progressBar");
  els.bucketGrid = document.getElementById("bucketGrid");
  els.updatedList = document.getElementById("updatedList");
  els.loadedList = document.getElementById("loadedList");
  els.pendingList = document.getElementById("pendingList");

  els.updateDateInput.value = formatLocalDate(new Date());
  els.updateDateInput.addEventListener("change", loadStatus);
  els.reloadButton.addEventListener("click", loadStatus);
  els.autoRefreshButton.addEventListener("click", toggleAutoRefresh);

  loadStatus();
  scheduleRefresh();
});

async function loadStatus() {
  setStatus("正在刷新...");
  try {
    const params = new URLSearchParams();
    if (els.updateDateInput.value) {
      params.set("update_date", els.updateDateInput.value);
    }
    params.set("_", String(Date.now()));
    const response = await fetch(`/api/data-status?${params.toString()}`);
    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.error || "数据状态接口请求失败");
    }

    const data = await response.json();
    renderStatus(data);
    setStatus(`已刷新 ${new Date().toLocaleTimeString()}`);
  } catch (error) {
    setStatus(error.message);
  }
}

function renderStatus(data) {
  const totalStocks = Number(data.total_stocks || 0);
  const stocksWithPrices = Number(data.stocks_with_prices || 0);
  const dailyPriceRows = Number(data.daily_price_rows || 0);
  const todayUpdate = data.today_update || {};
  const updatedStocks = Number(todayUpdate.updated_stocks || 0);
  const updatedRows = Number(todayUpdate.updated_rows || 0);
  const progress = totalStocks > 0 ? (stocksWithPrices / totalStocks) * 100 : 0;

  els.totalStocksText.textContent = formatInteger(totalStocks);
  els.stocksWithPricesText.textContent = `${formatInteger(stocksWithPrices)} / ${formatInteger(totalStocks)}`;
  els.dailyPriceRowsText.textContent = formatInteger(dailyPriceRows);
  els.dateRangeText.textContent = data.start_date && data.end_date ? `${data.start_date} 至 ${data.end_date}` : "-";
  els.updateDateText.textContent = data.update_date || "-";
  els.updatedStocksText.textContent = formatInteger(updatedStocks);
  els.updatedRowsText.textContent = formatInteger(updatedRows);
  els.lastUpdatedAtText.textContent = formatDateTime(todayUpdate.last_updated_at);
  els.progressText.textContent = `${progress.toFixed(2)}%`;
  els.progressBar.style.width = `${Math.min(progress, 100)}%`;
  renderBuckets(data.buckets || {});
  renderUpdatedList(data.updated_samples || []);
  renderLoadedList(data.loaded_samples || []);
  renderPendingList(data.pending_samples || []);
}

function renderBuckets(buckets) {
  const items = [
    ["未拉取", buckets.no_data || 0],
    ["1-99 条", buckets.under_100 || 0],
    ["100-999 条", buckets.under_1000 || 0],
    ["1000 条以上", buckets.over_1000 || 0],
  ];
  els.bucketGrid.innerHTML = items
    .map(
      ([label, value]) => `
        <div class="bucket-card">
          <span>${label}</span>
          <strong>${formatInteger(value)}</strong>
        </div>
      `
    )
    .join("");
}

function renderUpdatedList(items) {
  if (items.length === 0) {
    els.updatedList.innerHTML = `<div class="empty-result">查询日期暂无更新记录。</div>`;
    return;
  }

  els.updatedList.innerHTML = items
    .map(
      (item) => `
        <a class="status-row" href="/kline?symbol=${encodeURIComponent(item.symbol)}">
          <span>${item.symbol} ${item.name}</span>
          <strong>${formatInteger(item.updated_rows)} 行</strong>
          <small>${item.start_date || "-"} 至 ${item.end_date || "-"}，最后更新 ${formatDateTime(item.last_updated_at)}</small>
        </a>
      `
    )
    .join("");
}

function renderLoadedList(items) {
  if (items.length === 0) {
    els.loadedList.innerHTML = `<div class="empty-result">暂无已拉取股票。</div>`;
    return;
  }

  els.loadedList.innerHTML = items
    .map(
      (item) => `
        <a class="status-row" href="/kline?symbol=${encodeURIComponent(item.symbol)}">
          <span>${item.symbol} ${item.name}</span>
          <strong>${formatInteger(item.price_count)} 条</strong>
          <small>${item.start_date || "-"} 至 ${item.end_date || "-"}</small>
        </a>
      `
    )
    .join("");
}

function renderPendingList(items) {
  if (items.length === 0) {
    els.pendingList.innerHTML = `<div class="empty-result">暂无待拉取股票。</div>`;
    return;
  }

  els.pendingList.innerHTML = items
    .map(
      (item) => `
        <div class="status-row">
          <span>${item.symbol} ${item.name}</span>
          <strong>等待中</strong>
          <small>尚未写入日K</small>
        </div>
      `
    )
    .join("");
}

function toggleAutoRefresh() {
  autoRefresh = !autoRefresh;
  els.autoRefreshButton.textContent = autoRefresh ? "暂停自动刷新" : "开启自动刷新";
  scheduleRefresh();
}

function scheduleRefresh() {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
  if (autoRefresh) {
    refreshTimer = setInterval(loadStatus, 10000);
  }
}

function setStatus(message) {
  els.statusText.textContent = message;
}

function formatDateTime(value) {
  if (!value) {
    return "-";
  }
  return value.replace("T", " ");
}

function formatLocalDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatInteger(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "-";
  }
  return number.toLocaleString("zh-CN");
}
