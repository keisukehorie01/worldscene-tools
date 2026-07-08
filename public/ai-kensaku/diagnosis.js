const urlPattern = /^https?:\/\/[^\s/$.?#].[^\s]*$/i;

const dimensions = [
  {
    id: "entity",
    name: "Entity",
    label: "公式情報",
    description: "AIが同一事業者として理解できる会社情報、所在地、サービス情報の一貫性",
  },
  {
    id: "answer",
    name: "Answer",
    label: "回答性",
    description: "AI OverviewやChatGPTが回答に使いやすいFAQ、説明文、比較検討情報",
  },
  {
    id: "technical",
    name: "Technical",
    label: "技術基盤",
    description: "構造化データ、表示速度、モバイル品質などのクロールしやすさ",
  },
  {
    id: "trust",
    name: "Trust",
    label: "信頼性",
    description: "運営者情報、実績、口コミ、更新性などの信頼シグナル",
  },
];

const checks = [
  {
    id: "official",
    label: "公式HPまたは自社サービスページがある",
    points: 16,
    dimension: "entity",
    impact: "critical",
    roadMap:
      "会社名、所在地、電話番号、営業時間、対応エリア、サービス内容を公式ページにまとめ、AIが一次情報として参照しやすい状態にします。",
  },
  {
    id: "local",
    label: "Googleビジネスプロフィールや外部掲載情報が整っている",
    points: 14,
    dimension: "entity",
    impact: "high",
    roadMap:
      "Googleビジネスプロフィール、SNS、掲載サイトの会社名・住所・営業時間を公式HPと一致させ、情報のズレを減らします。",
  },
  {
    id: "faq",
    label: "よくある質問と回答をページ内に掲載している",
    points: 16,
    dimension: "answer",
    impact: "critical",
    roadMap:
      "料金、対応範囲、納期、予約方法、注意点などの質問に本文で直接回答し、FAQ構造化データも追加します。",
  },
  {
    id: "schema",
    label: "構造化データを入れている",
    points: 14,
    dimension: "technical",
    impact: "critical",
    roadMap:
      "Organization、LocalBusiness、Service、FAQPage、BreadcrumbListなど、業種とページ内容に合うJSON-LDを追加します。",
  },
  {
    id: "servicePages",
    label: "サービス・料金・事例などの個別ページがある",
    points: 12,
    dimension: "answer",
    impact: "high",
    roadMap:
      "代表サービス、対象者、料金目安、実績、問い合わせ導線をテーマ別に整理し、AIが引用しやすい説明単位を増やします。",
  },
  {
    id: "speed",
    label: "スマホ表示が速く、レイアウトが崩れない",
    points: 10,
    dimension: "technical",
    impact: "medium",
    roadMap:
      "画像サイズ、不要なスクリプト、サーバー応答、モバイル表示を見直し、ユーザーと検索エンジンの双方が読みやすい状態にします。",
  },
  {
    id: "authorTrust",
    label: "運営者情報・実績・口コミ導線がある",
    points: 10,
    dimension: "trust",
    impact: "high",
    roadMap:
      "誰が運営しているか、どんな実績があるか、第三者評価をどこで確認できるかを明記し、信頼材料を増やします。",
  },
  {
    id: "freshness",
    label: "営業時間やお知らせを定期的に更新している",
    points: 8,
    dimension: "trust",
    impact: "medium",
    roadMap:
      "最新情報、休業日、キャンペーン、サービス変更を更新し、古い情報として扱われるリスクを下げます。",
  },
];

export function getChecks() {
  return checks.map((check) => ({ ...check }));
}

export function normalizeUrls(rawText) {
  const normalized = rawText
    .split(/\s+/)
    .map((url) => normalizeUrl(url))
    .filter(Boolean);

  return [...new Set(normalized)].sort();
}

export function diagnoseSite({ urls, checkedIds, businessType }) {
  const normalizedUrls = normalizeUrls(Array.isArray(urls) ? urls.join("\n") : String(urls || ""));
  const validUrls = normalizedUrls.filter((url) => urlPattern.test(url));
  const invalidUrls = normalizedUrls.filter((url) => !urlPattern.test(url));
  const urlAudit = buildUrlAudit(validUrls);
  const checked = new Set([...checkedIds, ...inferChecksFromUrls(urlAudit)]);
  const baseScore = checks.reduce((score, check) => score + (checked.has(check.id) ? check.points : 0), 0);
  const urlBonus = Math.min(validUrls.length * 2, 8);
  const score = Math.min(100, baseScore + urlBonus);
  const missingChecks = checks.filter((check) => !checked.has(check.id));
  const dimensionScores = buildDimensionScores(checked, validUrls.length);
  const riskRegister = buildRiskRegister(missingChecks, score);
  const cleanBusinessType = String(businessType || "店舗・サービス").trim() || "店舗・サービス";

  return {
    score,
    grade: getGrade(score),
    businessType: cleanBusinessType,
    validUrls,
    invalidUrls,
    completedChecks: checks.filter((check) => checked.has(check.id)),
    missingChecks,
    dimensionScores,
    urlAudit,
    analysisScope: buildAnalysisScope(validUrls, cleanBusinessType),
    riskRegister,
    actionPlan: buildActionPlan(missingChecks, score),
    opportunityScore: buildOpportunityScore(score, validUrls.length, missingChecks.length),
    roadMap: buildRoadMap(missingChecks, score),
    summary: buildSummary(score, validUrls.length),
  };
}

function normalizeUrl(rawUrl) {
  const value = String(rawUrl || "").trim();
  if (!value) return "";

  try {
    const url = new URL(value);
    url.hash = "";
    url.protocol = url.protocol.toLowerCase();
    url.hostname = url.hostname.toLowerCase();
    if (url.pathname.length > 1) url.pathname = url.pathname.replace(/\/+$/, "");
    url.searchParams.sort();
    return url.toString();
  } catch {
    return value;
  }
}

function buildAnalysisScope(validUrls, businessType) {
  const officialUrls = validUrls.filter(
    (url) => !/(google|instagram|tabelog|gnavi|hotpepper|facebook|x\.com|twitter|tiktok|maps\.app\.goo\.gl)/i.test(url),
  );
  const externalUrls = validUrls.filter((url) => !officialUrls.includes(url));
  const hasOfficial = officialUrls.length > 0;

  return [
    {
      title: "公式HP / サービスページ",
      status: hasOfficial ? "解析対象" : "URL追加推奨",
      detail: hasOfficial
        ? "入力された公式URLを一次情報の中心として扱い、タイトル、説明文、見出し、問い合わせ導線の充足度を評価します。"
        : "公式サイトURLが未入力です。AI回答の根拠となる一次情報ページを追加すると診断精度が上がります。",
    },
    {
      title: "主要ページ",
      status: "優先確認対象",
      detail:
        "FAQ、サービス、料金、アクセス、会社概要、問い合わせ、事例ページがAI検索に必要な情報源として整っているかを確認します。",
    },
    {
      title: "構造化データ / HTML構造",
      status: "評価対象",
      detail:
        "JSON-LD、見出し階層、内部リンク、パンくず、FAQPageやLocalBusiness系スキーマの有無を確認します。",
    },
    {
      title: "外部掲載・SNS・Googleプロフィール",
      status: externalUrls.length > 0 ? `${externalUrls.length}件を参照候補` : "URL追加推奨",
      detail:
        "公式HPと外部掲載情報の会社名、住所、営業時間、問い合わせ導線にズレがないかを確認する前提で評価します。",
    },
    {
      title: "業種別AI回答シナリオ",
      status: businessType,
      detail:
        "業種に応じて、料金、予約可否、対応エリア、比較検討、実績など、AI Overviewで回答されやすい質問群を評価します。",
    },
  ];
}

function getGrade(score) {
  if (score >= 82) return { label: "強い", tone: "good" };
  if (score >= 58) return { label: "改善余地あり", tone: "medium" };
  return { label: "要整備", tone: "low" };
}

function buildSummary(score, urlCount) {
  if (score >= 82) {
    return `AI検索に必要な情報設計はかなり整っています。外部掲載URL ${urlCount}件との情報一致を保ちながら、FAQと構造化データを継続更新しましょう。`;
  }
  if (score >= 58) {
    return "AI検索に拾われる土台はあります。FAQ、構造化データ、サービス説明、外部掲載情報の統一を進めると表示機会を増やしやすくなります。";
  }
  return "AI検索に必要な公式情報の整理が不足している可能性があります。まずは公式ページ、FAQ、構造化データ、信頼情報を整えるのがおすすめです。";
}

function buildRoadMap(missingChecks, score) {
  const topMissing = missingChecks.slice(0, 4).map((check, index) => ({
    step: index + 1,
    title: check.label,
    action: check.roadMap,
  }));

  if (topMissing.length > 0) return topMissing;

  return [
    {
      step: 1,
      title: "AI検索での見え方を継続チェック",
      action:
        score >= 82
          ? "主要な質問文でAI OverviewやChatGPTにどの情報が引用されるかを定期的に確認します。"
          : "不足しているページとFAQを追加し、検索結果とAI回答の変化を確認します。",
    },
  ];
}

function buildDimensionScores(checked, urlCount) {
  return dimensions.map((dimension) => {
    const related = checks.filter((check) => check.dimension === dimension.id);
    const max = related.reduce((sum, check) => sum + check.points, 0);
    const current = related.reduce((sum, check) => sum + (checked.has(check.id) ? check.points : 0), 0);
    const bonus = dimension.id === "entity" ? Math.min(urlCount * 3, 10) : 0;
    return {
      ...dimension,
      score: Math.min(100, Math.round(((current + bonus) / max) * 100)),
      current,
      max,
    };
  });
}

function buildUrlAudit(validUrls) {
  const patterns = [
    { type: "公式サイト", test: /^(?!.*(google|instagram|tabelog|gnavi|hotpepper|facebook|x\.com|twitter))/i },
    { type: "Googleプロフィール", test: /google\.[^/]+\/maps|maps\.app\.goo\.gl/i },
    { type: "SNS", test: /instagram|facebook|x\.com|twitter|tiktok/i },
    { type: "掲載サイト", test: /tabelog|gnavi|hotpepper|retty|ikyu|ozmall/i },
  ];

  return validUrls.map((url) => {
    const found = patterns.find((pattern) => pattern.test.test(url));
    return {
      url,
      type: found?.type ?? "外部ページ",
      role:
        found?.type === "公式サイト"
          ? "AI回答の一次情報として整備する中心ページ"
          : "公式情報との整合性を確認する参照情報",
    };
  });
}

function inferChecksFromUrls(urlAudit) {
  const inferred = new Set();
  for (const item of urlAudit) {
    if (item.type === "公式サイト") inferred.add("official");
    if (item.type === "Googleプロフィール" || item.type === "掲載サイト") inferred.add("local");
    if (item.type === "SNS") inferred.add("authorTrust");
  }
  return inferred;
}

function buildRiskRegister(missingChecks, score) {
  const risks = missingChecks.map((check) => ({
    title: check.label,
    severity: check.impact,
    detail: riskDetail(check.id),
  }));

  if (score < 58) {
    risks.unshift({
      title: "AI回答に必要な一次情報が不足",
      severity: "critical",
      detail:
        "公式情報、FAQ、構造化データが不足すると、AIが競合や外部掲載サイトを優先して参照する可能性があります。",
    });
  }

  return risks.slice(0, 6);
}

function riskDetail(id) {
  const details = {
    official: "公式サイトが弱い場合、AIは第三者サイトの断片情報を回答根拠にしやすくなります。",
    local: "外部掲載情報に差分があると、営業時間、住所、予約可否などの回答が不安定になります。",
    faq: "質問への直接回答がないと、AI Overviewで引用される文章が不足します。",
    schema: "JSON-LDがないと、業種、所在地、FAQ、パンくずなどの意味づけが弱くなります。",
    servicePages: "サービス別ページがないと、検索意図ごとの着地先と回答材料が不足します。",
    speed: "表示速度やモバイル品質が低いと、ユーザー体験とクロール効率の両方を損ないます。",
    authorTrust: "運営者や実績が曖昧だと、AIとユーザーが信頼できる根拠を見つけにくくなります。",
    freshness: "更新が止まっているページは、古い情報として扱われる可能性があります。",
  };
  return details[id] ?? "AI検索での引用・表示に必要なシグナルが不足しています。";
}

function buildActionPlan(missingChecks, score) {
  const priority = missingChecks.slice(0, 5);
  return [
    {
      phase: "0-30日",
      title: score < 58 ? "公式情報とFAQの緊急整備" : "AI回答に使われる本文の強化",
      tasks: priority.slice(0, 2).map((check) => check.roadMap),
    },
    {
      phase: "31-60日",
      title: "構造化データと外部掲載情報の整合",
      tasks: priority.slice(2, 4).map((check) => check.roadMap),
    },
    {
      phase: "61-90日",
      title: "検索クエリ別ページと継続改善",
      tasks: [
        "主要な質問文でAI Overview、ChatGPT、検索結果の表示状況を記録します。",
        "アクセス、予約、料金、事例、口コミ導線のページを増やし、内部リンクでつなぎます。",
      ],
    },
  ].map((phase) => ({
    ...phase,
    tasks: phase.tasks.length > 0 ? phase.tasks : ["現状の強みを維持し、更新頻度と外部掲載情報の整合性を確認します。"],
  }));
}

function buildOpportunityScore(score, urlCount, missingCount) {
  const upside = Math.min(100, Math.max(18, 100 - score + missingCount * 5 + urlCount * 2));
  return {
    label: upside >= 70 ? "改善余地 大" : upside >= 42 ? "改善余地 中" : "改善余地 小",
    value: upside,
  };
}
