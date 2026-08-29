from __future__ import annotations

import io

import yaml

from config import AppConfig
from glossary_manager import (
    load_terms_from_csv,
    run_glossary_add,
    run_glossary_import,
    run_glossary_search,
    split_multi_value,
    upsert_terms,
)


def test_split_multi_value_accepts_common_separators() -> None:
    assert split_multi_value("Kunden Tabelle, customer table | client table; Kunden Tabelle") == [
        "Kunden Tabelle",
        "customer table",
        "client table",
    ]


def test_upsert_terms_adds_and_updates_existing_source(tmp_path) -> None:
    path = tmp_path / "terms.yaml"
    path.write_text(
        """
- source: Kundentabelle
  variants: ["Kunden Tabelle"]
  zh: Kunden-Tabelle-alt
  category: data
  priority: medium
  profiles: ["de"]
""",
        encoding="utf-8",
    )

    result = upsert_terms(
        path,
        [
            {
                "source": "Kundentabelle",
                "variants": ["customer table"],
                "zh": "客户表",
                "category": "data",
                "priority": "high",
                "profiles": ["de-en"],
            },
            {
                "source": "Rollout",
                "variants": ["deployment"],
                "zh": "发布",
                "category": "release",
                "priority": "high",
            },
        ],
    )

    terms = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert result.added == 1
    assert result.updated == 1
    assert terms[0]["zh"] == "客户表"
    assert terms[0]["variants"] == ["Kunden Tabelle", "customer table"]
    assert terms[0]["profiles"] == ["de", "de-en"]
    assert terms[1]["source"] == "Rollout"


def test_load_terms_from_csv_supports_bom_and_alias_columns(tmp_path) -> None:
    path = tmp_path / "terms.csv"
    path.write_text(
        "Source,target_zh,variants,category,priority,profiles\n"
        "Datenqualität,数据质量,Datenqualitaet|data quality,data,high,de;de-en\n",
        encoding="utf-8-sig",
    )

    terms = load_terms_from_csv(path)

    assert terms == [
        {
            "source": "Datenqualität",
            "variants": ["Datenqualitaet", "data quality"],
            "zh": "数据质量",
            "category": "data",
            "priority": "high",
            "profiles": ["de", "de-en"],
        }
    ]


def test_run_glossary_add_writes_default_yaml_shape(tmp_path) -> None:
    output = io.StringIO()
    config = AppConfig(profile_terms_dir=tmp_path / "profiles")

    code = run_glossary_add(
        source="Freigabe",
        zh="批准",
        variants="approval,sign-off",
        category="process",
        priority="medium",
        profiles="de,de-en",
        config=config,
        output=output,
    )

    terms = yaml.safe_load((tmp_path / "profiles" / "terms.yaml").read_text(encoding="utf-8"))

    assert code == 0
    assert terms[0]["source"] == "Freigabe"
    assert "added=1" in output.getvalue()


def test_run_glossary_import_merges_csv_terms(tmp_path) -> None:
    csv_path = tmp_path / "terms.csv"
    csv_path.write_text(
        "source,zh,variants,category,priority\n"
        "Blocker,阻塞问题,blocking issue,risk,high\n",
        encoding="utf-8",
    )
    output = io.StringIO()

    code = run_glossary_import(
        csv_path,
        config=AppConfig(profile_terms_dir=tmp_path / "profiles"),
        output=output,
    )

    assert code == 0
    assert "total=1" in output.getvalue()


def test_run_glossary_search_prints_matches(tmp_path) -> None:
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    (profile_dir / "terms.yaml").write_text(
        """
- source: Kundentabelle
  variants: ["Kunden Tabelle"]
  zh: 客户表
  priority: high
""",
        encoding="utf-8",
    )
    output = io.StringIO()

    code = run_glossary_search(
        "Bitte pruefen Sie die Kunden Tabelle.",
        config=AppConfig(profile_terms_dir=profile_dir, custom_terms_file=profile_dir / "custom.txt"),
        output=output,
    )

    assert code == 0
    assert "Kundentabelle => 客户表" in output.getvalue()
