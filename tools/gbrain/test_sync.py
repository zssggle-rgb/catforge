import json
from pathlib import Path
import shutil
from subprocess import CalledProcessError, CompletedProcess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from graph import DEFINITIONS, verified
from snapshot import persist
from sync import sync


class SyncTest(unittest.TestCase):
    def test_change_failure_retry_and_replay(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            state, db = root / "state", root / "native"
            definitions = {k: {table: [], "taxonomy_version": "v1"} for k, (table, _) in DEFINITIONS.items()}

            def record(price):
                return {"parameter": [{"param_values_json": {"dimension_tier_profile": {"size": "large"}}}],
                        "market": [{"price_wavg": price}], "week": [{"period_week_index": 1, "sales_volume": price}]}

            first = persist(root, "p", "b", "A", {"A": record(1), "B": record(2)}, definitions)
            next_version = persist(root, "p", "b", "A", {"A": record(3), "C": record(1)}, definitions)
            fail = False

            def native(args, **kwargs):
                if args[1] == "import":
                    stage = Path(args[2])
                    shutil.copytree(stage, db, dirs_exist_ok=True)
                    output = {"total_files": len(list(stage.rglob("*.md"))), "errors": 0}
                elif args[1] == "extract":
                    output = {"skipped_missing_target": 0, "skipped_cross_source": 0}
                else:
                    if fail:
                        raise CalledProcessError(1, args)
                    dest, prefix = Path(args[args.index("--dir") + 1]), args[-1]
                    for path in db.rglob("*.md"):
                        rel = path.relative_to(db)
                        if str(rel).startswith(prefix):
                            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
                            shutil.copyfile(path, dest / rel)
                    output = {}
                return CompletedProcess(args, 0, stdout=json.dumps(output))

            with patch("sync.subprocess.run", side_effect=native):
                sync(first, state, db)
                before = next(state.glob("*.json")).read_bytes()
                self.assertTrue(sync(first, state, db)["reused"])
                fail = True
                with self.assertRaises(CalledProcessError):
                    sync(next_version, state, db)
                self.assertEqual(next(state.glob("*.json")).read_bytes(), before)
                self.assertEqual(verified(state / "readback" / first.name), verified(first))
                fail = False
                result = sync(next_version, state, db)
                self.assertEqual(result["changes"], {"added": ["C"], "revised": ["A"], "withdrawn": ["B"]})
                self.assertEqual(result["affected_cohorts"], ["common_active_week", "same_size_priced"])
                self.assertEqual(verified(state / "readback" / next_version.name), verified(next_version))
