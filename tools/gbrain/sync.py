"""Publish a verified, immutable native snapshot. Advance the scope pointer only after readback."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from graph import project, restore, verified
from snapshot import atomic_write, canonical, changes, digest


def sync(snapshot, state, brain_home):
    manifest, _, _ = verified(snapshot)
    state.mkdir(parents=True, exist_ok=True)
    scope = digest({k: manifest[k] for k in ("project_id", "category_code", "target")})
    env = {**os.environ, "GBRAIN_HOME": str(brain_home.resolve()), "GBRAIN_SCHEMA_PACK": "catforge-sku"}
    def native(*args):
        return subprocess.run(["gbrain", *map(str, args)], env=env, check=True, text=True, stdout=subprocess.PIPE).stdout
    with (state / (scope + ".lock")).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        pointer = state / (scope + ".json")
        previous = json.loads(pointer.read_text()) if pointer.exists() else {}
        with TemporaryDirectory(dir=state) as tmp:
            stage = Path(tmp) / "stage"
            count = project(snapshot, stage)
            receipt = json.loads(native("import", stage, "--no-embed", "--workers", "1", "--allow-noncanonical-root", "--fresh", "--json"))
            if receipt["errors"] or receipt["total_files"] != count:
                raise ValueError("native import did not cover the entire projection")
            links = json.loads(native("extract", "links", "--source", "db", "--source-id", "default", "--include-frontmatter", "--json"))
            exported = Path(tmp) / "export"
            native("export", "--source", "default", "--dir", exported, "--slug-prefix", "catforge/input-snapshot/")
            restored = restore(exported, state / "readback", snapshot.name)
        delta = changes(previous.get("records", {}), manifest["records"])
        report = {"snapshot": snapshot.name, "readback": str(restored), "pages": count, "import": receipt,
                  "links": links, "changes": delta, "definition_changed": previous.get("definitions") != manifest["definitions"]}
        atomic_write(state / "receipts" / (snapshot.name + ".json"), canonical(report))
        atomic_write(pointer, canonical({**manifest, "snapshot": snapshot.name}))
        return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("snapshot", "state", "brain_home"):
        p.add_argument(key, type=Path)
    a = p.parse_args()
    print(canonical(sync(a.snapshot, a.state, a.brain_home)))
