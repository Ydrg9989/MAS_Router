"""The three figures and the percentile table the pool sweep pre-registered.

Reads `data/runs/pool_sweep_<suite>.json` and emits section 4's deliverables:

``Figure A`` the headroom excess of every pool against the joint null's own band — the figure
that replaces six Bonferroni-corrected p-values with one family-wise picture.
``Figure B`` whole-pool vote minus capability router as a distribution. Section 4 calls its width
and sign the single most decisive number in the sweep.
``Figure C`` the pre-registered descriptor relationship against routing gain, which is where
`correlated4` either becomes explicable or becomes noise.

    python scripts/report_pool_sweep.py --suite crosscap240
"""

from __future__ import annotations

import argparse
import json

import numpy as np

from mas_harness import config

# Categorical slots 1-3 of the validated default palette, which are the three that clear the
# all-pairs colour-vision floors; a scatter needs all-pairs separation, not merely adjacent.
OBSERVED = "#2a78d6"
NAMED = "#eb6834"
ACCENT = "#1baf7a"
INK = "#0b0b0b"
MUTED = "#52514e"
BAND = "#c9c8c3"


def _style():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": MUTED,
            "axes.linewidth": 0.8,
            "axes.labelcolor": INK,
            "axes.titlesize": 11,
            "axes.labelsize": 9.5,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "xtick.labelsize": 8.5,
            "ytick.labelsize": 8.5,
            "grid.color": "#e8e7e3",
            "grid.linewidth": 0.7,
            "legend.frameon": False,
            "legend.fontsize": 8.5,
            "font.size": 9.5,
        }
    )
    return plt


def figure_a(report: dict, plt, path):
    """Observed headroom excess per pool against the joint null's own spread."""
    pools = report["pools"]
    excess = np.array([p["headroom_excess_over_joint_null"] for p in pools])
    replicates = np.array(report["joint_null_replicates"])
    centred = replicates - replicates.mean(axis=0, keepdims=True)

    order = np.argsort(excess)
    rank = np.arange(len(order))
    low = np.quantile(centred, 0.05, axis=0)[order]
    high = np.quantile(centred, 0.95, axis=0)[order]

    named = {tuple(v): k for k, v in report["named_pools"].items()}
    is_named = np.array([tuple(p["pool"]) in named for p in pools])[order]

    figure, axes = plt.subplots(figsize=(7.2, 4.0))
    axes.fill_between(
        rank, low, high, color=BAND, alpha=0.55, linewidth=0,
        label="joint null, 5th–95th percentile",
    )
    axes.axhline(0, color=MUTED, linewidth=0.8, linestyle=(0, (4, 3)))
    axes.scatter(
        rank[~is_named], excess[order][~is_named], s=26, color=OBSERVED, zorder=3,
        edgecolor="white", linewidth=0.8, label="observed pool",
    )
    axes.scatter(
        rank[is_named], excess[order][is_named], s=64, color=NAMED, zorder=4, marker="D",
        edgecolor="white", linewidth=1.0, label="the three published pools",
    )
    # Named pools can land next to one another, so alternate the label offset rather than
    # letting two annotations overprint.
    for offset, (position, pool) in enumerate(
        zip(rank[is_named], np.array(pools, dtype=object)[order][is_named], strict=True)
    ):
        axes.annotate(
            named[tuple(pool["pool"])],
            (position, pool["headroom_excess_over_joint_null"]),
            textcoords="offset points", xytext=(0, 11 if offset % 2 == 0 else -19), ha="center",
            fontsize=8.5, color=INK,
        )

    family = report["family_wise_null"]
    expected = family["null_frac_pools_p_below_05_mean"] * len(pools)
    axes.set_xlabel(f"pools, ordered by excess (n = {len(pools)})")
    axes.set_ylabel("oracle headroom excess over the null (pp)")
    axes.set_title(
        "No pool exceeds a null that removes agent-by-task interaction\n"
        f"median excess {family['median_excess']:+.2f} pp (p = {family['p_median']:.3f})\n"
        f"{int(round(family['frac_pools_p_below_05'] * len(pools)))} of {len(pools)} pools at "
        f"p ≤ 0.05, against {expected:.1f} expected",
        loc="left", color=INK, fontsize=10.5,
    )
    axes.grid(axis="y")
    axes.set_axisbelow(True)
    axes.legend(loc="upper left")
    figure.tight_layout()
    figure.savefig(path, dpi=200)
    plt.close(figure)


