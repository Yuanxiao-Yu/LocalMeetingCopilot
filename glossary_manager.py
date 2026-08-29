from __future__ import annotations

import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

import yaml

from config import AppConfig, load_config
from glossary import (
    GlossaryTerm,
    load_glossary_terms,
    match_terms,
    normalise_term_text,
)

VALID_PRIORITIES = {"low", "medium", "high"}


@dataclass(frozen=True, slots=True)
class GlossaryWriteResult:
    path: Path
    added: int
    updated: int
    total: int


def run_glossary_search(
    text: str,
    *,
    config: AppConfig | None = None,
    profile: str | None = None,
    limit: int | None = None,
    output: TextIO | None = None,
) -> int:
    cfg = config or load_config(profile=profile)
    terms = load_glossary_terms(
        profile=cfg.meeting_profile,
        profile_terms_dir=cfg.profile_terms_dir,
        custom_terms_file=cfg.custom_terms_file,
    )
    matches = match_terms(text, terms, limit=limit or cfg.glossary_max_terms)
    out = output or sys.stdout
    print(format_glossary_search(text, matches), file=out)
    return 0


def run_glossary_add(
    *,
    source: str,
    zh: str = "",
    variants: str = "",
    category: str = "general",
    priority: str = "medium",
    profiles: str = "",
    config: AppConfig | None = None,
    glossary_file: str | Path | None = None,
    output: TextIO | None = None,
) -> int:
    cfg = config or load_config()
    path = Path(glossary_file) if glossary_file else cfg.profile_terms_dir / "terms.yaml"
    term = term_mapping(
        source=source,
        zh=zh,
        variants=split_multi_value(variants),
        category=category,
        priority=priority,
        profiles=split_multi_value(profiles),
    )
    result = upsert_terms(path, [term])
    print(format_write_result("Glossary add", result), file=output or sys.stdout)
    return 0


def run_glossary_import(
    csv_file: str | Path,
    *,
    config: AppConfig | None = None,
    glossary_file: str | Path | None = None,
    output: TextIO | None = None,
) -> int:
    cfg = config or load_config()
    path = Path(glossary_file) if glossary_file else cfg.profile_terms_dir / "terms.yaml"
    imported = load_terms_from_csv(Path(csv_file))
    result = upsert_terms(path, imported)
    print(format_write_result("Glossary import", result), file=output or sys.stdout)
    return 0


def load_terms_from_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "source" not in {name.strip().lower() for name in reader.fieldnames}:
            raise ValueError("Glossary CSV must include a source column")
        terms = []
        for row in reader:
            term = term_mapping(
                source=_row_value(row, "source"),
                zh=_row_value(row, "zh", "target_zh", "chinese"),
                variants=split_multi_value(_row_value(row, "variants")),
                category=_row_value(row, "category") or "general",
                priority=_row_value(row, "priority") or "medium",
                profiles=split_multi_value(_row_value(row, "profiles")),
            )
            if term:
                terms.append(term)
    return terms


