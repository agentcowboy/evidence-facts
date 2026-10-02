# evidence-facts

A small plain-text format and Python linter for addressable claims, evidence metadata, and checked references.

Use it when a claim should keep its address, declared evidence, owner, observation date, and references together on one line. This standalone v0.1 is derived from a private commit gate, with a stricter, generalized public profile: six required fields, duplicate-field rejection, real calendar dates, explicit structural errors. The public implementation is written for this profile; it has its own synthetic tests.

## Run the example

```bash
git clone https://github.com/agentcowboy/evidence-facts.git && cd evidence-facts && bash ACCEPTANCE
```

Requirements: Bash, writable temporary storage, and POSIX file permissions for the acquisition controls. Python 3.7+ syntax and standard library; exercised on 3.11 (author) and 3.13 (clean room). Git is needed only for cloning. Acceptance runs offline without credentials or package installation; Python honors `TMPDIR`. Run permission tests as a non-root user; running as root fails explicitly. Acceptance works from another directory by absolute path and leaves the checkout unchanged.

Success prints exactly:

```text
EVIDENCE_FACTS DEMO facts=4 files=1 errors=0
EVIDENCE_FACTS REJECTS rules=17 all-rejected-for-the-right-reason=yes
EVIDENCE_FACTS TESTS run=57 failures=0 errors=0 skips=0
EVIDENCE_FACTS ACCEPTANCE PASS
```

The wrapper checks the real CLI on the demo and 41 invalid fixtures covering 17 rule IDs, then inspects the result of 16 behaviour tests + the 41 rejection fixtures. Every invalid fixture must return exit `1` with empty stderr, the intended rule ID in a finding, and a final error summary. A failed assertion, crash, acquisition failure, unexpected test count, or skipped test prevents the final PASS line. Temporary fixtures are removed.

## Write and lint records

The [four-fact demo](examples/demo/demo.facts) is entirely synthetic, including its evidence declarations. For example:

```text
demo.service = sample service | probe:text:example only | owner:ops | kind:service | asof:2026-10-03 | stale-after:30d | confidence:asserted | depends-on:demo.item | owned-by:demo.team
```

`demo.item` resolves through `demo.item.name` in the demo. Exact-address references also work. Every metadata field is required exactly once; relations may repeat. Owners and kinds are generic tokens without registries. See [GRAMMAR.md](GRAMMAR.md) for the normative syntax and rule IDs. The exact delimiter ` | ` is reserved for fields and cannot appear literally inside a value.

```bash
python3 -B facts_lint.py --root examples
python3 -B facts_lint.py --root /path/to/records
python3 -B -m unittest discover -s tests -p 'test_facts_lint.py'
```

The CLI reads only `ROOT/*/*.facts`; the file stem must match the address domain. It emits `file:line: rule: message` findings followed by `facts=N files=M errors=E`. Exit `0` means no structural findings, `1` means invalid records, and `2` means usage or acquisition failure. Missing roots, file roots, and failed discovery or reads fail with `2`. A valid empty directory passes with `facts=0 files=0 errors=0`; acceptance separately requires the nonempty demo.

## Limits and prior art

Passing lint establishes structure and resolvable references. Claims, owners, probes, dates, and confidence remain unverified declarations. Probes are never executed. The linter does not establish truth, freshness, provenance authenticity, operational health, or authorization, and does not classify prose. It does not lint the Git index or run probes.

The closest prior art identified for this format is [av/facts](https://github.com/av/facts), which uses Markdown/YAML claims, lifecycle tags, and optional executable checks. The formats are incompatible despite sharing the `.facts` extension. This tool combines dotted addresses, declared evidence metadata, and static reference checks; that is a format choice, with no novelty or superiority claim.

Maintenance is best effort. Re-run `bash ACCEPTANCE` after changes and review the normative grammar against the implementation.

Built with AI coding agents; tested as described in ACCEPTANCE.

MIT licensed; see [LICENSE](LICENSE).
