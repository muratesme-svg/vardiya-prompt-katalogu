#!/usr/bin/env python3
"""Daily source discovery and signed catalog builder for vardiya-prompt-katalogu.

Only reads public GitHub metadata and prompt-like text files. It never imports or executes
source code. Unknown redistribution rights become link-only records; content warnings are
metadata and do not suppress records.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "seed_catalog.json"
CANDIDATES = ROOT / "discovered_candidates.json"
SOURCES = ROOT / "official_sources.json"
CONTRIBUTIONS = ROOT / "contributions"
VARIANTS = ROOT / "variants"
OUT = ROOT
MAX_SEARCH_REPOS = 20
SEARCHES_PER_RUN = 3
MAX_FILES_PER_REPO = 2
MAX_FILE_BYTES = 2_000_000
MAX_TEXT_BYTES = 40_000
MAX_RESPONSE_BYTES = 3_000_000
USER_AGENT = "VardiyaPromptCatalog/1.0 (+https://github.com/muratesme-svg/vardiya-prompt-katalogu)"


class _SameHostRedirect(urllib.request.HTTPRedirectHandler):
    """Keep credentialed API requests and public file requests on their original HTTPS host."""
    def __init__(self, host: str):
        super().__init__()
        self.host = host

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if (parsed.scheme != "https" or parsed.hostname != self.host
                or parsed.username is not None or parsed.password is not None
                or parsed.port not in (None, 443)):
            raise RuntimeError(f"GitHub request refused a redirect outside {self.host}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)

LICENSES = {
    "MIT": "MIT", "Apache-2.0": "Apache 2.0", "CC0-1.0": "CC0 / kamu malı",
    "Unlicense": "Unlicense", "ISC": "ISC", "BSD-2-Clause": "BSD 2-clause",
    "BSD-3-Clause": "BSD 3-clause", "CC-BY-4.0": "CC BY 4.0", "CC-BY-SA-4.0": "CC BY-SA 4.0",
}
PROVIDER_MAP = {
    "openai": "gpt", "anthropic": "claude", "google": "gemini", "google-gemini": "gemini",
    "deepseek-ai": "deepseek", "qwenlm": "qwen", "mistralai": "mistral",
}
CATEGORY_TERMS = {
    "kod": ("code", "coding", "developer", "programming", "software", "flutter", "python", "typescript",
            "programmierung", "entwickler", "código", "programación", "développement", "编程", "برمجة", "программирование"),
    "inceleme": ("review", "debug", "bug", "security", "audit", "test", "prüfung", "revisión", "révision", "denetim", "审查"),
    "arastirma": ("research", "academic", "source", "fact-check", "citation", "investigate", "araştırma",
                  "forschung", "investigación", "recherche", "pesquisa", "研究", "بحث", "исследование"),
    "ozet": ("summary", "summarize", "extract", "notes", "zusammenfassung", "resumen", "résumé", "özet", "摘要", "резюме"),
    "yazi": ("writing", "writer", "draft", "copywriting", "email", "document", "schreiben", "redacción", "rédaction", "yazı", "写作"),
    "ogrenme": ("teach", "tutor", "learn", "lesson", "education", "student", "lernen", "aprender", "enseigner", "öğren", "学习", "تعليم"),
    "veri": ("data", "csv", "sql", "spreadsheet", "analytics", "daten", "datos", "données", "veri", "数据", "данные"),
    "gorsel": ("image", "design", "visual", "ui", "ux", "art", "illustration", "bild", "imagen", "image", "görsel", "图像"),
    "yaratici": ("story", "creative", "game", "fiction", "character", "roleplay", "geschichte", "historia", "jeu", "oyun", "创作"),
    "ajan": ("agent", "subagent", "workflow", "tool-use", "assistant", "werkzeug", "agente", "outil", "ajan", "代理"),
}
_PROMPT_FILE = re.compile(
    r"(?:prompt|system|agent|skill|rule|cursor|copilot|claude|instruction|komut|istem|y[oö]nerge|talimat|"
    r"[sş]ablon|anweisung|vorlage|instrucci[oó]n|plantilla|modele|mod[eè]le|提示词|提示|模板|指示|"
    r"تعليمات|قالب|промпт|шаблон|инструкция|プロンプト|テンプレート|프롬프트|템플릿)", re.I)
_PII = re.compile(r"(?i)\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b|(?:\+?\d[\d ()-]{8,}\d)")
_COPYRIGHT_HINT = re.compile(r"(?i)all rights reserved|\bcopyright\b|adapted from|copied from")
_RISK_HINTS = {
    "instruction_override": re.compile(r"(?i)ignore (all |previous |prior )?instructions|bypass (the )?(filter|safety)|jailbreak|do anything now"),
    "credential_or_data_request": re.compile(r"(?i)send (all )?(keys|credentials|secrets|private data)|exfiltrat|steal (an )?api key"),
    "hidden_text": re.compile(r"[\u200b-\u200f\u202a-\u202e\ufeff]"),
}


def _read_json(path: Path, fallback):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value
    except (OSError, json.JSONDecodeError):
        return fallback


def _json_write(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _api(url: str, token: str = "", limit: int = MAX_RESPONSE_BYTES):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != "api.github.com"
            or parsed.username is not None or parsed.password is not None
            or parsed.port not in (None, 443)):
        raise RuntimeError("GitHub API request is not on the approved HTTPS host")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT,
               "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        opener = urllib.request.build_opener(_SameHostRedirect("api.github.com"))
        with opener.open(request, timeout=18) as response:
            final = urllib.parse.urlsplit(response.geturl())
            if final.scheme != "https" or final.hostname != "api.github.com":
                raise RuntimeError("GitHub API redirected outside api.github.com")
            body = response.read(limit + 1)
    except urllib.error.HTTPError as error:
        if error.code in (403, 429):
            raise RuntimeError("GitHub rate limit reached; the previous catalog remains available") from error
        raise RuntimeError(f"GitHub API returned HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise RuntimeError(f"GitHub source could not be reached ({type(error).__name__})") from error
    if len(body) > limit:
        raise RuntimeError("GitHub response exceeded the allowed size")
    return json.loads(body.decode("utf-8"))


def _raw(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != "raw.githubusercontent.com"
            or parsed.username is not None or parsed.password is not None or parsed.port not in (None, 443)):
        raise RuntimeError("Prompt file URL is not a raw.githubusercontent.com HTTPS URL")
    headers = {"User-Agent": USER_AGENT, "Accept": "text/plain"}
    # Public source files do not need a credential. Never forward the GitHub API token
    # to raw content hosting, even if a redirect or future refactor changes the host.
    request = urllib.request.Request(url, headers=headers)
    try:
        opener = urllib.request.build_opener(_SameHostRedirect("raw.githubusercontent.com"))
        with opener.open(request, timeout=18) as response:
            if urllib.parse.urlsplit(response.geturl()).hostname != "raw.githubusercontent.com":
                raise RuntimeError("Prompt source redirected to a different host")
            body = response.read(MAX_FILE_BYTES + 1)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Prompt file returned HTTP {error.code}") from error
    if len(body) > MAX_FILE_BYTES:
        raise RuntimeError("Prompt file is larger than the discovery limit")
    return body.decode("utf-8-sig", errors="replace")


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")[:72] or "prompt"


def _categories(text: str, path: str) -> list[str]:
    sample = f"{path}\n{text[:4000]}".casefold()
    found = [name for name, words in CATEGORY_TERMS.items() if any(word in sample for word in words)]
    # General is intentionally cross-listed with any inferred specialty category.
    return list(dict.fromkeys(["genel", *found]))


def _guess_language(text: str) -> str:
    """Best-effort language tag; ambiguous text stays `und` instead of being presented as verified."""
    sample = text[:16000]
    if re.search(r"[\u3040-\u30ff]", sample): return "ja"
    if re.search(r"[\uac00-\ud7af]", sample): return "ko"
    if re.search(r"[\u0600-\u06ff]", sample): return "ar"
    if re.search(r"[\u0590-\u05ff]", sample): return "he"
    if re.search(r"[\u0900-\u097f]", sample): return "hi"
    if re.search(r"[\u0e00-\u0e7f]", sample): return "th"
    if re.search(r"[\u0370-\u03ff]", sample): return "el"
    if re.search(r"[\u4e00-\u9fff]", sample): return "zh"
    if re.search(r"[\u0400-\u052f]", sample):
        return "uk" if re.search(r"[іїєґІЇЄҐ]", sample) else "ru"
    low = sample.casefold()
    # ö, ü ve ç Almanca/Fransızca metinlerde de geçer; yalnızca Türkçeye özgü harfler belirleyicidir.
    if re.search(r"[ıİğĞşŞ]", sample): return "tr"
    words = set(re.findall(r"\b[\wÀ-ÿ]+\b", low))
    lexicons = (
        ("de", {"und", "der", "die", "das", "nicht", "ist", "mit", "für", "eine", "auch"}),
        ("es", {"el", "los", "las", "una", "para", "con", "que", "por", "como", "está"}),
        ("fr", {"le", "les", "des", "une", "pour", "avec", "dans", "est", "vous", "que"}),
        ("pt", {"não", "uma", "para", "com", "que", "você", "está", "são", "por"}),
        ("it", {"il", "lo", "gli", "una", "per", "con", "che", "sono", "della"}),
        ("nl", {"het", "een", "van", "voor", "met", "niet", "zijn", "deze"}),
        ("pl", {"oraz", "jest", "nie", "dla", "się", "przez", "który"}),
        ("en", {"the", "and", "you", "your", "with", "for", "that", "this", "are", "from"}),
    )
    ranked = sorted(((len(words & vocab), tag) for tag, vocab in lexicons), reverse=True)
    if ranked and ranked[0][0] >= 3 and (len(ranked) == 1 or ranked[0][0] > ranked[1][0]):
        return ranked[0][1]
    return "und"


def _provider(owner: str, repo: str, path: str) -> str:
    low = f"{owner}/{repo}/{path}".casefold()
    for owner_name, provider in PROVIDER_MAP.items():
        if owner.casefold() == owner_name or owner.casefold().startswith(owner_name):
            return provider
    for needle, provider in (("claude", "claude"), ("anthropic", "claude"), ("openai", "gpt"),
                             ("gemini", "gemini"), ("deepseek", "deepseek"), ("qwen", "qwen"),
                             ("mistral", "mistral")):
        if needle in low:
            return provider
    return "genel"


def _extract(title: str, path: str, content: str, redistribute: bool) -> tuple[str, list[str]]:
    if not redistribute or len(content.encode("utf-8")) > MAX_TEXT_BYTES:
        return "", ["Tam metin otomatik yayımlanmadı; kaynağı açıp incele."]
    if _PII.search(content) or _COPYRIGHT_HINT.search(content):
        return "", ["Kaynakta ek atıf veya kişisel veri işareti var; tam metin yerine kaynak bağlantısı gösteriliyor."]
    # Extract marked prompt blocks first. Keep headings and code as source text, without rewriting it.
    blocks = []
    for match in re.finditer(r"(?is)(?:^|\n)(#{1,4}[^\n]*\n)?```[^\n]*\n(.*?)\n```", content):
        block = ((match.group(1) or "") + match.group(2)).strip()
        if len(block) >= 100:
            blocks.append(block)
    if blocks:
        return "\n\n---\n\n".join(blocks[:8]), []
    if _PROMPT_FILE.search(Path(path).name) and len(content.strip()) >= 100:
        return content.strip(), []
    if _PROMPT_FILE.search(title) and len(content.strip()) >= 100:
        return content.strip(), []
    return "", ["Dosya prompt benzeri göründü ancak çıkarılabilir bir prompt bölümü bulunamadı."]


def _candidate(repo: dict, path: str, content: str = "") -> dict:
    full_name = str(repo.get("full_name") or "")
    owner, _, name = full_name.partition("/")
    branch = str(repo.get("default_branch") or "main")
    provider = _provider(owner, name, path)
    title = Path(path).stem.replace("_", " ").replace("-", " ").strip().title() or name
    raw_url = f"https://raw.githubusercontent.com/{full_name}/{urllib.parse.quote(branch, safe='')}/{urllib.parse.quote(path, safe='/')}"
    page_url = f"https://github.com/{full_name}/blob/{urllib.parse.quote(branch, safe='/')}/{urllib.parse.quote(path, safe='/')}"
    license_id = str((repo.get("license") or {}).get("spdx_id") or "NOASSERTION")
    license_name = LICENSES.get(license_id, "bilinmiyor")
    text, notes = _extract(title, path, content, bool(license_name != "bilinmiyor")) if content else ("", ["Kaynak bağlantısı; içerik bu taramada alınmadı."])
    risk_tags = []
    warnings = list(notes)
    risk_level = "unknown"
    for tag, pattern in _RISK_HINTS.items():
        if content and pattern.search(content):
            risk_tags.append(tag)
            warnings.append("Otomatik tarama işareti: " + tag + ". Bu etiket inceleme önerisidir, konuya göre gizleme değildir.")
            risk_level = "moderate"
    if not text:
        distribution = "link_only"
        risk_tags.append("rights_or_extraction_unverified")
    else:
        distribution = "full_text"
    categories = _categories(content, path)
    language = _guess_language(content) if content else "und"
    # Kayıt kimliği içerik değişse de sabit kalsın: her yeni taramada aynı kaynak
    # güncellenir, eski metin sürümleri çoğaltılıp güncelmiş gibi listelenmez.
    identity = "discovered-" + hashlib.sha256(f"{full_name.casefold()}/{path.casefold()}".encode("utf-8")).hexdigest()[:24]
    return {
        "kimlik": identity, "ad": title[:120], "model": provider,
        "kategori": categories[1] if len(categories) > 1 else "genel",
        "categories": categories, "task_types": categories, "tags": ["otomatik-kesif", "aday"],
        "model_families": [provider],
        "model_fit": [{"provider": provider if provider != "genel" else "any", "family": provider,
                       "model_id": None, "model_version": None, "basis": "repository_metadata",
                       "tested": False, "checked_at": str(repo.get("pushed_at") or "")[:10]}],
        "aciklama": f"{full_name} deposundaki {path} kaydından keşfedildi. Kaynak ve lisans ayrıntısını incele.",
        "aciklama_en": f"Discovered from {full_name}/{path}. Check the source and redistribution status.",
        "description": f"{full_name} deposundan otomatik keşfedilen kayıt.",
        "usage_notes": "Otomatik keşif; modelde denenmiş ya da içerikçe onaylanmış olduğu anlamına gelmez.",
        "warnings": list(dict.fromkeys(warnings)), "limitations": ["Otomatik sınıflandırma; uzman incelemesi değildir."],
        "metin": text, "redistribution": distribution,
        "review_status": "candidate", "risk_tags": list(dict.fromkeys(risk_tags)),
        "risk_level": risk_level, "sensitivity": "none",
        "evidence": {"kind": "source_only", "rated_tasks": 0}, "tarama": list(dict.fromkeys(risk_tags)),
        "guven": "topluluk", "kaynak_adi": str((repo.get("owner") or {}).get("login") or owner),
        "kaynak": {"adres": page_url, "lisans": license_name, "yazar": str((repo.get("owner") or {}).get("login") or owner),
                   "tarih": str(repo.get("pushed_at") or "")[:10], "depo": full_name, "yol": path},
        "dil": language, "dil_inceleme": "language_guess" if language != "und" else "unknown",
    }


def discover(token: str, candidates: dict) -> tuple[dict, dict]:
    config = _read_json(SOURCES, {})
    queries = config.get("search_queries") or ["prompt engineering language:Markdown", "LLM prompt library"]
    run = int(os.environ.get("GITHUB_RUN_NUMBER", "1") or 1)
    # Slide the daily window by one so a fixed stride cannot skip query groups.
    start = (run - 1) % len(queries)
    selected = [queries[(start + i) % len(queries)] for i in range(min(SEARCHES_PER_RUN, len(queries)))]
    repositories, errors = [], []
    seen_repositories = set()
    for query in selected:
        search_url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode(
            {"q": query, "sort": "updated", "order": "desc", "per_page": MAX_SEARCH_REPOS})
        try:
            result = _api(search_url, token)
            for repo in result.get("items", [])[:MAX_SEARCH_REPOS]:
                name = str(repo.get("full_name") or "").casefold()
                if name and name not in seen_repositories:
                    repositories.append(repo)
                    seen_repositories.add(name)
        except (RuntimeError, json.JSONDecodeError, AttributeError) as error:
            errors.append(f"Search {query}: {error}")
    # Önceki sürümde kimlik prompt metnine göreydi. Kaynak yolu üzerinden
    # kararlı kimliğe geçirip aynı dosyaya ait eski adayları tek kayda indir.
    normalized = {}
    for old_id, record in list(candidates.items()):
        source = record.get("kaynak") if isinstance(record, dict) else None
        if isinstance(source, dict) and source.get("depo") and source.get("yol"):
            stable = "discovered-" + hashlib.sha256(
                f"{str(source['depo']).casefold()}/{str(source['yol']).casefold()}".encode("utf-8")).hexdigest()[:24]
            record["kimlik"] = stable
            normalized[stable] = record
        else:
            normalized[old_id] = record
    candidates.clear()
    candidates.update(normalized)
    scanned = 0
    new_records = 0
    truncated_repositories = []
    for repo in repositories:
        if repo.get("archived") or repo.get("disabled") or not repo.get("full_name"):
            continue
        full_name = repo["full_name"]
        branch = str(repo.get("default_branch") or "main")
        tree_url = f"https://api.github.com/repos/{full_name}/git/trees/{urllib.parse.quote(branch, safe='')}?recursive=1"
        try:
            tree = _api(tree_url, token)
            if tree.get("truncated"):
                truncated_repositories.append(full_name)
            paths = [x for x in tree.get("tree", []) if x.get("type") == "blob"
                     and _PROMPT_FILE.search(str(x.get("path") or ""))
                     and Path(str(x.get("path") or "")).suffix.lower() in {".md", ".txt", ".prompt", ".yaml", ".yml"}]
            paths.sort(key=lambda x: (0 if "prompt" in x["path"].casefold() else 1, len(x["path"]), x["path"]))
            for item in paths[:MAX_FILES_PER_REPO]:
                path = str(item["path"])
                raw_url = f"https://raw.githubusercontent.com/{full_name}/{urllib.parse.quote(branch, safe='')}/{urllib.parse.quote(path, safe='/')}"
                # Depolar herkese açık; token'ı raw içerik sunucusuna hiç gönderme.
                content = _raw(raw_url) if int(item.get("size") or 0) <= MAX_FILE_BYTES else ""
                record = _candidate(repo, path, content)
                candidates[record["kimlik"]] = record
                new_records += 1
            scanned += 1
            time.sleep(0.15)
        except (RuntimeError, ValueError, KeyError) as error:
            errors.append(f"{full_name}: {error}")
    return candidates, {"queries": selected, "repositories_found": len(repositories),
                       "repositories_scanned": scanned, "truncated_repositories": truncated_repositories[:20],
                       "records_updated": new_records, "errors": errors[:20],
                       "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def official_link_records() -> list[dict]:
    data = _read_json(SOURCES, {})
    result = []
    for item in data.get("official_sources", []):
        if not isinstance(item, dict):
            continue
        provider = str(item.get("model") or "genel")
        url = str(item.get("url") or "")
        if not url.startswith("https://"):
            continue
        key = "official-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        result.append({"kimlik": key, "ad": str(item.get("title") or "Resmî model yönlendirmesi"),
                       "model": provider, "model_families": [provider], "kategori": "genel",
                       "categories": list(dict.fromkeys(["genel", str(item.get("category") or "prompt")])),
                       "task_types": [str(item.get("category") or "prompt"), "genel"],
                       "tags": ["resmi-rehber", "link-only"], "model_fit": [
                           {"provider": provider if provider != "genel" else "any", "family": provider,
                            "model_id": None, "model_version": None, "basis": "official_guide",
                            "tested": False, "checked_at": str(item.get("checked_at") or "")}],
                       "aciklama": str(item.get("summary_tr") or "Model üreticisinin güncel resmi yönlendirme sayfası."),
                       "aciklama_en": str(item.get("summary_en") or "Official model provider guide; opens at its source."),
                       "description": str(item.get("summary_en") or "Official model provider prompt guidance."),
                       "usage_notes": "Kaynak sayfasını aç; resmî rehber olması başarı garantisi değildir.",
                       "warnings": ["Tam metin yayımlanmıyor; kaynağı aç."], "limitations": ["Model sürümü zamanla değişebilir."],
                       "metin": "", "redistribution": "link_only", "review_status": "source_checked",
                       "risk_level": "unknown", "risk_tags": [], "sensitivity": "none",
                       "evidence": {"kind": "official_source", "rated_tasks": 0}, "guven": "resmi",
                       "kaynak_adi": str(item.get("publisher") or "Model üreticisi"),
                       "kaynak": {"adres": url, "lisans": "link_only", "yazar": str(item.get("publisher") or ""),
                       "tarih": str(item.get("checked_at") or ""), "depo": "", "yol": ""},
                       "dil": "und", "dil_inceleme": "unknown"})
    return result


def _mapped_locale(record: dict) -> list[dict]:
    variants = record.get("locales") if isinstance(record.get("locales"), list) else []
    if variants:
        return [v for v in variants if isinstance(v, dict) and isinstance(v.get("text"), str) and v["text"].strip()]
    text = str(record.get("metin") or "")
    if not text:
        return []
    return [{"tag": str(record.get("dil") or "und"), "kind": "original",
             "review": str(record.get("dil_inceleme") or "unknown"), "text": text}]


def _distribution(record: dict) -> str:
    requested = str(record.get("redistribution") or "")
    source = record.get("kaynak") if isinstance(record.get("kaynak"), dict) else {}
    license_name = str(source.get("lisans") or "bilinmiyor")
    allowed = {name.casefold() for name in LICENSES.values()}
    texts = _mapped_locale(record)
    if requested == "link_only" or license_name.casefold() not in allowed or not texts:
        return "link_only"
    if any(not str(v.get("text") or "").strip() for v in texts):
        return "link_only"
    return "full_text"


def _existing_package_matches(entries: list[dict]) -> dict | None:
    """Reuse a published version only when its signature and complete ZIP are valid."""
    manifest_path = OUT / "manifest.json"
    signature_path = OUT / "manifest.json.sig"
    archive_path = OUT / "catalog.zip"
    try:
        raw = manifest_path.read_bytes()
        manifest = json.loads(raw.decode("utf-8"))
        signature_bytes = signature_path.read_text(encoding="ascii").strip()
        public_key = base64.b64decode((ROOT / "public_key.txt").read_text(encoding="ascii").strip(), validate=True)
        signature = base64.b64decode(signature_bytes, validate=True)
        import ed25519
        if (not isinstance(manifest, dict) or manifest.get("schema_version") != 1
                or manifest.get("record_count") != len(entries) or manifest.get("entries") != entries
                or not ed25519.dogrula(public_key, raw, signature)):
            return None
        expected = {"manifest.json", "manifest.json.sig"}
        hashes = {}
        for record in entries:
            for locale in record.get("locales", []):
                path, digest = str(locale.get("path") or ""), str(locale.get("sha256") or "")
                if not re.fullmatch(r"texts/[a-f0-9]{2}/[a-f0-9]{64}\.txt", path):
                    return None
                expected.add(path)
                hashes[path] = digest
        with zipfile.ZipFile(archive_path) as archive:
            names = [item.filename for item in archive.infolist()]
            if len(names) != len(set(names)) or set(names) != expected:
                return None
            if archive.read("manifest.json") != raw:
                return None
            if archive.read("manifest.json.sig").decode("ascii").strip() != signature_bytes:
                return None
            for path, digest in hashes.items():
                if hashlib.sha256(archive.read(path)).hexdigest() != digest:
                    return None
        return manifest
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile, UnicodeError):
        return None


# ---------------------------------------------------------------- community ratings (schema 1)
# Contributions are written by the relay as contributions/<catalog-id>/<contribution_key>.json. One file per key
# means a re-sent rating replaces the earlier one, so counts cannot be inflated by repeating the same rating.
RATING_SCHEMA = "vardiya.prompt-rating"
RATING_FIELDS = {"schema", "schema_version", "catalog_id", "model", "model_version", "task_type", "usefulness",
                 "ease", "correction", "recommend", "comment", "contributor", "contribution_key", "rated_month"}
_SECRET_LIKE = re.compile(r"(?i)\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,})|"
                          r"(?:api[_ -]?key|token|password)\s*[:=]\s*\S+|[A-Za-z]:\\\S+|https?://\S+")


def _round1(value: float) -> float:
    from decimal import ROUND_HALF_UP, Decimal
    return float(Decimal(repr(float(value))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _score(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 10:
        raise ValueError("score")
    return _round1(value)


def valid_contribution(packet) -> dict | None:
    """Strict check of one contribution packet; anything unexpected is rejected (never repaired)."""
    try:
        if not isinstance(packet, dict) or set(packet) != RATING_FIELDS:
            return None
        if packet["schema"] != RATING_SCHEMA or packet["schema_version"] != 1:
            return None
        key = str(packet["contribution_key"])
        if not re.fullmatch(r"[0-9a-f]{32}", key) or not re.fullmatch(r"\d{4}-\d{2}", str(packet["rated_month"])):
            return None
        catalog_id = packet["catalog_id"]
        if not isinstance(catalog_id, str) or not 0 < len(catalog_id) <= 200:
            return None
        texts = {name: packet[name] for name in ("model", "model_version", "task_type")}
        if any(not isinstance(v, str) or len(v) > 100 for v in texts.values()):
            return None
        comment = packet["comment"]
        if not isinstance(comment, str) or len(comment) > 2000:
            return None
        if packet["recommend"] not in (None, "yes", "maybe", "no"):
            return None
        who = packet["contributor"]
        if who == {"type": "anonymous"}:
            author = ""
        elif (isinstance(who, dict) and set(who) == {"type", "display_name"} and who["type"] == "named"
              and isinstance(who["display_name"], str) and 0 < len(who["display_name"].strip()) <= 60):
            author = " ".join(who["display_name"].split())
        else:
            return None
        scores = {name: _score(packet[name]) for name in ("usefulness", "ease", "correction")}
        if all(v is None for v in scores.values()) and packet["recommend"] is None:
            return None
    except (KeyError, ValueError, TypeError):
        return None
    # Comments that look like they carry personal data or secrets are not published (the rating still counts).
    comment = comment.strip()
    if comment and (_PII.search(comment) or _SECRET_LIKE.search(comment)):
        comment = ""
    return {"catalog_id": catalog_id, "key": key, "month": packet["rated_month"], "comment": comment,
            "author": author, "recommend": packet["recommend"], **texts, **scores}


def ratings_from_contributions(folder: Path = CONTRIBUTIONS) -> dict[str, dict]:
    """catalog id -> manifest `ratings` (schema 1). Invalid files are skipped; only the newest packet of each
    contribution key counts."""
    latest: dict[str, dict] = {}
    if folder.is_dir():
        for path in sorted(folder.rglob("*.json")):
            try:
                if path.stat().st_size > 16_000:
                    continue
                item = valid_contribution(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
            if item and (item["key"] not in latest or item["month"] >= latest[item["key"]]["month"]):
                latest[item["key"]] = item
    by_prompt: dict[str, list[dict]] = {}
    for item in latest.values():
        by_prompt.setdefault(item["catalog_id"], []).append(item)

    def mean(items, name):
        values = [i[name] for i in items if i[name] is not None]
        return {"mean": _round1(sum(values) / len(values)) if values else None, "count": len(values)}

    result = {}
    for catalog_id, items in sorted(by_prompt.items()):
        contexts: dict[tuple, list] = {}
        for i in items:
            contexts.setdefault((i["model"], i["model_version"], i["task_type"]), []).append(i)
        newest = sorted(items, key=lambda i: i["month"], reverse=True)
        result[catalog_id] = {
            "schema_version": 1, "count": len(items),
            "usefulness": mean(items, "usefulness"), "ease": mean(items, "ease"),
            "correction": mean(items, "correction"),
            "recommend": {r: sum(1 for i in items if i["recommend"] == r) for r in ("yes", "maybe", "no")},
            "contexts": sorted(({"model": m, "model_version": v, "task_type": t, "count": len(group),
                                 "usefulness_mean": mean(group, "usefulness")["mean"]}
                                for (m, v, t), group in contexts.items()),
                               key=lambda c: (-c["count"], c["model"], c["model_version"], c["task_type"])),
            "comments": [{"text": i["comment"], "recommend": i["recommend"], "model": i["model"],
                          **({"author": i["author"]} if i["author"] else {})}
                         for i in newest if i["comment"]][:20],
        }
    return result


# ---------------------------------------------------------------- community language variants (candidates)
# The relay writes candidates as variants/<catalog-id>/<lang>/<contribution_key>.json. NOTHING is published
# automatically: only entries listed in variants/approved.json (edited by the repository owner on GitHub) with the
# exact text SHA-256 are put into the signed manifest. A candidate replaced after approval no longer matches the
# approved hash and stays out until it is approved again. Ratings never decide publication.
VARIANT_SCHEMA = "vardiya.prompt-variant"
VARIANT_FIELDS = {"schema", "schema_version", "catalog_id", "source_sha256", "lang", "purpose", "kind", "text",
                  "model", "edited_ratio", "license", "author", "contributor", "contribution_key", "created_month",
                  "checks"}
VARIANT_PURPOSES = {"sadik", "dogal", "resmi", "teknik", "sanatsal", "kendi"}
RISK_KINDS = {"disari_gonderme", "gizli_bilgi_isteme", "silme", "sistem_uzaktan", "kural_asma", "gizli_karakter"}
_VARIANT_SECRET = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|\b(?:sk-(?:ant-|proj-)?[A-Za-z0-9_-]{16,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"gh[pousr]_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,}|xox[abprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|"
    r"hf_[A-Za-z0-9]{30,}|gsk_[A-Za-z0-9]{30,})|(?i:\b(?:api[_ -]?key|access[_ -]?token|token|secret|password|"
    r"passwd|parola|şifre|sifre)\b\s*[:=]\s*[\"']?(?!\{)[^\s\"'{}]{6,})|\b[\w.+-]+@(?!example\.)[\w-]+(?:\.[\w-]+)+\b|"
    r"(?<![\w\d])\+?\d[\d ()-]{8,}\d(?!\d)|(?i:(?:[a-z]:\\users\\|/home/|/users/)(?!\{)[^\\/\s\"']+)")


def valid_variant(packet) -> dict | None:
    """Strict check of one variant candidate (same rules as the app and the relay)."""
    try:
        if not isinstance(packet, dict) or set(packet) != VARIANT_FIELDS:
            return None
        if packet["schema"] != VARIANT_SCHEMA or packet["schema_version"] != 1:
            return None
        if not re.fullmatch(r"[0-9a-f]{32}", str(packet["contribution_key"])):
            return None
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,200}", str(packet["catalog_id"])):
            return None
        if not re.fullmatch(r"[0-9a-f]{64}", str(packet["source_sha256"])) or \
                not re.fullmatch(r"[a-z]{2}", str(packet["lang"])) or \
                not re.fullmatch(r"\d{4}-\d{2}", str(packet["created_month"])):
            return None
        if packet["kind"] not in ("translation", "adaptation") or packet["purpose"] not in VARIANT_PURPOSES:
            return None
        text = packet["text"]
        if not isinstance(text, str) or not text.strip() or len(text) > 20000 or _VARIANT_SECRET.search(text):
            return None
        ratio = packet["edited_ratio"]
        if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not 0 <= ratio <= 1:
            return None
        if not isinstance(packet["checks"], list) or any(c not in RISK_KINDS for c in packet["checks"]):
            return None
        for name, limit in (("model", 100), ("license", 100), ("author", 200)):
            if not isinstance(packet[name], str) or len(packet[name]) > limit:
                return None
        who = packet["contributor"]
        if who != {"type": "anonymous"} and not (
                isinstance(who, dict) and set(who) == {"type", "display_name"} and who["type"] == "named"
                and isinstance(who["display_name"], str) and 0 < len(who["display_name"].strip()) <= 60
                and not _VARIANT_SECRET.search(who["display_name"])):
            return None
    except (KeyError, TypeError):
        return None
    return packet


def approved_variants(folder: Path = VARIANTS) -> dict[str, list[dict]]:
    """catalog id -> manifest `variants` (only owner-approved candidates whose text hash still matches)."""
    approved_file = folder / "approved.json"
    try:
        approved = json.loads(approved_file.read_text(encoding="utf-8")).get("approved") or []
    except (OSError, ValueError, AttributeError):
        return {}
    result: dict[str, list[dict]] = {}
    seen = set()
    for item in approved if isinstance(approved, list) else []:
        if not isinstance(item, dict):
            continue
        rel = str(item.get("path") or "")
        if not re.fullmatch(r"variants/[A-Za-z0-9._-]{1,200}/[a-z]{2}/[0-9a-f]{32}\.json", rel) or rel in seen:
            continue
        seen.add(rel)
        try:
            path = ROOT / rel
            if path.stat().st_size > 64_000:
                continue
            packet = valid_variant(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
        if packet is None:
            continue
        digest = hashlib.sha256(packet["text"].encode("utf-8")).hexdigest()
        if digest != str(item.get("sha256") or "") or rel.split("/")[1] != packet["catalog_id"] or \
                rel.split("/")[2] != packet["lang"] or not rel.endswith(packet["contribution_key"] + ".json"):
            continue
        result.setdefault(packet["catalog_id"], []).append({
            "id": packet["contribution_key"], "lang": packet["lang"], "kind": packet["kind"],
            "purpose": packet["purpose"], "model": packet["model"], "edited_ratio": packet["edited_ratio"],
            "contributor": packet["contributor"], "text": packet["text"], "sha256": digest,
            "source_sha256": packet["source_sha256"], "review": "owner_approved",
            "approved_at": str(item.get("approved_at") or "")[:30]})
    for items in result.values():
        items.sort(key=lambda v: (v["lang"], v["id"]))
    return result


def build(seed: dict, discovered: dict, run_number: int, private_key_b64: str) -> dict:
    # Preserve every seed record and append discoveries; content/risk classification never removes a record.
    records = list(seed.get("kayitlar") or [])
    positions = {str(k.get("kimlik")): i for i, k in enumerate(records) if isinstance(k, dict)}
    for record in [*discovered.values(), *official_link_records()]:
        record_id = str(record.get("kimlik") or "")
        if not record_id:
            continue
        if record_id in positions:
            # A stable source/path ID means the current source replaces the older
            # snapshot instead of silently freezing its first discovered version.
            records[positions[record_id]] = record
        else:
            positions[record_id] = len(records)
            records.append(record)

    entries, text_files = [], {}
    for record in records:
        if not isinstance(record, dict):
            continue
        source = record.get("kaynak") if isinstance(record.get("kaynak"), dict) else {}
        source_url = str(source.get("adres") or "")
        if not source_url.startswith("https://"):
            continue
        distribution = _distribution(record)
        locales = []
        if distribution == "full_text":
            for locale in _mapped_locale(record):
                raw = str(locale["text"]).encode("utf-8")
                digest = hashlib.sha256(raw).hexdigest()
                path = f"texts/{digest[:2]}/{digest}.txt"
                text_files.setdefault(path, raw)
                locales.append({"tag": str(locale.get("tag") or "und"), "kind": str(locale.get("kind") or "original"),
                                "from": str(locale.get("from") or ""), "review": str(locale.get("review") or "not_reviewed"),
                                "path": path, "sha256": digest})
        categories = record.get("categories") if isinstance(record.get("categories"), list) else [record.get("kategori", "genel")]
        categories = list(dict.fromkeys(str(x) for x in categories if str(x).strip())) or ["genel"]
        if "genel" not in categories:
            categories.append("genel")
        model_fit = record.get("model_fit") if isinstance(record.get("model_fit"), list) else []
        if not model_fit:
            provider = str(record.get("model") or "genel")
            model_fit = [{"provider": provider if provider != "genel" else "any", "family": provider,
                          "model_id": None, "model_version": str(record.get("model_surumu") or "") or None,
                          "basis": "source_only", "tested": False}]
        entry = {
            "id": str(record.get("kimlik") or hashlib.sha256(source_url.encode()).hexdigest()[:24]),
            "record_version": 1, "title": str(record.get("ad") or "Untitled prompt")[:160],
            "summary": str(record.get("aciklama") or record.get("description") or ""),
            "summary_en": str(record.get("aciklama_en") or ""),
            "description": str(record.get("description") or record.get("aciklama") or ""),
            "usage_notes": str(record.get("usage_notes") or ""),
            "warnings": list(record.get("warnings") or []), "limitations": list(record.get("limitations") or []),
            "categories": categories,
            "modules": list(dict.fromkeys(x for x in categories if x != "genel")) or ["sohbet"],
            "task_types": list(dict.fromkeys(x for x in (record.get("task_types") or categories) if x != "genel")) or ["genel"],
            "tags": list(record.get("tags") or []),
            "scope": list(record.get("scope") or ["unspecified"]), "locales": locales,
            "redistribution": distribution,
            "review_status": str(record.get("review_status") or ("source_checked" if record.get("guven") == "resmi" else "candidate")),
            "risk_tags": list(record.get("risk_tags") or record.get("tarama") or []),
            "sensitivity": str(record.get("sensitivity") or "none"),
            "risk_level": str(record.get("risk_level") or "unknown"),
            "model_fit": model_fit,
            "evidence": record.get("evidence") if isinstance(record.get("evidence"), dict) else {"kind": "source_only", "rated_tasks": 0},
            # Aggregated community ratings (schema 1) are carried over only when present.
            **({"ratings": record["ratings"]} if isinstance(record.get("ratings"), dict) else {}),
            "sensitive_reason": str(record.get("hassas") or ""), "legacy_note": str(record.get("not") or ""),
            "scan_flags": list(record.get("tarama") or []),
            "legacy_trust": str(record.get("guven") or "topluluk"),
            "provenance": {"kind": "official_guide" if record.get("guven") == "resmi" else "open_collection",
                           "url": source_url, "author": str(source.get("yazar") or record.get("kaynak_adi") or "Unknown"),
                           "license": str(source.get("lisans") or "unknown"),
                           "redistribution_basis": "recognized_license" if distribution == "full_text" else "",
                           "checked_at": str(source.get("tarih") or ""), "repository": str(source.get("depo") or ""),
                           "path": str(source.get("yol") or "")},
        }
        entries.append(entry)
    community = ratings_from_contributions(CONTRIBUTIONS)
    for entry in entries:
        if entry["id"] in community:
            entry["ratings"] = community[entry["id"]]
    variants = approved_variants(VARIANTS)
    for entry in entries:
        if entry["id"] in variants and entry["redistribution"] == "full_text":
            entry["variants"] = variants[entry["id"]]
    # Do not issue a new app-facing catalog version or force every device to fetch
    # the full bundle when the discovered prompt records have not changed.
    old_manifest = _existing_package_matches(entries)
    if old_manifest is not None:
        return old_manifest

    now = datetime.now(timezone.utc)
    version = f"{now.year}.{now.month:02d}.{now.day:02d}.{max(1, run_number)}"
    manifest = {"schema_version": 1, "catalog_version": version,
                "published_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
                "signature_file": "manifest.json.sig", "record_count": len(entries),
                "source_catalog_version": str(seed.get("surum") or "seed"), "entries": entries}
    raw_manifest = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    try:
        key = base64.b64decode(private_key_b64.strip(), validate=True)
    except Exception as error:
        raise RuntimeError("VARDIYA_CATALOG_SIGNING_KEY_B64 must contain a base64-encoded 32-byte Ed25519 seed") from error
    if len(key) != 32:
        raise RuntimeError("Catalog signing key has an invalid length")
    import ed25519
    public_key = base64.b64encode(ed25519.acik_anahtar(key)).decode("ascii")
    expected = (ROOT / "public_key.txt").read_text(encoding="ascii").strip()
    if public_key != expected:
        raise RuntimeError("Configured signing key does not match public_key.txt; nothing was published")
    signature = base64.b64encode(ed25519.imzala(key, raw_manifest)).decode("ascii") + "\n"
    OUT.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="catalog-stage-", dir=OUT))
    try:
        for path, raw in text_files.items():
            destination = stage / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
        (stage / "manifest.json").write_bytes(raw_manifest)
        (stage / "manifest.json.sig").write_text(signature, encoding="ascii")
        with zipfile.ZipFile(stage / "catalog.zip", "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr("manifest.json", raw_manifest)
            archive.writestr("manifest.json.sig", signature)
            for path in sorted(text_files):
                archive.writestr(path, text_files[path])
        # Check the exact new signed bytes before touching the currently published files.
        import ed25519
        if not ed25519.dogrula(base64.b64decode(expected), raw_manifest, base64.b64decode(signature)):
            raise RuntimeError("New catalog signature did not validate; previous publication retained")
        for staged in stage.rglob("*.txt"):
            relative = staged.relative_to(stage)
            destination = OUT / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged, destination)
        for name in ("manifest.json", "manifest.json.sig", "catalog.zip"):
            os.replace(stage / name, OUT / name)
        # Remove orphaned text variants only after the new package and signed index are ready.
        current = {str(path).replace("\\", "/") for path in text_files}
        for old in (OUT / "texts").rglob("*.txt") if (OUT / "texts").exists() else []:
            if old.relative_to(OUT).as_posix() not in current:
                old.unlink()
        _json_write(OUT / "catalog-status.json", {"version": version, "count": len(entries),
                                                    "discovered": len(discovered), "built_at": manifest["published_at"]})
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return manifest


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN", "")
    private_key = os.environ.get("VARDIYA_CATALOG_SIGNING_KEY_B64", "")
    if not private_key:
        print("Missing VARDIYA_CATALOG_SIGNING_KEY_B64; existing signed catalog files remain untouched.", file=sys.stderr)
        return 2
    seed = _read_json(SEED, {})
    if not seed.get("kayitlar"):
        print("seed_catalog.json is missing or empty; no catalog was published.", file=sys.stderr)
        return 2
    candidates = _read_json(CANDIDATES, {})
    if not isinstance(candidates, dict):
        candidates = {}
    try:
        candidates, report = discover(token, candidates)
    except (RuntimeError, json.JSONDecodeError) as error:
        # Search downtime/rate limits never replace a good catalog with an empty one.
        report = {"error": str(error), "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    _json_write(CANDIDATES, candidates)
    manifest = build(seed, candidates, int(os.environ.get("GITHUB_RUN_NUMBER", "1") or 1), private_key)
    _json_write(OUT / "discovery-report.json", report)
    print(f"Signed catalog built: {manifest['catalog_version']} ({manifest['record_count']} records; {len(candidates)} community candidates)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
