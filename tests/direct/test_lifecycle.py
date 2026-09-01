import copy
import json

import pytest

from tests.conftest import case_payload, create_case, mock_response, mock_semantic


def finalize_two(cp, statuses=("CONSISTENT",)):
    case_id = create_case(cp)
    mock_response(cp.vm, r"docs\.example")
    mock_response(cp.vm, r"config\.example")
    mock_semantic(cp.vm, [("docs", "config", statuses[0])])
    cp.contract.evaluate(case_id)
    return case_id


def test_permissions_and_finality(cp):
    case_id = create_case(cp)
    with cp.vm.prank(cp.bob):
        with cp.vm.expect_revert("[EXPECTED] AUTH"):
            cp.contract.evaluate(case_id)
    assert cp.contract.is_finalized(case_id) is False
    with cp.vm.expect_revert("[EXPECTED] EVALUATION"):
        cp.contract.retry_evaluation(case_id)
    mock_response(cp.vm, r"docs\.example")
    mock_response(cp.vm, r"config\.example")
    mock_semantic(cp.vm, [("docs", "config", "CONSISTENT")])
    cp.contract.evaluate(case_id)
    assert cp.contract.is_finalized(case_id) is True
    with cp.vm.expect_revert("[EXPECTED] EVALUATION"):
        cp.contract.evaluate(case_id)
    with cp.vm.expect_revert("[EXPECTED] EVALUATION"):
        cp.contract.retry_evaluation(case_id)
    with cp.vm.prank(cp.bob):
        with cp.vm.expect_revert("[EXPECTED] AUTH"):
            cp.contract.retry_evaluation(case_id)


def test_retry_count_and_fourth_retry_rejected(cp):
    case_id = create_case(cp)
    mock_response(cp.vm, r"docs\.example", status=503)
    mock_response(cp.vm, r"config\.example")
    cp.contract.evaluate(case_id)
    assert cp.contract.get_evaluation(case_id)["retry_count"] == 0
    assert "comparisons" not in cp.contract.get_evaluation(case_id)
    for retry_count in (1, 2, 3):
        cp.vm.clear_mocks()
        mock_response(cp.vm, r"docs\.example", status=503)
        mock_response(cp.vm, r"config\.example")
        cp.contract.retry_evaluation(case_id)
        assert cp.contract.get_evaluation(case_id)["retry_count"] == retry_count
    with cp.vm.expect_revert("[EXPECTED] EVALUATION"):
        cp.contract.retry_evaluation(case_id)


@pytest.mark.parametrize("transient_index", [0, 1, 2])
def test_transient_at_first_middle_and_last_record_is_retryable(cp, transient_index):
    case_id = create_case(cp, 3)
    for index, host in enumerate(("docs\\.example", "config\\.example", "metadata\\.example")):
        mock_response(cp.vm, host, status=503 if index == transient_index else 200)
    cp.contract.evaluate(case_id)
    evaluation = cp.contract.get_evaluation(case_id)
    assert evaluation["state"] == "RETRYABLE_FAILURE"
    assert "comparisons" not in evaluation
    with cp.vm.expect_revert("[EXPECTED] EVALUATION"):
        cp.contract.evaluate(case_id)


def test_retry_can_finalize_but_cannot_change_immutable_case(cp):
    case_id = create_case(cp)
    original = cp.contract.get_case(case_id)
    mock_response(cp.vm, r"docs\.example", status=503)
    mock_response(cp.vm, r"config\.example")
    cp.contract.evaluate(case_id)
    cp.vm.clear_mocks()
    mock_response(cp.vm, r"docs\.example", body="Fee is one percent.")
    mock_response(cp.vm, r"config\.example", body="Withdrawal charge: one percent.")
    mock_semantic(cp.vm, [("docs", "config", "CONSISTENT")])
    cp.contract.retry_evaluation(case_id)
    assert cp.contract.get_evaluation(case_id)["state"] == "FINALIZED"
    assert cp.contract.get_case(case_id) == original


def test_views_enforce_state_and_canonical_pair_order(cp):
    case_id = create_case(cp, 3)
    assert cp.contract.get_case(case_id)["records"][0]["record_id"] == "docs"
    with cp.vm.expect_revert("[EXPECTED] EVALUATION"):
        cp.contract.get_evaluation(case_id)
    with cp.vm.expect_revert("[EXPECTED] RECORD"):
        cp.contract.get_record(case_id, "missing")
    with cp.vm.expect_revert("[EXPECTED] EVALUATION"):
        cp.contract.get_comparison(case_id, "docs", "config")
    with cp.vm.expect_revert("[EXPECTED] COMPARISON"):
        cp.contract.get_comparison(case_id, "config", "docs")
    mock_response(cp.vm, r"docs\.example")
    mock_response(cp.vm, r"config\.example")
    mock_response(cp.vm, r"metadata\.example")
    mock_semantic(cp.vm, [
        ("docs", "config", "CONSISTENT"), ("docs", "metadata", "UNRESOLVED"),
        ("config", "metadata", "CONSISTENT"),
    ])
    cp.contract.evaluate(case_id)
    assert cp.contract.get_record(case_id, "config")["source_url"] == "https://config.example/fee.json"
    assert cp.contract.get_comparison(case_id, "docs", "config")["status"] == "CONSISTENT"
    with cp.vm.expect_revert("[EXPECTED] COMPARISON"):
        cp.contract.get_comparison(case_id, "config", "docs")


