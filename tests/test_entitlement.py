"""The access-label arms: truthful, inverted, and structural.

`access_labels` reads only `context.spec` and the speaking order, so these tests use a minimal
fake context over REAL distributed30 specs — the payload shape under test is the produced one,
not a hand-written imitation.
"""

from __future__ import annotations

import pytest

from mas_harness.protocols.entitlement import (
    HOLDER_LABEL,
    NON_HOLDER_LABEL,
    SETS_TEMPLATE,
    _false_holder,
    access_labels,
)
from mas_harness.tasks.manifest import Manifest


class FakeContext:
    def __init__(self, spec):
        self.spec = spec


def distributed_spec(index: int = 0):
    return Manifest.read("data/manifests/distributed30.json").tasks[index]


def order_for(spec) -> list[int]:
    return [int(a) for a in spec.payload["distributed"]["required_agent_ids"]]


def test_truthful_labels_designate_exactly_the_holders():
    spec = distributed_spec()
    order = order_for(spec)
    holders = set(spec.payload["distributed"]["holder_agent_ids"])
    labels, truth = access_labels(FakeContext(spec), order, mode="truthful")
    for a in order:
        assert labels[a] == (HOLDER_LABEL if a in holders else NON_HOLDER_LABEL)
    assert truth["advertised_holder_agent_ids"] == sorted(holders)
    assert truth["true_holder_agent_ids"] == sorted(holders)


def test_inverted_labels_preserve_the_designation_multiset_and_move_it():
    spec = distributed_spec()
    order = order_for(spec)
    holders = set(spec.payload["distributed"]["holder_agent_ids"])
    labels, truth = access_labels(FakeContext(spec), order, mode="inverted")
    advertised = set(truth["advertised_holder_agent_ids"])
    assert len(advertised) == len(holders)
    assert advertised.isdisjoint(holders), "the inverted arm must not advertise a true holder"
    assert sum(1 for a in order if labels[a] == HOLDER_LABEL) == len(holders)
    assert truth["true_holder_agent_ids"] == sorted(holders)


def test_false_holder_is_deterministic_a_non_holder_and_varies_across_tasks():
    manifest = Manifest.read("data/manifests/distributed30.json")
    picks = set()
    for spec in manifest.tasks:
        holders = set(spec.payload["distributed"]["holder_agent_ids"])
        non_holders = [a for a in order_for(spec) if a not in holders]
        first = _false_holder(spec.task_id, non_holders)
        assert first == _false_holder(spec.task_id, non_holders)
        assert first in non_holders
        picks.add(first)
    assert len(picks) > 1, "the inverted designation must not be pinned to one member"


def test_sets_labels_show_exactly_the_visible_options_and_no_designation():
    spec = distributed_spec()
    order = order_for(spec)
    visible = spec.payload["distributed"]["visible_by_agent_id"]
    labels, truth = access_labels(FakeContext(spec), order, mode="sets")
    for a in order:
        assert labels[a] == SETS_TEMPLATE.format(", ".join(visible[str(a)]))
        assert "correct answer" not in labels[a]
    assert truth["label_mode"] == "sets"


def test_access_labels_refuse_non_distributed_tasks():
    spec = Manifest.read("data/manifests/distctl30.json").tasks[0]
    with pytest.raises(ValueError, match="no distributed payload"):
        access_labels(FakeContext(spec), [0, 1, 2, 3], mode="truthful")


def test_unknown_mode_is_rejected():
    spec = distributed_spec()
    with pytest.raises(ValueError, match="unknown access-label mode"):
        access_labels(FakeContext(spec), order_for(spec), mode="banana")
