import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "analyze_plan.py"
EXAMPLES = ROOT / "examples"


class AnalyzerTests(unittest.TestCase):
    def cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], text=True,
                              encoding="utf-8", capture_output=True, cwd=ROOT)

    def report(self, *args):
        result = self.cli(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_distinguishes_cn_visibility_from_dn_scan(self):
        plans = self.report("analyze", "--plan", "cn=examples/q2-customer-index-cn.json",
                            "--plan", "dn=examples/q2-customer-index-dn0001.json")["plans"]
        self.assertIn({"code": "remote_plan_not_expanded", "path": "0"}, plans["cn"]["findings"])
        self.assertEqual(plans["cn"]["nodes"][0]["remote_targets"], ["dn0001", "dn0002"])
        self.assertEqual(plans["dn"]["nodes"][0]["removed_by_filter_per_loop"], 25)
        self.assertEqual(plans["dn"]["nodes"][1]["index"], "idx_customer")

    def test_compares_real_nodes_by_label_and_uses_root_buffer_counts(self):
        report = self.report(
            "compare",
            "--before", "dn1=examples/q2-customer-index-dn0001.json",
            "--before", "dn2=examples/q2-customer-index-dn0002.json",
            "--after", "dn2=examples/q2-composite-index-dn0002.json",
            "--after", "dn1=examples/q2-composite-index-dn0001.json",
        )["comparisons"]
        self.assertEqual(report["dn1"]["root_delta"]["shared_hit_blocks"], -25)
        self.assertEqual(report["dn2"]["root_delta"]["shared_hit_blocks"], -20)
        self.assertEqual(report["dn1"]["root_delta"]["actual_rows_per_loop"], 0)
        self.assertIn("order_date", report["dn1"]["after"]["nodes"][0]["index_cond"])
        self.assertNotIn("removed_by_filter_per_loop", report["dn1"]["root_delta"])

    def test_seq_scan_is_listed_inside_a_real_aggregate_plan(self):
        plan = self.report("analyze", "--plan", "dn=examples/q3-status-index-dn0001.json")["plans"]["dn"]
        paths = {node["path"]: node for node in plan["nodes"]}
        scans = [paths[item["path"]] for item in plan["findings"] if item["code"] == "sequential_scan"]
        self.assertEqual(len(scans), 1)
        self.assertIn("status", scans[0]["filter"])
        self.assertGreater(scans[0]["actual_loops"], 0)

    def test_estimate_only_and_zero_loops_keep_distinct_meanings(self):
        with tempfile.TemporaryDirectory() as directory:
            estimate = Path(directory) / "sample plan=estimate.json"
            after = Path(directory) / "actual.json"
            estimate.write_text('{"Plan":{"Node Type":"Seq Scan","Plan Rows":4}}', encoding="utf-8-sig")
            after.write_text('[{"Plan":{"Node Type":"Seq Scan","Plan Rows":4,"Actual Loops":0,"Actual Rows":0}}]', encoding="utf-8")
            pair = self.report("compare", "--before", f"dn={estimate}", "--after", f"dn={after}")["comparisons"]["dn"]
            self.assertFalse(pair["before"]["analyzed"])
            self.assertNotIn("actual_rows_per_loop", pair["before"]["nodes"][0])
            self.assertTrue(pair["after"]["analyzed"])
            self.assertEqual(pair["after"]["findings"], [])
            self.assertEqual(pair["root_delta"], {"estimated_rows": 0})

    def test_rejects_text_multiple_statements_and_invalid_tree(self):
        invalid = [
            "Seq Scan on orders",
            '[{"Plan":{"Node Type":"Result"}},{"Plan":{"Node Type":"Result"}}]',
            '{"Plan":{"Node Type":"Gather","Plans":[null]}}',
            '{"Plan":{"Node Type":"Result","Actual Rows":1e999}}',
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            for sample in invalid:
                with self.subTest(sample=sample):
                    path.write_text(sample, encoding="utf-8")
                    result = self.cli("analyze", "--plan", f"dn={path}")
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, "")
                    self.assertIn("error: dn:", result.stderr)

    def test_rejects_duplicate_and_unmatched_labels(self):
        fixture = EXAMPLES / "q2-customer-index-dn0001.json"
        duplicate = self.cli("analyze", "--plan", f"dn={fixture}", "--plan", f"dn={fixture}")
        mismatch = self.cli("compare", "--before", f"dn1={fixture}", "--after", f"dn2={fixture}")
        self.assertEqual(duplicate.returncode, 2)
        self.assertIn("duplicate label", duplicate.stderr)
        self.assertEqual(mismatch.returncode, 2)
        self.assertIn("same labels", mismatch.stderr)


if __name__ == "__main__":
    unittest.main()
