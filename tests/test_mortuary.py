import sys

import pytest

import mortuary


class FakeError(Exception):
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_dump(tmp_path):
    dump_file = tmp_path / "dump.pkl"
    with pytest.raises(FakeError) as excinfo:
        with mortuary.context(dump_file):
            raise FakeError(message="Test message")

    assert excinfo.value.message == "Test message"
    dump = mortuary.read(dump_file)

    assert dump["dump_version"] == mortuary.MORTUARY_DUMP_VERSION
    assert dump["python_executable"] == sys.executable
    for path in dump["python_path"]:
        assert path in sys.path

    tb = dump["traceback"]
    assert tb.tb_lineno == 18
