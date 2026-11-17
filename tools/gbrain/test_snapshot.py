import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from graph import Graph, blob, restore, verified
from snapshot import changes, digest, persist, read_scope


class FactsTest(unittest.TestCase):
    def test_scope_and_changes(self):
        with self.assertRaises(ValueError):
            read_scope("'", "b", "s", [])
        self.assertEqual(changes({"A": "a", "B": "old"}, {"B": "new", "C": "c"}),
                         {"added": ["C"], "withdrawn": ["A"], "revised": ["B"]})
        self.assertEqual(changes({"A": 1}, {"A": 1}), {"added": [], "revised": [], "withdrawn": []})

    def test_graph_roundtrip_and_corruption(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = {"TV1": {"parameter": [{"present": False, "unknown": None}]}}
            db = persist(root / "db", "p", "b", "TV1", records, {})
            manifest, definitions, _ = verified(db)
            graph = Graph(root / "export", manifest)
            for name, value in [("manifest", manifest), ("definitions", definitions), *records.items()]:
                graph.node("input-snapshot", {"content_hash": digest(value)}, {"member": name, "payload": blob(value)})
            graph.save()
            copy = restore(root / "export", root / "readback", db.name)
            self.assertEqual(verified(copy), verified(db))
            (copy / "TV1.json").write_text("{}")
            with self.assertRaises(ValueError):
                verified(copy)

    def test_contract_cardinality(self):
        with TemporaryDirectory() as tmp:
            graph = Graph(Path(tmp), {"project_id": "p", "category_code": "TV"})
            a,b = [graph.node("sku", {"sku_code": x}, {}) for x in "AB"]
            fact = graph.node("sku-parameter", {"sku_code": "A", "code": "size", "snapshot_id": "s"}, {})
            graph.edge(fact, "observed_for", a)
            with self.assertRaises(ValueError):
                graph.edge(fact, "observed_for", b)
            with self.assertRaises(ValueError):
                graph.edge(a, "measures", b)
