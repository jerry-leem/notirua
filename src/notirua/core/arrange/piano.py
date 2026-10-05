"""Piano hand split around middle C with hysteresis (SPEC 6.5). Pure functions only."""

from __future__ import annotations

from collections.abc import Sequence
from fractions import Fraction

from notirua.core.model import ScoreNote

MIDDLE_C = 60
MAX_HAND_SPAN = 16  # a major tenth


def split_hands(
    notes: Sequence[ScoreNote], hysteresis: int = 4, max_span: int = MAX_HAND_SPAN
) -> tuple[list[ScoreNote], list[ScoreNote]]:
    """Return ``(right, left)``.

    Each onset group is split at the index whose split pitch stays close to the
    previous split (hysteresis) while keeping each hand within ``max_span``.
    """
    groups: dict[Fraction, list[ScoreNote]] = {}
    for n in notes:
        groups.setdefault(n.onset, []).append(n)
    right: list[ScoreNote] = []
    left: list[ScoreNote] = []
    split = float(MIDDLE_C)
    for onset in sorted(groups):
        chord = sorted(groups[onset], key=lambda n: n.pitch)
        best_k = 0
        best_cost = float("inf")
        for k in range(len(chord) + 1):
            lh, rh = chord[:k], chord[k:]
            cost = 0.0
            for hand in (lh, rh):
                if hand:
                    span = hand[-1].pitch - hand[0].pitch
                    if span > max_span:
                        cost += 100 + 10 * (span - max_span)
            # Notes on the "wrong" side of the running split cost more the farther they are.
            cost += sum(max(0.0, (split - hysteresis) - n.pitch) for n in rh)
            cost += sum(max(0.0, n.pitch - (split + hysteresis)) for n in lh)
            # Prefer giving each hand a share of a wide chord.
            if lh and rh:
                cost -= 0.5
            if cost < best_cost:
                best_cost, best_k = cost, k
        lh, rh = chord[:best_k], chord[best_k:]
        left.extend(lh)
        right.extend(rh)
        if lh and rh:
            boundary = (lh[-1].pitch + rh[0].pitch) / 2
            split = 0.7 * split + 0.3 * boundary
        elif rh:
            split = min(split, 0.85 * split + 0.15 * (rh[0].pitch - 2))
        elif lh:
            split = max(split, 0.85 * split + 0.15 * (lh[-1].pitch + 2))
        split = min(max(split, MIDDLE_C - 12), MIDDLE_C + 12)
    return right, left
