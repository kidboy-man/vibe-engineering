"""Load-robust complexity checks shared by the wikify tests.

A wall-clock limit tests the machine; these compare a run against the same
code on a smaller input, so a slow or busy CI box does not flip the verdict
but a quadratic regression (about 16x for 4x the input, versus 4x linear) does.
"""

import time

GROWTH = 4  # large input = GROWTH x small input
MAX_RATIO = 8.0  # linear is about 4x, quadratic about 16x
NOISE_FLOOR = 0.2  # seconds; below this a ratio says nothing


def assert_scales_linearly(case, make, fn, small, repeats=2, label=""):
    """Time ``fn(*make(n))`` at ``small`` and ``GROWTH * small``; best of ``repeats``.

    ``make`` runs outside the timed region, so fixtures may write and commit.
    """

    def best(n):
        args = make(n)
        times = []
        for _ in range(repeats):
            start = time.perf_counter()
            fn(*args)
            times.append(time.perf_counter() - start)
        return min(times)

    t_small, t_large = best(small), best(small * GROWTH)
    case.assertLessEqual(
        t_large,
        max(MAX_RATIO * t_small, NOISE_FLOOR),
        f"{label}: {t_small:.3f}s at {small} -> {t_large:.3f}s at {small * GROWTH}",
    )