def upsert_terms(path: Path, incoming_terms: list[dict[str, Any]]) -> GlossaryWriteResult:
    existing_terms = load_terms_file(path)
    by_source = {normalise_term_text(str(term.get("source", ""))): index for index, term in enumerate(existing_terms)}
    added = 0
    updated = 0
    for incoming in incoming_terms:
        key = normalise_term_text(str(incoming.get("source", "")))
        if not key:
            continue
        if key in by_source:
            existing_terms[by_source[key]] = merge_term(existing_terms[by_source[key]], incoming)
            updated += 1
        else:
            by_source[key] = len(existing_terms)
            existing_terms.append(clean_term_mapping(incoming))
            added += 1

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(existing_terms, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    return GlossaryWriteResult(path=path, added=added, updated=updated, total=len(existing_terms))


def load_terms_file(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw_terms = payload.get("terms", payload) if isinstance(payload, dict) else payload
    if raw_terms is None:
        return []
    if not isinstance(raw_terms, list):
        raise ValueError(f"Structured glossary must be a list or terms object: {path}")
    return [clean_term_mapping(term) for term in raw_terms if isinstance(term, dict) and term.get("source")]


def merge_term(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = clean_term_mapping(existing)
    incoming_clean = clean_term_mapping(incoming)
    for key in ("zh", "category", "priority"):
        if incoming_clean.get(key):
            merged[key] = incoming_clean[key]
    merged["variants"] = unique_values(
        [*as_string_list(merged.get("variants")), *as_string_list(incoming_clean.get("variants"))]
    )
    merged["profiles"] = unique_values(
        [*as_string_list(merged.get("profiles")), *as_string_list(incoming_clean.get("profiles"))]
    )
    return remove_empty_optional_fields(merged)


def term_mapping(
    *,
    source: str,
    zh: str = "",
    variants: list[str] | tuple[str, ...] = (),
    category: str = "general",
    priority: str = "medium",
    profiles: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    cleaned_source = source.strip()
    if not cleaned_source:
        return {}
    return remove_empty_optional_fields(
        {
            "source": cleaned_source,
            "variants": unique_values(variants),
            "zh": zh.strip(),
            "category": category.strip() or "general",
            "priority": normalise_priority(priority),
            "profiles": unique_values(profiles),
        }
    )


def clean_term_mapping(term: dict[str, Any]) -> dict[str, Any]:
    return term_mapping(
        source=str(term.get("source", "")),
        zh=str(term.get("zh") or term.get("target_zh") or term.get("chinese") or ""),
        variants=as_string_list(term.get("variants")),
        category=str(term.get("category", "general")),
        priority=str(term.get("priority", "medium")),
        profiles=as_string_list(term.get("profiles")),
    )


def format_glossary_search(text: str, matches: list[Any]) -> str:
    lines = [f"Glossary search: {text}", ""]
    if not matches:
        lines.append("No matched terms.")
        return "\n".join(lines)
    for match in matches:
        term: GlossaryTerm = match.term
        target = f" => {term.zh}" if term.zh else ""
        profiles = f" profiles={','.join(term.profiles)}" if term.profiles else ""
        variants = f" variants={', '.join(term.variants)}" if term.variants else ""
        lines.append(
            f"- {term.source}{target} "
            f"[{term.category}/{term.priority}] score={match.score:0.1f}{profiles}{variants}"
        )
    return "\n".join(lines)


def format_write_result(label: str, result: GlossaryWriteResult) -> str:
    return (
        f"{label}: added={result.added}, updated={result.updated}, "
        f"total={result.total}\nPath: {result.path}"
    )


def split_multi_value(value: str | list[str] | tuple[str, ...]) -> list[str]:
    if isinstance(value, list | tuple):
        raw_items = [str(item) for item in value]
    else:
        raw_items = re.split(r"[|;,]", str(value))
    return unique_values(raw_items)


def as_string_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return split_multi_value(value)
    if isinstance(value, list | tuple):
        return unique_values(str(item) for item in value)
    return []


def unique_values(values: Any) -> list[str]:
    seen: set[str] = set()
    result = []
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        key = normalise_term_text(text)
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def normalise_priority(priority: str) -> str:
    lowered = priority.lower().strip()
    return lowered if lowered in VALID_PRIORITIES else "medium"


def remove_empty_optional_fields(term: dict[str, Any]) -> dict[str, Any]:
    cleaned = {key: value for key, value in term.items() if value not in ("", [], (), None)}
    cleaned.setdefault("category", "general")
    cleaned.setdefault("priority", "medium")
    return cleaned


def _row_value(row: dict[str, str], *keys: str) -> str:
    normalised = {
        key.strip().lower(): value
        for key, value in row.items()
        if key is not None and value is not None
    }
    for key in keys:
        value = normalised.get(key)
        if value:
            return value.strip()
    return ""
