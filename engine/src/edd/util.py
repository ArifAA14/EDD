"""Small shared helpers: hashing, time, frontmatter, git."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import subprocess
from pathlib import Path

import yaml


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def hash_obj(obj) -> str:
    return sha256_text(canonical_json(obj))


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(ts: dt.datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def make_report_id(ts: dt.datetime, token: str) -> str:
    return ts.strftime("%Y%m%dT%H%M%SZ") + "-" + token


_FM = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?(.*)\Z", re.S)


def split_frontmatter(text: str) -> tuple[dict, str]:
    m = _FM.match(text)
    if not m:
        return {}, text
    data = yaml.safe_load(m.group(1)) or {}
    if not isinstance(data, dict):
        data = {}
    return data, m.group(2)


def join_frontmatter(fm: dict, body: str) -> str:
    dumped = yaml.safe_dump(
        fm, sort_keys=False, allow_unicode=True, width=100000, default_flow_style=None
    ).rstrip()
    return "---\n" + dumped + "\n---\n" + body


def git_info(root: Path) -> tuple[str | None, bool | None]:
    """Return (short sha, dirty). Result files under evals/*/results are ignored for dirtiness."""

    def run(*args: str) -> tuple[int, str]:
        try:
            r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            return 1, ""
        return r.returncode, r.stdout.strip()

    rc, sha = run("rev-parse", "--short", "HEAD")
    if rc != 0:
        return None, None
    rc2, status = run("status", "--porcelain", "--", ".", ":(exclude,glob)evals/**/results/**")
    return sha, (bool(status) if rc2 == 0 else None)


def git_diff_stat(root: Path, old_sha: str, limit: int = 15) -> list[str]:
    try:
        r = subprocess.run(
            ["git", "diff", "--stat", old_sha, "HEAD", "--", ".", ":(exclude,glob)evals/**/results/**"],
            cwd=root, capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if r.returncode != 0:
        return []
    lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    return lines[:limit] + (["..."] if len(lines) > limit else [])


def hash_files(root: Path, patterns: list[str]) -> tuple[str | None, list[str]]:
    """Hash the contents (and relative paths) of all files matching the globs."""
    files: list[Path] = []
    for pattern in patterns:
        files.extend(p for p in root.glob(pattern) if p.is_file())
    files = sorted(set(files))
    if not files:
        return None, []
    h = hashlib.sha256()
    names = []
    for p in files:
        rel = p.relative_to(root).as_posix()
        names.append(rel)
        h.update(rel.encode() + b"\0" + p.read_bytes() + b"\0")
    return "sha256:" + h.hexdigest(), names


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)
