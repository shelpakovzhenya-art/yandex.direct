#!/usr/bin/env python3
"""Deterministic helpers for the yandex-direct agent skill.

Standard library only. Network commands are preview-only unless --execute is
supplied. Live Yandex Direct mutations additionally require an exact confirmation
token printed by the preview.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


NARROW_CHARS = set('!,.;:"')
MUTATING_METHODS = {
    "add",
    "update",
    "delete",
    "suspend",
    "resume",
    "archive",
    "unarchive",
    "moderate",
    "set",
    "toggle",
}
DIRECT_SERVICES = {
    "adextensions",
    "adgroups",
    "ads",
    "audiencetargets",
    "bidmodifiers",
    "businesses",
    "campaigns",
    "clients",
    "creatives",
    "dictionaries",
    "dynamictextadtargets",
    "feeds",
    "keywordbids",
    "keywords",
    "keywordsresearch",
    "leads",
    "negativekeywordsharedsets",
    "retargetinglists",
    "sitelinks",
    "smartadtargets",
    "strategies",
    "turbopages",
    "vcards",
}
DISPLAY_PATH_RE = re.compile(r"^[0-9A-Za-zА-Яа-яЁё№/%#-]+$")
WORD_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё]+(?:[-'][0-9A-Za-zА-Яа-яЁё]+)*")
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-zА-Яа-я]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?7|8)[\s()\-]*\d{3}[\s()\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)")
SUPERLATIVE_RE = re.compile(
    r"\b(?:лучш(?:ий|ая|ее|ие)|сам(?:ый|ая|ое|ые)|единственн\w*|"
    r"гарантир\w*|номер\s*1|топ[- ]?1)\b|№\s*1",
    re.IGNORECASE,
)
PROVOCATIVE_RE = re.compile(
    r"\b(?:шок|сенсаци\w*|жми|успей|немедленно|секрет,?\s+который|"
    r"все\s+скрывают)\b",
    re.IGNORECASE,
)
STOP_WORDS_RU = {
    "а", "без", "бы", "был", "была", "были", "в", "во", "вот", "вы", "где",
    "да", "для", "до", "его", "ее", "если", "есть", "же", "за", "и", "из", "или",
    "к", "как", "ко", "ли", "мы", "на", "над", "не", "но", "о", "об", "от", "по",
    "под", "при", "про", "с", "со", "то", "у", "что", "это",
}
TRANSACTIONAL_MARKERS = {
    "купить", "заказать", "цена", "стоимость", "доставка", "монтаж", "установка",
    "вызвать", "записаться", "аренда", "ремонт", "под ключ", "рядом", "срочно",
}
COMMERCIAL_MARKERS = {
    "отзывы", "сравнение", "рейтинг", "лучший", "выбрать", "подбор", "условия",
    "сколько стоит", "прайс", "каталог",
}
INFORMATIONAL_MARKERS = {
    "как", "что такое", "почему", "своими руками", "инструкция", "бесплатно",
    "скачать", "вакансия", "вакансии", "работа", "обучение", "курсовая", "реферат",
    "фото", "видео", "форум",
}


def fail(message: str, code: int = 2) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def load_json(path: str | Path) -> Any:
    try:
        with Path(path).open("r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read JSON {path}: {exc}")


def dump_json(data: Any, output: str | None = None) -> None:
    rendered = json.dumps(data, ensure_ascii=False, indent=2)
    if output:
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered + "\n", encoding="utf-8")
        print(f"Wrote {target}")
    else:
        print(rendered)


def issue(severity: str, code: str, path: str, message: str, **extra: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "severity": severity,
        "code": code,
        "path": path,
        "message": message,
    }
    item.update(extra)
    return item


def normalized_text(value: str) -> str:
    value = value.lower().replace("ё", "е")
    value = re.sub(r"[^0-9a-zа-я]+", " ", value, flags=re.IGNORECASE)
    return " ".join(value.split())


def semantic_tokens(value: str) -> list[str]:
    return [token for token in normalized_text(value).split() if len(token) > 2 and token not in STOP_WORDS_RU]


def message_overlap(headline: str, h1: str) -> float | None:
    headline_tokens = set(semantic_tokens(headline))
    if not headline_tokens:
        return None
    h1_tokens = set(semantic_tokens(h1))
    return len(headline_tokens & h1_tokens) / len(headline_tokens)


def check_word_lengths(value: str, limit: int, path: str) -> list[dict[str, Any]]:
    result = []
    for word in WORD_RE.findall(value.replace("#", "")):
        if len(word) > limit:
            result.append(
                issue(
                    "error",
                    "word_too_long",
                    path,
                    f"word '{word}' has {len(word)} characters; maximum is {limit}",
                )
            )
    return result


def check_style(value: str, path: str, has_claim_refs: bool) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    alpha = "".join(char for char in value if char.isalpha())
    if len(alpha) >= 4 and alpha.isupper():
        result.append(issue("error", "all_caps", path, "all-caps text is not moderation-safe"))
    if re.search(r"[!?.,]{3,}", value):
        result.append(issue("warning", "excessive_punctuation", path, "three or more adjacent punctuation marks"))
    if EMAIL_RE.search(value) or PHONE_RE.search(value):
        result.append(issue("error", "contact_in_ad", path, "email or phone detected in ad copy"))
    if SUPERLATIVE_RE.search(value) and not has_claim_refs:
        result.append(
            issue(
                "error",
                "unproven_superlative",
                path,
                "superlative/guarantee requires independent evidence visible on the landing page",
            )
        )
    if PROVOCATIVE_RE.search(value):
        result.append(
            issue(
                "warning",
                "provocative_language",
                path,
                "sensational or aggressive wording may fail moderation and reduce trust",
            )
        )
    return result


def validate_title(value: Any, path: str, has_claim_refs: bool) -> list[dict[str, Any]]:
    if not isinstance(value, str) or not value.strip():
        return [issue("error", "empty_title", path, "title must be a non-empty string")]
    clean = value.replace("#", "")
    result: list[dict[str, Any]] = []
    if len(clean) > 56:
        result.append(issue("error", "title_too_long", path, f"{len(clean)} characters; maximum is 56"))
    result.extend(check_word_lengths(value, 22, path))
    result.extend(check_style(value, path, has_claim_refs))
    return result


def validate_ad_text(value: Any, path: str, has_claim_refs: bool) -> list[dict[str, Any]]:
    if not isinstance(value, str) or not value.strip():
        return [issue("error", "empty_text", path, "ad text must be a non-empty string")]
    clean = value.replace("#", "")
    narrow = sum(1 for char in clean if char in NARROW_CHARS)
    ordinary = len(clean) - narrow
    result: list[dict[str, Any]] = []
    if ordinary > 81:
        result.append(
            issue(
                "error",
                "text_too_long",
                path,
                f"{ordinary} ordinary characters; maximum is 81 (narrow punctuation is counted separately)",
            )
        )
    if narrow > 15:
        result.append(issue("error", "too_many_narrow_chars", path, f"{narrow} narrow punctuation marks; maximum is 15"))
    result.extend(check_word_lengths(value, 23, path))
    result.extend(check_style(value, path, has_claim_refs))
    return result


def validate_href(value: Any, path: str) -> list[dict[str, Any]]:
    if not isinstance(value, str) or not value:
        return [issue("error", "missing_href", path, "Href is required unless BusinessId is used")]
    if len(value) > 1024:
        return [issue("error", "href_too_long", path, "Href exceeds 1024 characters")]
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return [issue("error", "invalid_href", path, "Href must include http(s) scheme and a domain")]
    return []


def validate_display_path(value: Any, path: str) -> list[dict[str, Any]]:
    if value in (None, ""):
        return []
    if not isinstance(value, str):
        return [issue("error", "invalid_display_path", path, "display_url_path must be a string")]
    result: list[dict[str, Any]] = []
    if len(value.replace("#", "")) > 20:
        result.append(issue("error", "display_path_too_long", path, "display URL path exceeds 20 characters"))
    if not DISPLAY_PATH_RE.fullmatch(value) or "_" in value or " " in value or "--" in value or "//" in value:
        result.append(
            issue(
                "error",
                "display_path_characters",
                path,
                "allowed: letters, digits, -, №, /, %, #; no spaces, _, --, or //",
            )
        )
    return result


def validate_package_data(data: Any) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not isinstance(data, dict):
        return [issue("error", "invalid_root", "$", "package root must be an object")]
    segments = data.get("segments")
    if not isinstance(segments, list) or not segments:
        return [issue("error", "missing_segments", "$.segments", "at least one segment is required")]

    seen_ids: set[str] = set()
    for index, segment in enumerate(segments):
        base = f"$.segments[{index}]"
        if not isinstance(segment, dict):
            issues.append(issue("error", "invalid_segment", base, "segment must be an object"))
            continue
        segment_id = str(segment.get("segment_id", "")).strip()
        if not segment_id:
            issues.append(issue("error", "missing_segment_id", f"{base}.segment_id", "segment_id is required"))
        elif segment_id in seen_ids:
            issues.append(issue("error", "duplicate_segment_id", f"{base}.segment_id", f"duplicate id {segment_id}"))
        else:
            seen_ids.add(segment_id)

        ad = segment.get("responsive_ad")
        if not isinstance(ad, dict):
            issues.append(issue("error", "missing_responsive_ad", f"{base}.responsive_ad", "ResponsiveAd data is required"))
            continue
        claim_refs = segment.get("claim_refs")
        has_claim_refs = isinstance(claim_refs, list) and bool(claim_refs)
        titles = ad.get("titles")
        texts = ad.get("texts")
        if not isinstance(titles, list) or not 1 <= len(titles) <= 7:
            issues.append(issue("error", "title_count", f"{base}.responsive_ad.titles", "provide 1 to 7 titles"))
            titles = titles if isinstance(titles, list) else []
        elif len(titles) < 5:
            issues.append(issue("warning", "thin_title_set", f"{base}.responsive_ad.titles", "5 to 7 distinct titles are recommended"))
        if not isinstance(texts, list) or not 1 <= len(texts) <= 3:
            issues.append(issue("error", "text_count", f"{base}.responsive_ad.texts", "provide 1 to 3 texts"))
            texts = texts if isinstance(texts, list) else []
        elif len(texts) < 3:
            issues.append(issue("warning", "thin_text_set", f"{base}.responsive_ad.texts", "3 distinct texts are recommended"))

        for title_index, title in enumerate(titles):
            issues.extend(validate_title(title, f"{base}.responsive_ad.titles[{title_index}]", has_claim_refs))
        for text_index, text_value in enumerate(texts):
            issues.extend(validate_ad_text(text_value, f"{base}.responsive_ad.texts[{text_index}]", has_claim_refs))

        title_norms = [normalized_text(item) for item in titles if isinstance(item, str)]
        if len(set(title_norms)) != len(title_norms):
            issues.append(issue("error", "duplicate_titles", f"{base}.responsive_ad.titles", "duplicate normalized titles detected"))
        text_norms = [normalized_text(item) for item in texts if isinstance(item, str)]
        if len(set(text_norms)) != len(text_norms):
            issues.append(issue("error", "duplicate_texts", f"{base}.responsive_ad.texts", "duplicate normalized texts detected"))

        business_id = ad.get("business_id")
        if not business_id:
            issues.extend(validate_href(ad.get("href"), f"{base}.responsive_ad.href"))
        issues.extend(validate_display_path(ad.get("display_url_path"), f"{base}.responsive_ad.display_url_path"))

        image_hashes = ad.get("ad_image_hashes", [])
        if image_hashes not in (None, []) and (not isinstance(image_hashes, list) or not 1 <= len(image_hashes) <= 5):
            issues.append(issue("error", "image_count", f"{base}.responsive_ad.ad_image_hashes", "provide 1 to 5 image hashes"))

        landing = segment.get("landing", {})
        h1 = landing.get("h1") if isinstance(landing, dict) else None
        if titles and isinstance(titles[0], str):
            if not isinstance(h1, str) or not h1.strip():
                issues.append(issue("warning", "missing_landing_h1", f"{base}.landing.h1", "cannot verify message match without H1"))
            else:
                ratio = message_overlap(titles[0], h1)
                if ratio is not None and ratio < 0.35:
                    issues.append(issue("error", "message_match_fail", f"{base}.landing.h1", f"primary-title/H1 overlap is {ratio:.2f}; below 0.35", ratio=ratio))
                elif ratio is not None and ratio < 0.60:
                    issues.append(issue("warning", "message_match_review", f"{base}.landing.h1", f"primary-title/H1 overlap is {ratio:.2f}; review meaning", ratio=ratio))

        if not has_claim_refs and any(SUPERLATIVE_RE.search(str(value)) for value in [*titles, *texts]):
            issues.append(issue("error", "missing_claim_refs", f"{base}.claim_refs", "claim_refs required for comparative, superlative, or guarantee claims"))
    return issues


def validation_report(data: Any) -> dict[str, Any]:
    issues = validate_package_data(data)
    counts = defaultdict(int)
    for item in issues:
        counts[item["severity"]] += 1
    return {
        "valid": counts["error"] == 0,
        "counts": {"error": counts["error"], "warning": counts["warning"], "info": counts["info"]},
        "issues": issues,
    }


def command_validate(args: argparse.Namespace) -> None:
    report = validation_report(load_json(args.input))
    dump_json(report, args.output)
    if not report["valid"]:
        raise SystemExit(1)


def remove_empty(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {key: remove_empty(item) for key, item in value.items()}
        return {key: item for key, item in cleaned.items() if item not in (None, [], {}, "")}
    if isinstance(value, list):
        return [remove_empty(item) for item in value if item not in (None, "")]
    return value


def build_responsive_payload(data: dict[str, Any]) -> dict[str, Any]:
    report = validation_report(data)
    if not report["valid"]:
        fail("package has validation errors; run validate-package for details")
    ads = []
    for index, segment in enumerate(data["segments"]):
        ad_group_id = segment.get("ad_group_id")
        if not isinstance(ad_group_id, int) or ad_group_id <= 0:
            fail(f"segments[{index}].ad_group_id must be a positive integer for API payload")
        source = segment["responsive_ad"]
        responsive = {
            "Titles": source["titles"],
            "Texts": source["texts"],
            "Href": source.get("href"),
            "AgeLabel": source.get("age_label"),
            "DisplayUrlPath": source.get("display_url_path"),
            "AdImageHashes": source.get("ad_image_hashes"),
            "SitelinkSetId": source.get("sitelink_set_id"),
            "AdExtensionIds": source.get("ad_extension_ids"),
            "VideoExtensionIds": source.get("video_extension_ids"),
            "BusinessId": source.get("business_id"),
            "ErirAdDescription": source.get("erir_ad_description"),
        }
        if source.get("price_extension"):
            responsive["PriceExtension"] = source["price_extension"]
        ads.append({"AdGroupId": ad_group_id, "ResponsiveAd": remove_empty(responsive)})
    return {"method": "add", "params": {"Ads": ads}}


def command_build_payload(args: argparse.Namespace) -> None:
    data = load_json(args.input)
    if not isinstance(data, dict):
        fail("package root must be an object")
    dump_json(build_responsive_payload(data), args.output)


def sniff_delimiter(path: Path) -> str:
    sample = path.read_text(encoding="utf-8-sig")[:8192]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except csv.Error:
        return ";" if sample.count(";") >= sample.count(",") else ","


def find_header(row: dict[str, Any], aliases: Iterable[str]) -> str | None:
    normalized = {normalized_text(key): key for key in row}
    for alias in aliases:
        key = normalized.get(normalized_text(alias))
        if key is not None:
            return key
    return None


def parse_number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    text_value = str(value).strip().replace("\u00a0", "").replace(" ", "")
    text_value = re.sub(r"[^0-9,.-]", "", text_value)
    if text_value.count(",") == 1 and text_value.count(".") == 0:
        text_value = text_value.replace(",", ".")
    elif text_value.count(",") > 0 and text_value.count(".") == 1:
        text_value = text_value.replace(",", "")
    try:
        return float(text_value)
    except ValueError:
        return 0.0


def intent_hint(phrase: str) -> tuple[str, float]:
    value = normalized_text(phrase)
    if any(marker in value for marker in TRANSACTIONAL_MARKERS):
        return "transactional", 0.75
    if any(marker in value for marker in COMMERCIAL_MARKERS):
        return "commercial", 0.65
    if any(marker in value for marker in INFORMATIONAL_MARKERS):
        return "informational", 0.70
    return "unknown", 0.25


def command_normalize_semantics(args: argparse.Namespace) -> None:
    source = Path(args.input)
    delimiter = args.delimiter or sniff_delimiter(source)
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter=delimiter))
    if not rows:
        fail("semantic CSV has no rows")
    phrase_key = find_header(rows[0], ["phrase", "query", "keyword", "фраза", "поисковый запрос", "ключевая фраза"])
    if not phrase_key:
        fail("cannot find phrase column")
    volume_key = find_header(rows[0], ["count", "volume", "impressions", "частотность", "показы"])
    source_key = find_header(rows[0], ["source", "источник"])
    seed_key = find_header(rows[0], ["seed", "маркер", "база"])
    region_key = find_header(rows[0], ["region", "регион"])
    device_key = find_header(rows[0], ["device", "устройство"])
    offer_terms = [normalized_text(item) for item in (args.offer_term or []) if normalized_text(item)]
    exclude_terms = [normalized_text(item) for item in (args.exclude_term or []) if normalized_text(item)]

    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        phrase = str(row.get(phrase_key, "")).strip()
        canonical = normalized_text(phrase)
        if not canonical:
            continue
        hint, confidence = intent_hint(phrase)
        offer_match = "unknown"
        if exclude_terms and any(term in canonical for term in exclude_terms):
            offer_match = "excluded_candidate"
        elif offer_terms:
            offer_match = "yes" if any(term in canonical for term in offer_terms) else "review"
        item = {
            "phrase": phrase,
            "normalized_phrase": canonical,
            "volume": parse_number(row.get(volume_key)) if volume_key else 0,
            "source": str(row.get(source_key, "unknown")) if source_key else "unknown",
            "seed": str(row.get(seed_key, "")) if seed_key else "",
            "region": str(row.get(region_key, "")) if region_key else "",
            "device": str(row.get(device_key, "")) if device_key else "",
            "intent_hint": hint,
            "confidence": f"{confidence:.2f}",
            "offer_match": offer_match,
            "review_required": "yes",
            "duplicate_count": 1,
        }
        if canonical in grouped:
            current = grouped[canonical]
            current["duplicate_count"] += 1
            if item["volume"] > current["volume"]:
                item["duplicate_count"] = current["duplicate_count"]
                grouped[canonical] = item
        else:
            grouped[canonical] = item

    output_rows = sorted(grouped.values(), key=lambda item: (-float(item["volume"]), item["normalized_phrase"]))
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    fields = list(output_rows[0]) if output_rows else []
    with target.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter=args.output_delimiter)
        writer.writeheader()
        writer.writerows(output_rows)
    print(json.dumps({"input_rows": len(rows), "unique_rows": len(output_rows), "output": str(target)}, ensure_ascii=False))


def request_json(url: str, body: dict[str, Any], headers: dict[str, str], timeout: int) -> tuple[int, dict[str, str], str]:
    encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=encoded, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers.items()), response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        return exc.code, dict(exc.headers.items()), text
    except urllib.error.URLError as exc:
        fail(f"network error: {exc}")


def payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def command_direct_request(args: argparse.Namespace) -> None:
    service = args.service.lower()
    if service not in DIRECT_SERVICES:
        fail(f"unsupported Direct service: {service}")
    payload = load_json(args.payload)
    if not isinstance(payload, dict) or not isinstance(payload.get("method"), str):
        fail("payload must contain a string method")
    method = payload["method"].lower()
    environment = args.environment or os.getenv("YANDEX_DIRECT_ENV", "sandbox").lower()
    if environment not in {"sandbox", "production"}:
        fail("environment must be sandbox or production")
    host = "api-sandbox.direct.yandex.com" if environment == "sandbox" else "api.direct.yandex.com"
    url = f"https://{host}/json/{args.version}/{service}"
    mutation = method in MUTATING_METHODS
    token_prefix = "SANDBOX" if environment == "sandbox" else "LIVE"
    required_confirmation = f"{token_prefix}:{service}:{method}" if mutation else None
    preview = {
        "execute": bool(args.execute),
        "environment": environment,
        "url": url,
        "service": service,
        "method": method,
        "mutation": mutation,
        "required_confirmation": required_confirmation,
        "payload_sha256": payload_hash(payload),
        "payload": payload,
    }
    if not args.execute:
        dump_json(preview)
        return
    if mutation and args.confirm != required_confirmation:
        dump_json(preview)
        fail(f"mutation blocked; repeat with --confirm {required_confirmation}")
    oauth = os.getenv("YANDEX_DIRECT_TOKEN")
    if not oauth:
        fail("YANDEX_DIRECT_TOKEN is not set")
    headers = {
        "Authorization": f"Bearer {oauth}",
        "Accept-Language": "ru",
        "Content-Type": "application/json; charset=utf-8",
    }
    client_login = os.getenv("YANDEX_DIRECT_CLIENT_LOGIN")
    if client_login:
        headers["Client-Login"] = client_login
    status, response_headers, response_text = request_json(url, payload, headers, args.timeout)
    result: dict[str, Any] = {
        "status": status,
        "request": {key: value for key, value in preview.items() if key != "payload"},
        "retry_in": response_headers.get("retryIn") or response_headers.get("Retry-In"),
        "units": response_headers.get("Units"),
    }
    try:
        result["response"] = json.loads(response_text)
    except json.JSONDecodeError:
        result["response_text"] = response_text
    dump_json(result, args.output)
    if status >= 400 or (isinstance(result.get("response"), dict) and result["response"].get("error")):
        raise SystemExit(1)


def command_wordstat_top(args: argparse.Namespace) -> None:
    phrases = args.phrase
    call_count = len(phrases)
    confirmation = f"WORDSTAT:{call_count}"
    preview = {
        "execute": bool(args.execute),
        "endpoint": "https://searchapi.api.cloud.yandex.net/v2/wordstat/topRequests",
        "paid_calls": call_count,
        "required_confirmation": confirmation,
        "phrases": phrases,
        "num_phrases_each": args.num_phrases,
        "regions": args.regions,
        "devices": args.devices,
    }
    if not args.execute:
        dump_json(preview)
        return
    if args.confirm != confirmation:
        dump_json(preview)
        fail(f"paid Wordstat calls blocked; repeat with --confirm {confirmation}")
    api_key = os.getenv("YANDEX_SEARCH_API_KEY")
    folder_id = os.getenv("YANDEX_FOLDER_ID")
    if not api_key or not folder_id:
        fail("YANDEX_SEARCH_API_KEY and YANDEX_FOLDER_ID must be set")
    endpoint = preview["endpoint"]
    headers = {"Authorization": f"Api-Key {api_key}", "Content-Type": "application/json"}
    collected = []
    for phrase in phrases:
        body = {
            "phrase": phrase,
            "numPhrases": args.num_phrases,
            "folderId": folder_id,
            "devices": args.devices,
        }
        if args.regions:
            body["regions"] = args.regions
        status, _, response_text = request_json(endpoint, body, headers, args.timeout)
        try:
            response: Any = json.loads(response_text)
        except json.JSONDecodeError:
            response = {"raw": response_text}
        collected.append({"phrase": phrase, "status": status, "response": response})
        if status >= 400:
            dump_json({"requests": collected}, args.output)
            raise SystemExit(1)
    dump_json({"source": "Yandex Search API Wordstat v2", "requests": collected}, args.output)


def command_build_utm(args: argparse.Namespace) -> None:
    parsed = urllib.parse.urlsplit(args.url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        fail("URL must include http(s) and a domain")
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    query.update(
        {
            "utm_source": args.source,
            "utm_medium": args.medium,
            "utm_campaign": args.campaign,
            "utm_content": args.content,
            "utm_term": args.term,
        }
    )
    query = {key: value for key, value in query.items() if value not in (None, "")}
    encoded = urllib.parse.urlencode(query, safe="{}")
    print(urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, encoded, parsed.fragment)))


def command_experiment(args: argparse.Namespace) -> None:
    if not (0 <= args.control_success <= args.control_n and 0 <= args.variant_success <= args.variant_n):
        fail("success counts must be between 0 and sample size")
    if args.control_n <= 0 or args.variant_n <= 0:
        fail("sample sizes must be positive")
    p1 = args.control_success / args.control_n
    p2 = args.variant_success / args.variant_n
    pooled = (args.control_success + args.variant_success) / (args.control_n + args.variant_n)
    pooled_se = math.sqrt(pooled * (1 - pooled) * (1 / args.control_n + 1 / args.variant_n))
    z_score = (p2 - p1) / pooled_se if pooled_se else 0.0
    normal_cdf = lambda value: 0.5 * (1 + math.erf(value / math.sqrt(2)))
    p_value = 2 * (1 - normal_cdf(abs(z_score)))
    unpooled_se = math.sqrt(p1 * (1 - p1) / args.control_n + p2 * (1 - p2) / args.variant_n)
    z_crit = 1.959963984540054
    diff = p2 - p1
    ci_low = diff - z_crit * unpooled_se
    ci_high = diff + z_crit * unpooled_se
    relative_lift = diff / p1 if p1 else None
    practical = relative_lift is not None and relative_lift >= args.min_relative_lift
    result = {
        "method": "two-proportion z-test (pooled); unpooled 95% CI for absolute difference",
        "control_rate": p1,
        "variant_rate": p2,
        "absolute_difference": diff,
        "relative_lift": relative_lift,
        "z_score": z_score,
        "p_value": p_value,
        "alpha": args.alpha,
        "statistically_significant": p_value < args.alpha,
        "minimum_relative_lift": args.min_relative_lift,
        "practically_material": practical,
        "difference_ci_95": [ci_low, ci_high],
        "decision": "UNDECIDED",
        "note": "Statistical and practical flags do not authorize a campaign action.",
    }
    dump_json(result, args.output)


def command_audit_search_terms(args: argparse.Namespace) -> None:
    source = Path(args.input)
    delimiter = args.delimiter or sniff_delimiter(source)
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter=delimiter))
    if not rows:
        fail("search-terms CSV has no rows")
    aliases = {
        "query": ["query", "search term", "поисковый запрос", "запрос"],
        "impressions": ["impressions", "показы"],
        "clicks": ["clicks", "клики"],
        "cost": ["cost", "spend", "расход", "затраты"],
        "conversions": ["conversions", "конверсии", "целевые визиты"],
        "revenue": ["revenue", "выручка", "доход"],
    }
    keys = {name: find_header(rows[0], values) for name, values in aliases.items()}
    if not keys["query"]:
        fail("cannot find query/search-term column")
    output_rows = []
    for row in rows:
        query = str(row.get(keys["query"], "")).strip()
        impressions = parse_number(row.get(keys["impressions"])) if keys["impressions"] else 0
        clicks = parse_number(row.get(keys["clicks"])) if keys["clicks"] else 0
        cost = parse_number(row.get(keys["cost"])) if keys["cost"] else 0
        conversions = parse_number(row.get(keys["conversions"])) if keys["conversions"] else 0
        revenue = parse_number(row.get(keys["revenue"])) if keys["revenue"] else 0
        ctr = clicks / impressions if impressions else None
        cr = conversions / clicks if clicks else None
        cpa = cost / conversions if conversions else None
        roas = revenue / cost if cost else None
        hint, confidence = intent_hint(query)
        if conversions > 0:
            if args.target_cpa and cpa is not None and cpa > args.target_cpa:
                recommendation = "economics_review"
            else:
                recommendation = "positive_or_keep_review"
        elif (args.target_cpa and cost >= args.target_cpa) or clicks >= args.min_clicks:
            recommendation = "negative_review"
        else:
            recommendation = "observe"
        output_rows.append(
            {
                "query": query,
                "impressions": f"{impressions:g}",
                "clicks": f"{clicks:g}",
                "cost": f"{cost:.2f}",
                "conversions": f"{conversions:g}",
                "revenue": f"{revenue:.2f}",
                "ctr": "" if ctr is None else f"{ctr:.4f}",
                "cr": "" if cr is None else f"{cr:.4f}",
                "cpa": "" if cpa is None else f"{cpa:.2f}",
                "roas": "" if roas is None else f"{roas:.4f}",
                "intent_hint": hint,
                "intent_confidence": f"{confidence:.2f}",
                "recommendation": recommendation,
                "human_review_required": "yes",
            }
        )
    output_rows.sort(key=lambda item: (-float(item["cost"]), item["query"]))
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output_rows[0]), delimiter=args.output_delimiter)
        writer.writeheader()
        writer.writerows(output_rows)
    summary = defaultdict(int)
    for row in output_rows:
        summary[row["recommendation"]] += 1
    print(json.dumps({"rows": len(output_rows), "recommendations": dict(summary), "output": str(target)}, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Yandex Direct research, validation, measurement, and safe API toolkit")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-package", help="validate a campaign package and ResponsiveAd limits")
    validate.add_argument("input")
    validate.add_argument("--output")
    validate.set_defaults(func=command_validate)

    payload = subparsers.add_parser("build-responsive-payload", help="build ads.add ResponsiveAd payload")
    payload.add_argument("input")
    payload.add_argument("--output")
    payload.set_defaults(func=command_build_payload)

    semantics = subparsers.add_parser("normalize-semantics", help="deduplicate and annotate semantic CSV")
    semantics.add_argument("input")
    semantics.add_argument("--output", required=True)
    semantics.add_argument("--delimiter")
    semantics.add_argument("--output-delimiter", default=";")
    semantics.add_argument("--offer-term", action="append")
    semantics.add_argument("--exclude-term", action="append")
    semantics.set_defaults(func=command_normalize_semantics)

    direct = subparsers.add_parser("direct-request", help="preview or execute one generic Direct API request")
    direct.add_argument("service")
    direct.add_argument("payload")
    direct.add_argument("--version", default="v501", choices=["v5", "v501"])
    direct.add_argument("--environment", choices=["sandbox", "production"])
    direct.add_argument("--execute", action="store_true")
    direct.add_argument("--confirm")
    direct.add_argument("--timeout", type=int, default=60)
    direct.add_argument("--output")
    direct.set_defaults(func=command_direct_request)

    wordstat = subparsers.add_parser("wordstat-top", help="preview or execute paid Wordstat v2 topRequests calls")
    wordstat.add_argument("--phrase", action="append", required=True)
    wordstat.add_argument("--regions", nargs="*", default=[])
    wordstat.add_argument(
        "--devices",
        nargs="+",
        default=["DEVICE_ALL"],
        choices=["DEVICE_ALL", "DEVICE_DESKTOP", "DEVICE_PHONE", "DEVICE_TABLET"],
    )
    wordstat.add_argument("--num-phrases", type=int, default=100, choices=range(1, 2001), metavar="1..2000")
    wordstat.add_argument("--execute", action="store_true")
    wordstat.add_argument("--confirm")
    wordstat.add_argument("--timeout", type=int, default=60)
    wordstat.add_argument("--output")
    wordstat.set_defaults(func=command_wordstat_top)

    utm = subparsers.add_parser("build-utm", help="append a stable Yandex UTM package to a URL")
    utm.add_argument("url")
    utm.add_argument("--source", default="yandex")
    utm.add_argument("--medium", default="cpc")
    utm.add_argument("--campaign", required=True)
    utm.add_argument("--content", default="{ad_id}_{phrase_id}")
    utm.add_argument("--term", default="{keyword}")
    utm.set_defaults(func=command_build_utm)

    experiment = subparsers.add_parser("experiment-readout", help="calculate a two-proportion A/B readout")
    experiment.add_argument("--control-success", type=int, required=True)
    experiment.add_argument("--control-n", type=int, required=True)
    experiment.add_argument("--variant-success", type=int, required=True)
    experiment.add_argument("--variant-n", type=int, required=True)
    experiment.add_argument("--alpha", type=float, default=0.05)
    experiment.add_argument("--min-relative-lift", type=float, default=0.10)
    experiment.add_argument("--output")
    experiment.set_defaults(func=command_experiment)

    audit = subparsers.add_parser("audit-search-terms", help="calculate query economics and human-review flags")
    audit.add_argument("input")
    audit.add_argument("--output", required=True)
    audit.add_argument("--delimiter")
    audit.add_argument("--output-delimiter", default=";")
    audit.add_argument("--target-cpa", type=float)
    audit.add_argument("--min-clicks", type=float, default=20)
    audit.set_defaults(func=command_audit_search_terms)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
