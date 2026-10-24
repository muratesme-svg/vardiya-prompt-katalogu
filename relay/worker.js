// Vardiya prompt-rating relay (Cloudflare Worker).
//
// Accepts ONE confirmed rating packet (schema "vardiya.prompt-rating" v1) per request and stores it in the
// catalog repository as contributions/<key[0:2]>/<contribution_key>.json. Because the file name is the
// contribution key, re-sending the same rating replaces the earlier file instead of adding a new count.
//
// Privacy: the relay never stores or forwards IP addresses, headers, cookies or user agents. Anonymous packets
// reach GitHub without any identity; named packets carry only the display name the user typed. The GitHub
// token (secret GITHUB_TOKEN) must be a fine-grained token with "Contents: read and write" on the catalog
// repository ONLY. It never leaves this worker.
//
// Configuration (wrangler.toml / dashboard):
//   vars:    REPO = "muratesme-svg/vardiya-prompt-katalogu", BRANCH = "main"
//   secrets: GITHUB_TOKEN
//   optional binding: RATE_LIMITER (Cloudflare rate limiting) — strongly recommended against spam.

const FIELDS = ["schema", "schema_version", "catalog_id", "model", "model_version", "task_type", "usefulness",
  "ease", "correction", "recommend", "comment", "contributor", "contribution_key", "rated_month"];
const MAX_BODY = 8000;
let knownIds = null;
let knownIdsAt = 0;

function json(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}

function score(v) {
  if (v === null) return true;
  return typeof v === "number" && Number.isFinite(v) && v >= 0 && v <= 10;
}

function shortText(v, max) {
  return typeof v === "string" && v.length <= max;
}

export function validPacket(p) {
  if (!p || typeof p !== "object" || Array.isArray(p)) return false;
  const keys = Object.keys(p).sort();
  if (keys.length !== FIELDS.length || keys.join() !== [...FIELDS].sort().join()) return false;
  if (p.schema !== "vardiya.prompt-rating" || p.schema_version !== 1) return false;
  if (!/^[0-9a-f]{32}$/.test(p.contribution_key) || !/^\d{4}-\d{2}$/.test(p.rated_month)) return false;
  if (!shortText(p.catalog_id, 200) || p.catalog_id.length === 0) return false;
  if (!["model", "model_version", "task_type"].every((k) => shortText(p[k], 100))) return false;
  if (!shortText(p.comment, 2000)) return false;
  if (![null, "yes", "maybe", "no"].includes(p.recommend)) return false;
  if (![p.usefulness, p.ease, p.correction].every(score)) return false;
  if (p.usefulness === null && p.ease === null && p.correction === null && p.recommend === null) return false;
  const c = p.contributor;
  if (!c || typeof c !== "object") return false;
  const ck = Object.keys(c).sort().join();
  if (c.type === "anonymous" && ck === "type") return true;
  return c.type === "named" && ck === "display_name,type" && shortText(c.display_name, 60) &&
    c.display_name.trim().length > 0;
}

// ---- language variant candidates (schema "vardiya.prompt-variant" v1) ------------------------------------------
// Stored as variants/<catalog_id>/<lang>/<contribution_key>.json. Nothing is published from here: only the
// repository owner's variants/approved.json decides publication. Secret-like text is rejected (second lock).
const VARIANT_FIELDS = ["schema", "schema_version", "catalog_id", "source_sha256", "lang", "purpose", "kind", "text",
  "model", "edited_ratio", "license", "author", "contributor", "contribution_key", "created_month", "checks"];
const PURPOSES = ["sadik", "dogal", "resmi", "teknik", "sanatsal", "kendi"];
const RISKS = ["disari_gonderme", "gizli_bilgi_isteme", "silme", "sistem_uzaktan", "kural_asma", "gizli_karakter"];
const MAX_VARIANT_BODY = 90000;
const SECRET = new RegExp([
  "-----BEGIN [A-Z ]*PRIVATE KEY-----",
  "\\b(?:sk-(?:ant-|proj-)?[A-Za-z0-9_-]{16,}|github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|" +
    "AIza[0-9A-Za-z_-]{30,}|xox[abprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|hf_[A-Za-z0-9]{30,}|gsk_[A-Za-z0-9]{30,})",
  "\\b(?:[Aa][Pp][Ii][_ -]?[Kk][Ee][Yy]|[Aa]ccess[_ -]?[Tt]oken|[Tt]oken|[Ss]ecret|[Pp]assword|[Pp]asswd|[Pp]arola|" +
    "[Şş]ifre|[Ss]ifre)\\b\\s*[:=]\\s*[\"']?(?!\\{)[^\\s\"'{}]{6,}",
  "\\b[\\w.+-]+@(?!example\\.)[\\w-]+(?:\\.[\\w-]+)+\\b",
  "(?<![\\w\\d])\\+?\\d[\\d ()-]{8,}\\d(?!\\d)",
  "(?:[A-Za-z]:\\\\[Uu]sers\\\\|/home/|/[Uu]sers/)(?!\\{)[^\\\\/\\s\"']+",
].join("|"));

