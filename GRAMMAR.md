# evidence-facts grammar v0.1.1

This is the normative static contract. Records are declarations. A corpus is all files acquired in one run. Validation checks syntax, metadata shapes, uniqueness, and references; it does not verify evidence or claims.

## Records and delimiters

Files are UTF-8 text; an optional leading BOM is ignored. Physical lines end with LF or CRLF; a lone CR inside a line is data. A final line without a terminator is also accepted. One record occupies one physical line:

```text
ADDRESS = VALUE( | SEGMENT)*
```

The delimiters are exactly ` = ` and ` | `, including their surrounding ASCII spaces. Elsewhere, blanks and whitespace mean Unicode whitespace as recognized by Python's `str.strip()` and regex `\s`. Split at the first ` = `; all subsequent ` | ` delimiters introduce segments. A literal ` | ` inside `VALUE` is forbidden. Other pipes and equals signs are data. Blank lines and whole-line comments beginning with `#` after optional leading blanks are ignored. Inline `#` is data. Comments cannot override domains.

Text after ` = ` that begins with `|` after optional blanks fails with `stray-segment`, so an empty value cannot hide a field-shaped segment.

`ADDRESS` has at least two dot-separated segments, each matching `[a-z0-9][a-z0-9_-]*`. It contains no blanks, has no depth limit, and is unique across the corpus. Its first segment is its domain, which must equal its file's stem (the filename without `.facts`). Address padding is invalid. Surrounding blanks in `VALUE`, segments, and field values are trimmed; the remaining value is uninterpreted text. It must be nonempty when fields follow; an empty value without fields still fails the required-metadata checks. There is no escaping, multiline continuation, or prose classification.

Every segment must be `name:value`, with `name` matching `[a-z][a-z0-9-]*`. Only the six metadata names and four relation names below are accepted. Unsupported field-shaped names fail; bare tags, prose segments, malformed field names, and empty segments also fail. There are no flags or domain directives.

## Required metadata

Each field occurs exactly once. Repetition fails even when the values agree. Every field value is nonempty.

| Field | Accepted value |
| --- | --- |
| `probe` | `<type>:<arg>`; type matches `[a-z][a-z0-9-]*`, argument is nonempty. Additional colons belong to the argument. |
| `owner` | Token matching `[a-z0-9][a-z0-9_-]*`; no registry or authorization check. |
| `kind` | Token matching `[a-z0-9][a-z0-9_-]*`; no registry. |
| `asof` | Real Gregorian calendar date `YYYY-MM-DD`, year `0001` through `9999`. |
| `stale-after` | `<N>d`, where `N` is a nonnegative integer written with ASCII digits. |
| `confidence` | Exactly `probed`, `asserted`, or `UNPROBEABLE`, case-sensitive. |

Confidence declares `asserted`: claimed, not reported as checked by its probe; `probed`: a claim checked by its probe; or `UNPROBEABLE`: a claim that cannot be checked by a probe. These are unverified declarations. A probe is never executed or dereferenced, `probed` does not prove probing occurred, and the date and duration do not trigger a freshness decision.

## Relations

`depends-on`, `contains`, `owned-by`, and `impacts` may repeat. Each value is a nonempty comma/blank-separated list of targets; repeated separators are ignored. Each target must have the same dotted syntax as an address and resolve to either an exact address or an entity prefix of at least one address. A prefix matches only at a dot boundary: `demo.item` resolves through `demo.item.name`, while `demo.item-other` does not satisfy it. A bare domain such as `demo` fails. References resolve across all files, regardless of record order. No acyclicity, relation semantics, or owner authorization is checked.

## Corpus and CLI

```bash
python3 facts_lint.py --root DIR
python3 facts_lint.py --root examples
```

Scope is exactly `DIR/*/*.facts`: immediate directories and matching regular files directly inside them, without recursive discovery. Directories and FIFOs named `*.facts` are skipped. The directory name is organizational; the file stem determines the domain. The root must exist and be a readable directory. Any failed discovery or UTF-8 read within scope is acquisition failure, including an unreadable child directory. A valid empty root succeeds with `facts=0 files=0 errors=0`.

Symbolic links are followed. A broken link among the root's non-hidden entries, or a broken `*.facts` link inside a domain folder, is an acquisition failure; hidden names (starting with `.`) are skipped.

For acquired input, output contains one line per finding, `file:line: rule: message`, followed by `facts=N files=M errors=E`. Filenames in findings are relative to the root. `N` counts record lines with the ` = ` delimiter, including structurally invalid records; `M` counts acquired files, including empty files; `E` counts findings. Missing delimiters produce findings without adding records. No warnings are emitted. Acquisition failure emits an `acquisition` diagnostic to stderr without a corpus summary; usage errors use the argument parser's stderr diagnostics.

Printed paths and other input-derived diagnostic text escape control characters (codes 0–31 and 127–159): LF, CR and tab become `\n`, `\r` and `\t`; other controls become `\xhh` (for example, ESC becomes `\x1b`).

| Exit | Meaning |
| --- | --- |
| `0` | Acquired corpus has no findings, including a valid empty corpus. |
| `1` | Acquired corpus has structural findings. |
| `2` | Usage, discovery, or read failure. |

## Structural rule IDs

Each rejection fixture asserts exit `1` and only its intended rule ID in every finding line, with a matching summary count. One record may produce multiple findings.

| Rule ID | Rejected condition |
| --- | --- |
| `malformed-line` | Non-comment record lacks ` = `. |
| `malformed-address` | Address violates dotted syntax. |
| `domain-mismatch` | Address domain differs from file stem. |
| `duplicate-address` | Address repeats anywhere in the corpus. |
| `duplicate-field` | Scalar metadata repeats. |
| `missing-field` | Required metadata is absent. |
| `empty-field` | Required metadata has an empty value. |
| `bad-probe` | Probe lacks a valid type or argument. |
| `bad-owner` | Owner is not a valid token. |
| `bad-kind` | Kind is not a valid token. |
| `bad-date` | Date has invalid shape or is not a real calendar date. |
| `bad-duration` | Duration is not a nonnegative integer followed by `d`. |
| `bad-confidence` | Confidence is outside the declared enum. |
| `unknown-field` | Field-shaped name is unsupported. |
| `stray-segment` | Pipe segment is empty or is not field-shaped. |
| `empty-relation` | Relation has no targets. |
| `unresolved-target` | Target lacks dotted syntax or does not resolve. |
