"""Score M1-M5 of the 2026-08-19 entitlement main study against its frozen thresholds.

Written and committed before any Stage B spend, as the pre-registration requires
(Docs/preregistrations/2026-08-19-entitlement-main.md).

    python scripts/measure_entitlement_main.py
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

import numpy as np

from mas_harness import config
from mas_harness.metrics.adoption import adoption_rows
from mas_harness.records.writer import RunDirectory
from mas_harness.tasks.adapters import build_evaluator
from mas_harness.tasks.distributed import declared_no_answer
from mas_harness.tasks.manifest import Manifest

PRESS, COOP, H2 = "dist250-press", "dist250-coop", "dist250-press-h2"
FULLINFO = "dist250-fullinfo"
MANIFESTS = {
    PRESS: "distributed250_pressure",
    COOP: "distributed250",
    H2: "distributed250_pressure_h2",
}
JUDGE = "independent_judge"
ACCESS, INVERTED, SETS = "judge_access_labelled", "judge_access_inverted", "judge_access_sets"
COMPETENCE = "judge_labelled"
OUTPUT = config.RUNS_DIR / "entitlement_main.json"

M1_MIN_ADOPTION_SHIFT_PP = 10.0
M2_RESTORED, M2_PERSISTS = 0.80, 0.60
M2_MIN_ACC_GAIN_PP = 5.0
M3_MIN_PP = 3.0
M4_MIN_GAIN_RATIO = 0.5


def load_run(run_id: str) -> dict[str, Any]:
    manifest = Manifest.read(config.DATA_DIR / "manifests" / f"{MANIFESTS[run_id]}.json")
    specs = {t.task_id: t for t in manifest.tasks}
    directory = RunDirectory(config.RUNS_DIR, run_id)
    bank: dict[str, dict[int, Any]] = defaultdict(dict)
    for r in directory.load_answers():
        bank[r.task_id][r.agent_id] = r
    episodes: dict[str, dict[str, Any]] = defaultdict(dict)
    grand = max(len(s.payload["distributed"]["required_agent_ids"]) for s in specs.values())
    for e in directory.load_episodes():
        if e.intervention.kind == "none" and len(e.coalition) == grand:
            episodes[e.protocol_id][e.task_id] = e
    return {"specs": specs, "bank": bank, "episodes": episodes}


def wrong_majority_tasks(data: dict[str, Any]) -> list[str]:
    """Pressure-arm tasks where a holder is right and >=2 non-holders share a wrong answer."""
    out = []
    for task_id, spec in data["specs"].items():
        meta = spec.payload["distributed"]
        holders = set(meta["holder_agent_ids"])
        answers = data["bank"].get(task_id, {})
        if len(answers) < len(meta["required_agent_ids"]):
            continue
        if not any(answers[a].correct for a in holders if a in answers):
            continue
        wrong: dict[str, int] = defaultdict(int)
        for a, rec in answers.items():
            letter = (rec.extracted_answer or "").strip().upper()
            if a not in holders and letter and not rec.correct \
                    and letter in meta["visible_by_agent_id"][str(a)]:
                wrong[letter] += 1
        if wrong and max(wrong.values()) >= 2:
            out.append(task_id)
    return sorted(out)


def accuracy(data: dict[str, Any], protocol: str, tasks: list[str] | None = None) -> float:
    eps = data["episodes"].get(protocol, {})
    pool = sorted(eps) if tasks is None else [t for t in tasks if t in eps]
    return float(np.mean([eps[t].correct for t in pool])) if pool else float("nan")


def shared_tasks(data: dict[str, Any], protocols: list[str]) -> list[str]:
    sets_ = [set(data["episodes"].get(p, {})) for p in protocols]
    return sorted(set.intersection(*sets_)) if all(sets_) else []


def access_adoption(data: dict[str, Any], protocols: list[str]) -> dict[str, Any]:
    """The stratified adoption table over advertised x true holder status."""
    cells: dict[tuple[int, int], list[int]] = defaultdict(list)
    for protocol in protocols:
        for task_id, e in data["episodes"].get(protocol, {}).items():
            spec = data["specs"][task_id]
            meta = e.protocol_meta
            advertised = {int(a): 1.0 for a in meta.get("advertised_holder_agent_ids", [])}
            true = {int(a): 1.0 for a in meta.get("true_holder_agent_ids", [])}
            answers = data["bank"][task_id]
            order = [int(a) for a in meta.get("visible_order", sorted(answers))]
            rows, _ = adoption_rows(
                task_id=task_id, pool=MANIFESTS[PRESS], arm=protocol, order=order,
                member_answers={a: answers[a].extracted_answer for a in order},
                member_correct={a: bool(answers[a].correct) for a in order},
                final_answer=e.final_answer,
                advertised={a: advertised.get(a, 0.0) for a in order},
                true={a: true.get(a, 0.0) for a in order},
                evaluator=build_evaluator(spec),
            )
            for row in rows:
                cells[(int(row.advertised), int(row.true))].append(row.adopted)

    table = {
        f"adv={adv},true={tru}": {"n": len(v), "adoption": float(np.mean(v))}
        for (adv, tru), v in sorted(cells.items()) if v
    }
    # The advertised effect with true status controlled: within-stratum contrasts where both
    # advertised values exist, weighted by stratum size. The inverted arm supplies adv=1,true=0
    # and adv=0,true=1; the truthful arm supplies the diagonal.
    contrasts, weights = [], []
    for tru in (0, 1):
        a1, a0 = cells.get((1, tru)), cells.get((0, tru))
        if a1 and a0:
            contrasts.append(float(np.mean(a1)) - float(np.mean(a0)))
            weights.append(len(a1) + len(a0))
    shift_pp = 100.0 * float(np.average(contrasts, weights=weights)) if contrasts else float("nan")
    return {"table": table, "advertised_shift_pp": shift_pp}


def follow_holder_rate(data: dict[str, Any], protocol: str, tasks: list[str]) -> float:
    followed, n = 0, 0
    for task_id in tasks:
        e = data["episodes"].get(protocol, {}).get(task_id)
        if e is None:
            continue
        spec = data["specs"][task_id]
        evaluator = build_evaluator(spec)
        holders = set(spec.payload["distributed"]["holder_agent_ids"])
        answers = data["bank"][task_id]
        n += 1
        if any(evaluator.equivalent(e.final_answer or "", answers[a].extracted_answer or "")
               for a in holders if a in answers):
            followed += 1
    return followed / n if n else float("nan")


def contamination_at_scale(coop: dict[str, Any]) -> dict[str, Any]:
    """The pilot's H2 rule on the 250-task cooperative arm, against dist250-fullinfo."""
    fullinfo: dict[tuple[int, str], bool] = {}
    try:
        for r in RunDirectory(config.RUNS_DIR, FULLINFO).load_answers():
            fullinfo[(r.agent_id, r.task_id.split("::")[1])] = bool(r.correct)
    except FileNotFoundError:
        return {"note": f"{FULLINFO} not banked yet"}
    known, unknown = [], []
    for task_id, spec in coop["specs"].items():
        holders = set(spec.payload["distributed"]["holder_agent_ids"])
        qid = task_id.split("::")[2]
        for a, rec in coop["bank"].get(task_id, {}).items():
            if a in holders:
                continue
            declined = declared_no_answer(rec.text)
            (known if fullinfo.get((a, qid), False) else unknown).append(int(declined))
    pooled = float(np.mean(known + unknown)) if (known or unknown) else float("nan")
    gap = float(np.mean(known)) - float(np.mean(unknown)) if known and unknown else float("nan")
    return {
        "decline_when_knows": float(np.mean(known)) if known else float("nan"),
        "decline_when_does_not": float(np.mean(unknown)) if unknown else float("nan"),
        "n_known": len(known), "n_unknown": len(unknown),
        "pooled_decline": pooled,
        "kill": bool(gap > 0.5 * pooled) if pooled and not np.isnan(gap) else False,
    }


