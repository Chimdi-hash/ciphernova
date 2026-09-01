import json

import pytest

from tests.conftest import SOURCE_URLS, case_payload, create_case, mock_response, records_payload


@pytest.mark.parametrize("count,expected", [(2, 1), (3, 3), (4, 6), (5, 10)])
def test_valid_record_counts_and_nested_loop_pair_counts(cp, count, expected):
    case_id = create_case(cp, count)
    case = cp.contract.get_case(case_id)
    assert len(case["records"]) == count
    assert len(cp.module._all_pairs(case)) == expected


@pytest.mark.parametrize("count", [1, 6, 0])
def test_record_count_is_bounded(cp, count):
    value = case_payload(5 if count == 6 else count)
    if count == 6:
        value["records"].append({
            "record_id": "sixth", "label": "Sixth record",
            "source_url": "https://sixth.example/fee.json",
        })
    with cp.vm.expect_revert("[EXPECTED] CASE"):
        cp.contract.create_case(json.dumps(value))
    assert cp.contract.get_creator_case_count(cp.module._address_text(cp.alice)) == 0


def test_creator_is_sender_derived_and_case_definition_is_immutable(cp):
    case_id = create_case(cp)
    case = cp.contract.get_case(case_id)
    assert case["creator"] == cp.module._address_text(cp.alice)
    assert case["case_id"] == case_id
    assert isinstance(case["created_at"], int)
    assert len(case["case_digest"]) == 64
    assert not hasattr(cp.contract, "update_case")
    assert not hasattr(cp.contract, "cancel_case")


def test_any_valid_caller_can_create_a_case(cp):
    with cp.vm.prank(cp.bob):
        case_id = cp.contract.create_case(json.dumps(case_payload()))
    assert cp.contract.get_case(case_id)["creator"] == cp.module._address_text(cp.bob)


@pytest.mark.parametrize("raw", [
    '{"schema_version":"1.0","title":"x","subject":"x","consistency_claim":"x","records":[]}',
    '{"schema_version":"1.0","title":"x","subject":"x","consistency_claim":"x","records":[],"extra":1}',
    '{"schema_version":"1.0","title":"x","subject":"x","consistency_claim":"x","records":[',
    '{"schema_version":"1.0","title":"x","title":"y","subject":"x","consistency_claim":"x","records":[]}',
])
def test_case_parser_requires_exact_json_and_rejects_duplicate_top_level_keys(cp, raw):
    with cp.vm.expect_revert("[EXPECTED] CASE"):
        cp.contract.create_case(raw)
    assert cp.contract.get_creator_case_count(cp.module._address_text(cp.alice)) == 0


def test_nested_record_shape_and_duplicate_keys_are_strict(cp):
    value = case_payload()
    value["records"][0]["extra"] = True
    with cp.vm.expect_revert("[EXPECTED] CASE"):
        cp.contract.create_case(json.dumps(value))
    value = case_payload()
    value["records"][0] = {"record_id": "docs", "label": "x"}
    with cp.vm.expect_revert("[EXPECTED] CASE"):
        cp.contract.create_case(json.dumps(value))
    raw = (
        '{"schema_version":"1.0","title":"x","subject":"x",'
        '"consistency_claim":"x","records":['
        '{"record_id":"docs","record_id":"other","label":"x",'
        '"source_url":"https://docs.example/fee.json"},'
        '{"record_id":"config","label":"x",'
        '"source_url":"https://config.example/fee.json"}]}'
    )
    with cp.vm.expect_revert("[EXPECTED] CASE"):
        cp.contract.create_case(raw)


@pytest.mark.parametrize("field,limit", [
    ("title", 160), ("subject", 800), ("consistency_claim", 2000),
])
def test_case_text_byte_bounds(cp, field, limit):
    value = case_payload()
    value[field] = "x" * (limit + 1)
    with cp.vm.expect_revert("[EXPECTED] CASE"):
        cp.contract.create_case(json.dumps(value))


def test_label_byte_bound_and_whitespace_only_text_rejected(cp):
    value = case_payload()
    value["records"][0]["label"] = "x" * 161
    with cp.vm.expect_revert("[EXPECTED] CASE"):
        cp.contract.create_case(json.dumps(value))
    value = case_payload()
    value["records"][0]["label"] = " \t\n "
    with cp.vm.expect_revert("[EXPECTED] CASE"):
        cp.contract.create_case(json.dumps(value))
    assert cp.contract.get_creator_case_count(cp.module._address_text(cp.alice)) == 0


@pytest.mark.parametrize("record_id", [
    "", "Bad", "has space", "bad.dot", "bad/slash", "-starts", "a" * 49,
])
def test_record_id_format_and_bounds(cp, record_id):
    value = case_payload()
    value["records"][0]["record_id"] = record_id
    with cp.vm.expect_revert("[EXPECTED] CASE"):
        cp.contract.create_case(json.dumps(value))


