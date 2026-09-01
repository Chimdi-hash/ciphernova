import hashlib
import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "contract" / "CipherNova.py"


def run_lint(*args):
    return subprocess.run(
        ["genvm-lint", *args, str(CONTRACT), "--json"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )


def test_contract_is_utf8_small_and_pinned():
    data = CONTRACT.read_bytes()
    data.decode("utf-8")
    assert len(data) < 52000
    assert data.startswith(b'# { "Depends": "py-genlayer:')
    assert hashlib.sha256(data).hexdigest()


def test_lint_and_sdk_validation_pass():
    result = run_lint("check")
    assert result.returncode == 0, result.stdout + result.stderr
    value = json.loads(result.stdout)
    assert value["ok"] is True
    assert value["validate"]["ctor_params"] == 0
    assert value["validate"]["methods"] == 10
    assert value["validate"]["view_methods"] == 7
    assert value["validate"]["write_methods"] == 3


def test_typecheck_passes_or_reports_no_errors():
    result = run_lint("typecheck")
    assert result.returncode == 0, result.stdout + result.stderr


def test_abi_is_exactly_three_writes_and_seven_views():
    result = run_lint("schema")
    assert result.returncode == 0, result.stdout + result.stderr
    abi = json.loads(result.stdout)["schema"]
    assert not abi["ctor"]["params"]
    methods = abi["methods"]
    assert set(methods) == {
        "create_case", "evaluate", "retry_evaluation", "get_case", "get_evaluation",
        "get_record", "get_comparison", "is_finalized", "get_creator_case_count",
        "get_creator_case_id",
    }
    assert sum(not value["readonly"] for value in methods.values()) == 3
    assert sum(value["readonly"] for value in methods.values()) == 7


def test_schema_documents_are_valid_and_strict():
    jsonschema = pytest.importorskip("jsonschema")
    for filename in ("case.schema.json", "semantic-comparisons.schema.json"):
        value = json.loads((ROOT / "schemas" / filename).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(value)
