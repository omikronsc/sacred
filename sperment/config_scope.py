#!/usr/bin/python
# coding=utf-8
from __future__ import division, print_function, unicode_literals
from copy import copy
from functools import update_wrapper
import inspect
import json
import re


def blocking_dictify(x):
    if isinstance(x, dict):
        return DogmaticDict({k: blocking_dictify(v) for k, v in x.iteritems()})
    elif isinstance(x, (list, tuple)):
        return type(x)(blocking_dictify(v) for v in x)
    else:
        return x


class DogmaticDict(dict):
    def __init__(self, fixed=None):
        super(DogmaticDict, self).__init__()
        if fixed is not None:
            self._fixed = fixed
        else:
            self._fixed = ()

    def __setitem__(self, key, value):
        if key not in self._fixed:
            dict.__setitem__(self, key, value)
        else:
            fixed_val = self._fixed[key]
            dict.__setitem__(self, key, fixed_val)
            if isinstance(fixed_val, DogmaticDict) and isinstance(value, dict):
                #recursive update
                bd = self[key]
                for k, v in value.items():
                    bd[k] = v

    def __delitem__(self, key):
        if key not in self._fixed:
            dict.__delitem__(self, key)

    def update(self, iterable=None, **kwargs):
        if iterable is not None:
            if hasattr(iterable, 'keys'):
                for k in iterable:
                    self[k] = iterable[k]
            else:
                for (k, v) in iterable:
                    self[k] = v
        for k in kwargs:
            self[k] = kwargs[k]

    def revelation(self):
        missing = []
        for key in self._fixed:
            if not key in self:
                self[key] = self._fixed[key]
                missing.append(key)
            elif isinstance(self[key], DogmaticDict):
                missing += [key + "." + k for k in self[key].revelation()]
        return missing


class DogmaticList(list):
    def __init__(self, fixed=None):
        if fixed is not None:
            self._fixed = fixed
        else:
            self._fixed = ()
        super(DogmaticList, self).__init__(self._fixed)

    def _is_fixed(self, value):
        return (value not in self._fixed or
                self.count(value) > self._fixed.count(value))

    def pop(self, index=None):
        index = index or -1
        value = self[index]
        if not self._is_fixed(value):
            list.pop(self, index)

    def remove(self, value):
        if not self._is_fixed(value):
            list.remove(self, value)

    def __delitem__(self, key):
        value = self[key]
        if not self._is_fixed(value):
            list.__delitem__(self, key)

    def __delslice__(self, i, j):
        assert 0 <= i <= j
        for idx in reversed(range(i, j)):
            value = self[idx]
            if not self._is_fixed(value):
                list.__delitem__(self, idx)

    def __setitem__(self, i, y):
        value = self[i]
        if not self._is_fixed(value):
            list.__setitem__(self, i, y)


def is_zero_argument_function(func):
    arg_spec = inspect.getargspec(func)
    return (arg_spec.args == [] and
            arg_spec.varargs is None and
            arg_spec.keywords is None)


def get_function_body_source(func):
    func_code_lines, start_idx = inspect.getsourcelines(func)
    func_code = ''.join(func_code_lines)
    func_def = re.compile(
        r"^[ \t]*def[ \t]*{}[ \t]*\(\s*\)[ \t]*:[ \t]*\n".format(func.__name__),
        flags=re.MULTILINE)
    defs = list(re.finditer(func_def, func_code))
    assert defs
    func_body = func_code[defs[0].end():]
    return inspect.cleandoc(func_body)


class ConfigScope(dict):
    def __init__(self, func):
        super(ConfigScope, self).__init__()
        assert is_zero_argument_function(func), \
            "only zero-argument function can be ConfigScopes"
        self._func = func
        update_wrapper(self, func)
        func_body = get_function_body_source(func)
        self._body_code = compile(func_body, "<string>", "exec")
        self._initialized = False

    def __call__(self, fixed=None, preset=None):
        self._initialized = True
        self.clear()
        l = blocking_dictify(fixed) if fixed is not None else {}
        if preset is not None:
            l.update(preset)
        eval(self._body_code, copy(self._func.func_globals), l)
        for k, v in l.items():
            if k.startswith('_'):
                continue
            try:
                json.dumps(v)
                self[k] = v
            except TypeError:
                pass

    def __getattr__(self, k):
        """
        Gets key if it exists, otherwise throws AttributeError.
        """
        try:
            # Throws exception if not in prototype chain
            return object.__getattribute__(self, k)
        except AttributeError:
            try:
                return self[k]
            except KeyError:
                raise AttributeError(k)

    def __getitem__(self, item):
        assert self._initialized, "ConfigScope has to be executed before access"
        return dict.__getitem__(self, item)