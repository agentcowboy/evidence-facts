"""Synthetic conformance, rejection, and acquisition controls."""

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import facts_lint


BASE = ("demo.source = synthetic claim | probe:text:sample | owner:ops"
        " | kind:document | asof:2026-10-03 | stale-after:30d | confidence:asserted")

INVALID_FIXTURES = [
    ("duplicate-equal", "duplicate-field", BASE + " | owner:ops"),
    ("duplicate-unequal", "duplicate-field", BASE + " | owner:docs"),
    ("missing", "missing-field", BASE.replace(" | kind:document", "")),
    ("probe-untyped", "bad-probe", BASE.replace("probe:text:sample", "probe:sample")),
    ("probe-no-arg", "bad-probe", BASE.replace("probe:text:sample", "probe:text:")),
    ("probe-bad-type", "bad-probe", BASE.replace("probe:text:sample", "probe:Text:sample")),
    ("owner-token", "bad-owner", BASE.replace("owner:ops", "owner:two teams")),
    ("kind-token", "bad-kind", BASE.replace("kind:document", "kind:Document")),
    ("date-impossible", "bad-date", BASE.replace("2026-10-03", "2026-02-30")),
    ("date-zero", "bad-date", BASE.replace("2026-10-03", "0000-99-99")),
    ("date-shape", "bad-date", BASE.replace("2026-10-03", "2026-2-03")),
    ("duration", "bad-duration", BASE.replace("stale-after:30d", "stale-after:-1d")),
    ("confidence", "bad-confidence", BASE.replace("confidence:asserted", "confidence:certain")),
    ("unknown", "unknown-field", BASE + " | other:value"),
    ("stray", "stray-segment", BASE + " | extra prose"),
    ("stray-before-fields", "stray-segment", BASE.replace(" | probe:", " | extra prose | probe:")),
    ("value-leading-pipe", "stray-segment", BASE.replace("synthetic claim", "| depends-on:demo.missing")),
    ("empty-segment", "stray-segment", BASE + " | "),
    ("empty-middle", "stray-segment", BASE.replace(" | owner:", " |  | owner:")),
    ("bare-tag", "stray-segment", BASE + " | tag"),
    ("uppercase-field", "stray-segment", BASE + " | Other:value"),
    ("empty-relation", "empty-relation", BASE + " | contains:"),
    ("separator-relation", "empty-relation", BASE + " | contains: , , "),
    ("dangling", "unresolved-target", BASE + " | depends-on:demo.missing"),
    ("sibling", "unresolved-target", BASE + " | depends-on:demo.item\n"
     + BASE.replace("demo.source", "demo.item-other")),
    ("bare-domain", "unresolved-target", BASE + " | depends-on:demo"),
    ("bad-target", "unresolved-target", BASE + " | depends-on:demo..source"),
    ("duplicate-address", "duplicate-address", BASE + "\n" + BASE),
    ("domain", "domain-mismatch", BASE.replace("demo.source", "other.source")),
    ("undotted", "malformed-address", BASE.replace("demo.source", "demo")),
    ("address-empty-part", "malformed-address", BASE.replace("demo.source", "demo..source")),
    ("address-blanks", "malformed-address", BASE.replace("demo.source", "demo.two words")),
    ("address-upper", "malformed-address", BASE.replace("demo.source", "demo.Source")),
    ("address-padding", "malformed-address", " " + BASE),
    ("line", "malformed-line", "demo.source synthetic claim"),
]
for name, value in (("probe", "text:sample"), ("owner", "ops"),
                    ("kind", "document"), ("asof", "2026-10-03"),
                    ("stale-after", "30d"), ("confidence", "asserted")):
    INVALID_FIXTURES.append(("empty-" + name, "empty-field",
                             BASE.replace(name + ":" + value, name + ":")))


def run_cli(root):
    return subprocess.run([sys.executable, "-B", str(ROOT / "facts_lint.py"),
                           "--root", str(root)], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, universal_newlines=True)


def write_fixture(root, text):
    domain = root / "demo"
    domain.mkdir(parents=True, exist_ok=True)
    file = domain / "demo.facts"
    file.write_text(text + "\n", encoding="utf-8")
    return file


