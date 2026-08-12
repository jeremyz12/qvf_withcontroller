"""Download benchmark datasets into data/.

Sources (public research benchmarks):
- LongMemEval (Wu et al., ICLR 2025): Hugging Face dataset
  `xiaowu0162/longmemeval` — files longmemeval_oracle.json, longmemeval_s.json,
  longmemeval_m.json. Falls back to listing the repo to find actual filenames
  (the release also exists as a tar archive on some mirrors).
- LoCoMo (Maharana et al., ACL 2024): GitHub snap-research/locomo,
  data/locomo10.json.

Usage:
    python eval/download_data.py [--longmemeval] [--locomo]
    (no flags = download both)
"""

from __future__ import annotations

import argparse
import sys
import tarfile
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

LOCOMO_URL = (
    "https://raw.githubusercontent.com/snap-research/locomo/main/data/locomo10.json"
)

# The 2025-09 cleaned re-release is the officially recommended version
# ("further cleaned up the history sessions to prevent interference on answer
# correctness"). Fall back to the original repo if unavailable.
LME_REPO = "xiaowu0162/longmemeval-cleaned"
LME_REPO_FALLBACK = "xiaowu0162/longmemeval"


def download_locomo() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / "locomo10.json"
    if out.exists():
        print(f"[skip] {out} already exists")
        return
    print(f"[get ] {LOCOMO_URL}")
    r = requests.get(LOCOMO_URL, timeout=120)
    r.raise_for_status()
    out.write_bytes(r.content)
    print(f"[ok  ] {out} ({out.stat().st_size / 1e6:.1f} MB)")


def _extract_if_archive(path: Path) -> None:
    if path.suffix in (".gz", ".tgz") or path.name.endswith(".tar.gz"):
        print(f"[extr] {path}")
        with tarfile.open(path) as tf:
            tf.extractall(DATA_DIR)


def download_longmemeval() -> None:
    from huggingface_hub import hf_hub_download, list_repo_files

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    repo = LME_REPO
    try:
        repo_files = list_repo_files(repo, repo_type="dataset")
    except Exception:  # noqa: BLE001
        print(f"[warn] cannot list {repo}; falling back to {LME_REPO_FALLBACK}")
        repo = LME_REPO_FALLBACK
        try:
            repo_files = list_repo_files(repo, repo_type="dataset")
        except Exception as e:  # noqa: BLE001
            print(f"[err ] cannot list {repo}: {e}")
            return
    print(f"[info] files in {repo}: {repo_files}")

    wanted = [f for f in repo_files if any(t in f for t in ("oracle", "_s", "_m"))]
    if not wanted:
        wanted = repo_files
    for fname in wanted:
        target = DATA_DIR / Path(fname).name
        if target.exists():
            print(f"[skip] {target} already exists")
            continue
        # Skip the medium split by default (~2.7 GB); enable manually if needed.
        if "longmemeval_m" in fname:
            print(f"[skip] {fname} (medium split; enable manually if needed)")
            continue
        print(f"[get ] {repo}/{fname}")
        local = hf_hub_download(repo, fname, repo_type="dataset")
        target.write_bytes(Path(local).read_bytes())
        print(f"[ok  ] {target} ({target.stat().st_size / 1e6:.1f} MB)")
        _extract_if_archive(target)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--longmemeval", action="store_true")
    parser.add_argument("--locomo", action="store_true")
    args = parser.parse_args()
    do_all = not (args.longmemeval or args.locomo)
    if args.locomo or do_all:
        download_locomo()
    if args.longmemeval or do_all:
        download_longmemeval()
    return 0


if __name__ == "__main__":
    sys.exit(main())
