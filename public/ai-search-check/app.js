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
const auditCategories = document.querySelector("[data-audit-categories]");
const auditCount = document.querySelector("[data-audit-count]");
const auditPager = document.querySelector("[data-audit-pager]");
const auditPageTitle = document.querySelector("[data-audit-page-title]");
const scenariosList = document.querySelector("[data-scenarios]");
let activeAuditCategories = [];
let activeAuditPage = 0;

const progressSteps = [
  "URLとページ種別を解析中",
  "100項目のAI検索シグナルを採点中",
  "業種別の検索意図と不足リスクを判定中",
  "改善優先度と推奨アクションを生成中",
];

checkList.innerHTML = getChecks()
  .map(
    (check) => `
      <label class="check-item">
        <input type="checkbox" name="checks" value="${check.id}" autocomplete="off">
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
  const checkedIds = [...new Set(formData.getAll("checks").map(String))].sort();
  const businessType = String(formData.get("businessType") || "Webサイト");
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
  reportMeta.textContent = `${result.businessType} / 有効URL ${result.validUrls.length}件 / 診断項目 ${result.auditItemCount}項目`;
  auditCount.textContent = `${result.auditItemCount}項目`;

  invalidUrlNote.textContent =
    result.invalidUrls.length > 0 ? `URL形式ではない入力があります: ${result.invalidUrls.join("、")}` : "";

  scenariosList.innerHTML = result.scenarios.map((scenario) => `<li>${scenario}</li>`).join("");

  riskList.innerHTML = result.findings
    .map(
      (finding) => `
        <article class="finding-card" data-severity="${finding.severity}">
          <span>${severityLabel(finding.severity)}</span>
          <h3>${finding.title}</h3>
          <p><strong>根拠:</strong> ${finding.evidence}</p>
          <p><strong>影響:</strong> ${finding.impact}</p>
          <p><strong>次の一手:</strong> ${finding.action}</p>
        </article>
      `,
    )
    .join("");

  activeAuditCategories = result.categoryAudits;
  activeAuditPage = 0;
  renderAuditPage();

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
      : `<tr><td colspan="3">URLが未入力です。公式サイトや外部掲載URLを入れると診断精度が上がります。</td></tr>`;

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

  drawRadarChart(radarCanvas, result.dimensionScores);
  drawBarChart(barCanvas, result.categoryAudits.slice(0, 5).map((category) => ({
    name: category.title.replace("エンティティ", "認識").replace("構造化データ", "技術").slice(0, 5),
    score: category.score,
  })));

  offerList.innerHTML = getRecommendedOffers(result)
    .map(
      (offer) => `
        <article class="offer-card offer-${offer.id}">
          ${offer.bannerImage ? `
            <a class="offer-banner" href="${offer.url}" target="_blank" rel="sponsored nofollow noopener" referrerpolicy="no-referrer-when-downgrade">
              <img src="${offer.bannerImage}" width="${offer.bannerWidth || 300}" height="${offer.bannerHeight || 250}" alt="${offer.name} 広告">
            </a>
            ${offer.impressionUrl ? `<img class="impression-pixel" src="${offer.impressionUrl}" width="1" height="1" alt="" loading="lazy">` : ""}
          ` : ""}
          <div>
            <span class="offer-rank">${offer.url ? "広告 / PR" : offer.statusLabel || "準備中"}・優先 ${offer.priority}</span>
            <p>${offer.category}</p>
          </div>
          <h3>${offer.name}</h3>
          <strong>${offer.headline}</strong>
          <p>${offer.description}</p>
          <ul>${offer.fitFor.map((fit) => `<li>${fit}</li>`).join("")}</ul>
          ${
            offer.url
              ? `<a href="${offer.url}" target="_blank" rel="sponsored nofollow noopener" referrerpolicy="no-referrer-when-downgrade">詳細を見る</a>`
              : `<span class="offer-disabled">${offer.ctaLabel || "準備中"}</span>`
          }
        </article>
      `,
    )
    .join("");

  resultPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderAuditPage() {
  const category = activeAuditCategories[activeAuditPage];
  if (!category) return;

  auditPageTitle.textContent = `${activeAuditPage + 1}/${activeAuditCategories.length} ${category.title}`;
  auditPager.innerHTML = activeAuditCategories
    .map(
      (item, index) => `
        <button type="button" class="${index === activeAuditPage ? "is-active" : ""}" data-audit-page="${index}">
          ${index + 1}
        </button>
      `,
    )
    .join("");

  auditCategories.innerHTML = `
    <article class="audit-page-card">
      <header>
        <div>
          <span>${category.title}</span>
          <h3>${category.score}/100</h3>
        </div>
        <p>OK ${category.ok} / 要確認 ${category.partial} / 不足 ${category.missing}</p>
      </header>
      <ul>
        ${category.items
          .map((item) => `<li data-status="${item.status}"><span>${statusLabel(item.status)}</span>${item.label}</li>`)
          .join("")}
      </ul>
    </article>
  `;
}

auditPager.addEventListener("click", (event) => {
  const button = event.target.closest("[data-audit-page]");
  if (!button) return;
  activeAuditPage = Number(button.dataset.auditPage);
  renderAuditPage();
});

async function runProgress(urlCount) {
  resultPanel.hidden = true;
  offerSection.hidden = true;
  progressPanel.hidden = false;
  progressPanel.scrollIntoView({ behavior: "smooth", block: "center" });
  progressBar.style.width = "0%";
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

function severityLabel(severity) {
  return { critical: "最重要", high: "重要", medium: "要改善", low: "良好" }[severity] || "要確認";
}

function statusLabel(status) {
  return { ok: "OK", partial: "要確認", missing: "不足" }[status] || "要確認";
}

function drawRadarChart(canvas, data) {
  if (!canvas) return;
  const ctx = setupCanvas(canvas);
  const { width, height } = canvas.getBoundingClientRect();
  const centerX = width / 2;
  const centerY = height / 2 + 8;
  const radius = Math.min(width, height) * 0.31;
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
  const padding = 28;
  const gap = 10;
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
    roundRect(ctx, x, 24, barWidth, chartHeight, 8);
    ctx.fill();
    ctx.fillStyle = gradient;
    roundRect(ctx, x, y, barWidth, barHeight, 8);
    ctx.fill();
    ctx.fillStyle = "#d7efff";
    ctx.font = "11px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(item.name, x + barWidth / 2, height - 18);
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 14px sans-serif";
    ctx.fillText(`${item.score}`, x + barWidth / 2, y - 8);
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
  ctx.arcTo(x, y, x + width, y, r);
  ctx.closePath();
}
