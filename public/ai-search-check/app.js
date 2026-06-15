import { diagnoseSite, getChecks, normalizeUrls } from "./diagnosis.js";
import { getDisclosure, getRecommendedOffers } from "./offers.js";

const form = document.querySelector("[data-diagnosis-form]");
const checkList = document.querySelector("[data-check-list]");
const resultPanel = document.querySelector("[data-result]");
const progressPanel = document.querySelector("[data-progress]");
const progressBar = document.querySelector("[data-progress-bar]");
const progressStatus = document.querySelector("[data-progress-status]");
const scoreValue = document.querySelector("[data-score]");
const gradeValue = document.querySelector("[data-grade]");
const summaryValue = document.querySelector("[data-summary]");
const roadMapList = document.querySelector("[data-roadmap]");
const riskList = document.querySelector("[data-risks]");
const actionPlanList = document.querySelector("[data-action-plan]");
const urlAuditBody = document.querySelector("[data-url-audit]");
const analysisScopeList = document.querySelector("[data-analysis-scope]");
const reportMeta = document.querySelector("[data-report-meta]");
const opportunityValue = document.querySelector("[data-opportunity]");
const offerSection = document.querySelector("[data-offers-section]");
const offerList = document.querySelector("[data-offers]");
const invalidUrlNote = document.querySelector("[data-invalid-urls]");
const disclosure = document.querySelector("[data-disclosure]");
const radarCanvas = document.querySelector("[data-radar-chart]");
const barCanvas = document.querySelector("[data-bar-chart]");

const checks = getChecks();
const progressSteps = [
  "URL形式とページ種別を確認中",
  "AI回答に使われる一次情報を整理中",
  "FAQと構造化データのシグナルを評価中",
  "改善ロードマップと推奨サービスを作成中",
];

checkList.innerHTML = checks
  .map(
    (check) => `
      <label class="check-item">
        <input type="checkbox" name="checks" value="${check.id}">
        <span>${check.label}</span>
      </label>
    `,
  )
  .join("");

disclosure.textContent = getDisclosure();

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const formData = new FormData(form);
  const urls = normalizeUrls(String(formData.get("urls") || ""));
  const checkedIds = formData.getAll("checks");
  const businessType = String(formData.get("businessType") || "店舗・サービス");
  const result = diagnoseSite({ urls, checkedIds, businessType });

  runProgress(urls.length).then(() => renderResult(result));
});

