from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from battlefield_analysis import reconciliation, sensitivity
from snapshot import digest
from value import check_parents, frozen, save


class BattlefieldAnalysisTest(unittest.TestCase):
    def test_secondary_perturbation_uses_all_eligible_dimensions(self):
        rows = [
            {"dimension_code": "picture", "allocation_role": "primary_value", "allocation_basis": "0.8", "relation_factor": "1"},
            {"dimension_code": "smart", "allocation_role": "secondary_value", "allocation_basis": "0.7", "relation_factor": "0.7"},
            {"dimension_code": "voice", "allocation_role": "observed", "allocation_basis": "0.4", "relation_factor": "0.45"},
        ]
        low, high = (sensitivity(rows, Decimal(v)) for v in ("0.6", "0.8"))
        self.assertGreater(low["weights"]["picture"], high["weights"]["picture"])
        self.assertEqual(low["unallocated_weight"], 0)
        self.assertEqual(sum(high["weights"].values()), 1)
        self.assertEqual(sensitivity([], Decimal("0.7"))["unallocated_weight"], 1)
        with self.assertRaises(ValueError):
            sensitivity(rows, Decimal("NaN"))

    def test_denominators_and_unknown_amount(self):
        markets = {"A": {"sales_volume_total": 10, "sales_amount_total": None},
                   "B": {"sales_volume_total": 5, "sales_amount_total": 100}}
        rows = [{"sku_code": "A", "dimension_type": "battlefield", "allocated_sales_volume": 10,
                 "allocated_sales_amount": 0}]
        totals = reconciliation(markets, markets, rows)
        self.assertEqual(totals["battlefield"]["volume"]["unallocated"], 5)
        self.assertEqual(totals["battlefield"]["volume"]["observed"], 15)
        self.assertEqual(totals["battlefield"]["amount"]["unknown_skus"], 1)
        self.assertEqual(totals["user_task"]["volume"]["unallocated"], 15)

    def test_parent_fingerprint_required(self):
        check_parents({"inputs": {"allocation": "a"}}, {"allocation": "a"})
        for inputs in ({}, {"allocation": "b"}):
            with self.assertRaises(ValueError):
                check_parents({"inputs": inputs}, {"allocation": "a"})

    def test_replay_after_method_update(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            old = save(directory, "allocation", {"snapshot_id": "s", "weight": "0.7"})
            new = save(directory, "allocation", {"snapshot_id": "s", "weight": "0.6"})
            self.assertEqual(frozen(directory, "allocation", "s"), new)
            self.assertEqual(frozen(directory, "allocation", "s", digest(old)), old)
            with self.assertRaises(ValueError):
                frozen(directory, "allocation", "other", digest(old))
