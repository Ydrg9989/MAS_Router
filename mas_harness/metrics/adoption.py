"""Whose answer did the judge take, and did the label or the evidence decide it?

The obvious way to score the conformity arms is to compare their accuracies. That is the weak
analysis: one observation per task, effects of a couple of points, and D-045 showed how easily a
quantity that size is swamped. This module scores the mechanism instead.

For every episode and every member, ``adopted`` records whether the judge's final answer matches
that member's banked answer under the task's own equivalence relation. Four members and ~475 tasks
give roughly 1,900 observations per arm, and the question — *whose* answer was taken — is the thing
the manipulation is actually about.

The identification argument is why both arms are needed and it is worth restating here, because a
reader of the results will ask. In the truthful arm a member's advertised competence *is* its true
competence, so the two regressors are perfectly collinear and no fit on that arm alone can separate
following the label from weighing the evidence. The inverted arm anti-correlates them. Pooled, the
design identifies both coefficients; either arm alone identifies neither.

Three outcomes are possible per episode and all are recorded: the judge adopts a member's answer, it
adopts an answer several members share, or it states something **no member said** — the last being
the rescue behaviour D-044 found, which the labels might plausibly move.

**Read the contrast, not the two coefficients separately.** With four members and a full reversal,
advertised and true competence are perfectly correlated inside the truthful arm and almost perfectly
anti-correlated inside the inverted one. Pooled, their overall correlation is near zero — which
is what makes the fit possible at all — but the pair stays entangled, and a logistic fit
splits the signal between them in a way that depends on the ratio of arms. The quantity that is
robustly identified is ``advertised_minus_true``: strongly positive means the judge followed the
label, strongly negative means it followed the evidence, near zero means neither.
`test_conformity.py` pins the sign of that contrast under data generated each way, and
deliberately does not pin the two coefficients individually. A follow-up arm using a *random
derangement* rather than a full reversal would decorrelate them further and identify each
separately, at the cost of a weaker manipulation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np


@dataclass
class AdoptionRow:
    """One (episode, member) pair: the unit the conformity model is fitted on."""

    task_id: str
    pool: str
    arm: str
    member: int
    position: int
    """Where the member appeared in the judge's prompt, so order effects are separable."""
    advertised: float
    """Competence as shown to the judge. Equals ``true`` in the truthful arm."""
    true: float
    """Competence as measured on the calibration split."""
    adopted: int
    """1 if the judge's final answer matches this member's banked answer."""
    member_correct: int
    in_majority: int
    """1 if this member's answer was the plurality answer among the members."""

    def features(self) -> list[float]:
        return [
            1.0, self.advertised, self.true, float(self.in_majority), float(self.position)
        ]


FEATURE_NAMES = ("intercept", "advertised", "true", "in_majority", "position")


def _equivalence_classes(
    answers: Mapping[int, str], evaluator: Any
) -> dict[int, int]:
    """Group member answers into classes with the task's own relation, greedily.

    Same approach as `sharing_null.build_task_spaces`, and it carries the same caveat: grouping by
    a precomputed class assumes the relation is transitive. That assumption was checked there by
    replaying recorded episodes at agreement 1.0000, and it is not re-checked here.
    """
    representatives: list[str] = []
    classes: dict[int, int] = {}
    for member in sorted(answers):
        answer = (answers[member] or "").strip()
        if not answer:
            classes[member] = -1
            continue
        for index, canonical in enumerate(representatives):
            if evaluator.equivalent(answer, canonical):
                classes[member] = index
                break
        else:
            representatives.append(answer)
            classes[member] = len(representatives) - 1
    return classes


