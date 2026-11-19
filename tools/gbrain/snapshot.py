"""Transfer a repeatable-read snapshot through psql (local or SSH stdin)."""
import argparse
from collections import defaultdict
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return sha256(canonical(value).encode()).hexdigest()


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, encoding="utf-8", delete=False) as tmp:
        try:
            tmp.write(text)
            tmp.flush()
            os.fsync(tmp.fileno())
        except BaseException:
            os.unlink(tmp.name)
            raise
    os.replace(tmp.name, path)


def read_scope(project, batch, target, command):
    arguments = {"project": project, "batch": batch, "target": target}
    if not all(re.fullmatch(r"[A-Za-z0-9_-]{1,160}", v) for v in arguments.values()):
        raise ValueError("invalid scope identifier")
    sql = "".join(f"\\set {k} {v}\n" for k, v in arguments.items())
    sql += Path(__file__).with_name("facts.sql").read_text()
    rows = defaultdict(lambda: defaultdict(list))
    # On a failed transaction discard the entire stream, including rows emitted before COMMIT.
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stream:
        subprocess.run(command, input=sql, stdout=stream, text=True, check=True)
        stream.seek(0)
        for line in stream:
            family, sku, row = json.loads(line)
            rows[sku][family].append(row)
    if target not in rows or not rows[target].get("sku"):
        raise ValueError("target has no clean SKU and matching parameter snapshot in the requested scope")
    for sku, buckets in rows.items():
        if len(buckets["parameter"]) != 1 or len(buckets.get("market", [])) > 1:
            raise ValueError(f"{sku}: ambiguous source snapshot")
        for records in buckets.values():
            records.sort(key=canonical)
        profiles = buckets.get("comment_profile", [])
        if profiles and (len(profiles) != 1 or profiles[0]["fact_atom_count"] != len(buckets.get("comment", []))):
            raise ValueError(f"{sku}: incomplete comment batch")
    return dict(rows)


def read_definitions():
    from dataclasses import asdict
    from app.services.core3_real_data.m03b_param_profile_service import tv_param_taxonomy_v0_1
    from app.services.core3_real_data.m04c_claim_fact_profile_service import tv_claim_taxonomy_v0_1
    from app.services.core3_real_data.m05c_comment_fact_profile_service import tv_comment_fact_taxonomy_v0_1
    from app.services.core3_real_data.m09c_user_task_service import tv_user_task_taxonomy_v0_1
    from app.services.core3_real_data.m10c_target_group_service import tv_target_group_taxonomy_v0_1
    from app.services.core3_real_data.m11c_value_battlefield_service import tv_value_battlefield_taxonomy_v0_2
    return {kind: asdict(loader()) for kind, loader in {
        "parameter": tv_param_taxonomy_v0_1, "claim": tv_claim_taxonomy_v0_1,
        "comment-topic": tv_comment_fact_taxonomy_v0_1, "user-task": tv_user_task_taxonomy_v0_1,
        "target-group": tv_target_group_taxonomy_v0_1, "value-battlefield": tv_value_battlefield_taxonomy_v0_2,
    }.items()}


def persist(root, project, batch, target, records, definitions):
    hashes = {sku: digest(row) for sku, row in records.items()}
    scope = {"project_id": project, "category_code": "TV", "batch_id": batch, "target": target}
    manifest = {**scope, "records": hashes, "definitions": digest(definitions), "format": 1}
    snapshot_id = digest(manifest)
    directory = Path(root) / snapshot_id
    for sku, data in records.items():
        atomic_write(directory / f"{sku}.json", canonical(data))
    atomic_write(directory / "definitions.json", canonical(definitions))
    atomic_write(directory / "manifest.json", canonical(manifest))
    return directory


def changes(previous, current):
    return {name: sorted(sku for sku in set(previous) | set(current) if predicate(sku))
            for name, predicate in {
                "added": lambda s: s not in previous, "withdrawn": lambda s: s not in current,
                "revised": lambda s: s in previous and s in current and previous[s] != current[s],
            }.items()}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for field in ("project", "batch", "target", "out"):
        p.add_argument("--" + field, required=True)
    p.add_argument("command", nargs=argparse.REMAINDER, help="after --, psql -XqAt or SSH command running it")
    a = p.parse_args()
    cmd = a.command[1:] if a.command[:1] == ["--"] else a.command
    records = read_scope(a.project, a.batch, a.target, cmd or ["psql", "-XqAt"])
    print(persist(a.out, a.project, a.batch, a.target, records, read_definitions()))
