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


def test_dump_path_callback(tmp_path):
    dump_file = tmp_path / "dump.pkl"

    class DumpPathCallback:
        """A callable that tracks if it's been called"""

        def __init__(self):
            self.triggered = False

        def __call__(self, exc_type, exc_value, traceback):  # noqa: ARG002
            self.triggered = True
            return dump_file

    dump_path_callback = DumpPathCallback()

    assert dump_path_callback.triggered is False
    assert dump_file.exists() is False
    with pytest.raises(FakeError):
        with mortuary.context(dump=dump_path_callback):
            raise FakeError(message="Test message")

    assert dump_path_callback.triggered is True
    assert dump_file.exists() is True