export function validVariant(p) {
  if (!p || typeof p !== "object" || Array.isArray(p)) return false;
  const keys = Object.keys(p).sort();
  if (keys.join() !== [...VARIANT_FIELDS].sort().join()) return false;
  if (p.schema !== "vardiya.prompt-variant" || p.schema_version !== 1) return false;
  if (!/^[0-9a-f]{32}$/.test(p.contribution_key) || !/^\d{4}-\d{2}$/.test(p.created_month)) return false;
  if (typeof p.catalog_id !== "string" || !/^[A-Za-z0-9._-]{1,200}$/.test(p.catalog_id)) return false;
  if (!/^[0-9a-f]{64}$/.test(p.source_sha256) || !/^[a-z]{2}$/.test(p.lang)) return false;
  if (!["translation", "adaptation"].includes(p.kind) || !PURPOSES.includes(p.purpose)) return false;
  if (typeof p.text !== "string" || !p.text.trim() || p.text.length > 20000 || SECRET.test(p.text)) return false;
  if (typeof p.edited_ratio !== "number" || !(p.edited_ratio >= 0 && p.edited_ratio <= 1)) return false;
  if (!Array.isArray(p.checks) || !p.checks.every((c) => RISKS.includes(c))) return false;
  if (!shortText(p.model, 100) || !shortText(p.license, 100) || !shortText(p.author, 200)) return false;
  const c = p.contributor;
  if (!c || typeof c !== "object") return false;
  const ck = Object.keys(c).sort().join();
  if (c.type === "anonymous" && ck === "type") return true;
  return c.type === "named" && ck === "display_name,type" && shortText(c.display_name, 60) &&
    c.display_name.trim().length > 0 && !SECRET.test(c.display_name);
}

async function github(env, path, init = {}) {
  return fetch(`https://api.github.com/repos/${env.REPO}/${path}`, {
    ...init,
    headers: {
      authorization: `Bearer ${env.GITHUB_TOKEN}`,
      accept: "application/vnd.github+json",
      "user-agent": "vardiya-rating-relay",
      "x-github-api-version": "2022-11-28",
      ...(init.headers || {}),
    },
  });
}

async function catalogIds(env) {
  // Only ratings for prompts that exist in the published catalog are accepted (cached for 1 hour).
  if (knownIds && Date.now() - knownIdsAt < 3600_000) return knownIds;
  const r = await fetch(`https://raw.githubusercontent.com/${env.REPO}/${env.BRANCH || "main"}/manifest.json`);
  if (!r.ok) throw new Error("manifest unavailable");
  const m = await r.json();
  knownIds = new Set((m.entries || []).map((e) => e.id));
  knownIdsAt = Date.now();
  return knownIds;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const variant = url.pathname === "/v1/variants";
    if (request.method !== "POST" || (url.pathname !== "/v1/contributions" && !variant)) {
      return json(404, { error: "not_found" });
    }
    if (!(request.headers.get("content-type") || "").startsWith("application/json")) {
      return json(415, { error: "json_required" });
    }
    const raw = await request.text();
    if (raw.length > (variant ? MAX_VARIANT_BODY : MAX_BODY)) return json(413, { error: "too_large" });
    let packet;
    try {
      packet = JSON.parse(raw);
    } catch {
      return json(400, { error: "invalid_json" });
    }
    if (!(variant ? validVariant(packet) : validPacket(packet))) return json(422, { error: "invalid_packet" });
    if (env.RATE_LIMITER) {
      const { success } = await env.RATE_LIMITER.limit({ key: packet.contribution_key });
      if (!success) return json(429, { error: "rate_limited" });
    }
    try {
      if (!(await catalogIds(env)).has(packet.catalog_id)) return json(422, { error: "unknown_prompt" });
    } catch {
      return json(503, { error: "catalog_unavailable" });
    }
    const file = variant
      ? `variants/${packet.catalog_id}/${packet.lang}/${packet.contribution_key}.json`
      : `contributions/${packet.contribution_key.slice(0, 2)}/${packet.contribution_key}.json`;
    const branch = env.BRANCH || "main";
    let sha;
    const old = await github(env, `contents/${file}?ref=${branch}`);
    if (old.ok) sha = (await old.json()).sha;
    const body = JSON.stringify(packet, null, 1) + "\n";
    const put = await github(env, `contents/${file}`, {
      method: "PUT",
      body: JSON.stringify({
        message: variant ? "Add language variant candidate" : "Add prompt rating contribution",
        content: btoa(String.fromCharCode(...new TextEncoder().encode(body))),
        branch,
        ...(sha ? { sha } : {}),
      }),
    });
    if (!put.ok) return json(502, { error: "store_failed" });
    return json(200, { ok: true, replaced: Boolean(sha) });
  },
};
