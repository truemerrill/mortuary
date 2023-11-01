"""
The MIT License (MIT)
Copyright (C) 2012 Eli Finer <eli.finer@gmail.com>
Copyright (C) 2023 True Merrill <true.merrill@gmail.com>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

import builtins
import pickle
import sys
from argparse import ArgumentParser
from pathlib import Path
from traceback import print_tb
from types import CodeType, FrameType, TracebackType
from typing import Any, Callable, Optional, Type, Union

try:
    import dill  # type: ignore
except ModuleNotFoundError:
    dill = None

try:
    # TODO: TypedDict was added in 3.8.  Remove this when 3.7 is dropped.
    from typing import TypedDict
except ImportError:

    class TypedDict:  # type: ignore
        pass


__version__ = "0.1.1"


__all__ = (
    "dump",
    "log",
    "read",
    "debug",
    "context",
)


MORTUARY_DUMP_VERSION = 1


# Type aliases
PostMortemFn = Union[
    Callable[[TracebackType], None], Callable[["TracebackProxy"], None]
]
TracebackLike = Union[TracebackType, "TracebackProxy"]
PathLike = Union[str, Path]
PathCallbackFn = Callable[
    [Type[BaseException], BaseException, TracebackType],
    Union[PathLike, None],
]
AfterCallbackFn = Callable[[], None]


def _convert(v: Any) -> Any:
    if dill is not None:
        try:
            dill.dumps(v)
            return v
        except Exception:
            return _safe_repr(v)
    else:
        from datetime import date, datetime, time, timedelta

        builtin = (str, int, float, date, time, datetime, timedelta)
        # XXX: what about bytes and bytearray?

        if v is None:
            return v

        if type(v) in builtin:
            return v

        if type(v) is tuple:
            return tuple(_convert_seq(v))

        if isinstance(v, list):
            return list(_convert_seq(v))

        if isinstance(v, set):
            return set(_convert_seq(v))

        if isinstance(v, dict):
            return _convert_dict(v)

        return _safe_repr(v)


def _safe_repr(v: Any) -> str:
    try:
        return repr(v)
    except Exception as e:
        return "repr error: " + str(e)


def _convert_seq(v):
    return (_convert(i) for i in v)


def _convert_dict(v):
    return {_convert(k): _convert(i) for (k, i) in v.items()}


def _convert_obj(obj):
    try:
        return ClassProxy(_safe_repr(obj), _convert_dict(obj.__dict__))
    except Exception:
        return _convert(obj)


def _remove_builtins(tb: "TracebackProxy"):
    while tb:
        frame = tb.tb_frame
        while frame:
            frame.f_globals = {
                k: v
                for k, v in frame.f_globals.items()
                if k not in dir(builtins)
            }
            frame = frame.f_back  # type: ignore
        tb = tb.tb_next  # type: ignore


def _insert_builtins(tb: "TracebackProxy"):
    while tb:
        frame = tb.tb_frame
        while frame:
            frame.f_globals.update(builtins.__dict__)
            frame = frame.f_back  # type: ignore
        tb = tb.tb_next  # type: ignore


def _get_files(tb: "TracebackProxy") -> "dict[str, list[str]]":
    files = {}
    while tb:
        frame = tb.tb_frame
        while frame:
            filename = frame.f_code.co_filename
            if filename not in files:
                try:
                    with open(filename) as f:
                        files[filename] = f.readlines()
                except FileNotFoundError:
                    files[filename] = [
                        f"couldn't locate {filename} during dump"
                    ]
            frame = frame.f_back  # type: ignore
        tb = tb.tb_next  # type: ignore
    return files


# --- Proxies -----------------------------------------------------------------
#
# Proxy types are Pickle-serializable implementations of Python tracebacks.
# These are interchangeable with the original types in the sense of ducktyping.
# When a user attaches a debugger to a traceback dump, the debugger is actually
# interacting with these proxy types (which are restored from the pickle file)
# rather than the original Python traceback.


class CoLinesProxy:
    def __init__(self, co_lines):
        self._co_lines = list(co_lines())

    def __call__(self):
        yield from self._co_lines


class CodeProxy:
    def __init__(self, code: CodeType):
        self.co_filename = str(Path(code.co_filename).resolve())
        self.co_name = code.co_name
        self.co_argcount = code.co_argcount
        self.co_kwonlyargcount = code.co_kwonlyargcount
        self.co_consts = tuple(
            CodeProxy(c) if hasattr(c, "co_filename") else c
            for c in code.co_consts
        )
        self.co_firstlineno = code.co_firstlineno
        self.co_lnotab = code.co_lnotab
        self.co_varnames = code.co_varnames
        self.co_flags = code.co_flags
        self.co_code = code.co_code

        if hasattr(code, "co_lines"):
            self.co_lines = CoLinesProxy(code.co_lines)


class ClassProxy:
    def __init__(self, repr_, vars_):
        self._repr = repr_
        self.__dict__.update(vars_)

    def __repr__(self):
        return self._repr


class FrameProxy:
    def __init__(self, frame: FrameType):
        self.f_code = CodeProxy(frame.f_code)
        self.f_locals = _convert_dict(frame.f_locals)
        self.f_globals = _convert_dict(frame.f_globals)
        self.f_lineno = frame.f_lineno
        self.f_back = FrameProxy(frame.f_back) if frame.f_back else None

        if "self" in self.f_locals:
            self.f_locals["self"] = _convert_obj(frame.f_locals["self"])


class TracebackProxy:
    def __init__(self, traceback: TracebackType):
        self.tb_frame = FrameProxy(traceback.tb_frame)
        self.tb_lineno = traceback.tb_lineno
        self.tb_next = (
            TracebackProxy(traceback.tb_next) if traceback.tb_next else None
        )
        self.tb_lasti = 0


# --- Traceback serialize / deserialize ---------------------------------------


class TracebackDump(TypedDict):
    dump_version: int
    traceback: TracebackProxy
    files: "dict[str, list[str]]"
    python_version: str
    python_executable: str
    python_path: "list[str]"


def dump(filename: PathLike, tb: Optional[TracebackLike] = None):
    """Dump a traceback to a pickle file for later analysis.

    Args:
        filename (PathLike): the dump file
        tb (TracebackLike, optional): the traceback to dump. If not provided,
            defaults to the traceback on `sys.exc_info()` (i.e. the last thrown
            error).
    """
    if not isinstance(filename, Path):
        filename = Path(filename)
    if tb is None:
        tb = sys.exc_info()[2]
    if tb is None:
        msg = "could not resolve traceback"
        raise ValueError(msg)

    tb_proxy = TracebackProxy(tb)  # type: ignore
    _remove_builtins(tb_proxy)

    dump = {
        "dump_version": MORTUARY_DUMP_VERSION,
        "traceback": tb_proxy,
        "files": _get_files(tb_proxy),
        "python_version": sys.version,
        "python_executable": sys.executable,
        "python_path": sys.path,
    }
    filename.parent.mkdir(exist_ok=True, parents=True)
    with open(filename, "wb") as f:
        if dill is not None:
            dill.dump(dump, f)
        else:
            pickle.dump(dump, f, protocol=pickle.HIGHEST_PROTOCOL)


def log(filename: PathLike, tb: Optional[TracebackType] = None):
    """Write a traceback to a log file.

    Args:
        filename (PathLike): the log file
        tb (TracebackType, optional): the traceback to dump. If not provided,
            defaults to the traceback on `sys.exc_info()` (i.e. the last thrown
            error).
    """
    if not isinstance(filename, Path):
        filename = Path(filename)
    if tb is None:
        tb = sys.exc_info()[2]
    filename.parent.mkdir(exist_ok=True, parents=True)
    with open(filename, "w") as f:
        f.write("Traceback (most recent call last):\n")
        print_tb(tb, file=f)


def read(filename: PathLike) -> TracebackDump:
    """Read a traceback dump from a pickle file for analysis.

    Args:
        filename (PathLike): the dump file

    Returns:
        TracebackDump: the traceback dump
    """
    with open(filename, "rb") as f:
        if dill is not None:
            try:
                return dill.load(f)
            except pickle.UnpicklingError:
                pass
        return pickle.load(f)  # noqa: S301


def _monkey_patch_inspect(inspect):
    inspect.isframe = (
        lambda obj: isinstance(obj, FrameType)
        or obj.__class__.__name__ == "FrameProxy"
    )
    inspect.iscode = (
        lambda obj: isinstance(obj, CodeType)
        or obj.__class__.__name__ == "CodeProxy"
    )
    inspect.isclass = (
        lambda obj: isinstance(obj, type)
        or obj.__class__.__name__ == "ClassProxy"
    )
    inspect.istraceback = (
        lambda obj: isinstance(obj, TracebackType)
        or obj.__class__.__name__ == "TracebackProxy"
    )


def _monkey_patch_linecache(linecache, dump: TracebackDump):
    original_getlines = linecache.getlines

    def getlines(filename, module_globals=None):
        if filename in dump["files"]:
            return dump["files"][filename]
        return original_getlines(filename, module_globals)

    linecache.checkcache = lambda _=None: None
    linecache.getlines = getlines


def debug(filename: PathLike, post_mortem: Optional[PostMortemFn] = None):
    """Attach a debugger to a traceback dump file.

    Note:
        This function will launch an interactive debugger session.

    Args:
        filename (PathLike): the dump file
        post_mortem (PostMortemFn, optional): callback used to enter
            post-mortem debugging of a traceback. This callback allows you to
            use any python debugger you like, so long as it provides a
            post_mortem function. If not provided, defaults to pdb.post_mortem.
    """
    import inspect
    import linecache

    if not isinstance(filename, Path):
        filename = Path(filename)
    if post_mortem is None:
        from pdb import post_mortem
    if post_mortem is None:
        raise ValueError()

    dump = read(filename)
    tb = dump["traceback"]

    _monkey_patch_inspect(inspect)
    _monkey_patch_linecache(linecache, dump)
    _insert_builtins(tb)
    post_mortem(tb)  # type: ignore


# --- Context manager ---------------------------------------------------------


def _resolve_path(
    path: Union[PathLike, PathCallbackFn, None],
    exc_type: Type[BaseException],
    exc_value: BaseException,
    traceback: TracebackType,
) -> Union[Path, None]:
    def _as_path(path: Union[PathLike, None]) -> Union[Path, None]:
        return Path(path) if path is not None else None

    if path is None:
        return None
    elif callable(path):
        return _as_path(path(exc_type, exc_value, traceback))
    else:
        return Path(path) if isinstance(path, str) else path


class TracebackContextManager:
    """Context manager to capture exceptions and create traceback files."""

    def __init__(
        self,
        dump: Optional[Union[PathLike, PathCallbackFn]] = None,
        log: Optional[Union[PathLike, PathCallbackFn]] = None,
        after: Optional[AfterCallbackFn] = None,
    ):
        self.dump = dump if dump is not None else Path("traceback-dump.pkl")
        self.log = log
        self.after = after

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        exc_traceback: Optional[TracebackType],
    ):
        if (
            (exc_type is not None)
            and (exc_value is not None)
            and (exc_traceback is not None)
        ):
            dump_file = _resolve_path(
                self.dump, exc_type, exc_value, exc_traceback
            )
            log_file = _resolve_path(
                self.log, exc_type, exc_value, exc_traceback
            )

            if dump_file:
                dump(dump_file, exc_traceback)
            if log_file:
                log(log_file, exc_traceback)
            if self.after:
                self.after()
        return False


def context(
    dump: Optional[Union[PathLike, PathCallbackFn]] = None,
    log: Optional[Union[PathLike, PathCallbackFn]] = None,
    after: Optional[AfterCallbackFn] = None,
) -> TracebackContextManager:
    """Execute code within a traceback context manager.

    Note:
        This context manager does not capture exceptions.  Any exceptions
        raised by the enclosed code will continue to propagate after being
        logged by the context manager.

    Examples:
        >>> with context():
        >>>     print(1 / 0)

    Args:
        dump (PathLike, PathCallbackFn, optional): the traceback dump file. If
            this argument is a Path or string it is treated as a the filename
            of the dump file. If instead this argument is a callback function,
            the callback is evaluated when the exception is detected. The
            callback returns the filename of the dump file or `None` if no
            dump file should be captured. Defaults to "traceback-dump.pkl".
        log (PathLike, PathCallbackFn, optional): the traceback log file. If
            this argument is a Path or string it is treated as a the filename
            of the traceback log file. If instead this argument is a callback
            function, the callback is evaluated when the exception is detected.
            The callback returns the filename of the log file or `None` if no
            log file should be captured. Defaults to None.
        after (AfterCallbackFn, optional): callback executed after the
            exception is logged and immediately prior to exiting the context.
            This callback is used to execute arbitrary cleanup code.  Defaults
            to None.

    Returns:
        TracebackContextManager: the traceback context
    """
    return TracebackContextManager(dump, log, after)


def cli():
    """Simple CLI to launch an interactive debugging session."""

    def get_post_mortem_func(debugger: str) -> Union[PostMortemFn, None]:
        post_mortem = None
        try:
            if debugger == "pdb":
                from pdb import post_mortem  # type: ignore
            elif debugger == "ipdb":
                from ipdb import post_mortem  # type: ignore
        except ImportError:
            pass
        return post_mortem

    parser = ArgumentParser(
        description="Launch a debugging session from a dump file"
    )
    parser.add_argument(
        "-d", "--debugger", nargs=1, choices=["pdb", "ipdb"], default="pdb"
    )
    parser.add_argument("filename")
    args = parser.parse_args()
    debug(Path.cwd() / args.filename, get_post_mortem_func(args.debugger))


if __name__ == "__main__":
    cli()
