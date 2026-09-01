import pytest

from tests.consensus.test_consensus import prepare
from tests.conftest import mock_response, mock_semantic


def test_restored_validator_independently_reproduces_proposal(cp):
    cloudpickle = pytest.importorskip("cloudpickle")
    prepare(cp)
    stored, _, validator_fn = cp.vm._captured_validators[-1]
    restored = cloudpickle.loads(cloudpickle.dumps(validator_fn))
    cp.vm.clear_mocks()
    for host in (r"docs\.example", r"config\.example", r"metadata\.example"):
        mock_response(cp.vm, host)
    mock_semantic(cp.vm, [
        ("docs", "config", "CONSISTENT"), ("docs", "metadata", "CONFLICT"),
        ("config", "metadata", "CONFLICT"),
    ])
    import genlayer.gl.vm as gl_vm
    assert restored(gl_vm.Return(calldata=stored)) is True
