import json
import sys
from types import SimpleNamespace

import pytest


CREATED = "2026-01-01T00:00:00+00:00"
SOURCE_URLS = [
    "https://docs.example/fee.json",
    "https://config.example/fee.json",
    "https://metadata.example/fee.json",
    "https://api.example/fee.json",
    "https://public.example/fee.json",
]
SOURCE_BODY = "Withdrawal fee: one percent."


def address_text(value):
    if isinstance(value, bytes):
        return "0x" + value.hex()
    candidate = getattr(value, "as_hex", None)
    if callable(candidate):
        return candidate().lower()
    if isinstance(candidate, str):
        return candidate.lower()
    return str(value).lower()


def set_time(vm, value=CREATED):
    vm.warp(value)
    module = sys.modules.get("genlayer.gl")
    if module is not None and getattr(module, "message_raw", None) is not None:
        module.message_raw["datetime"] = value


def records_payload(count=2):
    return [
        {
            "record_id": ["docs", "config", "metadata", "api", "public"][index],
            "label": [
                "Official documentation", "Public configuration", "Public metadata",
                "Service API", "Published record",
            ][index],
            "source_url": SOURCE_URLS[index],
        }
        for index in range(count)
    ]


def case_payload(count=2, **overrides):
    value = {
        "schema_version": "1.0",
        "title": "Protocol Fee Consistency",
        "subject": "Protocol X withdrawal fee",
        "consistency_claim": "These records are expected to describe the same withdrawal fee.",
        "records": records_payload(count),
    }
    value.update(overrides)
    return value


def mock_response(vm, pattern, body=SOURCE_BODY, status=200, media="application/json"):
    if isinstance(body, str):
        body = body.encode("utf-8")
    vm.mock_web(pattern, {
        "method": "GET",
        "response": {
            "status": status,
            "headers": {"content-type": media.encode("ascii")},
            "body": body,
        },
    })


def mock_semantic(vm, statuses):
    vm.mock_llm(
        r"CipherNova v1 semantic pair evaluator",
        json.dumps({
            "comparisons": [
                {"left_record_id": left, "right_record_id": right, "status": status}
                for left, right, status in statuses
            ],
        }),
    )


@pytest.fixture
def cp(request):
    try:
        direct_vm = request.getfixturevalue("direct_vm")
        direct_deploy = request.getfixturevalue("direct_deploy")
        direct_alice = request.getfixturevalue("direct_alice")
        direct_bob = request.getfixturevalue("direct_bob")
        direct_charlie = request.getfixturevalue("direct_charlie")
    except pytest.FixtureLookupError:
        pytest.skip("genlayer-test direct fixtures are not installed")
    direct_vm.sender = direct_alice
    set_time(direct_vm)
    contract = direct_deploy("contract/CipherNova.py")
    module = sys.modules[contract.__class__.__module__]
    return SimpleNamespace(
        contract=contract,
        module=module,
        vm=direct_vm,
        alice=direct_alice,
        bob=direct_bob,
        charlie=direct_charlie,
    )


def create_case(cp, count=2, **overrides):
    return cp.contract.create_case(json.dumps(case_payload(count, **overrides)))


def mock_all_sources(cp, count=2, body=SOURCE_BODY, media="application/json"):
    for url in SOURCE_URLS[:count]:
        host = url.split("/")[2]
        mock_response(cp.vm, host.replace(".", r"\."), body=body, media=media)
