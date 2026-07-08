import { affiliateConfig } from "./config.js";

const serviceRules = {
  "aeo-lp": ["faq", "schema", "servicePages", "official", "authorTrust"],
};

export function getRecommendedOffers(result) {
  const missing = new Set(result.missingChecks.map((check) => check.id));

  return affiliateConfig.services
    .filter((service) => service.enabled)
    .map((service) => {
      const relatedMissing = serviceRules[service.id]?.filter((id) => missing.has(id)) ?? [];
      const urgency = Math.max(1, relatedMissing.length);
      return {
        ...adaptServiceCopy(service, result.businessType),
        urgency,
        relatedMissing,
      };
    })
    .sort((a, b) => a.priority - b.priority);
}

function adaptServiceCopy(service, businessType) {
  const type = String(businessType || "");
  const isLocal = /店舗|医院|歯科|美容|整体|飲食|工務店|不動産|地域/.test(type);

  if (isLocal) {
    return service;
  }

  const serviceSiteCopy = {
    "aeo-lp": {
      category: "AI検索対策LP制作",
      headline: "AI検索でサービス名と強みを見つけてもらうLPづくり",
      description:
        "サービス内容、運営者情報、FAQ、比較検討時の質問、問い合わせ導線をLPとして整理したい場合に向いています。",
      fitFor: [
        "サービス説明が伝わりにくい",
        "比較検討クエリを取りたい",
        "AI Overviewで引用される情報を増やしたい",
      ],
    },
  };

  return { ...service, ...(serviceSiteCopy[service.id] || {}) };
}

export function getDisclosure() {
  return affiliateConfig.disclosure;
}