def figure_b(report: dict, plt, path):
    """Whole-pool vote minus the capability router, across every pool."""
    pools = report["pools"]
    margin = np.array(
        [
            100.0 * (p["ladder"]["whole_pool_vote"] - p["ladder"]["capability_router_agents"])
            for p in pools
        ]
    )
    named = {tuple(v): k for k, v in report["named_pools"].items()}

    figure, axes = plt.subplots(figsize=(7.2, 3.8))
    axes.hist(
        margin, bins=18, color=OBSERVED, edgecolor="white", linewidth=1.0, alpha=0.9,
        label="pools",
    )
    axes.axvline(0, color=MUTED, linewidth=1.0, linestyle=(0, (4, 3)))
    top = axes.get_ylim()[1]
    marks = sorted(
        (
            100.0
            * (pool["ladder"]["whole_pool_vote"] - pool["ladder"]["capability_router_agents"]),
            named[tuple(pool["pool"])],
        )
        for pool in pools
        if tuple(pool["pool"]) in named
    )
    for rank_of, (value, label) in enumerate(marks):
        # Two named pools can share a value to the point of overprinting, so stagger the labels.
        crowded = rank_of > 0 and value - marks[rank_of - 1][0] < 0.6
        axes.vlines(value, 0, top * (0.74 if crowded else 0.84), color=NAMED, linewidth=2.0)
        axes.annotate(
            label,
            (value, top * (0.76 if crowded else 0.86)),
            ha="center", fontsize=8.5, color=INK,
        )

    ahead = float(np.mean(margin >= 0))
    axes.set_xlabel("whole-pool majority vote minus capability router, accuracy points")
    axes.set_ylabel("pools")
    axes.set_title(
        "Voting and an oracle-labelled capability router are near-tied\n"
        f"vote at least matches the router in {ahead:.0%} of {len(pools)} pools\n"
        f"mean margin {margin.mean():+.2f} pp, 5th-95th {np.quantile(margin, 0.05):+.1f} to "
        f"{np.quantile(margin, 0.95):+.1f} pp",
        loc="left", color=INK, fontsize=10.5,
    )
    axes.set_ylim(0, top * 1.02)
    axes.grid(axis="y")
    axes.set_axisbelow(True)
    figure.tight_layout()
    figure.savefig(path, dpi=200)
    plt.close(figure)


def figure_c(report: dict, plt, path):
    """The pre-registered relationship: does ability spread predict routing gain?

    Deliberately *not* the strongest correlation in the matrix. P4 names a specific pair and a
    specific sign, and showing whichever pair happened to score highest would be the same
    maximise-then-report move the sweep exists to audit. The strongest pair is named in the
    subtitle so it is not hidden.
    """
    pools = report["pools"]
    prediction = report["predictions"]["P4_descriptors_predict_routing_gain"]
    correlations = prediction["correlations"]
    target_name, descriptor = "capability_router_minus_vote", "ability_spread"
    best = correlations[target_name][descriptor]

    strongest_target, strongest_key, strongest = None, None, 0.0
    for target, row in correlations.items():
        for key, value in row.items():
            if np.isfinite(value) and abs(value) > abs(strongest):
                strongest_target, strongest_key, strongest = target, key, value

    label = "capability router minus whole-pool vote (accuracy)"
    x = np.array([p["descriptors"][descriptor] for p in pools])
    y = np.array(
        [
            p["ladder"]["capability_router_agents"] - p["ladder"]["whole_pool_vote"]
            for p in pools
        ]
    )
    finite = np.isfinite(x) & np.isfinite(y)
    named = {tuple(v): k for k, v in report["named_pools"].items()}
    is_named = np.array([tuple(p["pool"]) in named for p in pools])

    figure, axes = plt.subplots(figsize=(6.4, 4.0))
    axes.scatter(
        x[finite & ~is_named], y[finite & ~is_named], s=28, color=OBSERVED,
        edgecolor="white", linewidth=0.8, zorder=3, label="pools",
    )
    axes.scatter(
        x[finite & is_named], y[finite & is_named], s=64, color=NAMED, marker="D",
        edgecolor="white", linewidth=1.0, zorder=4, label="published pools",
    )
    for pool, xi, yi in zip(pools, x, y, strict=True):
        if tuple(pool["pool"]) in named and np.isfinite(xi) and np.isfinite(yi):
            axes.annotate(
                named[tuple(pool["pool"])], (xi, yi), textcoords="offset points",
                xytext=(0, 9), ha="center", fontsize=8.5, color=INK,
            )
    if finite.sum() > 2:
        slope, intercept = np.polyfit(x[finite], y[finite], 1)
        line = np.linspace(x[finite].min(), x[finite].max(), 2)
        axes.plot(line, slope * line + intercept, color=ACCENT, linewidth=2.0, zorder=2)

    axes.axhline(0, color=MUTED, linewidth=0.8, linestyle=(0, (4, 3)))
    axes.set_xlabel("ability spread of the pool (best member minus worst, calibration)")
    axes.set_ylabel(label)
    axes.set_title(
        f"P4 predicted this slope negative; it is r = {best:+.2f}\n"
        "no descriptor reaches |r| = 0.3 against any routing gain\n"
        f"strongest pair in the matrix: {strongest_key.replace('_', ' ')}\n"
        f"against {strongest_target.replace('_', ' ')}, r = {strongest:+.2f}",
        loc="left", color=INK, fontsize=9.5,
    )
    axes.grid(True)
    axes.set_axisbelow(True)
    axes.legend(loc="best")
    figure.tight_layout()
    figure.savefig(path, dpi=200)
    plt.close(figure)


