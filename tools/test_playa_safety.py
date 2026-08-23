"""Regression checks for safety-critical instructions shipped to playa kiosks."""

import json
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


class DeepPlayaSafetyTest(unittest.TestCase):
    def setUp(self):
        cards = json.loads((REPO / "data" / "cards.json").read_text(encoding="utf-8"))
        self.card = next(card for card in cards["cards"] if card["id"] == "roots-08")
        self.playa = json.loads(
            (REPO / "data" / "playa_2026.json").read_text(encoding="utf-8")
        )
        self.web = json.loads((REPO / "cards.web.json").read_text(encoding="utf-8"))

    def test_deep_playa_dare_keeps_seeker_equipped_and_accompanied(self):
        dare = self.card["turtle_dare"].lower()
        for unsafe in ("walk alone", "no phone", "not sure of the way back"):
            self.assertNotIn(unsafe, dare)
        for safeguard in ("companion", "water", "lights", "navigation", "return"):
            self.assertIn(safeguard, dare)

    def test_directions_repeat_the_safeguards(self):
        directions = self.playa["hooks"]["deep-playa"]["directions"].lower()
        for safeguard in ("companion", "water", "lights", "navigation"):
            self.assertIn(safeguard, directions)

    def test_static_deck_matches_runtime_source(self):
        web_card = next(card for card in self.web["cards"] if card["id"] == "roots-08")
        self.assertEqual(web_card["turtle_dare"], self.card["turtle_dare"])
        self.assertEqual(
            web_card["location"]["directions"],
            self.playa["hooks"]["deep-playa"]["directions"],
        )


if __name__ == "__main__":
    unittest.main()
