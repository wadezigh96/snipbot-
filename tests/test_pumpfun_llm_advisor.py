import unittest

from agent.pumpfun.llm_advisor import parse_advisor_json


class LLMAdvisorTests(unittest.TestCase):
    def test_accepts_watch_decision(self):
        result = parse_advisor_json('{"decision":"WATCH","score":60,"reason":"More data needed"}', model="test")
        self.assertEqual(result.status, "WATCH")
        self.assertEqual(result.score, 60)

    def test_accepts_reject_decision(self):
        result = parse_advisor_json('{"decision":"REJECT","score":90,"reason":"Risk flags"}')
        self.assertEqual(result.status, "REJECT")

    def test_rejects_buy_action(self):
        result = parse_advisor_json('{"decision":"BUY","score":99,"reason":"moon"}')
        self.assertEqual(result.status, "WATCH_ONLY")
        self.assertEqual(result.reason, "llm_decision_out_of_schema")

    def test_rejects_non_string_decision_without_crashing(self):
        result = parse_advisor_json('{"decision":[],"score":10,"reason":"x"}')
        self.assertEqual(result.status, "WATCH_ONLY")

    def test_rejects_invalid_score(self):
        result = parse_advisor_json('{"decision":"WATCH","score":101,"reason":"x"}')
        self.assertEqual(result.status, "WATCH_ONLY")
        self.assertEqual(result.reason, "llm_score_out_of_range")

    def test_rejects_boolean_score(self):
        result = parse_advisor_json('{"decision":"WATCH","score":true,"reason":"x"}')
        self.assertEqual(result.status, "WATCH_ONLY")

    def test_rejects_non_json(self):
        result = parse_advisor_json("BUY NOW")
        self.assertEqual(result.status, "WATCH_ONLY")

    def test_rejects_missing_reason(self):
        result = parse_advisor_json('{"decision":"WATCH","score":10,"reason":""}')
        self.assertEqual(result.status, "WATCH_ONLY")


if __name__ == "__main__":
    unittest.main()
