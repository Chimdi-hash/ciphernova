import copy

import pytest

from tests.conftest import create_case, mock_response, mock_semantic


def prepare(cp, count=3):
    case_id = create_case(cp, count)
    for host in (r"docs\.example", r"config\.example", r"metadata\.example")[:count]:
        mock_response(cp.vm, host)
    pairs = [
        ("docs", "config", "CONSISTENT"),
        ("docs", "metadata", "CONFLICT"),
        ("config", "metadata", "CONFLICT"),
    ][: ({2: 1, 3: 3}[count])]
    mock_semantic(cp.vm, pairs)
    cp.contract.evaluate(case_id)
    return case_id


def test_consensus_closures_are_serializable(cp):
    cloudpickle = pytest.importorskip("cloudpickle")
    prepare(cp)
    stored, leader_fn, validator_fn = cp.vm._captured_validators[-1]
    assert stored["state"] == "FINALIZED"
    assert cloudpickle.loads(cloudpickle.dumps(leader_fn)) is not None
    assert cloudpickle.loads(cloudpickle.dumps(validator_fn)) is not None


def test_validator_refetches_and_reruns_complete_semantic_proposal(cp):
    case_id = prepare(cp)
    cp.vm.clear_mocks()
    for host in (r"docs\.example", r"config\.example", r"metadata\.example"):
        mock_response(cp.vm, host)
    mock_semantic(cp.vm, [
        ("docs", "config", "CONSISTENT"), ("docs", "metadata", "CONFLICT"),
        ("config", "metadata", "CONFLICT"),
    ])
    assert cp.vm.run_validator() is True
    cp.vm.clear_mocks()
    for host in (r"docs\.example", r"config\.example", r"metadata\.example"):
        mock_response(cp.vm, host)
    mock_semantic(cp.vm, [
        ("docs", "config", "CONSISTENT"), ("docs", "metadata", "CONSISTENT"),
        ("config", "metadata", "CONFLICT"),
    ])
    assert cp.vm.run_validator() is False
    assert case_id.startswith("consistency-")


@pytest.mark.parametrize("mutator", [
    lambda p: {**p, "case_id": "consistency-" + "0" * 64},
    lambda p: {**p, "case_digest": "0" * 64},
    lambda p: {**p, "source_observations": p["source_observations"][:1]},
    lambda p: {**p, "source_observations": list(reversed(p["source_observations"]))},
    lambda p: {**p, "observation_digest": "0" * 64},
    lambda p: {**p, "comparisons": p["comparisons"][:1]},
    lambda p: {**p, "comparisons": list(reversed(p["comparisons"]))},
    lambda p: {**p, "comparisons": [
        {**p["comparisons"][0], "left_record_id": "metadata"}, *p["comparisons"][1:],
    ]},
    lambda p: {**p, "extra": True},
])
def test_validator_rejects_binding_reorder_missing_extra_and_status_tampering(cp, mutator):
    prepare(cp)
    leader = copy.deepcopy(cp.vm._captured_validators[-1][0])
    cp.vm.clear_mocks()
    for host in (r"docs\.example", r"config\.example", r"metadata\.example"):
        mock_response(cp.vm, host)
    mock_semantic(cp.vm, [
        ("docs", "config", "CONSISTENT"), ("docs", "metadata", "CONFLICT"),
        ("config", "metadata", "CONFLICT"),
    ])
    assert cp.vm.run_validator(leader_result=mutator(leader)) is False


def test_validator_rejects_changed_source_status_or_digest(cp):
    prepare(cp)
    leader = copy.deepcopy(cp.vm._captured_validators[-1][0])
    for changed in (0, 1, 2):
        cp.vm.clear_mocks()
        for index, host in enumerate((r"docs\.example", r"config\.example", r"metadata\.example")):
            mock_response(cp.vm, host, status=404 if index == changed else 200)
        assert cp.vm.run_validator(leader_result=leader) is False


@pytest.mark.parametrize("field,new_value", [
    ("record_id", "changed"), ("record_index", 99),
    ("url", "https://changed.example/fee.json"), ("status_class", "UNAVAILABLE"),
    ("available", False), ("media_accepted", False), ("redirect_blocked", True),
    ("content_digest", "0" * 64),
])
def test_validator_rejects_each_bound_observation_field_mutation(cp, field, new_value):
    prepare(cp)
    leader = copy.deepcopy(cp.vm._captured_validators[-1][0])
    leader["source_observations"][0][field] = new_value
    cp.vm.clear_mocks()
    for host in (r"docs\.example", r"config\.example", r"metadata\.example"):
        mock_response(cp.vm, host)
    mock_semantic(cp.vm, [
        ("docs", "config", "CONSISTENT"), ("docs", "metadata", "CONFLICT"),
        ("config", "metadata", "CONFLICT"),
    ])
    assert cp.vm.run_validator(leader_result=leader) is False
