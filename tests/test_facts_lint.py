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
    ("empty-value-with-fields", "stray-segment", BASE.replace("synthetic claim", "")),
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
    ("address-padding", "malformed-address", BASE.replace("demo.source", "demo.source ")),
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
    if not all(re.fullmatch(pattern, line) for line in lines[:-1]):
        raise AssertionError(case + ": expected only findings for " + rule)
    if not lines[:-1] or int(lines[-1].rsplit("=", 1)[1]) != len(lines) - 1:
        raise AssertionError(case + ": finding count does not match summary")


class FactsTests(unittest.TestCase):
    def check_control_filename(self, control, escaped):
        with tempfile.TemporaryDirectory(prefix="facts-names-") as temporary:
            root = Path(temporary)
            domain = root / "demo"
            domain.mkdir()
            (domain / ("bad" + control + ".facts")).write_text("invalid\n", encoding="utf-8")
            result = run_cli(root)
        self.assertEqual((result.returncode, result.stderr), (1, ""))
        self.assertEqual(result.stdout,
                         "demo/bad" + escaped + ".facts:1: malformed-line: expected ADDRESS = VALUE\n"
                         "facts=0 files=1 errors=1\n")

    def test_newline_filename(self):
        self.check_control_filename("\n", r"\n")

    def test_cr_filename(self):
        self.check_control_filename("\r", r"\r")

    def test_esc_filename(self):
        self.check_control_filename("\x1b", r"\x1b")

    def test_output_controls(self):
        for code in list(range(32)) + list(range(127, 160)):
            char = chr(code)
            escaped = {10: r"\n", 13: r"\r", 9: r"\t"}.get(code, "\\x{:02x}".format(code))
            finding = facts_lint.Finding("dir" + char + "/demo.facts", 1, "rule", "message" + char)
            self.assertEqual(finding.render(),
                             "dir" + escaped + "/demo.facts:1: rule: message" + escaped)

    def test_usage_controls(self):
        result = subprocess.run([sys.executable, "-B", str(ROOT / "facts_lint.py"),
                                 "--root", ".", "--bad\n\r\x1b\x85"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                universal_newlines=True)
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertIn(r"--bad\n\r\x1b\x85", result.stderr)
        self.assertNotIn("\r", result.stderr)
        self.assertNotIn("\x1b", result.stderr)
        self.assertNotIn("\x85", result.stderr)

    def test_unicode_whitespace(self):
        text = "\u2003\u00a0\n\u2003# comment\n" + BASE.replace(
            "synthetic claim", "\u2003claim\u00a0").replace(
            "owner:ops", "\u2003owner:\u00a0ops\u2003")
        text += " | contains:\u2003demo.source\u00a0,\u2003demo.source"
        facts, findings = facts_lint.lint_sources({"demo/demo.facts": text})
        self.assertEqual(findings, [])
        self.assertEqual((len(facts), facts[0].value, facts[0].metadata["owner"]),
                         (1, "claim", "ops"))
        self.assertEqual(facts[0].relations, [("contains", ["demo.source", "demo.source"])])

    def test_empty_value_without_fields(self):
        fact, findings = facts_lint.parse_line("demo.source = ", "demo/demo.facts", 1)
        self.assertEqual(fact.value, "")
        self.assertEqual([finding.rule for finding in findings], ["missing-field"] * 6)

    def test_duplicate_address_across_files(self):
        with tempfile.TemporaryDirectory(prefix="facts-files-") as temporary:
            root = Path(temporary)
            write_fixture(root, BASE)
            other = root / "other"
            other.mkdir()
            (other / "demo.facts").write_text(BASE + "\n", encoding="utf-8")
            result = run_cli(root)
        self.assertEqual((result.returncode, result.stderr), (1, ""))
        self.assertEqual(result.stdout,
                         "other/demo.facts:1: duplicate-address: address already defined\n"
                         "facts=2 files=2 errors=1\n")

    def test_reference_across_files(self):
        with tempfile.TemporaryDirectory(prefix="facts-files-") as temporary:
            root = Path(temporary)
            write_fixture(root, BASE + " | depends-on:other.target")
            other = root / "other"
            other.mkdir()
            (other / "other.facts").write_text(BASE.replace("demo.source", "other.target.name")
                                                + "\n", encoding="utf-8")
            result = run_cli(root)
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, "facts=2 files=2 errors=0\n", ""))

    def test_directory_name_differs_from_stem(self):
        with tempfile.TemporaryDirectory(prefix="facts-files-") as temporary:
            root = Path(temporary)
            write_fixture(root, BASE)
            (root / "demo").rename(root / "records")
            result = run_cli(root)
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, "facts=1 files=1 errors=0\n", ""))

    def test_hidden_root_entries(self):
        with tempfile.TemporaryDirectory(prefix="facts-links-") as temporary:
            root = Path(temporary)
            write_fixture(root, BASE)
            (root / ".#demo.facts").symlink_to("missing")
            hidden = root / ".hidden"
            hidden.mkdir()
            (hidden / "demo.facts").write_text("invalid\n", encoding="utf-8")
            result = run_cli(root)
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, "facts=1 files=1 errors=0\n", ""))

    def test_hidden_domain_entries(self):
        with tempfile.TemporaryDirectory(prefix="facts-links-") as temporary:
            root = Path(temporary)
            write_fixture(root, BASE)
            domain = root / "demo"
            (domain / ".#demo.facts").symlink_to("missing")
            (domain / ".hidden.facts").write_text("invalid\n", encoding="utf-8")
            result = run_cli(root)
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, "facts=1 files=1 errors=0\n", ""))

    def test_dangling_file_link(self):
        with tempfile.TemporaryDirectory(prefix="facts-links-") as temporary:
            root = Path(temporary)
            (root / "demo").mkdir()
            (root / "demo" / "demo.facts").symlink_to("missing")
            result = run_cli(root)
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (2, "", "<input>:0: acquisition: discovery or read failed\n"))

    def test_dangling_directory_link(self):
        with tempfile.TemporaryDirectory(prefix="facts-links-") as temporary:
            root = Path(temporary)
            (root / "demo").symlink_to("missing", target_is_directory=True)
            result = run_cli(root)
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (2, "", "<input>:0: acquisition: discovery or read failed\n"))

    def test_valid_file_and_directory_links(self):
        with tempfile.TemporaryDirectory(prefix="facts-links-") as temporary:
            base = Path(temporary)
            root = base / "records"
            root.mkdir()
            target = base / "target"
            target.mkdir()
            (base / "claim").write_text(BASE + "\n", encoding="utf-8")
            (target / "demo.facts").symlink_to(base / "claim")
            (root / "demo").symlink_to(target, target_is_directory=True)
            result = run_cli(root)
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, "facts=1 files=1 errors=0\n", ""))

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
        expected_code = 1
        expected_output = ("demo/bad-\\udcff.facts:1: malformed-line: expected ADDRESS = VALUE\n"
                           "facts=0 files=1 errors=1\n")
        with tempfile.TemporaryDirectory(prefix="facts-names-") as temporary:
            root = Path(temporary)
            domain = root / "demo"
            domain.mkdir()
            file = domain / os.fsdecode(b"bad-\xff.facts")
            try:  # Some filesystems (e.g. APFS) refuse non-UTF-8 names; Linux must accept it.
                file.write_text("invalid\n", encoding="utf-8")
            except OSError:
                if sys.platform.startswith("linux"):
                    raise
                expected_code = 0
                expected_output = "facts=0 files=0 errors=0\n"
            result = run_cli(root)
        self.assertEqual((result.returncode, result.stderr), (expected_code, ""))
        self.assertEqual(result.stdout, expected_output)

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
