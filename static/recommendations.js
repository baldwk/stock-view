/*
 * @(#)recommendations.js, June 13, 2026.
 * <p/>
 * Copyright 2026 fenbi.com. All rights reserved.
 * FENBI.COM PROPRIETARY/CONFIDENTIAL. Use is subject to license terms.
 *
 * @Author: wukeyu
 * @Date: 2026/6/13 20:01
 */

const els = {};

document.addEventListener("DOMContentLoaded", () => {
  els.runTypeSelect = document.getElementById("runTypeSelect");
  els.limitInput = document.getElementById("limitInput");
  els.reloadButton = document.getElementById("reloadButton");
  els.runIntradayButton = document.getElementById("runIntradayButton");
  els.runCloseButton = document.getElementById("runCloseButton");
  els.recommendationResult = document.getElementById("recommendationResult");
  els.runTypeText = document.getElementById("runTypeText");
  els.tradeDateText = document.getElementById("tradeDateText");
  els.screenedAtText = document.getElementById("screenedAtText");
  els.itemCountText = document.getElementById("itemCountText");
  els.statusText = document.getElementById("statusText");

  els.reloadButton.addEventListener("click", loadRecommendations);
  els.runTypeSelect.addEventListener("change", loadRecommendations);
  els.runIntradayButton.addEventListener("click", () => runRecommendation("intraday_1430"));
  els.runCloseButton.addEventListener("click", () => runRecommendation("close_1600"));

  loadRecommendations();
});

async function loadRecommendations() {
  const params = new URLSearchParams();
  const runType = els.runTypeSelect.value;
  const limit = Number(els.limitInput.value) || 50;
  params.set("limit", String(limit));
  if (runType) {
    params.set("run_type", runType);
  }

  setStatus("正在加载推荐结果...");
  setResultMessage("正在加载推荐结果...");

  try {
    const response = await fetch(`/api/recommendations/zxt?${params.toString()}`);
    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.error || "推荐接口请求失败");
    }

    const data = await response.json();
    renderRun(data.run);
    renderRecommendations(data.items || []);
    setStatus("推荐结果已更新");
  } catch (error) {
    setResultMessage(error.message);
    setStatus("加载失败");
  }
}

async function runRecommendation(runType) {
  const params = new URLSearchParams();
  const limit = Number(els.limitInput.value) || 50;
  params.set("run_type", runType);
  params.set("limit", String(limit));

  setStatus("正在运行筛选，请稍候...");
  setResultMessage("正在运行筛选，请稍候...");

  try {
    const response = await fetch(`/api/recommendations/zxt/run?${params.toString()}`, { method: "POST" });
    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.error || "筛选运行失败");
    }

    els.runTypeSelect.value = runType;
    await loadRecommendations();
  } catch (error) {
    setResultMessage(error.message);
    setStatus("运行失败");
  }
}

function renderRun(run) {
  if (!run) {
    els.runTypeText.textContent = "-";
    els.tradeDateText.textContent = "-";
    els.screenedAtText.textContent = "-";
    els.itemCountText.textContent = "0";
    return;
  }

  els.runTypeText.textContent = formatRunType(run.run_type);
  els.tradeDateText.textContent = run.trade_date || "-";
  els.screenedAtText.textContent = formatDateTime(run.screened_at);
  els.itemCountText.textContent = String(run.item_count || 0);
}

function renderRecommendations(items) {
  els.recommendationResult.innerHTML = "";

  if (items.length === 0) {
    setResultMessage("暂无推荐结果，请等待定时任务执行或手动运行筛选。");
    return;
  }

  for (const item of items) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "result-card recommendation-card";
    card.innerHTML = `
      <div class="result-main">
        <span>${item.symbol}</span>
        <strong>${item.name}</strong>
      </div>
      <div class="result-metric">
        <span>交易日</span>
        <strong>${item.trade_date}</strong>
      </div>
      <div class="result-metric">
        <span>收盘/现价</span>
        <strong>${formatNumber(item.close)}</strong>
      </div>
      <div class="result-metric">
        <span>ZXT</span>
        <strong>${formatNumber(item.zxt)}</strong>
      </div>
      <div class="result-metric">
        <span>涨幅%</span>
        <strong>${formatNumber(item.pct_change)}</strong>
      </div>
      <div class="result-metric">
        <span>黄线</span>
        <strong>${formatNumber(item.yl)}</strong>
      </div>
    `;
    card.addEventListener("click", () => {
      window.location.href = `/kline?symbol=${encodeURIComponent(item.symbol)}`;
    });
    els.recommendationResult.appendChild(card);
  }
}

function setResultMessage(message) {
  els.recommendationResult.innerHTML = `<div class="empty-result">${message}</div>`;
}

function setStatus(message) {
  els.statusText.textContent = message;
}

function formatRunType(value) {
  if (value === "intraday_1430") {
    return "14:30 盘中推荐";
  }
  if (value === "close_1600") {
    return "16:00 收盘后推荐";
  }
  return value || "-";
}

function formatDateTime(value) {
  if (!value) {
    return "-";
  }
  return value.replace("T", " ");
}

function formatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "-";
  }
  return number.toFixed(3);
}
