#!/usr/bin/env python3
"""Validate declared records and references; never execute probes."""

import argparse
import datetime
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path


METADATA = ("probe", "owner", "kind", "asof", "stale-after", "confidence")
RELATIONS = ("depends-on", "contains", "owned-by", "impacts")
ADDRESS = re.compile(r"[a-z0-9][a-z0-9_-]*(?:\.[a-z0-9][a-z0-9_-]*)+")
TOKEN = re.compile(r"[a-z0-9][a-z0-9_-]*")
FIELD = re.compile(r"([a-z][a-z0-9-]*):(.*)")
PROBE = re.compile(r"[a-z][a-z0-9-]*:.+")
DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
DURATION = re.compile(r"[0-9]+d")


def printable(text):
    """Escape terminal controls in untrusted output text."""
    escapes = {"\n": r"\n", "\r": r"\r", "\t": r"\t"}
    return "".join(escapes.get(char, "\\x{:02x}".format(ord(char)))
                   if ord(char) < 32 or 127 <= ord(char) <= 159 else char
                   for char in text)


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        super().error(printable(message))


@dataclass
class Fact:
    address: str
    domain: str
    value: str
    metadata: dict
    relations: list
    file: str
    line: int


@dataclass
class Finding:
    file: str
    line: int
    rule: str
    message: str

    def render(self):
        return "{}:{}: {}: {}".format(
            printable(self.file), self.line, printable(self.rule), printable(self.message))


def valid_date(value):
    if not DATE.fullmatch(value):
        return False
    try:
        datetime.date(*[int(part) for part in value.split("-")])
    except ValueError:
        return False
    return True


def parse_line(raw, file, line):
    """Return (record or None, findings) for one physical line."""
    findings = []

    def report(rule, message):
        findings.append(Finding(file, line, rule, message))

    text = raw
    if text.endswith("\n"):
        text = text[:-1]
        if text.endswith("\r"):
            text = text[:-1]
    if not text.strip() or text.lstrip().startswith("#"):
        return None, findings
    if " = " not in text:
        report("malformed-line", "expected ADDRESS = VALUE")
        return None, findings
    address, rest = text.split(" = ", 1)
    if rest.lstrip().startswith("|"):
        report("stray-segment", "value must not begin with a pipe")
    if not ADDRESS.fullmatch(address):
        report("malformed-address", "expected at least two valid dotted segments")
    domain = address.split(".", 1)[0]
    if domain != Path(file).stem:
        report("domain-mismatch", "address domain must equal the file stem")
    segments = rest.split(" | ")
    metadata = {}
    relations = []
    for segment in segments[1:]:
        segment = segment.strip()
        match = FIELD.fullmatch(segment)
        if not match:
            report("stray-segment", "expected a name:value segment; empty segments fail")
            continue
        name, value = match.groups()
        value = value.strip()
        if name in RELATIONS:
            targets = [part for part in re.split(r"[,\s]+", value) if part]
            if not targets:
                report("empty-relation", "relation requires at least one target")
            relations.append((name, targets))
        elif name in METADATA:
            if name in metadata:
                report("duplicate-field", "metadata must occur exactly once: " + name)
            else:
                metadata[name] = value
            if not value:
                report("empty-field", "metadata must be nonempty: " + name)
        else:
            report("unknown-field", "unsupported field: " + name)
    for name in METADATA:
        if name not in metadata:
            report("missing-field", "required metadata: " + name)
    validators = (
        ("probe", "bad-probe", lambda value: bool(PROBE.fullmatch(value))),
        ("owner", "bad-owner", lambda value: bool(TOKEN.fullmatch(value))),
        ("kind", "bad-kind", lambda value: bool(TOKEN.fullmatch(value))),
        ("asof", "bad-date", valid_date),
        ("stale-after", "bad-duration", lambda value: bool(DURATION.fullmatch(value))),
        ("confidence", "bad-confidence", lambda value: value in
         ("probed", "asserted", "UNPROBEABLE")),
    )
    for name, rule, validate in validators:
        if metadata.get(name) and not validate(metadata[name]):
            report(rule, "invalid metadata: " + name)
    return Fact(address, domain, segments[0].strip(), metadata, relations,
                file, line), findings


def resolves(target, addresses):
    if not ADDRESS.fullmatch(target):
        return False
    return target in addresses or any(
        address.startswith(target + ".") for address in addresses)


def lint_sources(sources):
    """Validate supplied {relative filename: text} without file access."""
    facts = []
    findings = []
    addresses = set()
    for file, text in sorted(sources.items()):
        lines = text.split("\n")
        for line, raw in enumerate(lines, 1):
            if line < len(lines):
                raw += "\n"
            fact, parsed = parse_line(raw, file, line)
            findings.extend(parsed)
            if fact is None:
                continue
            facts.append(fact)
            if fact.address in addresses:
                findings.append(Finding(file, line, "duplicate-address",
                                        "address already defined"))
            if ADDRESS.fullmatch(fact.address):
                addresses.add(fact.address)
    for fact in facts:
        for name, targets in fact.relations:
            for target in targets:
                if not resolves(target, addresses):
                    findings.append(Finding(fact.file, fact.line, "unresolved-target",
                                            "unresolved dotted target for " + name))
    return facts, findings


def acquire(root):
    """Discover exactly immediate directory / *.facts, raising on failures."""
    if not root.is_dir() or not os.access(str(root), os.R_OK | os.X_OK):
        raise OSError("root must be a readable directory")
    sources = {}
    with os.scandir(str(root)) as entries:
        domains = sorted(entries, key=lambda entry: entry.name)
    for domain in domains:
        if domain.name.startswith("."):
            continue
        if domain.is_symlink():
            domain.stat()
        if not domain.is_dir():
            continue
        with os.scandir(domain.path) as entries:
            files = sorted(entries, key=lambda entry: entry.name)
        for entry in files:
            if entry.name.startswith("."):
                continue
            if not entry.name.endswith(".facts"):
                continue
            if entry.is_symlink():
                entry.stat()
            if entry.is_file():
                relative = domain.name + "/" + entry.name
                with open(entry.path, encoding="utf-8-sig", newline="") as source:
                    sources[relative] = source.read()
    return sources


def main(argv=None):
    sys.stdout.reconfigure(errors="backslashreplace")
    parser = ArgumentParser(description=__doc__, prog=printable(os.path.basename(sys.argv[0])))
    parser.add_argument("--root", required=True, type=Path,
                        help="read DIR/*/*.facts beneath DIR")
    args = parser.parse_args(argv)
    try:
        sources = acquire(args.root)
    except (OSError, UnicodeError):
        print("<input>:0: acquisition: discovery or read failed", file=sys.stderr)
        return 2
    facts, findings = lint_sources(sources)
    for finding in findings:
        print(finding.render())
    print("facts={} files={} errors={}".format(len(facts), len(sources), len(findings)))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
