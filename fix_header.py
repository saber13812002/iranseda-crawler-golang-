import sys
p = "bot.py"
s = open(p, encoding="utf-8").read()
bad = 'headers["Content-Type": "application/json"]'
good = 'headers["Content-Type"] = "application/json"'
n = s.count(bad)
s = s.replace(bad, good)
open(p, "w", encoding="utf-8").write(s)
print("replaced:", n)
# verify no other colon-subscript patterns remain
import re
for i, line in enumerate(s.splitlines(), 1):
    if '": "' in line and "headers[" in line:
        print("SUSPECT line", i, ":", line.strip())
print("done")
