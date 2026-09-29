# CueDown

CueDown is a minimal, human-writable cue sheet format for tracklists and DJ sets. A tracklist in the common forum notation (`0:00 Artist - Title`) is already almost valid CueDown, and normalizing a file is always safe: every accepted line maps to exactly one canonical line, and canonical lines are fixed points. The full format definition lives in [`spec/cuedown-spec.md`](spec/cuedown-spec.md).

This repository is the canonical home of the spec and of the **conformance corpus** — a language-agnostic test suite modeled on [toml-test](https://github.com/toml-lang/toml-test). The fixtures are inert data files; there is no parser code here. Every implementation brings its own small harness.

## The corpus

```
tests/
  VERSION                  corpus version
  valid/
    <name>.cd              input
    <name>.json            expected semantic model
    <name>.canonical.cd    expected normalize/serialize output
  invalid/
    <name>.cd              input
    <name>.json            expected error: {"error": "E0x", "line": N}
```

A harness must assert, for each `valid/<name>`:

1. Parsing `<name>.cd` yields the semantic model in `<name>.json` (deep equality).
2. Serializing that model yields `<name>.canonical.cd`, byte-for-byte.
3. Parsing and re-serializing `<name>.canonical.cd` yields itself, byte-for-byte — normalization is idempotent, tested for free on every fixture.

For each `invalid/<name>`: parsing fails with the expected error code and 1-based line number of first failure. When a file parses under neither grammar, the canonical-pass diagnostic is primary; `E09` marks mixed-grammar files (see spec §3 and §6).

All fixture files are byte-exact: canonical `.cd` files end with a trailing LF, and `crlf-input.cd` intentionally contains CRLF line endings (protected by `.gitattributes` — do not let tooling "fix" fixture bytes).

Corpus versions are git tags (`corpus-v1.0.0`); `tests/VERSION` holds the current version. Implementations declare "passes corpus v1.0.0". Fixture additions bump patch/minor; a changed expectation for an existing fixture only happens when the spec itself changes, and bumps major.

Reference harnesses in Python and Swift are coming soon.

## Known implementations

| Implementation | Language | Corpus version |
| --- | --- | --- |
| cuedown-python | Python | coming soon |
| cuedown-swift | Swift | coming soon |

## Authority

When an implementation and this corpus disagree, the corpus is presumed correct; when the corpus and the spec disagree, the spec wins — file an issue.

## Appendix: CLI adapter contract (non-normative)

A suggestion only, toml-test style, so a future shared runner can drive any implementation: expose a binary that reads a `.cd` file on stdin; on success, print the expected-output JSON (the `valid/*.json` shape) to stdout and exit 0; on failure, print `E0x LINE` and exit 1.