def test_maximum_record_id_is_accepted_and_duplicate_ids_rejected(cp):
    value = case_payload()
    value["records"][0]["record_id"] = "a" + "b" * 47
    case_id = cp.contract.create_case(json.dumps(value))
    assert cp.contract.get_record(case_id, "a" + "b" * 47)["record_id"] == "a" + "b" * 47
    value = case_payload()
    value["records"][1]["record_id"] = value["records"][0]["record_id"]
    with cp.vm.expect_revert("[EXPECTED] CASE"):
        cp.contract.create_case(json.dumps(value))


def test_creator_index_is_one_based_and_preserves_creation_order(cp):
    first = create_case(cp)
    second = create_case(cp, count=3)
    creator = cp.module._address_text(cp.alice)
    assert cp.contract.get_creator_case_count(creator) == 2
    assert cp.contract.get_creator_case_id(creator, 1) == first
    assert cp.contract.get_creator_case_id(creator, 2) == second
    with cp.vm.expect_revert("[EXPECTED] CASE"):
        cp.contract.get_creator_case_id(creator, 0)
    with cp.vm.expect_revert("[EXPECTED] CASE"):
        cp.contract.get_creator_case_id(creator, 3)


def test_case_id_format_and_unknown_case_validation(cp):
    case_id = create_case(cp)
    assert cp.module.CASE_ID.fullmatch(case_id)
    with cp.vm.expect_revert("[EXPECTED] CASE"):
        cp.contract.get_case("consistency-" + "0" * 63)
    with cp.vm.expect_revert("[EXPECTED] CASE"):
        cp.contract.get_case("not-a-case")


@pytest.mark.parametrize("url", [
    "http://example.com/fee.json",
    "https://user:pass@example.com/fee.json",
    "https://example.com/fee.json?x=1",
    "https://example.com/fee.json?",
    "https://example.com/fee.json#fragment",
    "https://example.com:443/fee.json",
    "https://example.com:8443/fee.json",
    "https://example.com:/fee.json",
    "https://localhost/fee.json",
    "https://example.local/fee.json",
    "https://example.internal/fee.json",
    "https://example.lan/fee.json",
    "https://example.invalid/fee.json",
    "https://example.test/fee.json",
    "https://127.0.0.1/fee.json",
    "https://127.1/fee.json",
    "https://[::1]/fee.json",
    "https://2130706433/fee.json",
    "https://0x7f000001/fee.json",
    "https://127.0.0.1.1/fee.json",
    "https://éxample.com/fee.json",
    "https://example.com/fee.html",
    "https://example.com/%ZZ/fee.json",
    "https://example.com/a%5Cb/fee.json",
    "https://example.com/a b/fee.json",
    "https://example.com/a\tb/fee.json",
])
def test_source_url_security_rejects_unsafe_inputs(cp, url):
    value = case_payload()
    value["records"][0]["source_url"] = url
    with cp.vm.expect_revert("[EXPECTED] CASE"):
        cp.contract.create_case(json.dumps(value))


@pytest.mark.parametrize("url", [
    "https://EXAMPLE.COM/fee.json",
    "https://example.com./fee.json",
    "https://example.com/a/%2e%2e/fee.json",
])
def test_source_url_normalizes_authority_and_dot_segments(cp, url):
    value = case_payload()
    value["records"][0]["source_url"] = url
    case_id = cp.contract.create_case(json.dumps(value))
    assert cp.contract.get_record(case_id, "docs")["source_url"] == "https://example.com/fee.json"


def test_duplicate_normalized_source_url_is_rejected(cp):
    value = case_payload()
    value["records"][1]["source_url"] = "https://DOCS.EXAMPLE./fee.json"
    with cp.vm.expect_revert("[EXPECTED] CASE"):
        cp.contract.create_case(json.dumps(value))


def test_url_maximum_and_raw_json_preflight_bounds(cp):
    prefix, suffix = "https://example.com/", ".json"
    value = case_payload()
    value["records"][0]["source_url"] = prefix + "a" * (cp.module.MAX_URL - len(prefix) - len(suffix)) + suffix
    case_id = cp.contract.create_case(json.dumps(value))
    assert len(cp.contract.get_record(case_id, "docs")["source_url"]) == cp.module.MAX_URL
    oversized = case_payload()
    oversized["title"] = "x" * 160
    raw = json.dumps(oversized) + (" " * cp.module.MAX_JSON)
    with cp.vm.expect_revert("[EXPECTED] CASE"):
        cp.contract.create_case(raw)


@pytest.mark.parametrize("media,accepted", [
    ("text/plain", True), ("text/markdown", True), ("application/json", True),
    ("application/ld+json", True), ("application/xml", True), ("text/xml", True),
    ("application/vnd.example+json", True), ("application/vnd.example+xml", True),
    ("image/svg+xml", False), ("image/png", False), ("image/jpeg", False),
    ("application/pdf", False), ("text/html", False), ("application/octet-stream", False),
])
def test_textual_media_policy(cp, media, accepted):
    case = cp.module._validate_case(json.dumps(case_payload()))
    cp.vm.clear_mocks()
    mock_response(cp.vm, r"docs\.example", media=media)
    fetched = cp.module._fetch(case)
    assert fetched[0]["status_class"] == ("OK" if accepted else "REJECTED_MEDIA")
    assert fetched[0]["available"] is accepted