def adoption_rows(
    *,
    task_id: str,
    pool: str,
    arm: str,
    order: Sequence[int],
    member_answers: Mapping[int, str],
    member_correct: Mapping[int, bool],
    final_answer: str,
    advertised: Mapping[int, float],
    true: Mapping[int, float],
    evaluator: Any,
) -> tuple[list[AdoptionRow], bool]:
    """Rows for one episode, plus whether the judge stated something no member did."""
    classes = _equivalence_classes(member_answers, evaluator)
    counts: dict[int, int] = {}
    for klass in classes.values():
        if klass != -1:
            counts[klass] = counts.get(klass, 0) + 1
    top = max(counts.values(), default=0)

    final = (final_answer or "").strip()
    adopted_class: int | None = None
    if final:
        for member, klass in classes.items():
            if klass != -1 and evaluator.equivalent(final, (member_answers[member] or "").strip()):
                adopted_class = klass
                break

    rows = [
        AdoptionRow(
            task_id=task_id,
            pool=pool,
            arm=arm,
            member=member,
            position=position,
            advertised=float(advertised.get(member, 0.0)),
            true=float(true.get(member, 0.0)),
            adopted=int(classes.get(member, -1) == adopted_class and adopted_class is not None),
            member_correct=int(bool(member_correct.get(member, False))),
                in_majority=int(
                classes.get(member, -1) != -1 and counts.get(classes[member], 0) == top
            ),
        )
        for position, member in enumerate(order)
    ]
    return rows, adopted_class is None


def fit_adoption_model(rows: Sequence[AdoptionRow]) -> dict[str, Any]:
    """Logistic fit of adoption on advertised competence, true competence, majority and position.

    Returns coefficients with a bootstrap interval. The two coefficients that matter are
    ``advertised`` and ``true``; their relative size is the result, and they are only separately
    identifiable because the inverted arm is in the pooled data. A fit on one arm reports its
    condition number so a collinear fit cannot be mistaken for an answer.
    """
    from sklearn.linear_model import LogisticRegression

    if not rows:
        return {"note": "no rows"}
    design = np.array([r.features() for r in rows])
    labels = np.array([r.adopted for r in rows])
    if len(set(labels.tolist())) < 2:
        return {"note": "adoption is constant"}

    # Standardised so the two competence coefficients are on a comparable scale; the intercept
    # column is dropped because LogisticRegression fits its own.
    x = design[:, 1:]
    names = list(FEATURE_NAMES[1:])
    # A column with no variance carries no information and makes the design singular, which would
    # report an uninterpretable `inf` condition number and hide the collinearity that actually
    # matters. Drop such columns and say which, rather than silently regularising through them.
    spread = x.std(axis=0)
    keep = spread >= 1e-12
    dropped = [n for n, k in zip(names, keep, strict=True) if not k]
    x, names = x[:, keep], [n for n, k in zip(names, keep, strict=True) if k]
    if x.shape[1] == 0:
        return {"note": "every regressor is constant", "dropped_constant": dropped}
    x = (x - x.mean(axis=0)) / x.std(axis=0)

    model = LogisticRegression(max_iter=2000)
    model.fit(x, labels)
    coefficients = dict(zip(names, model.coef_[0].tolist(), strict=True))

    rng = np.random.default_rng(20260814)
    draws = []
    for _ in range(200):
        pick = rng.integers(0, len(labels), size=len(labels))
        if len(set(labels[pick].tolist())) < 2:
            continue
        boot = LogisticRegression(max_iter=2000).fit(x[pick], labels[pick])
        draws.append(boot.coef_[0])
    interval = (
        {
            name: [float(np.quantile(np.array(draws)[:, i], 0.025)),
                   float(np.quantile(np.array(draws)[:, i], 0.975))]
            for i, name in enumerate(names)
        }
        if draws
        else {}
    )

    return {
        "n_rows": len(rows),
        "n_adopted": int(labels.sum()),
        "coefficients": coefficients,
        "dropped_constant": dropped,
        "ci95": interval,
        # Near-singular means advertised and true competence did not vary independently, which is
        # exactly what happens if the inverted arm is missing.
        "condition_number": float(np.linalg.cond(x)),
        "advertised_minus_true": float(
            coefficients.get("advertised", float("nan"))
            - coefficients.get("true", float("nan"))
        ),
    }
