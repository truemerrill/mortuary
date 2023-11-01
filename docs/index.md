---
hide:
  - navigation
---

![alt text](https://github.com/truemerrill/mortuary/blob/main/docs/assets/logo-color.png?raw=true)

![Tests](https://github.com/truemerrill/mortuary/actions/workflows/python-test.yml/badge.svg)
[![Documentation](https://github.com/truemerrill/mortuary/actions/workflows/pages-publish.yml/badge.svg)](https://truemerrill.github.io/mortuary/)
[![PyPI - Version](https://img.shields.io/pypi/v/mortuary.svg)](https://pypi.org/project/mortuary)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/mortuary.svg)](https://pypi.org/project/mortuary)

-----

# Mortuary

Mortuary is a dead-simple post-mortem debugging tool for Python.  It provides a
context manager to grab uncaught exceptions, dumps a traceback into a portable
pickle format, and later allows you to attach a debugger to the traceback file.

* _Dead simple_: Mortuary is a single < 500 line Python file.
* _No dependencies_: Mortuary has no dependencies outside the standard library.
  `dill` and `ipdb` are optional dependencies.
* _Portable_: Mortuary's dump files are portable between different versions of
  Python and different machines.  Attach dump files to tickets to share a
  debugging context between developers.

## Example

Here is a script with an error in it.

```python
import mortuary

def is_even(number):
    return number % 2 == 0

def add(a, b):
    return a + b

with mortuary.context():
    is_even(add("1", "2"))

```

Running this script will raise a `ValueError` and print a traceback.
Additionally Mortuary will create a `traceback-dump.pkl` file.

```bash
$ python script.py 
Traceback (most recent call last):
  File "script.py", line 13, in <module>
    is_even(add("1", "2"))
  File "script.py", line 5, in is_even
    return number % 2 == 0
           ~~~~~~~^~~
TypeError: not all arguments converted during string formatting
$ ls | grep dump.pkl
traceback-dump.pkl
```
Later, we can open a debugger session using the dump file

```bash
$ python -m mortuary traceback-dump.pkl
> script.py(5)is_even()
-> return number % 2 == 0
(Pdb) p number
'12'
```

## Installation

Mortuary is distributed on PyPI and is pip-installable

```console
pip install mortuary
```
Alternatively, you can simply copy the `mortuary.py` file directly into your project.

## Reference

### Types

::: mortuary.PathLike

The type of an object that can be coerced into a path to a file.


::: mortuary.PathCallbackFn

The type of a callback function that can resolve a file path.  

!!! note
    `PathCallbackFn` callbacks are executed when an exception is detected by
    the mortuary context.  Callbacks must accept the exception type, the exception, and the traceback as input arguments and return the path
    to the file or `None` if no file should be written.  This behavior makes
    it possible to control **when** and **where** traceback files are created.

**Examples:**

```python

# Only capture dumps from a particular exception type

def dump_path(exc_type, exc_value, exc_traceback):
    if exc_type is MySpecialException:
        return "dump.pkl"
    return None

with mortuary.context(dump=dump_path):
    risky_code()
```

```python

# Use a filename that depends on data that is only available when the exception
# is raised

def dump_path(exc_type, exc_value, exc_traceback):
    filename = exc_traceback.tb_frame.f_code.co_filename
    lineno = exc_traceback.tb_lineno
    return f"{filename}-{lineno}.pkl"

with mortuary.context(dump=dump_path):
    risky_code()
```

::: mortuary.AfterCallbackFn

The type of a callback function executed after the exception is logged and immediately prior to exiting the context. This callback is used to execute arbitrary cleanup code.

::: mortuary.PostMortemFn

The type of a callback function used to enter a post-mortem debugging session.
See [pdb.post_mortem](https://docs.python.org/3/library/pdb.html#pdb.post_mortem) and [ipdb.post_mortem](https://github.com/gotcha/ipdb) for example implementations.


### Functions

::: mortuary.context

::: mortuary.debug

::: mortuary.dump

::: mortuary.read

::: mortuary.log


## Similar projects

* [pystack](https://github.com/bloomberg/pystack)
* [debuglater](https://github.com/ploomber/debuglater)

## License

`mortuary` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.

## Credits

Mortuary's traceback dump is based on [debuglater](https://github.com/ploomber/debuglater) and [pydump](https://github.com/elifiner/pydump).
