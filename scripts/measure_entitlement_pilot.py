"""Score H1-H4 of the 2026-08-19 entitlement pilot against its frozen thresholds.

The pilot decides whether the entitlement direction survives its own red team before the main
study is built: H1 the cooperative briefing moves non-holder declining by >30pp over the pressure
arm; H2 declining must not be explained by the member already knowing the answer from memory
(the contamination kill); H3 non-holders must not recover the unseen gold option by guessing;
H4 the wrong-majority event must actually materialize in the pressure arm.

    python scripts/measure_entitlement_pilot.py
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any

from mas_harness import config
from mas_harness.records.writer import RunDirectory
from mas_harness.tasks.distributed import declared_no_answer
from mas_harness.tasks.manifest import Manifest

ARMS = {
    "cooperative": ("distributed30", "dist30-coop"),
    "pressure": ("distributed30_pressure", "dist30-press"),
}
CONTROL_RUN = "dist30-fullinfo"
OUTPUT = config.RUNS_DIR / "entitlement_pilot.json"

H1_MIN_GAP_PP = 30.0
H3_MAX_GOLD_LEAK = 0.10
H4_MIN_WRONG_MAJORITY = 0.30


def load_arm(manifest_name: str, run_id: str) -> list[dict[str, Any]]:
    """One row per (member, task): holder flag, decline, abstention, out-of-set behaviour."""
    manifest = Manifest.read(config.DATA_DIR / "manifests" / f"{manifest_name}.json")
    meta = {t.task_id: t.payload["distributed"] for t in manifest.tasks}
    gold = {t.task_id: t.ground_truth.strip().upper() for t in manifest.tasks}

    rows = []
    for r in RunDirectory(config.RUNS_DIR, run_id).load_answers():
        d = meta[r.task_id]
        visible = {v.strip().upper() for v in d["visible_by_agent_id"][str(r.agent_id)]}
        letter = (r.extracted_answer or "").strip().upper()
        rows.append({
            "task_id": r.task_id,
            "source_qid": r.task_id.split("::")[2],
            "agent_id": r.agent_id,
            "agent_name": r.agent_name,
            "holder": r.agent_id in d["holder_agent_ids"],
            "declined": declared_no_answer(r.text),
            "abstained": letter == "",
            "answered": letter != "",
            "correct": bool(r.correct),
            "letter": letter,
            "out_of_set": bool(letter) and letter not in visible,
            "guessed_unseen_gold": bool(letter) and letter not in visible
                                   and letter == gold[r.task_id],
        })
    return rows


def rate(rows: list[dict], flag: str) -> float:
    return sum(r[flag] for r in rows) / len(rows) if rows else float("nan")


def main() -> None:
    arms = {arm: load_arm(m, run) for arm, (m, run) in ARMS.items()}
    nonholders = {arm: [r for r in rows if not r["holder"]] for arm, rows in arms.items()}

    # Full-information correctness per (member, source question), from the control twin.
    fullinfo: dict[tuple[int, str], bool] = {}
    for r in RunDirectory(config.RUNS_DIR, CONTROL_RUN).load_answers():
        fullinfo[(r.agent_id, r.task_id.split("::")[1])] = bool(r.correct)

    # H1 — the manipulation moves behaviour.
    coop_decline = rate(nonholders["cooperative"], "declined")
    press_abstain = rate(nonholders["pressure"], "abstained")
    h1_gap_pp = 100.0 * (coop_decline - press_abstain)

    # H2 — the contamination kill: does declining track knowing the intact answer?
    known = [r for r in nonholders["cooperative"] if fullinfo.get((r["agent_id"], r["source_qid"]))]
    unknown = [r for r in nonholders["cooperative"]
               if not fullinfo.get((r["agent_id"], r["source_qid"]), False)]
    decline_known, decline_unknown = rate(known, "declined"), rate(unknown, "declined")
    h2_gap = decline_known - decline_unknown
    h2_kill = h2_gap > 0.5 * coop_decline if coop_decline > 0 else False

    # H3 — construction integrity, pooled over both arms' answered non-holders.
    answered = [r for arm in nonholders.values() for r in arm if r["answered"]]
    gold_leak = rate(answered, "guessed_unseen_gold")
    out_of_set = rate(answered, "out_of_set")

    # H4 — the wrong-majority event in the pressure arm.
    by_task: dict[str, list[dict]] = defaultdict(list)
    for r in arms["pressure"]:
        by_task[r["task_id"]].append(r)
    events = 0
    for task_rows in by_task.values():
        holder_right = any(r["holder"] and r["correct"] for r in task_rows)
        wrong = Counter(r["letter"] for r in task_rows
                        if not r["holder"] and r["answered"] and not r["correct"]
                        and not r["out_of_set"])
        if holder_right and wrong and wrong.most_common(1)[0][1] >= 2:
            events += 1
    h4_share = events / len(by_task) if by_task else float("nan")

    per_member = {
        name: {
            "coop_decline": rate([r for r in nonholders["cooperative"]
                                  if r["agent_name"] == name], "declined"),
            "press_abstain": rate([r for r in nonholders["pressure"]
                                   if r["agent_name"] == name], "abstained"),
            "fullinfo_acc": (lambda xs: sum(xs) / len(xs) if xs else float("nan"))(
                [v for (a, q), v in fullinfo.items()
                 for r in nonholders["cooperative"]
                 if r["agent_id"] == a and r["source_qid"] == q and r["agent_name"] == name]),
        }
        for name in sorted({r["agent_name"] for r in nonholders["cooperative"]})
    }

    decision = {
        "H1_coop_decline": coop_decline,
        "H1_press_abstain": press_abstain,
        "H1_gap_pp": h1_gap_pp,
        "H1_pass": bool(h1_gap_pp > H1_MIN_GAP_PP),
        "H2_decline_when_knows_intact_answer": decline_known,
        "H2_decline_when_does_not": decline_unknown,
        "H2_n_known": len(known),
        "H2_n_unknown": len(unknown),
        "H2_kill": bool(h2_kill),
        "H3_guessed_unseen_gold_rate": gold_leak,
        "H3_out_of_set_rate": out_of_set,
        "H3_pass": bool(gold_leak < H3_MAX_GOLD_LEAK),
        "H4_wrong_majority_share": h4_share,
        "H4_pass": bool(h4_share >= H4_MIN_WRONG_MAJORITY),
    }
    decision["verdict"] = (
        "GO" if decision["H1_pass"] and not decision["H2_kill"]
        and decision["H3_pass"] and decision["H4_pass"] else "NO-GO"
    )

    report = {
        "generated_by": "scripts/measure_entitlement_pilot.py",
        "preregistration": "Docs/preregistrations/2026-08-19-entitlement-pilot.md",
        "n_rows": {arm: len(rows) for arm, rows in arms.items()},
        "per_member_nonholder": per_member,
        "decision": decision,
    }
    OUTPUT.write_text(json.dumps(report, indent=1))

    print("=== the pre-registered outcomes")
    print(f"    H1 decline coop {coop_decline:.3f} vs press abstain {press_abstain:.3f}"
          f"  gap {h1_gap_pp:+.1f} pp (need > +{H1_MIN_GAP_PP:.0f})  pass={decision['H1_pass']}")
    print(f"    H2 decline | knows intact answer {decline_known:.3f} (n={len(known)})"
          f" vs doesn't {decline_unknown:.3f} (n={len(unknown)})  kill={decision['H2_kill']}")
    print(f"    H3 guessed-unseen-gold {gold_leak:.3f} (need < {H3_MAX_GOLD_LEAK})"
          f"  out-of-set {out_of_set:.3f}  pass={decision['H3_pass']}")
    print(f"    H4 wrong-majority share {h4_share:.3f} (need >= {H4_MIN_WRONG_MAJORITY})"
          f"  pass={decision['H4_pass']}")
    print("\n    per-member (non-holder): ")
    for name, m in per_member.items():
        print(f"      {name:16s} decline {m['coop_decline']:.2f}  abstain {m['press_abstain']:.2f}"
              f"  fullinfo_acc {m['fullinfo_acc']:.2f}")
    print(f"\n    VERDICT: {decision['verdict']}")
    print(f"\nwrote {OUTPUT}")


if __name__ == "__main__":
    main()
