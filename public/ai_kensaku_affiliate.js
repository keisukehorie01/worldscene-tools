(function () {
  const storageKey = "ai_kensaku_affiliate_id";
  const agencyStorageKey = "ai_kensaku_agency_code";
  const defaultAgencyCode = "0001";
  const sourceParams = ["aff_id", "affiliate_id", "partner_id", "ref"];
  const agencyParams = ["agency_code", "agency", "agency_id"];
  const targetHosts = new Set(["aeo-lp.com", "www.aeo-lp.com"]);

  function normalizeId(value) {
    const normalized = String(value || "").trim();
    if (!/^[a-zA-Z0-9_-]{1,64}$/.test(normalized)) return "";
    return normalized;
  }

  function getStoredParam(keys, storageKeyName, fallback) {
    const params = new URLSearchParams(window.location.search);
    for (const key of keys) {
      const value = normalizeId(params.get(key));
      if (value) {
        localStorage.setItem(storageKeyName, value);
        return value;
      }
    }
    return normalizeId(localStorage.getItem(storageKeyName)) || fallback || "";
  }

  function buildClickId() {
    const timestamp = new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14);
    const random = Math.random().toString(36).slice(2, 10);
    return `ak_${timestamp}_${random}`;
  }

  function decorateUrl(rawHref, affiliateId, agencyCode, withClickId) {
    let url;
    try {
      url = new URL(rawHref, window.location.href);
    } catch (error) {
      return rawHref;
    }
    if (!targetHosts.has(url.hostname)) return rawHref;
    url.searchParams.set("agency_code", agencyCode || defaultAgencyCode);
    if (affiliateId) url.searchParams.set("aff_id", affiliateId);
    if (withClickId) url.searchParams.set("click_id", buildClickId());
    url.searchParams.set("utm_source", url.searchParams.get("utm_source") || "ai-kensaku.jp");
    url.searchParams.set("utm_medium", url.searchParams.get("utm_medium") || "affiliate");
    return url.toString();
  }

  function decorateLinks() {
    const affiliateId = getStoredParam(sourceParams, storageKey, "");
    const agencyCode = getStoredParam(agencyParams, agencyStorageKey, defaultAgencyCode);
    document.querySelectorAll('a[href*="aeo-lp.com"]').forEach((link) => {
      link.href = decorateUrl(link.getAttribute("href"), affiliateId, agencyCode, false);
      link.rel = Array.from(new Set(`${link.rel || ""} sponsored noopener`.trim().split(/\s+/))).join(" ");
      if (link.dataset.aiKensakuAffiliateReady === "true") return;
      link.dataset.aiKensakuAffiliateReady = "true";
      link.addEventListener("click", () => {
        link.href = decorateUrl(link.getAttribute("href"), affiliateId, agencyCode, true);
      });
    });
  }

  window.aiKensakuDecorateAffiliateLinks = decorateLinks;
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", decorateLinks);
  else decorateLinks();
  new MutationObserver(decorateLinks).observe(document.documentElement, { childList: true, subtree: true });
})();