def percentile_table(report: dict) -> str:
    """Where the three published pools sit in the distribution of all of them."""
    pools = report["pools"]
    named = {k: tuple(v) for k, v in report["named_pools"].items()}
    index = {tuple(p["pool"]): i for i, p in enumerate(pools)}

    columns = {
        "headroom excess (pp)": np.array(
            [p["headroom_excess_over_joint_null"] for p in pools]
        ),
        "observed headroom (pp)": np.array(
            [p["observed_headroom_over_best"] for p in pools]
        ),
        "vote − capability router (pp)": np.array(
            [
                100.0 * (p["ladder"]["whole_pool_vote"] - p["ladder"]["capability_router_agents"])
                for p in pools
            ]
        ),
        "q_theta gain (pp)": np.array(
            [
                p["routing"]["gain_over_fixed_best"].get("q_theta", {}).get("mean", np.nan)
                for p in pools
            ]
        ),
        "budget gain, unconstrained (pp)": np.array(
            [p["budget"].get("unconstrained_gain_pp", np.nan) for p in pools]
        ),
        "budget gain, tightest (pp)": np.array(
            [p["budget"].get("tightest_gain_pp", np.nan) for p in pools]
        ),
    }

    lines = [
        f"{'statistic':32s} {'median':>8s} "
        + " ".join(f"{name:>22s}" for name in named)
    ]
    lines.append("-" * len(lines[0]))
    for label, values in columns.items():
        finite = np.isfinite(values)
        cells = []
        for pool in named.values():
            i = index[pool]
            percentile = 100.0 * np.mean(values[finite] <= values[i]) if finite[i] else float("nan")
            cells.append(f"{values[i]:+8.2f} ({percentile:3.0f}th)")
        lines.append(
            f"{label:32s} {np.nanmedian(values):+8.2f} " + " ".join(f"{c:>22s}" for c in cells)
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default="crosscap240")
    arguments = parser.parse_args()

    path = config.RUNS_DIR / f"pool_sweep_{arguments.suite}.json"
    report = json.loads(path.read_text())
    plt = _style()

    figures = config.RUNS_DIR / "figures"
    figures.mkdir(exist_ok=True)
    for name, builder in (
        ("A_headroom_distribution", figure_a),
        ("B_vote_minus_router", figure_b),
        ("C_descriptor_regression", figure_c),
    ):
        target = figures / f"pool_sweep_{arguments.suite}_{name}.png"
        builder(report, plt, target)
        print(f"wrote {target}")

    print(f"\n=== {arguments.suite}: {report['n_pools']} pools, {report['n_tasks']} tasks")
    print(percentile_table(report))

    print("\n=== pre-registered predictions")
    for key, entry in report["predictions"].items():
        print(f"\n  {key}  ->  {entry['verdict']}")
        print(f"    predicted: {entry['prediction']}")
        for field, value in entry.items():
            if field in {"prediction", "verdict", "correlations", "family_wise"}:
                continue
            print(
                f"      {field:44s} {value:.4f}"
                if isinstance(value, float)
                else f"      {field:44s} {value}"
            )

    calibration = report.get("calibration")
    if calibration:
        print("\n=== null calibration (double bootstrap on additive banks)")
        print(
            f"    false positives at 0.05: {calibration['false_positive_rate_at_05']:.3f} "
            f"(nominal 0.050) over {calibration['n_outer']} banks"
        )


if __name__ == "__main__":
    main()
