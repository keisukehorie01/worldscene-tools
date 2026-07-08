import { affiliateConfig } from "./config.js";

const serviceRules = {
  localgoat: ["local", "authorTrust", "freshness", "official"],
  "aeo-lp": ["official", "faq", "schema", "servicePages", "conversion", "authorTrust"],
  "conoha-wing": ["speed", "official"],
};

export function getRecommendedOffers(result) {
  const missing = new Set(result.missingChecks.map((check) => check.id));
  const profileKind = result.profile?.kind || "general";

  return affiliateConfig.services
    .filter((service) => service.enabled)
    .map((service) => {
      const relatedMissing = serviceRules[service.id]?.filter((id) => missing.has(id)) ?? [];
      const urgency = Math.max(1, relatedMissing.length);
      return {
        ...adaptServiceCopy(service, profileKind),
        urgency,
        relatedMissing,
      };
    })
    .sort((a, b) => a.priority - b.priority);
}

function adaptServiceCopy(service, profileKind) {
  if (service.id === "aeo-lp") {
    if (profileKind === "local") {
      return {
        ...service,
        headline: "地域名・FAQ・予約導線まで、AI検索で見つかるLPに整える",
        description:
          "店舗情報、Googleプロフィールとの整合性、来店前FAQ、予約・問い合わせ導線をまとめてLP化したい場合に向いています。",
        fitFor: ["店舗情報の一貫性が弱い", "来店前FAQを増やしたい", "予約・問い合わせ導線を改善したい"],
      };
    }

    return service;
  }

  if (profileKind === "local") return service;

  const serviceSiteCopy = {
    localgoat: {
      category: "AI検索・認知基盤改善",
      headline: "AI検索でサービス名と強みを見つけてもらう土台づくり",
      description:
        "サービス内容、運営者情報、外部掲載、FAQ、比較検討時の質問に答える情報設計を優先したい場合に向いています。",
      fitFor: ["サービス説明が伝わりにくい", "比較検討クエリを取りたい", "AI Overviewで引用される情報を増やしたい"],
    },
    "conoha-wing": {
      category: "レンタルサーバー",
      headline: "サイトの表示速度と安定運用の基盤を整える",
      description:
        "表示速度、SSL、WordPress運用、独自ドメインの安定運用をまとめて見直したい場合に向いています。",
      fitFor: ["表示速度が遅い", "サーバーを見直したい", "サイトを安定運用したい"],
    },
  };

  return {
    ...service,
    ...(serviceSiteCopy[service.id] || {}),
  };
}

export function getDisclosure() {
  return affiliateConfig.disclosure;
}
