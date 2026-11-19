"""Publish a verified, immutable native snapshot. Advance the scope pointer only after readback."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from graph import page_slug, project, restore, verified
from snapshot import atomic_write, canonical, changes, digest


def sync(snapshot, state, brain_home):
    manifest, _, records = verified(snapshot)
    state.mkdir(parents=True, exist_ok=True)
    scope = digest({k: manifest[k] for k in ("project_id", "category_code", "target")})
    env = {**os.environ, "GBRAIN_HOME": str(brain_home.resolve()), "GBRAIN_SCHEMA_PACK": "catforge-sku"}
    def native(*args):
        return subprocess.run(["gbrain", *map(str, args)], env=env, check=True, text=True, stdout=subprocess.PIPE).stdout
    with (state / (scope + ".lock")).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        pointer = state / (scope + ".json")
        previous = json.loads(pointer.read_text()) if pointer.exists() else {}
        if previous.get("snapshot") == snapshot.name:
            restored = state / "readback" / snapshot.name
            report_path = state / "receipts" / (snapshot.name + ".json")
            if restored.is_dir() and report_path.is_file():
                slug = page_slug("input-snapshot", {**manifest, "content_hash": snapshot.name})
                with TemporaryDirectory(dir=state) as tmp:
                    native("export", "--source", "default", "--dir", tmp, "--slug-prefix", slug)
                    if (Path(tmp) / (slug + ".md")).exists():
                        try:
                            verified(restored)
                        except (FileNotFoundError, ValueError):
                            pass  # Rebuild the private readback from the frozen input.
                        else:
                            return {**json.loads(report_path.read_text()), "reused": True,
                                    "changes": changes(manifest["records"], manifest["records"]),
                                    "definition_changed": False, "affected_cohorts": []}
        with TemporaryDirectory(dir=state) as tmp:
            stage = Path(tmp) / "stage"
            graph = project(snapshot, stage, render=False)
            graph.save()
            count = len(graph.nodes)
            cohorts = {}
            for kind, key, attributes in graph.nodes.values():
                if kind == "market-cohort":
                    members = attributes["members"]
                    content = members
                    if key["purpose"] == "common_active_week":
                        content = {sku: [(row["period_week_index"], row.get("sales_volume"), row.get("sales_amount"))
                                         for row in records[sku].get("week", [])]
                                   for sku in sorted(set(members) | {manifest["target"]})}
                    cohorts[key["purpose"]] = digest(content)
            receipt = json.loads(native("import", stage, "--no-embed", "--workers", "1", "--allow-noncanonical-root", "--fresh", "--json"))
            if receipt["errors"] or receipt["total_files"] != count:
                raise ValueError("native import did not cover the entire projection")
            links = json.loads(native("extract", "links", "--source", "db", "--source-id", "default", "--include-frontmatter", "--json"))
            if links["skipped_missing_target"] or links["skipped_cross_source"]:
                raise ValueError("incomplete native links")
            exported = Path(tmp) / "export"
            native("export", "--source", "default", "--dir", exported, "--slug-prefix", "catforge/input-snapshot/")
            restored = restore(exported, state / "readback", snapshot.name)
        delta = changes(previous.get("records", {}), manifest["records"])
        report = {"snapshot": snapshot.name, "readback": str(restored), "pages": count, "import": receipt,
                  "links": links, "changes": delta, "definition_changed": previous.get("definitions") != manifest["definitions"],
                  "affected_cohorts": sorted(k for k in cohorts if previous.get("cohorts", {}).get(k) != cohorts[k])}
        atomic_write(state / "receipts" / (snapshot.name + ".json"), canonical(report))
        atomic_write(pointer, canonical({**manifest, "snapshot": snapshot.name, "cohorts": cohorts}))
        return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("snapshot", "state", "brain_home"):
        p.add_argument(key, type=Path)
    a = p.parse_args()
    print(canonical(sync(a.snapshot, a.state, a.brain_home)))