def main() -> None:
    press, coop, h2 = load_run(PRESS), load_run(COOP), load_run(H2)
    wm = wrong_majority_tasks(press)

    paired = shared_tasks(press, [JUDGE, ACCESS])
    m1 = access_adoption(press, [ACCESS, INVERTED])
    m2_rate = follow_holder_rate(press, ACCESS, wm)
    m2_gain = 100.0 * (accuracy(press, ACCESS, paired) - accuracy(press, JUDGE, paired))
    m3_tasks = shared_tasks(press, [ACCESS, COMPETENCE])
    m3_pp = 100.0 * (accuracy(press, ACCESS, m3_tasks) - accuracy(press, COMPETENCE, m3_tasks))
    m4_tasks = shared_tasks(press, [JUDGE, ACCESS, SETS])
    denom = accuracy(press, ACCESS, m4_tasks) - accuracy(press, JUDGE, m4_tasks)
    numer = accuracy(press, SETS, m4_tasks) - accuracy(press, JUDGE, m4_tasks)
    m4_ratio = numer / denom if denom > 0 else float("nan")

    decision = {
        "M1_advertised_shift_pp": m1["advertised_shift_pp"],
        "M1_pass": bool(m1["advertised_shift_pp"] >= M1_MIN_ADOPTION_SHIFT_PP),
        "M2_n_wrong_majority": len(wm),
        "M2_follow_labelled_holder": m2_rate,
        "M2_access_minus_judge_pp": m2_gain,
        "M2_branch": (
            "LABELS RESTORE ENTITLEMENT" if m2_rate >= M2_RESTORED
            and m2_gain >= M2_MIN_ACC_GAIN_PP
            else "CONFORMITY PERSISTS UNDER PROVABLE IGNORANCE" if m2_rate <= M2_PERSISTS
            else "REPORTED AS MEASURED, NO BRANCH"
        ),
        "M3_access_minus_competence_pp": m3_pp,
        "M3_notable": bool(m3_pp >= M3_MIN_PP),
        "M4_gain_ratio_sets": m4_ratio,
        "M4_notable": bool(not np.isnan(m4_ratio) and m4_ratio >= M4_MIN_GAIN_RATIO),
        "M5_h2": {
            "judge": accuracy(h2, JUDGE),
            "access_labelled": accuracy(h2, ACCESS),
            "n_wrong_majority": len(wrong_majority_tasks(h2)),
            "follow_labelled_holder": follow_holder_rate(h2, ACCESS, wrong_majority_tasks(h2)),
        },
        "H2_contamination_at_scale": contamination_at_scale(coop),
    }

    report = {
        "generated_by": "scripts/measure_entitlement_main.py",
        "preregistration": "Docs/preregistrations/2026-08-19-entitlement-main.md",
        "adoption_table": m1["table"],
        "accuracy_pressure": {
            p: accuracy(press, p) for p in (JUDGE, ACCESS, INVERTED, SETS, COMPETENCE)
        },
        "accuracy_coop": {p: accuracy(coop, p) for p in (JUDGE, ACCESS)},
        "decision": decision,
    }
    OUTPUT.write_text(json.dumps(report, indent=1))

    print("=== the pre-registered outcomes")
    print(f"    M1 advertised-holder adoption shift {decision['M1_advertised_shift_pp']:+.1f} pp "
          f"(need >= +{M1_MIN_ADOPTION_SHIFT_PP:.0f})  pass={decision['M1_pass']}")
    print(f"    M2 follow-labelled-holder on {len(wm)} wrong-majority tasks: "
          f"{m2_rate:.3f}; access-judge {m2_gain:+.2f} pp -> {decision['M2_branch']}")
    print(f"    M3 access minus competence labels {m3_pp:+.2f} pp  "
          f"notable={decision['M3_notable']}")
    print(f"    M4 sets/labelled gain ratio {m4_ratio:.2f}  notable={decision['M4_notable']}")
    print(f"    M5 h2: {json.dumps(decision['M5_h2'])}")
    print(f"    H2 at scale: {json.dumps(decision['H2_contamination_at_scale'])}")
    print(f"\nwrote {OUTPUT}")


if __name__ == "__main__":
    main()