def check_rejection(case, rule, text):
    with tempfile.TemporaryDirectory(prefix="facts-reject-") as temporary:
        root = Path(temporary)
        write_fixture(root, text)
        result = run_cli(root)
    if result.returncode != 1:
        raise AssertionError(case + ": expected exit 1")
    if result.stderr != "":
        raise AssertionError(case + ": expected empty stderr")
    lines = result.stdout.splitlines()
    if not lines or not re.fullmatch(r"facts=\d+ files=1 errors=[1-9]\d*", lines[-1]):
        raise AssertionError(case + ": expected final error summary")
    pattern = r"^demo/demo\.facts:[1-9][0-9]*: " + re.escape(rule) + r": .+$"
    if not any(re.fullmatch(pattern, line) for line in result.stdout.splitlines()):
        raise AssertionError(case + ": missing finding for " + rule)


class FactsTests(unittest.TestCase):
    def test_conformance_bom_and_line_endings(self):
        text = BASE.replace("synthetic claim", "claim\rdata")
        text += "\r\n" + BASE.replace("demo.source", "demo.second") + "\n"
        text += BASE.replace("demo.source", "demo.last")
        with tempfile.TemporaryDirectory(prefix="facts-text-") as temporary:
            root = Path(temporary)
            file = write_fixture(root, BASE)
            file.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
            facts, findings = facts_lint.lint_sources(facts_lint.acquire(root))
            result = run_cli(root)
        self.assertEqual(findings, [])
        self.assertEqual([(fact.address, fact.value, fact.line) for fact in facts],
                         [("demo.source", "claim\rdata", 1),
                          ("demo.second", "synthetic claim", 2),
                          ("demo.last", "synthetic claim", 3)])
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, "facts=3 files=1 errors=0\n", ""))

    def test_directory_with_facts_suffix(self):
        with tempfile.TemporaryDirectory(prefix="facts-files-") as temporary:
            root = Path(temporary)
            write_fixture(root, BASE)
            (root / "demo" / "x.facts").mkdir()
            result = run_cli(root)
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, "facts=1 files=1 errors=0\n", ""))

    def test_non_utf8_filename(self):
        with tempfile.TemporaryDirectory(prefix="facts-names-") as temporary:
            root = Path(temporary)
            domain = root / "demo"
            domain.mkdir()
            file = domain / os.fsdecode(b"bad-\xff.facts")
            file.write_text("invalid\n", encoding="utf-8")
            result = run_cli(root)
        self.assertEqual((result.returncode, result.stderr), (1, ""))
        self.assertEqual(result.stdout,
                         "demo/bad-\\udcff.facts:1: malformed-line: expected ADDRESS = VALUE\n"
                         "facts=0 files=1 errors=1\n")

    def test_conformance(self):
        lines = [
            "demo.entry = sample # literal | probe:text:alpha:beta | owner:ops | kind:note | asof:2024-02-29 | stale-after:0d | confidence:probed | contains:demo.item, demo.other | contains:demo.last | impacts:demo.other",
            "demo.item.name = second claim | probe:manual:sample | owner:docs | kind:label | asof:2026-10-03 | stale-after:30d | confidence:UNPROBEABLE | depends-on:demo.entry | owned-by:demo.other",
        ]
        expected = [
            ("demo.entry", "demo", "sample # literal",
             {"probe": "text:alpha:beta", "owner": "ops", "kind": "note",
              "asof": "2024-02-29", "stale-after": "0d", "confidence": "probed"},
             [("contains", ["demo.item", "demo.other"]), ("contains", ["demo.last"]),
              ("impacts", ["demo.other"])]),
            ("demo.item.name", "demo", "second claim",
             {"probe": "manual:sample", "owner": "docs", "kind": "label",
              "asof": "2026-10-03", "stale-after": "30d", "confidence": "UNPROBEABLE"},
             [("depends-on", ["demo.entry"]), ("owned-by", ["demo.other"])]),
        ]
        actual = []
        for number, line in enumerate(lines, 1):
            fact, findings = facts_lint.parse_line(line, "demo/demo.facts", number)
            self.assertEqual(findings, [])
            self.assertEqual((fact.file, fact.line), ("demo/demo.facts", number))
            actual.append((fact.address, fact.domain, fact.value, fact.metadata, fact.relations))
        self.assertEqual(actual, expected)

    def test_comments_and_inline_data(self):
        facts, findings = facts_lint.lint_sources({"demo/demo.facts":
            "\n  # domains: other\n" + BASE.replace("synthetic claim", "claim # literal")})
        self.assertEqual(findings, [])
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0].value, "claim # literal")

    def test_leap_day(self):
        with tempfile.TemporaryDirectory(prefix="facts-date-") as temporary:
            root = Path(temporary)
            write_fixture(root, BASE.replace("2026-10-03", "2024-02-29"))
            result = run_cli(root)
        self.assertEqual((result.returncode, result.stdout), (0, "facts=1 files=1 errors=0\n"))

    def test_relations_and_generic_tokens(self):
        text = BASE + " | contains:demo.item, demo.other | contains:demo.item.name"
        text += "\n" + BASE.replace("demo.source", "demo.item.name")
        text += "\n" + BASE.replace("demo.source", "demo.other").replace("owner:ops", "owner:docs")
        with tempfile.TemporaryDirectory(prefix="facts-relations-") as temporary:
            root = Path(temporary)
            write_fixture(root, text)
            result = run_cli(root)
        self.assertEqual((result.returncode, result.stdout), (0, "facts=3 files=1 errors=0\n"))

    def test_probe_not_executed(self):
        with tempfile.TemporaryDirectory(prefix="facts-probe-") as temporary:
            root = Path(temporary)
            marker = root / "marker"
            write_fixture(root, BASE.replace("probe:text:sample", "probe:sh:touch " + str(marker)))
            result = run_cli(root)
            self.assertFalse(marker.exists())
        self.assertEqual((result.returncode, result.stdout), (0, "facts=1 files=1 errors=0\n"))

    def test_nonexistent_root(self):
        with tempfile.TemporaryDirectory(prefix="facts-root-") as temporary:
            self.assertEqual(run_cli(Path(temporary) / "missing").returncode, 2)

    def test_regular_file_root(self):
        with tempfile.TemporaryDirectory(prefix="facts-root-") as temporary:
            root = Path(temporary) / "file"
            root.write_text("sample", encoding="utf-8")
            self.assertEqual(run_cli(root).returncode, 2)

    def test_empty_root(self):
        with tempfile.TemporaryDirectory(prefix="facts-root-") as temporary:
            result = run_cli(Path(temporary))
        self.assertEqual((result.returncode, result.stdout), (0, "facts=0 files=0 errors=0\n"))

    def test_unreadable_domain_and_readable_counterpart(self):
        self.assertNotEqual(os.geteuid(), 0, "permission control requires a non-root user")
        with tempfile.TemporaryDirectory(prefix="facts-permissions-") as temporary:
            root = Path(temporary)
            write_fixture(root, BASE)
            domain = root / "demo"
            domain.chmod(0)
            try:
                self.assertEqual(run_cli(root).returncode, 2)
            finally:
                domain.chmod(0o700)
            result = run_cli(root)
        self.assertEqual((result.returncode, result.stdout), (0, "facts=1 files=1 errors=0\n"))

    def test_unreadable_file(self):
        self.assertNotEqual(os.geteuid(), 0, "permission control requires a non-root user")
        with tempfile.TemporaryDirectory(prefix="facts-permissions-") as temporary:
            root = Path(temporary)
            file = write_fixture(root, BASE)
            file.chmod(0)
            try:
                self.assertEqual(run_cli(root).returncode, 2)
            finally:
                file.chmod(0o600)

    def test_bad_encoding(self):
        with tempfile.TemporaryDirectory(prefix="facts-read-") as temporary:
            root = Path(temporary)
            file = write_fixture(root, BASE)
            file.write_bytes(b"\xff")
            self.assertEqual(run_cli(root).returncode, 2)

    def test_scope(self):
        with tempfile.TemporaryDirectory(prefix="facts-scope-") as temporary:
            root = Path(temporary)
            write_fixture(root, BASE)
            (root / "outside.facts").write_text("invalid", encoding="utf-8")
            nested = root / "demo" / "nested"
            nested.mkdir()
            (nested / "demo.facts").write_text("invalid", encoding="utf-8")
            result = run_cli(root)
        self.assertEqual((result.returncode, result.stdout), (0, "facts=1 files=1 errors=0\n"))

    def test_usage(self):
        result = subprocess.run([sys.executable, "-B", str(ROOT / "facts_lint.py")],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 2)


def rejection_test(case, rule, text):
    def test(self):
        check_rejection(case, rule, text)
    return test


for case, rule, text in INVALID_FIXTURES:
    setattr(FactsTests, "test_reject_" + case.replace("-", "_"),
            rejection_test(case, rule, text))


if __name__ == "__main__":
    unittest.main()