function renderResult(result) {
  progressPanel.hidden = true;
  resultPanel.hidden = false;
  offerSection.hidden = false;
  scoreValue.textContent = String(result.score);
  gradeValue.textContent = result.grade.label;
  gradeValue.dataset.tone = result.grade.tone;
  summaryValue.textContent = result.summary;
  opportunityValue.textContent = `${result.opportunityScore.label} (${result.opportunityScore.value}/100)`;
  reportMeta.textContent = `${result.businessType} / 有効URL ${result.validUrls.length}件 / 診断日 ${new Date().toLocaleDateString("ja-JP")}`;

  invalidUrlNote.textContent =
    result.invalidUrls.length > 0
      ? `URL形式ではない入力があります: ${result.invalidUrls.join("、")}`
      : "";

  roadMapList.innerHTML = result.roadMap
    .map(
      (item) => `
        <li>
          <span>${item.step}</span>
          <div>
            <strong>${item.title}</strong>
            <p>${item.action}</p>
          </div>
        </li>
      `,
    )
    .join("");

  riskList.innerHTML = result.riskRegister
    .map(
      (risk) => `
        <li data-severity="${risk.severity}">
          <strong>${risk.title}</strong>
          <p>${risk.detail}</p>
        </li>
      `,
    )
    .join("");

  actionPlanList.innerHTML = result.actionPlan
    .map(
      (phase) => `
        <article>
          <span>${phase.phase}</span>
          <h3>${phase.title}</h3>
          <ul>${phase.tasks.map((task) => `<li>${task}</li>`).join("")}</ul>
        </article>
      `,
    )
    .join("");

  urlAuditBody.innerHTML =
    result.urlAudit.length > 0
      ? result.urlAudit
          .map(
            (item) => `
              <tr>
                <td>${item.type}</td>
                <td><a href="${item.url}" target="_blank" rel="noopener nofollow">${item.url}</a></td>
                <td>${item.role}</td>
              </tr>
            `,
          )
          .join("")
      : `<tr><td colspan="3">URLが未入力です。公式サイトやGoogleプロフィールなどのURLを入れると診断精度が上がります。</td></tr>`;

  analysisScopeList.innerHTML = result.analysisScope
    .map(
      (item) => `
        <article>
          <span>${item.status}</span>
          <h3>${item.title}</h3>
          <p>${item.detail}</p>
        </article>
      `,
    )
    .join("");

  drawRadarChart(radarCanvas, result.dimensionScores);
  drawBarChart(barCanvas, result.dimensionScores);

  offerList.innerHTML = getRecommendedOffers(result)
    .map(
      (offer) => `
        <article class="offer-card offer-${offer.id}">
          <div>
            <span class="offer-rank">推奨 ${offer.priority}</span>
            <p>${offer.category}</p>
          </div>
          <h3>${offer.name}</h3>
          <strong>${offer.headline}</strong>
          <p>${offer.description}</p>
          <ul>
            ${offer.fitFor.map((fit) => `<li>${fit}</li>`).join("")}
          </ul>
          <a href="${offer.url}" target="_blank" rel="sponsored noopener nofollow">AEO+LPを見る</a>
        </article>
      `,
    )
    .join("");

  resultPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function runProgress(urlCount) {
  resultPanel.hidden = true;
  offerSection.hidden = true;
  progressPanel.hidden = false;
  progressPanel.scrollIntoView({ behavior: "smooth", block: "center" });
  const duration = Math.min(4200, 1700 + urlCount * 450);

  for (let index = 0; index < progressSteps.length; index += 1) {
    const percent = Math.round(((index + 1) / progressSteps.length) * 100);
    progressStatus.textContent = progressSteps[index];
    progressBar.style.width = `${percent}%`;
    await wait(duration / progressSteps.length);
  }
}

function wait(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function drawRadarChart(canvas, data) {
  if (!canvas) return;
  const ctx = setupCanvas(canvas);
  const { width, height } = canvas.getBoundingClientRect();
  const centerX = width / 2;
  const centerY = height / 2 + 8;
  const radius = Math.min(width, height) * 0.32;
  ctx.clearRect(0, 0, width, height);
  ctx.font = "13px sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";

  for (let ring = 4; ring >= 1; ring -= 1) {
    ctx.beginPath();
    data.forEach((_, index) => {
      const point = radarPoint(centerX, centerY, radius * (ring / 4), index, data.length);
      if (index === 0) ctx.moveTo(point.x, point.y);
      else ctx.lineTo(point.x, point.y);
    });
    ctx.closePath();
    ctx.strokeStyle = `rgba(98, 231, 255, ${0.12 + ring * 0.07})`;
    ctx.stroke();
  }

  ctx.beginPath();
  data.forEach((item, index) => {
    const point = radarPoint(centerX, centerY, radius * (item.score / 100), index, data.length);
    if (index === 0) ctx.moveTo(point.x, point.y);
    else ctx.lineTo(point.x, point.y);
  });
  ctx.closePath();
  ctx.fillStyle = "rgba(60, 221, 179, 0.28)";
  ctx.strokeStyle = "#62e7ff";
  ctx.lineWidth = 2;
  ctx.fill();
  ctx.stroke();

  data.forEach((item, index) => {
    const labelPoint = radarPoint(centerX, centerY, radius + 34, index, data.length);
    ctx.fillStyle = "#d7efff";
    ctx.fillText(item.label, labelPoint.x, labelPoint.y - 8);
    ctx.fillStyle = "#8fffe1";
    ctx.fillText(`${item.score}`, labelPoint.x, labelPoint.y + 10);
  });
}

function drawBarChart(canvas, data) {
  if (!canvas) return;
  const ctx = setupCanvas(canvas);
  const { width, height } = canvas.getBoundingClientRect();
  ctx.clearRect(0, 0, width, height);
  const padding = 34;
  const gap = 18;
  const barWidth = (width - padding * 2 - gap * (data.length - 1)) / data.length;
  const chartHeight = height - 72;

  data.forEach((item, index) => {
    const x = padding + index * (barWidth + gap);
    const barHeight = chartHeight * (item.score / 100);
    const y = height - 42 - barHeight;
    const gradient = ctx.createLinearGradient(0, y, 0, height - 42);
    gradient.addColorStop(0, "#62e7ff");
    gradient.addColorStop(0.55, "#3cddb3");
    gradient.addColorStop(1, "#f5b94f");
    ctx.fillStyle = "rgba(255,255,255,0.08)";
    roundRect(ctx, x, 24, barWidth, chartHeight, 10);
    ctx.fill();
    ctx.fillStyle = gradient;
    roundRect(ctx, x, y, barWidth, barHeight, 10);
    ctx.fill();
    ctx.fillStyle = "#d7efff";
    ctx.font = "12px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(item.label, x + barWidth / 2, height - 18);
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 16px sans-serif";
    ctx.fillText(`${item.score}`, x + barWidth / 2, y - 10);
  });
}

function setupCanvas(canvas) {
  const ratio = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * ratio;
  canvas.height = rect.height * ratio;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  return ctx;
}

function radarPoint(centerX, centerY, radius, index, total) {
  const angle = -Math.PI / 2 + (Math.PI * 2 * index) / total;
  return {
    x: centerX + Math.cos(angle) * radius,
    y: centerY + Math.sin(angle) * radius,
  };
}

function roundRect(ctx, x, y, width, height, radius) {
  const r = Math.min(radius, width / 2, height / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + width, y, x + width, y + height, r);
  ctx.arcTo(x + width, y + height, x, y + height, r);
  ctx.arcTo(x, y + height, x, y, r);
  ctx.arcTo(x, y, x + r, y, r);
  ctx.closePath();
}
