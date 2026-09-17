"""Presentation acceptance tests; no live model or Telegram credentials."""

import copy
import importlib
import json
from pathlib import Path
import tempfile
import unittest

import fitz
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
PROJECT = {"offer": {"price_rub": 600000, "area_m2": 600, "plot_id": None}}


class ScriptedModel:
    """Only replace the paid network boundary; PDF work remains real."""

    def __init__(self, generations, reviews=()):
        self.generations = list(generations)
        self.reviews = list(reviews)
        self.feedback = []

    def json(self, system, prompt, schema, images=None, web=False):
        if images:
            for path in images:
                with Image.open(path) as rendered:
                    if rendered.width < 960 or rendered.height < 540:
                        raise AssertionError("Critic received an undersized preview")
            return copy.deepcopy(self.reviews.pop(0))
        self.feedback.append(prompt)
        return copy.deepcopy(self.generations.pop(0))


class PresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.service = importlib.import_module("skif_agents.presentations")
        except ModuleNotFoundError:
            cls.service = None

    def setUp(self):
        self.assertIsNotNone(self.service, "Presentation service is not implemented")
        self.example = json.loads((ROOT / "data/deck.example.json").read_text())
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)

    def generate(self, **kwargs):
        return self.service.generate_deck(
            "Презентация проекта СКИФ для первого знакомства",
            kwargs.pop("project", copy.deepcopy(PROJECT)), ASSETS, self.out, **kwargs
        )

    def test_offline_pdf_is_labeled_structural_demo_and_has_real_previews(self):
        result = self.generate()
        self.assertEqual(result["status"], "demo_structural_only")
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(len(result["previews"]), 6)
        with fitz.open(result["pdf"]) as deck:
            self.assertEqual(len(deck), 6)
            self.assertTrue(all(abs(p.rect.width / p.rect.height - 16 / 9) < .001 for p in deck))
            text = " ".join(" ".join(p.get_text() for p in deck).split())
        self.assertIn("600 000", text)
        self.assertIn("604", text)
        self.assertIn("строительство сейчас запрещено", text)
        self.assertIn("Доходность не гарантируется", text)
        self.assertIn("OpenStreetMap", text)
        report = json.loads(Path(result["report"]).read_text())
        self.assertFalse(report["ai_verified"])
        for preview in result["previews"]:
            with Image.open(preview) as image:
                self.assertEqual(image.size, (1440, 810))

    def test_bad_claim_then_visual_defect_are_repaired_within_three_attempts(self):
        invalid = copy.deepcopy(self.example)
        invalid["slides"][0]["body"].append("Разрешено строительство жилого дома.")
        repaired = copy.deepcopy(self.example)
        repaired["slides"][2]["photo_ids"] = ["electricity"]
        model = ScriptedModel(
            [invalid, self.example, repaired],
            [{"pass": False, "issues": ["Подпись фотографии слишком мелкая: оставьте один кадр на третьем слайде."]},
             {"pass": True, "issues": []}],
        )
        result = self.generate(model=model)
        self.assertEqual(result["status"], "needs_owner_review")
        self.assertEqual(result["attempts"], 3)
        report = json.loads(Path(result["report"]).read_text())
        self.assertEqual(len(report["history"]), 3)
        self.assertTrue(report["history"][0]["structural_issues"])
        self.assertFalse(report["history"][1]["critic"]["pass"])
        self.assertIn("Подпись фотографии", model.feedback[-1])
        with fitz.open(result["pdf"]) as deck:
            self.assertNotIn("Разрешено строительство", " ".join(p.get_text() for p in deck))
            self.assertNotIn("Существующие объекты.", deck[2].get_text())
            self.assertEqual(len(deck[2].get_images()), 1)

    def test_exhausted_attempts_never_expose_rejected_pdf_as_accepted(self):
        invalid = copy.deepcopy(self.example)
        invalid["dataPrice"]["price_rub"] = 60000
        result = self.generate(model=ScriptedModel([invalid] * 3), max_attempts=100)
        self.assertEqual(result["status"], "qa_failed")
        self.assertEqual(result["attempts"], 3)
        self.assertEqual(result["pdf"], "")
        self.assertEqual(result["previews"], [])
        self.assertTrue(Path(result["report"]).is_file())

    def test_malformed_critic_is_failure_not_approval(self):
        result = self.generate(
            model=ScriptedModel([self.example], [{"pass": "true", "issues": []}]),
            max_attempts=1,
        )
        self.assertEqual(result["status"], "qa_failed")
        self.assertEqual(result["pdf"], "")
        report = json.loads(Path(result["report"]).read_text())
        self.assertTrue(report["history"][0]["critic"]["issues"])

    def test_conflicting_offer_fails_before_generation(self):
        project = {"offer": {"price_rub": 60000, "area_m2": 600, "plot_id": None}}
        result = self.generate(project=project, model=ScriptedModel([]))
        self.assertEqual(result["status"], "qa_failed")
        self.assertEqual(result["attempts"], 0)
        self.assertEqual(result["pdf"], "")

    def test_input_limits_reject_zero_attempts(self):
        with self.assertRaises(ValueError):
            self.generate(max_attempts=0)

    def test_missing_offer_fails_closed_without_model_calls(self):
        result = self.generate(project={}, model=ScriptedModel([]))
        self.assertEqual(result["status"], "qa_failed")
        self.assertEqual(result["attempts"], 0)
        self.assertEqual(result["pdf"], "")

    def test_unsafe_spec_variants_are_rejected_before_rendering(self):
        edits = [
            lambda s: s.update(width_pt=100),
            lambda s: s["slides"][0].update(title="С" * 121),
            lambda s: s["slides"][0].update(photo_ids=["../private.jpeg"]),
            lambda s: s["slides"][0].update(body=["Гарантированный рост цены на 50%."]),
            lambda s: s["slides"][3]["body"].__setitem__(0, "60 000 ₽ за участок."),
            lambda s: s["slides"][4].update(body=["Вода привозная."]),
        ]
        for edit in edits:
            with self.subTest(edit=edit):
                spec = copy.deepcopy(self.example)
                edit(spec)
                self.assertTrue(self.service.validate_spec(spec, PROJECT, ASSETS))

    def test_missing_photo_is_a_reported_failure(self):
        with tempfile.TemporaryDirectory() as empty:
            result = self.service.generate_deck("СКИФ", PROJECT, Path(empty), self.out)
        self.assertEqual(result["status"], "qa_failed")
        self.assertEqual(result["pdf"], "")
        report = json.loads(Path(result["report"]).read_text())
        self.assertTrue(report["history"][0]["structural_issues"])


if __name__ == "__main__":
    unittest.main()
