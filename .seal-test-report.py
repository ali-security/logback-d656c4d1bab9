#!/usr/bin/env python3
# seal: prints a per-module surefire summary, then one line per skipped test with
# the reason found at the skip site in the test source (@Disabled / assume*).
# Run as the last step of the Travis script so the report is at the end of the log.
import glob
import os
import re
import sys
import xml.etree.ElementTree as ET


def find_source(module, cls):
    top = cls.split("$")[0]
    rel = top.replace(".", "/") + ".java"
    for root in ("src/test/java", "src/main/java"):
        path = os.path.join(module, root, rel)
        if os.path.exists(path):
            return path
    return None


def annotation_reason(lines, idx):
    # look upward from a method/class declaration for @Disabled/@Ignore and comments
    comments = []
    found = None
    j = idx - 1
    while j >= 0 and j >= idx - 8:
        s = lines[j].strip()
        m = re.match(r'@(Disabled|Ignore)\s*(\((.*)\))?', s)
        if m:
            found = "@%s%s" % (m.group(1), "(" + m.group(3) + ")" if m.group(3) else "")
        elif s.startswith("//") or s.startswith("*") or s.startswith("/*"):
            text = s.lstrip("/*").strip()
            if text:
                comments.insert(0, text)
        elif s.startswith("@") or s == "":
            pass
        else:
            break
        j -= 1
    if found:
        return found + (" -- " + " ".join(comments) if comments else "")
    return None


def source_reason(module, cls, name):
    path = find_source(module, cls)
    if not path:
        return None
    with open(path, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()
    meth = name.split("(")[0].split("[")[0]
    decl = None
    for i, line in enumerate(lines):
        if re.search(r'\b(void|[\w<>\[\]]+)\s+' + re.escape(meth) + r'\s*\(', line):
            decl = i
            break
    if decl is not None:
        r = annotation_reason(lines, decl)
        if r:
            return "upstream " + r
        # assumption inside the method body
        for k in range(decl, min(decl + 25, len(lines))):
            if re.search(r'assume\w*\(', lines[k]):
                return "upstream assumption not met: " + lines[k].strip()
    for i, line in enumerate(lines):
        if re.search(r'\bclass\s+' + re.escape(cls.split(".")[-1].split("$")[-1]) + r'\b', line):
            r = annotation_reason(lines, i)
            if r:
                return "upstream class-level " + r
            break
    return None


def main(modules):
    grand = [0, 0, 0, 0]
    skipped = []
    print("=" * 72)
    print("SEAL TEST REPORT (surefire XML)")
    for mod in modules:
        tot = [0, 0, 0, 0]
        seen = set()
        for f in sorted(glob.glob(os.path.join(mod, "target", "surefire-reports", "TEST-*.xml"))):
            root = ET.parse(f).getroot()
            for tc in root.iter("testcase"):
                key = (tc.get("classname"), tc.get("name"))
                tot[0] += 1
                if tc.find("failure") is not None:
                    tot[1] += 1
                elif tc.find("error") is not None:
                    tot[2] += 1
                s = tc.find("skipped")
                if s is not None:
                    tot[3] += 1
                    if key in seen:
                        continue
                    seen.add(key)
                    msg = (s.get("message") or "").strip()
                    reason = source_reason(mod, key[0], key[1] or "") or ("surefire: " + msg if msg else "no reason recorded")
                    skipped.append((mod, key[0], key[1], reason))
        passed = tot[0] - tot[1] - tot[2] - tot[3]
        print("%-28s run=%d passed=%d failures=%d errors=%d skipped=%d" % (mod, tot[0], passed, tot[1], tot[2], tot[3]))
        grand = [a + b for a, b in zip(grand, tot)]
    print("SKIPPED TESTS (one line per test, reason from the upstream source):")
    for mod, cls, name, reason in skipped:
        short = cls.replace("ch.qos.logback.", "")
        print("  SKIP %s#%s: %s" % (short, name, reason))
    passed = grand[0] - grand[1] - grand[2] - grand[3]
    print("TOTAL: tests run=%d, passed=%d, failures=%d, errors=%d, skipped=%d" % (grand[0], passed, grand[1], grand[2], grand[3]))
    print("=" * 72)
    return 1 if grand[1] or grand[2] or grand[0] == 0 else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
