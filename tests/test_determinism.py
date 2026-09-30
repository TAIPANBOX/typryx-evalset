import hashlib
import os
import subprocess
import sys
import unittest

from gen import build as B
from tests.helpers import DATA, ROOT, built, manifest


class Determinism(unittest.TestCase):
    def test_same_seed_same_bytes(self):
        a = B.build(7)
        b = B.build(7)
        self.assertEqual(a["blobs"], b["blobs"])
        self.assertEqual(a["manifest"], b["manifest"])

    def test_same_bytes_under_different_hash_seeds(self):
        code = "import hashlib; from gen import build; print(hashlib.sha256(build.build(7)['blobs']['all']).hexdigest())"
        outs = []
        for hs in ("1", "4242"):
            env = dict(os.environ, PYTHONHASHSEED=hs)
            outs.append(subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, check=True).stdout.strip())
        self.assertEqual(outs[0], outs[1])
        self.assertEqual(outs[0], hashlib.sha256(B.build(7)["blobs"]["all"]).hexdigest())

    def test_a_different_seed_changes_the_data(self):
        self.assertNotEqual(B.build(7)["blobs"]["all"], B.build(8)["blobs"]["all"])

    def test_data_on_disk_is_what_the_generator_writes(self):
        m = manifest()
        fresh = built(m["seed"])
        for name in ("all", "train", "dev", "test"):
            on_disk = (DATA / f"{name}.jsonl").read_bytes()
            self.assertEqual(on_disk, fresh["blobs"][name], f"data/{name}.jsonl is stale or edited")
        # the manifest agrees with the files on disk, apart from the commit it was built at
        expect = dict(fresh["manifest"])
        expect["generator_commit"] = m["generator_commit"]
        self.assertEqual(m, expect)


if __name__ == "__main__":
    unittest.main()
