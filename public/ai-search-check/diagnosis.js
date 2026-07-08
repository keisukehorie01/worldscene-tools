const urlPattern = /^https?:\/\/[^\s/$.?#].[^\s]*$/i;

const profiles = {
  b2b: {
    match: /bto?b|法人向け|企業向け|SaaS|B2B/i,
    name: "BtoBサービス",
    kind: "b2b",
    entityName: "企業・サービス認識",
    primaryPage: "サービスLP / 公式サイト",
    externalName: "外部掲載・比較記事・SNS",
    conversionName: "問い合わせ・資料請求導線",
    audience: "導入検討者・決裁者・比較検討者",
    scenarios: [
      "このサービスは何を解決するのか",
      "料金、導入期間、対象企業規模はどうか",
      "競合と比べた強みは何か",
      "導入事例や実績は信頼できるか",
    ],
    scopePages: "サービス、料金、機能、導入事例、FAQ、会社概要、問い合わせ、資料請求ページ",
    primaryAction: "問い合わせ・資料請求・無料相談に進める情報設計を整える",
  },
  local: {
    match: /飲食|美容|小売|店舗|サロン/i,
    name: "店舗・ローカルビジネス",
    kind: "local",
    entityName: "店舗・事業者認識",
    primaryPage: "LP / トップページ",
    externalName: "外部掲載・SNS・Googleマップ",
    conversionName: "予約・問い合わせ導線",
    audience: "来店前の比較検討ユーザー",
    scenarios: [
      "営業時間、場所、予約可否はどうか",
      "料金やメニュー、対応サービスは何か",
      "口コミや実績は信頼できるか",
      "初めて行く前に不安を解消できるか",
    ],
    scopePages: "FAQ、サービス、料金、アクセス、店舗情報、問い合わせ、口コミ・実績ページ",
    primaryAction: "来店前の疑問に直接答え、予約・問い合わせまで迷わず進める導線を作る",
  },
  clinic: {
    match: /クリニック|医院|病院|医療/i,
    name: "クリニック・医療サイト",
    kind: "medical",
    entityName: "医療機関・診療内容認識",
    primaryPage: "公式サイト / 診療案内ページ",
    externalName: "医療ポータル・Googleマップ・SNS",
    conversionName: "予約・問い合わせ導線",
    audience: "受診前に比較検討するユーザー",
    scenarios: [
      "どの診療に対応しているのか",
      "診療時間、予約方法、アクセスはどうか",
      "医師や設備、実績は信頼できるか",
      "初診前の不安を解消できるか",
    ],
    scopePages: "診療案内、料金、アクセス、医師紹介、FAQ、予約・問い合わせページ",
    primaryAction: "受診前の不安に直接答え、予約・問い合わせまで迷わず進める導線を作る",
  },
  professional: {
    match: /士業|専門|コンサル|税理士|弁護士|司法書士|行政書士|社労士|会計|制作|開発|マーケ/i,
    name: "士業・専門サービス",
    kind: "professional",
    entityName: "専門家・サービス認識",
    primaryPage: "公式サイト / サービスLP",
    externalName: "外部掲載・実績・SNS",
    conversionName: "相談・問い合わせ導線",
    audience: "相談先を比較検討するユーザー",
    scenarios: [
      "どの相談・業務に対応しているのか",
      "費用、対応範囲、相談方法は明確か",
      "実績や専門性は信頼できるか",
      "他の専門家と比べた強みは何か",
    ],
    scopePages: "サービス、料金、事例、専門家プロフィール、FAQ、問い合わせページ",
    primaryAction: "相談前の疑問に直接答え、問い合わせ・無料相談に進める導線を整える",
  },
  general: {
    match: /.*/,
    name: "Webサイト",
    kind: "general",
    entityName: "サイト・事業者認識",
    primaryPage: "LP / 公式サイト",
    externalName: "外部掲載・SNS",
    conversionName: "問い合わせ導線",
    audience: "検索・AI回答から訪れる検討者",
    scenarios: [
      "何を提供しているのか",
      "誰に向いているのか",
      "料金や利用条件は明確か",
      "信頼できる根拠はあるか",
    ],
    scopePages: "FAQ、サービス、料金、会社概要、問い合わせ、実績ページ",
    primaryAction: "AIが回答に使いやすい一次情報と問い合わせ導線を整える",
  },
};

const dimensions = [
  { id: "entity", name: "Entity", label: "認識", description: "AIが事業者・サービスを正しく認識できるか" },
  { id: "answer", name: "Answer", label: "回答", description: "AI回答に引用しやすい質問・回答・本文があるか" },
  { id: "technical", name: "Technical", label: "技術", description: "構造化データ、HTML、速度、モバイル品質" },
  { id: "trust", name: "Trust", label: "信頼", description: "実績、運営者、口コミ、更新性などの根拠" },
  { id: "conversion", name: "CV", label: "導線", description: "問い合わせ、申し込み、資料請求など次の行動に自然に進めるか" },
];

const checks = [
  {
    id: "official",
    label: "公式サイトまたは一次情報ページがある",
    points: 14,
    dimension: "entity",
    impact: "critical",
    roadMap: "公式ページを一次情報の中心にして、事業内容、対象者、提供価値、問い合わせ導線を明確にします。",
  },
  {
    id: "local",
    label: "外部掲載・SNS・マップ等の情報が整理されている",
    points: 12,
    dimension: "entity",
    impact: "high",
    roadMap: "外部掲載と公式情報の差分をなくし、AIが同じ事業者として認識しやすい状態にします。",
  },
  {
    id: "faq",
    label: "よくある質問と回答をページ内に掲載している",
    points: 15,
    dimension: "answer",
    impact: "critical",
    roadMap: "検討者がAIに聞きそうな質問をFAQ化し、本文とFAQ構造化データの両方で回答を明示します。",
  },
  {
    id: "schema",
    label: "構造化データを入れている",
    points: 13,
    dimension: "technical",
    impact: "critical",
    roadMap: "Organization、WebSite、FAQPage、BreadcrumbListなど、サイトに合うJSON-LDを追加します。",
  },
  {
    id: "servicePages",
    label: "サービス・料金・事例などの個別ページがある",
    points: 13,
    dimension: "answer",
    impact: "high",
    roadMap: "サービス、料金、対象者、比較軸、事例をページ単位で分け、AIが引用しやすい粒度にします。",
  },
  {
    id: "speed",
    label: "スマホ表示が速く、レイアウトが崩れない",
    points: 10,
    dimension: "technical",
    impact: "medium",
    roadMap: "画像、スクリプト、サーバー応答、モバイル表示を見直し、読みやすいサイトにします。",
  },
  {
    id: "authorTrust",
    label: "運営者情報・実績・導入事例・口コミなどがある",
    points: 12,
    dimension: "trust",
    impact: "high",
    roadMap: "運営者、実績、導入事例、第三者評価を明記し、AIとユーザー双方の信頼材料を増やします。",
  },
  {
    id: "freshness",
    label: "お知らせや実績を定期的に更新している",
    points: 8,
    dimension: "trust",
    impact: "medium",
    roadMap: "最新情報、事例、FAQ、サービス変更点を更新し、古い情報として扱われるリスクを下げます。",
  },
  {
    id: "conversion",
    label: "問い合わせ・申し込み・資料請求などの導線が明確",
    points: 13,
    dimension: "conversion",
    impact: "high",
    roadMap: "AI回答から来たユーザーが次に取る行動を想定し、CTA、フォーム、電話、資料請求を整理します。",
  },
];

const auditCategories = [
  {
    id: "entity",
    title: "エンティティ認識",
    dimension: "entity",
    items: [
      ["official", "公式サイトが一次情報として存在する"],
      ["official", "事業名・サービス名が明確に書かれている"],
      ["official", "提供価値が1文で理解できる"],
      ["official", "対象ユーザー・対象企業が明確"],
      ["official", "所在地または運営会社情報が確認できる"],
      ["local", "外部掲載と公式情報に矛盾が少ない"],
      ["local", "SNSや外部掲載が補助情報として機能している"],
      ["authorTrust", "ブランド・会社名で検索した時の受け皿がある"],
      ["freshness", "古い情報だけで構成されていない"],
      ["official", "AIが同一事業者として認識しやすい情報構造"],
    ],
  },
  {
    id: "answer",
    title: "AI回答適性",
    dimension: "answer",
    items: [
      ["faq", "よくある質問が本文に掲載されている"],
      ["faq", "質問に対して短く直接回答している"],
      ["servicePages", "サービス内容がページ単位で整理されている"],
      ["servicePages", "料金または費用感が確認できる"],
      ["servicePages", "対象者・対象企業が説明されている"],
      ["servicePages", "導入・利用の流れが説明されている"],
      ["faq", "比較検討時の不安に答えている"],
      ["authorTrust", "実績や事例が回答材料になる"],
      ["faq", "専門用語の説明がある"],
      ["servicePages", "AIが引用しやすい結論文がある"],
    ],
  },
  {
    id: "technical",
    title: "技術・構造化データ",
    dimension: "technical",
    items: [
      ["schema", "OrganizationまたはLocalBusiness系JSON-LDがある"],
      ["schema", "FAQPage JSON-LDを追加できる構成"],
      ["schema", "BreadcrumbListを追加できる構成"],
      ["schema", "titleとmeta descriptionがページ別に設計されている"],
      ["schema", "h1が1ページ1テーマになっている"],
      ["schema", "h2/h3で論点が整理されている"],
      ["speed", "スマホで読めるレイアウト"],
      ["speed", "画像が重すぎない"],
      ["speed", "不要なスクリプトが少ない"],
      ["schema", "内部リンクで重要ページがつながっている"],
    ],
  },
  {
    id: "trust",
    title: "信頼性・E-E-A-T",
    dimension: "trust",
    items: [
      ["authorTrust", "運営会社または運営者情報がある"],
      ["authorTrust", "実績・導入事例・制作事例がある"],
      ["authorTrust", "お客様の声・口コミ・評価がある"],
      ["authorTrust", "専門性を示す説明がある"],
      ["authorTrust", "問い合わせ先が明確"],
      ["freshness", "更新日や最新情報が確認できる"],
      ["authorTrust", "利用規約・プライバシーポリシーがある"],
      ["authorTrust", "第三者評価や掲載実績がある"],
      ["authorTrust", "代表者・チーム・監修者情報がある"],
      ["freshness", "情報が放置されている印象が少ない"],
    ],
  },
  {
    id: "conversion",
    title: "CV導線",
    dimension: "conversion",
    items: [
      ["conversion", "問い合わせ・申し込み・資料請求ボタンが見つけやすい"],
      ["conversion", "ファーストビューに主要CTAがある"],
      ["conversion", "FAQ後に次の行動が提示されている"],
      ["conversion", "フォームへの導線が明確"],
      ["conversion", "電話・メールなど代替手段がある"],
      ["conversion", "料金確認後の行動が明確"],
      ["conversion", "事例閲覧後の行動が明確"],
      ["conversion", "スマホでCTAが押しやすい"],
      ["conversion", "強引すぎない相談導線がある"],
      ["conversion", "AI回答から来た人向けの受け皿がある"],
    ],
  },
  {
    id: "coverage",
    title: "ページ網羅性",
    dimension: "answer",
    items: [
      ["servicePages", "トップページ以外の下層ページがある"],
      ["servicePages", "サービス詳細ページがある"],
      ["servicePages", "料金ページまたは料金セクションがある"],
      ["faq", "FAQページまたはFAQセクションがある"],
      ["authorTrust", "会社概要・事業者情報ページがある"],
      ["conversion", "問い合わせページがある"],
      ["servicePages", "導入事例・実績ページがある"],
      ["servicePages", "比較・選び方に答えるページがある"],
      ["freshness", "お知らせ・更新情報がある"],
      ["schema", "サイト全体のページ構造がAIに伝わる"],
    ],
  },
  {
    id: "query",
    title: "検索意図カバー",
    dimension: "answer",
    items: [
      ["faq", "What系の質問に答えている"],
      ["servicePages", "How系の質問に答えている"],
      ["servicePages", "料金・費用系の質問に答えている"],
      ["authorTrust", "信頼できるかという質問に答えている"],
      ["conversion", "申し込み方法に答えている"],
      ["servicePages", "比較検討系の質問に答えている"],
      ["faq", "不安・懸念に答えている"],
      ["servicePages", "対象外・できないことも説明している"],
      ["freshness", "最新状況に関する質問に答えられる"],
      ["official", "ブランド名検索の受け皿がある"],
    ],
  },
  {
    id: "snippet",
    title: "引用されやすさ",
    dimension: "answer",
    items: [
      ["faq", "結論が先に書かれている"],
      ["faq", "1問1答形式がある"],
      ["servicePages", "箇条書きで要点が整理されている"],
      ["servicePages", "数値・条件・対象が明確"],
      ["schema", "表やリストがHTMLで読める"],
      ["faq", "曖昧な宣伝文だけで終わっていない"],
      ["authorTrust", "根拠や実績が近くに書かれている"],
      ["servicePages", "ページごとの主題が明確"],
      ["schema", "重要情報が画像内テキストだけになっていない"],
      ["conversion", "回答後の次アクションが明確"],
    ],
  },
  {
    id: "external",
    title: "外部整合性",
    dimension: "entity",
    items: [
      ["local", "Googleマップ等の外部情報を確認できる"],
      ["local", "掲載サイトの情報と公式情報を合わせられる"],
      ["authorTrust", "SNSが信頼補強になる"],
      ["authorTrust", "第三者サイトの掲載がある"],
      ["freshness", "外部掲載の古い情報を更新できる"],
      ["local", "名称表記ゆれが少ない"],
      ["local", "住所・連絡先・営業時間の差分が少ない"],
      ["authorTrust", "口コミ・レビューへの導線がある"],
      ["official", "外部ではなく公式が最終情報源になっている"],
      ["schema", "外部URLを適切に関連情報として扱える"],
    ],
  },
  {
    id: "operation",
    title: "運用・改善体制",
    dimension: "trust",
    items: [
      ["freshness", "定期更新できる運用体制がある"],
      ["freshness", "FAQを追加し続けられる"],
      ["freshness", "実績や事例を追加し続けられる"],
      ["schema", "構造化データを保守できる"],
      ["speed", "表示速度を継続改善できる"],
      ["local", "外部掲載情報の棚卸しができる"],
      ["conversion", "問い合わせ導線を計測・改善できる"],
      ["servicePages", "新サービス追加時にページを増やせる"],
      ["authorTrust", "信頼材料を継続的に増やせる"],
      ["faq", "AI回答の表示状況を見て改善できる"],
    ],
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
  const profile = getProfile(businessType);
  const normalizedUrls = normalizeUrls(Array.isArray(urls) ? urls.join("\n") : String(urls || ""));
  const validUrls = normalizedUrls.filter((url) => urlPattern.test(url));
  const invalidUrls = normalizedUrls.filter((url) => !urlPattern.test(url));
  const urlAudit = buildUrlAudit(validUrls, profile);
  const checked = new Set([...(checkedIds || []).map(String), ...inferChecksFromUrls(urlAudit)]);
  const baseScore = checks.reduce((score, check) => score + (checked.has(check.id) ? check.points : 0), 0);
  const urlBonus = Math.min(validUrls.length * 2, 8);
  const score = Math.min(100, baseScore + urlBonus);
  const missingChecks = checks.filter((check) => !checked.has(check.id));
  const dimensionScores = buildDimensionScores(checked, validUrls.length);
  const categoryAudits = buildCategoryAudits(checked, validUrls.length);
  const findings = buildFindings(missingChecks, checked, profile, score);

  return {
    score,
    grade: getGrade(score),
    profile,
    businessType: profile.name,
    validUrls,
    invalidUrls,
    completedChecks: checks.filter((check) => checked.has(check.id)),
    missingChecks,
    dimensionScores,
    categoryAudits,
    auditItemCount: auditCategories.reduce((sum, category) => sum + category.items.length, 0),
    urlAudit,
    analysisScope: buildAnalysisScope(validUrls, profile),
    findings,
    riskRegister: findings.map((finding) => ({
      title: finding.title,
      severity: finding.severity,
      detail: finding.impact,
    })),
    actionPlan: buildActionPlan(missingChecks, score, profile),
    opportunityScore: buildOpportunityScore(score, validUrls.length, missingChecks.length),
    roadMap: buildRoadMap(missingChecks, score, profile),
    summary: buildSummary(score, validUrls.length, profile),
    scenarios: profile.scenarios,
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

function buildCategoryAudits(checked, urlCount) {
  return auditCategories.map((category) => {
    const items = category.items.map(([signal, label]) => {
      const status = checked.has(signal) ? "ok" : urlCount > 0 && ["official", "local", "authorTrust"].includes(signal) ? "partial" : "missing";
      const points = status === "ok" ? 1 : status === "partial" ? 0.45 : 0;
      return { label, signal, status, points };
    });
    const score = Math.round((items.reduce((sum, item) => sum + item.points, 0) / items.length) * 100);
    return {
      id: category.id,
      title: category.title,
      dimension: category.dimension,
      score,
      ok: items.filter((item) => item.status === "ok").length,
      partial: items.filter((item) => item.status === "partial").length,
      missing: items.filter((item) => item.status === "missing").length,
      items,
    };
  });
}

function getProfile(businessType) {
  const value = String(businessType || "");
  return Object.values(profiles).find((profile) => profile.match.test(value)) || profiles.general;
}

function getGrade(score) {
  if (score >= 82) return { label: "強い", tone: "good" };
  if (score >= 58) return { label: "改善余地あり", tone: "medium" };
  return { label: "要整備", tone: "low" };
}

function buildSummary(score, urlCount, profile) {
  const target = profile.audience;
  if (score >= 82) {
    return `${target}に対するAI回答の土台はかなり整っています。入力URL ${urlCount} 件の整合性を保ちつつ、FAQと実績情報を継続更新しましょう。`;
  }
  if (score >= 58) {
    return `${target}に見つけてもらう土台はあります。FAQ、構造化データ、事例・料金・サービスページを補強すると表示機会を増やしやすくなります。`;
  }
  return `${target}がAI検索で比較検討するには、一次情報がまだ不足している可能性があります。まず公式ページ、FAQ、信頼材料、導線を整えるのが優先です。`;
}

function buildAnalysisScope(validUrls, profile) {
  const officialUrls = validUrls.filter((url) => !/(google|instagram|tabelog|gnavi|hotpepper|facebook|x\.com|twitter|tiktok|maps\.app\.goo\.gl)/i.test(url));
  const externalUrls = validUrls.filter((url) => !officialUrls.includes(url));
  const hasOfficial = officialUrls.length > 0;

  return [
    {
      title: profile.primaryPage,
      status: hasOfficial ? "解析対象" : "URL追加推奨",
      detail: hasOfficial
        ? "title、description、h1、主要CTA、ファーストビュー、回答に使える本文を評価対象にします。"
        : "一次情報になる公式URLが未入力です。診断精度を上げるには公式ページURLが必要です。",
    },
    {
      title: "主要下層ページ",
      status: "本格版で最大30ページ",
      detail: `${profile.scopePages}を優先クロールする前提で、AI回答に必要な情報充足度を見ます。`,
    },
    {
      title: "構造化データ / HTML",
      status: "評価対象",
      detail: "JSON-LD、見出し階層、内部リンク、パンくず、FAQPage、Organization系スキーマを診断します。",
    },
    {
      title: profile.externalName,
      status: externalUrls.length > 0 ? `${externalUrls.length}件を参照元扱い` : "URL追加推奨",
      detail: "公式情報との整合性、第三者評価、認知補強、AIが参照しやすい情報のズレを確認します。",
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

function buildUrlAudit(validUrls, profile) {
  const patterns = [
    { type: "公式サイト", test: /^(?!.*(google|instagram|tabelog|gnavi|hotpepper|facebook|x\.com|twitter|tiktok|maps\.app\.goo\.gl))/i },
    { type: "Googleマップ", test: /google\.[^/]+\/maps|maps\.app\.goo\.gl/i },
    { type: "SNS", test: /instagram|facebook|x\.com|twitter|tiktok/i },
    { type: "掲載・比較サイト", test: /tabelog|gnavi|hotpepper|retty|ikyu|ozmall|note|wantedly|prtimes|itreview|boxil|aspic/i },
  ];

  return validUrls.map((url) => {
    const found = patterns.find((pattern) => pattern.test.test(url));
    const type = found?.type ?? "外部ページ";
    return {
      url,
      type,
      role:
        type === "公式サイト"
          ? `${profile.primaryPage}として一次情報の中心にする候補`
          : "公式情報との整合性・第三者評価・認知補強を確認する参照元",
    };
  });
}

function inferChecksFromUrls(urlAudit) {
  const inferred = new Set();
  for (const item of urlAudit) {
    if (item.type === "公式サイト") inferred.add("official");
    if (item.type === "Googleマップ" || item.type === "掲載・比較サイト") inferred.add("local");
    if (item.type === "SNS" || item.type === "掲載・比較サイト") inferred.add("authorTrust");
  }
  return inferred;
}

function buildFindings(missingChecks, checked, profile, score) {
  const missing = new Set(missingChecks.map((check) => check.id));
  const findings = [];

  if (score < 58) {
    findings.push({
      severity: "critical",
      title: "AI回答に使える一次情報が不足しています",
      evidence: `${profile.primaryPage}、FAQ、信頼材料、導線のいずれかが弱く、AIが外部情報や競合情報を優先する可能性があります。`,
      impact: `${profile.audience}がAI検索で比較した時に、貴社・貴サービスの強みが回答に出にくくなります。`,
      action: profile.primaryAction,
    });
  }

  if (missing.has("faq") || missing.has("servicePages")) {
    findings.push({
      severity: "high",
      title: "検討質問に対する回答ページが足りません",
      evidence: "FAQ、サービス詳細、料金、比較軸、事例などが不足している可能性があります。",
      impact: "AI OverviewやChatGPTが回答を作る時に、引用できる明確な文章が少なくなります。",
      action: `${profile.scenarios.slice(0, 3).join(" / ")} に直接答えるページを作ります。`,
    });
  }

  if (missing.has("schema") || missing.has("speed")) {
    findings.push({
      severity: "high",
      title: "技術シグナルが弱く、AIに意味が伝わりにくい状態です",
      evidence: "構造化データ、見出し階層、内部リンク、モバイル品質のいずれかに改善余地があります。",
      impact: "ページ内容が良くても、検索エンジンやAIに正しく分類されない可能性があります。",
      action: "Organization、FAQPage、BreadcrumbListを整え、重要ページ同士を内部リンクでつなぎます。",
    });
  }

  if (missing.has("authorTrust") || missing.has("freshness")) {
    findings.push({
      severity: "medium",
      title: "信頼材料と更新性が不足しています",
      evidence: "運営者、実績、導入事例、第三者評価、更新情報がAI回答の根拠として弱い可能性があります。",
      impact: "比較検討時に、信頼できる候補として選ばれにくくなります。",
      action: "実績、事例、利用者の声、更新日を明示し、古い情報に見えない状態を作ります。",
    });
  }

  if (missing.has("conversion")) {
    findings.push({
      severity: "medium",
      title: `${profile.conversionName}が弱い可能性があります`,
      evidence: "AI検索から来たユーザーが次に何をすればよいか、導線が明確でない可能性があります。",
      impact: "AI回答で認知されても、問い合わせ・申し込み・資料請求に進む率が落ちます。",
      action: "主要ページ上部とFAQ直後に、文脈に合うCTAを配置します。",
    });
  }

  if (findings.length === 0) {
    findings.push({
      severity: "low",
      title: "主要なAI検索シグナルは整っています",
      evidence: "一次情報、回答性、技術基盤、信頼材料の大きな欠落は少ない状態です。",
      impact: "今後は表示確認と継続更新が中心になります。",
      action: "主要な質問文でAI OverviewやChatGPTの表示状況を定点観測します。",
    });
  }

  const existingTitles = new Set(findings.map((finding) => finding.title));
  for (const check of missingChecks) {
    if (existingTitles.has(check.label)) continue;
    findings.push({
      severity: check.impact,
      title: check.label,
      evidence: "100項目診断の関連項目で不足または要確認が出ています。",
      impact: riskDetailForCheck(check.id, profile),
      action: check.roadMap,
    });
  }

  return findings;
}

function riskDetailForCheck(id, profile) {
  const details = {
    official: `${profile.primaryPage}が弱いと、AIが事業・サービスの一次情報を特定しにくくなります。`,
    local: "外部掲載やSNSとの情報差分があると、AIがどの情報を正とするべきか判断しにくくなります。",
    faq: "FAQが不足すると、AI OverviewやChatGPTが質問に直接答えるための引用材料が減ります。",
    schema: "構造化データが不足すると、ページの役割や運営者情報が検索エンジンに伝わりにくくなります。",
    servicePages: "サービスや料金、事例ページが不足すると、比較検討クエリで回答材料が足りなくなります。",
    speed: "スマホ表示や速度に課題があると、ユーザー体験とクロール効率の両方に影響します。",
    authorTrust: "信頼材料が少ないと、AI回答でも比較検討でも選ばれる根拠が弱くなります。",
    freshness: "更新性が弱いと、古い情報として扱われたり、現在の提供内容が伝わりにくくなります。",
    conversion: "導線が弱いと、AI検索で認知されても問い合わせや申し込みにつながりにくくなります。",
  };
  return details[id] || "AI検索で引用・理解されるための情報が不足しています。";
}

function buildRoadMap(missingChecks, score, profile) {
  const topMissing = missingChecks.slice(0, 3).map((check, index) => ({
    step: index + 1,
    title: check.label,
    action: check.roadMap,
  }));

  if (topMissing.length > 0) return topMissing;

  return [
    {
      step: 1,
      title: "AI検索での表示状況を継続チェック",
      action:
        score >= 82
          ? `${profile.scenarios[0]} などの質問で、AI回答にどの情報が引用されるか定期確認します。`
          : "不足しているページとFAQを追加し、検索結果とAI回答の変化を見ます。",
    },
  ];
}

function buildActionPlan(missingChecks, score, profile) {
  const priority = missingChecks.slice(0, 4);
  return [
    {
      phase: "0-30日",
      title: score < 58 ? "一次情報とFAQの緊急整備" : "AI回答に使われる本文の増強",
      tasks: (priority.slice(0, 2).map((check) => check.roadMap)),
    },
    {
      phase: "31-60日",
      title: "構造化データと主要下層ページの整備",
      tasks: priority.slice(2, 4).map((check) => check.roadMap),
    },
    {
      phase: "61-90日",
      title: "比較検討クエリとCV導線の改善",
      tasks: [
        `${profile.scenarios.join(" / ")} の質問でAI回答の表示状況を記録します。`,
        profile.primaryAction,
      ],
    },
  ].map((phase) => ({
    ...phase,
    tasks: phase.tasks.length > 0 ? phase.tasks : ["現状の強みを維持し、FAQ、事例、外部情報の整合性を更新します。"],
  }));
}

function buildOpportunityScore(score, urlCount, missingCount) {
  const upside = Math.min(100, Math.max(18, 100 - score + missingCount * 5 + urlCount * 2));
  return {
    label: upside >= 70 ? "改善余地 大" : upside >= 42 ? "改善余地 中" : "改善余地 小",
    value: upside,
  };
}
