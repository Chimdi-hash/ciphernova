import json

import pytest

from tests.conftest import SOURCE_BODY, case_payload, mock_response


@pytest.mark.parametrize("status,expected", [
    (404, "UNAVAILABLE"), (401, "UNAVAILABLE"), (408, "TRANSIENT_408"),
    (425, "TRANSIENT_425"), (429, "TRANSIENT_429"), (500, "TRANSIENT_5XX"),
    (503, "TRANSIENT_5XX"), (599, "TRANSIENT_5XX"), (302, "REDIRECT"),
])
def test_fetch_status_classification(cp, status, expected):
    case = cp.module._validate_case(json.dumps(case_payload()))
    mock_response(cp.vm, r"docs\.example", status=status)
    fetched = cp.module._fetch(case)
    assert fetched[0]["status_class"] == expected
    assert fetched[0]["available"] is False
    assert fetched[0]["redirect_blocked"] is (expected == "REDIRECT")


def test_fetch_success_normalizes_text_and_binds_digest(cp):
    case = cp.module._validate_case(json.dumps(case_payload()))
    mock_response(cp.vm, r"docs\.example", body="  Fee\n\t is   one percent.  ")
    item = cp.module._fetch(case)[0]
    assert item["status_class"] == "OK"
    assert item["content"] == "Fee is one percent."
    assert item["content_digest"] == cp.module._digest("source-content", item["content"])


def test_provider_exception_is_transient(cp):
    case = cp.module._validate_case(json.dumps(case_payload()))
    item = cp.module._fetch(case)[0]
    assert item["status_class"] == "TRANSIENT_PROVIDER"


@pytest.mark.parametrize("body,expected", [
    ("not-bytes", "INVALID_BODY"), (b"\xff", "INVALID_UTF8"),
    (b"", "EMPTY_CONTENT"), (b"x" * 120001, "OVERSIZED_BODY"),
    (b"x" * 2001, "OVERSIZED_TEXT"), (b"\x00", "INVALID_TEXT"),
])
def test_fetch_body_and_normalized_text_limits(cp, body, expected):
    case = cp.module._validate_case(json.dumps(case_payload()))
    cp.vm.clear_mocks()
    if isinstance(body, str):
        cp.vm.mock_web(r"docs\.example", {
            "method": "GET",
            "response": {
                "status": 200,
                "headers": {"content-type": b"application/json"},
                "body": body,
            },
        })
    else:
        mock_response(cp.vm, r"docs\.example", body=body)
    assert cp.module._fetch(case)[0]["status_class"] == expected
