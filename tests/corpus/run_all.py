#!/usr/bin/env python3
"""Stdlib-only test runner for the corpus package (no pytest on 53).

Usage:  python tests/corpus/run_all.py
Runs every test_* function in tests/corpus/test_*.py; exit 0 = all pass.
"""

import importlib.util
import os
import sys
import traceback
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    files = sorted(f for f in os.listdir(HERE)
                   if f.startswith("test_") and f.endswith(".py"))
    if not files:
        print("no test files found in %s" % HERE)
        return 1
    total = passed = 0
    failures = []
    t0 = time.time()
    for fn in files:
        mod = _load(fn[:-3], os.path.join(HERE, fn))
        tests = [(n, f) for n, f in vars(mod).items()
                 if n.startswith("test_") and callable(f)]
        for name, fn_ in tests:
            total += 1
            try:
                fn_()
                passed += 1
                print("PASS %s::%s" % (fn[:-3], name))
            except Exception:
                failures.append((fn[:-3], name))
                print("FAIL %s::%s" % (fn[:-3], name))
                print(traceback.format_exc())
    print("-" * 60)
    print("%d/%d passed in %.1fs" % (passed, total, time.time() - t0))
    if failures:
        print("FAILURES:")
        for f in failures:
            print("  %s::%s" % f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
