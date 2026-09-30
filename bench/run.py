#!/usr/bin/env python3
"""Benchmark runner: sends every row of a split to a typryx and records the answers.

  python3 bench/run.py --typryx-url http://127.0.0.1:4320 --key-file PATH \
      --backend-name NAME --split test --out results/NAME.jsonl [--limit N] [--concurrency 1]

- The frozen test split is refused unless its sha256 equals data/MANIFEST.json.
- One POST {url}/v1/ask per row with header X-Typryx-Key (read from the key file,
  never printed, logged or written to the output).
- One JSONL line per row, written as it completes; a bad row (HTTP error, timeout,
  transport failure, unparsable body) is recorded as unanswered with reason
  "error:<kind>" and never aborts the run.
- Resumable: ids already present in --out are skipped.
- Network: only the typryx URL on the command line. Proxy environment variables
  are ignored on purpose.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import socket
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROGRESS_EVERY = 25

FIELDS = ["id", "family", "gold", "answer", "probabilities", "unanswered", "reason",
          "backend", "model", "latency_ms", "wall_ms", "cost_usd", "held_back_fields",
          "http_status"]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_frozen(data_dir: Path, split: str):
    """Return None when fine, else the refusal message. Only the test split is frozen."""
    if split != "test":
        return None
    manifest, path = data_dir / "MANIFEST.json", data_dir / "test.jsonl"
    if not manifest.is_file() or not path.is_file():
        return f"refusing to run: measured nothing ({manifest} or {path} is missing)"
    want = json.loads(manifest.read_text())["files"]["test.jsonl"]["sha256"]
    got = sha256_file(path)
    if got != want:
        return (f"refusing to run: {path} sha256 {got} differs from MANIFEST {want}; "
                "the test split is frozen")
    return None


def read_rows(path: Path, limit):
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return rows[:limit] if limit else rows


def read_done(out: Path) -> set:
    done = set()
    if out.is_file():
        for line in out.read_text().splitlines():
            try:
                done.add(json.loads(line)["id"])
            except (json.JSONDecodeError, KeyError, TypeError):
                pass  # a torn last line: that row is asked again
    return done


def _record(row: dict, backend_name: str, **extra) -> dict:
    rec = {k: None for k in FIELDS}
    rec.update(id=row["id"], family=row["family"], gold=row["gold"],
               backend=backend_name, unanswered=False, held_back_fields=0)
    rec.update(extra)
    return rec


def ask_one(url: str, key: str, row: dict, backend_name: str, timeout: float) -> dict:
    body = json.dumps({"template": row["template"], "state": row["state"]}).encode()
    req = urllib.request.Request(
        url + "/v1/ask", data=body, method="POST",
        headers={"Content-Type": "application/json", "X-Typryx-Key": key})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    t0 = time.perf_counter()
    status, raw, err = None, b"", None
    try:
        with opener.open(req, timeout=timeout) as resp:
            status, raw = resp.status, resp.read()
    except urllib.error.HTTPError as e:
        status, err = e.code, f"http_{e.code}"
    except (socket.timeout, TimeoutError):
        err = "timeout"
    except urllib.error.URLError as e:
        err = "timeout" if isinstance(e.reason, (socket.timeout, TimeoutError)) else "transport"
    except (OSError, http.client.HTTPException):
        err = "transport"
    wall_ms = round((time.perf_counter() - t0) * 1000, 3)

    def failed(kind):
        return _record(row, backend_name, unanswered=True, reason=f"error:{kind}",
                       http_status=status, wall_ms=wall_ms)

    if err:
        return failed(err)
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError
    except ValueError:
        return failed("bad_json")
    unanswered = bool(data.get("unanswered")) or data.get("answer") is None
    reason = data.get("reason")
    if unanswered and not reason:
        reason = "error:no_answer"
    return _record(
        row, backend_name, answer=data.get("answer"),
        probabilities=data.get("probabilities"), unanswered=unanswered, reason=reason,
        model=data.get("model"), latency_ms=data.get("latency_ms"), wall_ms=wall_ms,
        cost_usd=data.get("cost_usd"), held_back_fields=data.get("held_back_fields", 0),
        http_status=status, typryx_backend=data.get("backend"),
        template_version=data.get("template_version"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--typryx-url", required=True)
    ap.add_argument("--key-file", required=True)
    ap.add_argument("--backend-name", required=True)
    ap.add_argument("--split", default="test", choices=["train", "dev", "test"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--concurrency", type=int, default=1)
    ap.add_argument("--timeout", type=float, default=30.0, help="per request, seconds")
    ap.add_argument("--data-dir", default=str(ROOT / "data"))
    args = ap.parse_args(argv)

    data_dir = Path(args.data_dir)
    refusal = verify_frozen(data_dir, args.split)
    if refusal:
        print(f"run: {refusal}", file=sys.stderr)
        return 3
    try:
        key = Path(args.key_file).read_text().strip()
    except OSError as e:
        print(f"run: cannot read key file: {e.strerror}", file=sys.stderr)
        return 2
    if not key:
        print("run: key file is empty", file=sys.stderr)
        return 2
    split_path = data_dir / f"{args.split}.jsonl"
    if not split_path.is_file():
        print(f"run: measured nothing ({split_path} is missing)", file=sys.stderr)
        return 2
    url = args.typryx_url.rstrip("/")
    if not url.startswith(("http://", "https://")):
        print("run: --typryx-url must start with http:// or https://", file=sys.stderr)
        return 2

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = read_rows(split_path, args.limit)
    done = read_done(out)
    todo = [r for r in rows if r["id"] not in done]
    print(f"run: backend={args.backend_name} split={args.split} rows={len(rows)} "
          f"already_done={len(rows) - len(todo)} to_ask={len(todo)}", flush=True)

    t_start = time.perf_counter()
    finished = bad = 0
    with open(out, "a") as fh:
        if out.stat().st_size and out.read_bytes()[-1:] != b"\n":
            fh.write("\n")   # a torn last line: keep the next record on its own line

        def write(rec):
            nonlocal finished, bad
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
            fh.flush()
            finished += 1
            bad += 1 if rec["unanswered"] else 0
            if finished % PROGRESS_EVERY == 0:
                print(f"run: {finished}/{len(todo)} done, {bad} unanswered/failed, "
                      f"{time.perf_counter() - t_start:.0f}s", flush=True)

        if args.concurrency <= 1:
            for row in todo:
                write(ask_one(url, key, row, args.backend_name, args.timeout))
        else:
            with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                futs = [pool.submit(ask_one, url, key, r, args.backend_name, args.timeout)
                        for r in todo]
                for fut in as_completed(futs):
                    write(fut.result())
    print(f"run: finished {finished}/{len(todo)} rows, {bad} unanswered/failed, "
          f"{time.perf_counter() - t_start:.0f}s -> {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