def test_digest_architecture_binds_definition_observations_comparisons_and_result(cp):
    case_id = finalize_two(cp)
    case = cp.contract.get_case(case_id)
    evaluation = cp.contract.get_evaluation(case_id)
    assert evaluation["case_digest"] == case["case_digest"]
    assert evaluation["observation_digest"] == cp.module._observation_digest(evaluation["source_observations"])
    assert evaluation["evaluation_digest"] == cp.module._evaluation_digest(
        case, evaluation["source_observations"], evaluation["comparisons"],
    )
    assert evaluation["result_digest"] == cp.module._result_digest(
        case, evaluation["source_observations"], evaluation["comparisons"], evaluation["result"],
    )
    definition = {key: case[key] for key in cp.module.CASE_DEFINITION_KEYS}
    for key in ("title", "subject", "consistency_claim"):
        changed = dict(definition)
        changed[key] = changed[key] + " changed"
        assert cp.module._digest("case", changed) != case["case_digest"]
    changed_records = copy.deepcopy(definition["records"])
    changed_records[0]["record_id"] = "changed"
    changed = dict(definition, records=changed_records)
    assert cp.module._digest("case", changed) != case["case_digest"]
    changed_observations = copy.deepcopy(evaluation["source_observations"])
    changed_observations[0]["content_digest"] = "f" * 64
    assert cp.module._observation_digest(changed_observations) != evaluation["observation_digest"]
    changed_comparisons = copy.deepcopy(evaluation["comparisons"])
    changed_comparisons[0]["status"] = "CONFLICT"
    assert cp.module._evaluation_digest(case, evaluation["source_observations"], changed_comparisons) != evaluation["evaluation_digest"]
    assert cp.module._result_digest(case, evaluation["source_observations"], changed_comparisons, "INCONSISTENT") != evaluation["result_digest"]


def test_context_and_prompt_worst_case_fit_with_escaped_valid_values(cp):
    def escaped(size):
        return ('"\\' * (size // 2)) + ('"' if size % 2 else "")

    records = []
    fetched = []
    for index, host in enumerate(("a", "b", "c", "d", "e")):
        prefix, suffix = "https://" + host + ".example/", ".json"
        url = prefix + "a" * (cp.module.MAX_URL - len(prefix) - len(suffix)) + suffix
        record_id = ("a" + "b" * 47)[:-1] + str(index)
        records.append({"record_id": record_id, "label": escaped(cp.module.MAX_LABEL), "source_url": url})
        fetched.append({
            "record_id": record_id, "record_index": index, "url": url,
            "status_class": "OK", "available": True, "media_accepted": True,
            "redirect_blocked": False, "content_digest": "f" * 64,
            "content": escaped(cp.module.MAX_SOURCE_TEXT),
        })
    case = {
        "schema_version": "1.0", "title": escaped(cp.module.MAX_TITLE),
        "subject": escaped(cp.module.MAX_SUBJECT),
        "consistency_claim": escaped(cp.module.MAX_CONSISTENCY_CLAIM),
        "records": records,
    }
    # The source IDs are intentionally valid lower-case identifiers, and all five URLs
    # are valid normalized HTTPS textual URLs at the configured bound.
    semantic_pairs = cp.module._semantic_pairs(case, fetched, cp.module._all_pairs(case))
    context = cp.module._context(case, fetched, semantic_pairs)
    prompt = cp.module._semantic_prompt(context)
    assert len(context.encode("utf-8")) == 39761
    assert len(prompt.encode("utf-8")) == 41200
    assert len(context.encode("utf-8")) <= cp.module.MAX_CONTEXT
    assert len(prompt.encode("utf-8")) <= cp.module.MAX_PROMPT
    oversized = case_payload()
    oversized["title"] = "x" * (cp.module.MAX_TITLE + 1)
    with cp.vm.expect_revert("[EXPECTED] CASE"):
        cp.contract.create_case(json.dumps(oversized))
    assert cp.contract.get_creator_case_count(cp.module._address_text(cp.alice)) == 0
