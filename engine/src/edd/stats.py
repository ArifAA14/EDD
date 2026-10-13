"""Small, dependency-free statistics: Wilson intervals and a seeded paired bootstrap."""
from __future__ import annotations

import random
from math import sqrt


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """95% Wilson score interval for k successes in n trials."""
    if n <= 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def paired_bootstrap(parent: list[float], new: list[float], iters: int = 4000, seed: int = 1337,
                     alpha: float = 0.05) -> tuple[float, float, float] | None:
    """Mean paired difference (new - parent) with a bootstrap interval, resampling cases."""
    if not parent or len(parent) != len(new):
        return None
    diffs = [b - a for a, b in zip(parent, new)]
    n = len(diffs)
    delta = sum(diffs) / n
    rng = random.Random(seed)
    samples = sorted(sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    lo = samples[int(alpha / 2 * iters)]
    hi = samples[max(int((1 - alpha / 2) * iters) - 1, 0)]
    return delta, lo, hi


def classify_delta(lo: float, hi: float) -> str:
    if lo > 0:
        return "improved"
    if hi < 0:
        return "regressed"
    return "within_noise"
