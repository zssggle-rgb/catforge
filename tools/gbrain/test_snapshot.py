import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from graph import Graph, blob, restore, verified
from position_graph import add_goal, matched_comments
from snapshot import changes, digest, persist, read_scope


class FactsTest(unittest.TestCase):
    def test_shared_source_is_not_a_scoring_match(self):
        rows = [("display", {"source": "one", "topic": "picture"}), ("sound", {"source": "one", "topic": "audio"})]
        def matcher(atoms, topic):
            return {"fact_count": sum(a["topic"] == topic for a in atoms)}
        self.assertEqual(matched_comments(rows, "picture", matcher, 1), ["display"])
        with self.assertRaises(ValueError):
            matched_comments(rows, "picture", matcher, 2)

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
            self.assertEqual(graph.edges[fact]["observed_for"], {a})
            with self.assertRaises(ValueError):
                graph.node("sku", {"sku_code": "A", "project_id": "other"}, {})
            with self.assertRaises(ValueError):
                graph.node("sku", {"sku_code": "A"}, {"category_code": "AC"})
            with self.assertRaises(ValueError):
                graph.edge(fact, "based_on", "catforge/foreign/missing")
            old = graph.node("input-snapshot", {"content_hash": "old"}, {})
            with self.assertRaises(ValueError):
                graph.edge(fact, "uses_snapshot", old)
            current = graph.node("input-snapshot", {"content_hash": "s"}, {})
            graph.edge(fact, "uses_snapshot", current)

    def test_goal_preserves_profile_and_versions(self):
        with TemporaryDirectory() as tmp:
            graph = Graph(Path(tmp), {"project_id": "p", "category_code": "TV"})
            sku = graph.node("sku", {"sku_code": "A"}, {})
            battlefield = graph.node("value-battlefield", {"code": "film", "taxonomy_version": "v1"}, {})
            key = {"sku_code": "A", "kind": "value-battlefield", "rule_version": "m1", "snapshot_id": "s"}
            profile = graph.node("sku-profile", key, {"score": 0.7})
            original = dict(graph.nodes)
            goal = dict(sku_code="A", goal_id="g", revision="1", battlefield_code="film", taxonomy_version="v1",
                        valid_from="2026-11-01", valid_until="2026-12-01", owner="PM", source_ref="sample",
                        objective="Assess campaign fit")
            node = add_goal(graph, goal, sku, {"film": battlefield})
            other = add_goal(graph, {**goal, "revision": "2"}, sku, {"film": battlefield})
            self.assertNotEqual(node, other)
            self.assertEqual(graph.nodes[profile], original[profile])
            self.assertEqual(graph.edges[node]["focuses_on"], {battlefield})
            with self.assertRaises(ValueError):
                add_goal(graph, {**goal, "valid_until": "2025-01-01"}, sku, {"film": battlefield})
