import { affiliateConfig } from "./config.js";

const serviceRules = {
  "aeo-lp": ["faq", "schema", "servicePages", "conversion", "official", "authorTrust"],
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
  if (profileKind === "local") {
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
