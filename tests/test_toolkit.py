import argparse
import csv
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "yandex-direct" / "scripts" / "yandex_direct_toolkit.py"
SPEC = importlib.util.spec_from_file_location("yandex_direct_toolkit", SCRIPT)
toolkit = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(toolkit)


def valid_package():
    return {
        "segments": [
            {
                "segment_id": "seg-1",
                "intent": "buy",
                "ad_group_id": 123,
                "responsive_ad": {
                    "titles": [
                        "Теплицы из поликарбоната в Москве",
                        "Доставка теплицы за 1 день",
                        "Каркас из оцинкованной стали",
                        "Монтаж по договору",
                        "Смета до начала работ",
                    ],
                    "texts": [
                        "Подберем теплицу под участок. Цена на сайте. Получить смету",
                        "Каркас, доставка и монтаж. Условия на странице. Рассчитать стоимость",
                        "Ответим по наличию в Москве. Выберите размер и оставьте заявку",
                    ],
                    "href": "https://example.ru/teplicy",
                    "display_url_path": "teplicy",
                },
                "landing": {"h1": "Теплицы из поликарбоната с монтажом в Москве"},
                "claim_refs": ["https://example.ru/teplicy#terms"],
            }
        ]
    }


class ValidationTests(unittest.TestCase):
    def test_valid_package(self):
        report = toolkit.validation_report(valid_package())
        self.assertTrue(report["valid"], report)

    def test_title_limit_blocks_payload(self):
        data = valid_package()
        data["segments"][0]["responsive_ad"]["titles"][0] = "А" * 57
        report = toolkit.validation_report(data)
        self.assertFalse(report["valid"])
        self.assertIn("title_too_long", {item["code"] for item in report["issues"]})

    def test_unproven_superlative_is_error(self):
        data = valid_package()
        data["segments"][0]["claim_refs"] = []
        data["segments"][0]["responsive_ad"]["titles"][1] = "Лучшие теплицы Москвы"
        report = toolkit.validation_report(data)
        self.assertFalse(report["valid"])
        self.assertIn("unproven_superlative", {item["code"] for item in report["issues"]})

    def test_responsive_payload_shape(self):
        payload = toolkit.build_responsive_payload(valid_package())
        ad = payload["params"]["Ads"][0]
        self.assertEqual(payload["method"], "add")
        self.assertEqual(ad["AdGroupId"], 123)
        self.assertIn("ResponsiveAd", ad)
        self.assertNotIn("TextAd", ad)
        self.assertEqual(len(ad["ResponsiveAd"]["Titles"]), 5)

    def test_message_overlap(self):
        ratio = toolkit.message_overlap(
            "Теплицы из поликарбоната в Москве",
            "Теплицы из поликарбоната с монтажом в Москве",
        )
        self.assertGreaterEqual(ratio, 0.75)


class SafetyTests(unittest.TestCase):
    def test_wordstat_is_preview_by_default(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "wordstat-top", "--phrase", "теплица"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"execute": false', result.stdout)
        self.assertIn("WORDSTAT:1", result.stdout)

    def test_live_mutation_requires_exact_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = Path(directory) / "payload.json"
            payload.write_text(json.dumps({"method": "add", "params": {"Ads": []}}), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "direct-request",
                    "ads",
                    str(payload),
                    "--environment",
                    "production",
                    "--execute",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("LIVE:ads:add", result.stdout + result.stderr)


class DataTests(unittest.TestCase):
    def test_semantic_normalizer_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.csv"
            output = Path(directory) / "output.csv"
            source.write_text(
                "phrase;count\nкупить теплицу;10\nКупить теплицу;12\nкак сделать теплицу;20\n",
                encoding="utf-8",
            )
            toolkit.command_normalize_semantics(
                argparse.Namespace(
                    input=str(source),
                    output=str(output),
                    delimiter=";",
                    output_delimiter=";",
                    offer_term=["теплица"],
                    exclude_term=None,
                )
            )
            with output.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle, delimiter=";"))
        self.assertEqual(len(rows), 2)
        deduplicated = next(row for row in rows if row["normalized_phrase"] == "купить теплицу")
        self.assertEqual(deduplicated["duplicate_count"], "2")
        self.assertEqual(deduplicated["volume"], "12.0")

    def test_intent_hint(self):
        self.assertEqual(toolkit.intent_hint("купить теплицу")[0], "transactional")
        self.assertEqual(toolkit.intent_hint("как сделать теплицу своими руками")[0], "informational")


if __name__ == "__main__":
    unittest.main()
