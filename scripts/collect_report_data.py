"""Dump every figure the report quotes, from the run records rather than from memory.

Exists because several numbers in `EXPERIMENT_LOG.md` were first written from recollection and had
to be corrected against the data afterwards. Anything the report states should be traceable to a
line of this output.

Accuracies for the paid protocols are computed only on the tasks a pool's seven protocols all ran:
the paid ones were restricted to the discriminating subset while the free ones cover all 366, so the
runner's own per-protocol summary mixes denominators and is not comparable across rows.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from mas_harness import config
from mas_harness.metrics.stats import holm_bonferroni, mcnemar
from mas_harness.pool.agents import AgentPool
from mas_harness.records.writer import RunDirectory

POOL_RUNS = {
    "strong4-a": "strong4",
    "decorr4-a": "decorrelated4",
    "correlated4-a": "correlated4",
}
SCREEN_RUNS = ["screen-a", "screen-strong", "cand4-a", "hard366-a"]
PRICED = [
    "independent_judge",
    "expert_verifier",
    "debate_vote",
    "expert_veto",
    "chair_information_seeking",
]
FREE = ["single_expert", "independent_majority"]
BASE = "single_expert"
AGGREGATOR_DECIDED = {"independent_judge", "chair_information_seeking"}


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def spend() -> None:
    rule("1. SPEND AND VOLUME BY RUN")
    grand = 0.0
    rows = []
    for d in sorted(Path(config.RUNS_DIR).iterdir()):
        if not d.is_dir():
            continue
        rd = RunDirectory(config.RUNS_DIR, d.name)
        usd = 0.0
        answers = episodes = calls = 0
        try:
            for r in rd.load_answers():
                answers += 1
                if not r.call.cached:
                    calls += 1
                    usd += r.call.provider_reported_cost_usd or r.call.cost_usd or 0.0
        except Exception:
            pass
        try:
            for e in rd.load_episodes():
                episodes += 1
                for c in e.calls:
                    if not c.cached:
                        calls += 1
                        usd += c.provider_reported_cost_usd or c.cost_usd or 0.0
        except Exception:
            pass
        if answers or episodes:
            rows.append((d.name, answers, episodes, calls, usd))
            grand += usd
    print(f"  {'run':22s} {'answers':>8s} {'episodes':>9s} {'paid calls':>11s} {'cost':>9s}")
    for name, a, e, c, usd in rows:
        print(f"  {name:22s} {a:8d} {e:9d} {c:11d} ${usd:8.4f}")
    print(f"  {'TOTAL':22s} {sum(r[1] for r in rows):8d} {sum(r[2] for r in rows):9d} "
          f"{sum(r[3] for r in rows):11d} ${grand:8.4f}")


def screening() -> None:
    rule("2. CANDIDATE SCREEN: accuracy, commit rate, non-termination")
    stats: dict[str, dict] = {}
    for run in SCREEN_RUNS:
        try:
            records = RunDirectory(config.RUNS_DIR, run).load_answers()
        except Exception:
            continue
        for r in records:
            s = stats.setdefault(
                r.agent_name,
                {"n": 0, "correct": 0, "commit": 0, "unfinished": 0, "out": 0, "usd": 0.0,
                 "model": r.model, "runs": set()},
            )
            s["runs"].add(run)
            s["n"] += 1
            s["correct"] += bool(r.correct and not r.parse_failed and r.extracted_answer)
            committed = bool(not r.parse_failed and r.extracted_answer)
            s["commit"] += committed
            if r.call.finish_reason not in ("stop", None):
                s["unfinished"] += 1
            s["out"] += r.call.usage.output_tokens or 0
            s["usd"] += r.call.provider_reported_cost_usd or r.call.cost_usd or 0.0
    print(f"  {'agent':20s} {'n':>5s} {'acc':>6s} {'commit':>7s} {'unfin':>6s} "
          f"{'out tok':>8s} {'$/call':>8s}  admitted")
    for name, s in sorted(stats.items(), key=lambda kv: -kv[1]["commit"] / kv[1]["n"]):
        n = s["n"]
        ok = "yes" if s["commit"] / n >= 0.95 else "NO (D-022)"
        print(f"  {name:20s} {n:5d} {s['correct']/n:6.3f} {s['commit']/n:7.3f} "
              f"{s['unfinished']/n:6.3f} {s['out']//n:8d} ${s['usd']/n:7.5f}  {ok}")


def pool_configs() -> None:
    rule("3. POOL DEFINITIONS")
    for run, pool_name in POOL_RUNS.items():
        pool = AgentPool.from_yaml(f"configs/pools/{pool_name}.yaml")
        print(f"\n  {pool_name}  (run {run})")
        for a in pool.agents:
            print(f"    id={a.agent_id} {a.name:15s} {a.model:42s} family={a.family:12s} "
                  f"T={a.temperature} max_tokens={a.max_tokens}")
        agg = pool.aggregator
        print(f"    AGGREGATOR      {agg.model:42s} T={agg.temperature} "
              f"max_tokens={agg.max_tokens}")


def stage_a() -> None:
    rule("4. STAGE A PER POOL")
    for run in POOL_RUNS:
        rd = RunDirectory(config.RUNS_DIR, run)
        per: dict[str, dict] = {}
        for r in rd.load_answers():
            s = per.setdefault(r.agent_name, {"n": 0, "c": 0, "commit": 0, "unfin": 0})
            s["n"] += 1
            s["c"] += bool(r.correct and not r.parse_failed and r.extracted_answer)
            s["commit"] += bool(not r.parse_failed and r.extracted_answer)
            if r.call.finish_reason not in ("stop", None):
                s["unfin"] += 1
        print(f"\n  {run}")
        for name, s in sorted(per.items(), key=lambda kv: -kv[1]["c"] / kv[1]["n"]):
            print(f"    {name:15s} n={s['n']:4d} acc={s['c']/s['n']:.4f} "
                  f"commit={s['commit']/s['n']:.4f} unfinished={s['unfin']/s['n']:.4f}")


def headroom_and_discrimination() -> None:
    rule("5. HEADROOM AND DISCRIMINATION PER POOL")
    for run in POOL_RUNS:
        d = Path(config.RUNS_DIR) / run
        print(f"\n  {run}")
        for name in ("headroom.json", "discrimination.json"):
            path = d / name
            if not path.exists():
                print(f"    {name}: absent")
                continue
            payload = json.loads(path.read_text())
            if name == "headroom.json":
                report, verdict = payload["report"], payload["verdict"]
                grand = report["grand_coalition"]
                print(f"    individual accuracy: {report['individual_accuracy']}")
                print(f"    ceiling {grand['ceiling']*100:.2f}%  best member "
                      f"{grand['best_member']*100:.2f}%  headroom {grand['headroom_pp']:.2f}pp")
                print(f"    dominance gap {report['top1_minus_top2_pp']:.2f}pp  "
                      f"competence range {report['competence_range_pp']:.2f}pp")
                print(f"    error corr mean {report['mean_error_correlation']:+.3f}  "
                      f"max {report['max_error_correlation']:+.3f}")
                print(f"    pairwise: {report['pairwise_error_correlation']}")
                print(f"    ADMISSIBLE at 8pp: {verdict['admissible']}")
            else:
                s = payload["summary"]
                print(f"    discriminating {s['discriminating_frac']*100:.1f}%  "
                      f"dilution eligible {s['dilution_eligible_frac']*100:.1f}%  "
                      f"mean agent acc {s['mean_agent_accuracy']:.4f}")
                print(f"    classes: {s['classes']}")
                print(f"    by suite: {s['by_suite']}")
                sel = payload["selection"]
                print(f"    stage B plan: {len(sel['stage_b_tasks'])} discriminating "
                      f"+ {len(sel['control_tasks'])} control")


def load_outcomes(run: str):
    by: dict[str, dict[str, bool]] = {}
    truncated: dict[str, set[str]] = {}
    for e in RunDirectory(config.RUNS_DIR, run).load_episodes():
        if e.intervention.kind != "none" or len(e.coalition) != 4:
            continue
        by.setdefault(e.protocol_id, {})[e.task_id] = bool(e.correct)
        if not e.final_answer and any(c.finish_reason == "length" for c in e.calls):
            truncated.setdefault(e.protocol_id, set()).add(e.task_id)
    return by, truncated


def protocol_effects() -> None:
    rule("6. PROTOCOL ACCURACY AND EFFECT VS single_expert")
    raw_p: dict[str, float] = {}
    for run in POOL_RUNS:
        by, truncated = load_outcomes(run)
        shared = sorted(set.intersection(*[set(by[p]) for p in PRICED + FREE]))
        print(f"\n  {run}  (n={len(shared)} tasks all seven protocols ran)")
        acc = {p: float(np.mean([by[p][t] for t in shared])) for p in PRICED + FREE}
        for p in sorted(acc, key=lambda k: -acc[k]):
            a = np.array([by[p][t] for t in shared], float)
            b = np.array([by[BASE][t] for t in shared], float)
            r = mcnemar(a.astype(bool).tolist(), b.astype(bool).tolist())
            disc = int((a != b).sum())
            note = ""
            if p in AGGREGATOR_DECIDED:
                keep = [t for t in shared if t not in truncated.get(p, set())]
                ka = np.array([by[p][t] for t in keep], float)
                kb = np.array([by[BASE][t] for t in keep], float)
                kr = mcnemar(ka.astype(bool).tolist(), kb.astype(bool).tolist())
                note = (f"   | excl. {len(shared)-len(keep)} non-terminating: "
                        f"{(ka.mean()-kb.mean())*100:+.2f}pp p={kr.p_value:.4f}")
            if p != BASE:
                raw_p[f"{run}|{p}"] = r.p_value
            print(f"    {p:28s} {acc[p]:.4f}  {(acc[p]-acc[BASE])*100:+6.2f}pp  "
                  f"disc={disc:3d}  p={r.p_value:.4f}{note}")
        spread = (max(acc.values()) - min(acc.values())) * 100
        print(f"    protocol spread {spread:.2f}pp "
              f"({'PASS' if spread >= 8 else 'FAIL'} at the 8pp gate)")

    print("\n  Holm-Bonferroni over all protocol-vs-expert tests, three pools:")
    for k, v in sorted(holm_bonferroni(raw_p).items(), key=lambda kv: kv[1]["p_adjusted"]):
        print(f"    p_raw={raw_p[k]:.4f} p_adj={v['p_adjusted']:.4f} "
              f"{'REJECT' if v['reject'] else '      '}  {k}")


def influence() -> None:
    rule("7. INFLUENCE: single-member mask flip rates")
    for run in POOL_RUNS:
        rd = RunDirectory(config.RUNS_DIR, run)
        base: dict[tuple[str, str], str] = {}
        masked: dict[str, dict] = {}
        names: dict[int, str] = {}
        pool = AgentPool.from_yaml(f"configs/pools/{POOL_RUNS[run]}.yaml")
        for a in pool.agents:
            names[a.agent_id] = a.name
        for e in rd.load_episodes():
            if len(e.coalition) != 4:
                continue
            if e.intervention.kind == "none":
                base[(e.protocol_id, e.task_id)] = e.final_answer or ""
            elif e.intervention.kind == "mask":
                masked.setdefault(e.protocol_id, {}).setdefault(
                    e.intervention.target_agent_id, []
                ).append(e)
        print(f"\n  {run}")
        for protocol, per_agent in sorted(masked.items()):
            total = flips = 0
            detail = []
            for agent_id, eps in sorted(per_agent.items()):
                f = sum(
                    1
                    for e in eps
                    if base.get((protocol, e.task_id), "") != (e.final_answer or "")
                )
                detail.append(f"{names.get(agent_id, agent_id)} {f/len(eps)*100:.1f}%")
                total += len(eps)
                flips += f
            print(f"    {protocol:24s} overall {flips/max(total,1)*100:5.1f}%  ({total} pairs)")
            print(f"      per member: {', '.join(detail)}")


def gate() -> None:
    rule("8. GO/NO-GO GATE PER POOL")
    for run in POOL_RUNS:
        path = Path(config.RUNS_DIR) / run / "gonogo.json"
        if not path.exists():
            print(f"  {run}: no gonogo.json")
            continue
        payload = json.loads(path.read_text())
        print(f"\n  {run}")
        for c in payload["criteria"]:
            print(f"    [{c['verdict']:4s}] {c['direction']:11s} {c['name']:34s} "
                  f"observed {c['observed']:8.3f}  n={c.get('n')}")
            print(f"           threshold: {c['threshold']}")
        for direction, verdict in payload["recommendation"].items():
            if isinstance(verdict, dict):
                print(f"    {direction:12s} {verdict.get('status')}")
            else:
                print(f"    {direction:12s} {verdict}")


if __name__ == "__main__":
    spend()
    screening()
    pool_configs()
    stage_a()
    headroom_and_discrimination()
    protocol_effects()
    influence()
    gate()
