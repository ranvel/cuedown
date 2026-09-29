# CueDown Specification — v1 (draft)

CueDown is a minimal, human-writable cue sheet format for tracklists and DJ sets. It is designed so that a tracklist in the common forum notation (`0:00 Artist - Title`) is *already almost valid* CueDown, and so that normalizing a file is always safe.

**Status:** draft, formalized 2026-09-12; fallback grammar adopted 2026-09-12; last revised 2026-09-27 (timecode-first rule, fallback verbatim rule).

---

## 1. Design principles

1. **Simple to write by hand.** Timecode and track text are the MVP; everything else is optional.
2. **Two grammars, one fallback.** A permissive *accept grammar* (what a parser must tolerate) and a strict *write grammar* (the single canonical form, a subset of the accept grammar) — plus an all-or-nothing, file-level fallback grammar for tracklists pasted from the web (§3).
3. **Round-trip guarantee.** Every accepted line maps to exactly one canonical line. Canonical lines are fixed points: parse → serialize on a canonical line returns it byte-for-byte, so normalization is idempotent and safe to run on every save.
4. **Strict errors.** Anything outside the accept grammar is an error. Stop early; never guess.

---

## 2. File rules

- Encoding: **UTF-8**. Line endings: **LF** on write; CRLF accepted on input.
- Extension: **`.cd`** (`.cue` is taken by CDRWIN cue sheets).
- **Exactly one cue per line** — a cue never spans multiple lines. Blank lines are ignored on parse and not emitted on write.
  - Rationale (added 2026-09-28): newline rendering is explicitly ignored because the surfaces where track strings are expected to appear are frozen single-line strings — MP3 text metadata, the "track string" in CarPlay, a small section of sand in a beach-themed muwav audio player. A newline has no meaning anywhere in the format: a cue is one line, and a track string can never contain one.
- No comment syntax in v1.
- Timecodes must be **strictly ascending** within a file. Out-of-order or duplicate timecodes are an error.

---

## 3. Line grammar

Canonical (write) form:

```
TIMECODE [FLAG] [SPEED] - TRACK STRING
```

- Tokens are separated by exactly one space on write.
- The **delimiter** is `-` (written as ` - `, space-hyphen-space) and is the **only** delimiter. `:` is not accepted — it collides with timecode syntax and may appear freely in track text. The delimiter is **required** on every line of a canonical file; a line without one is not canonical (see the fallback grammar below).
- **Everything after the first delimiter is the track string, verbatim.** No escaping, no exceptions. A track string may contain hyphens, colons, timecode-lookalikes, anything except a newline.
- The **timecode must be the first token** on the line — a line whose first token is not a timecode is an error (E03). `FLAG` and `SPEED` may appear in **either order** after it, before the delimiter, but are always written in canonical order (`FLAG` then `SPEED`).
- Duplicate tokens of any kind (two timecodes, two flags, two speeds) are an **error**.

### Fallback grammar: forum tracklists

The common forum notation for tracklists is:

```
0:00 Artist - Title
```

Because ` - ` is the CueDown delimiter, these lines cannot be read canonically (`Artist` would be an unrecognized token, E08). CueDown therefore defines a **file-level fallback grammar**:

```
TIMECODE TRACK STRING
```

- Everything after the timecode is the track string, **verbatim** — hyphens included. No flags, no speeds, no delimiter semantics; a token-lookalike after the timecode is just text.
- **Verbatim means verbatim — no lookalike detection, decided 2026-09-27.** `47:00 <3` in a fallback file is a cue for a track titled `<3` (it exists — Bad Bunny, 2020), not a loved cue with a missing title. Flag and speed lookalikes at the start of fallback text are deliberately just text; the only disambiguation mechanism in CueDown is the canonical delimiter. In a canonical file, a bare `47:00 <3` is E04 (empty track string) — loud, never guessed. To cue that song canonically: `47:00 - <3`. To love it: `47:00 <3 - <3`.
- **All-or-nothing.** A parser first attempts the canonical grammar on the whole file. Only if that pass fails may it attempt the fallback pass — and then **every** line must parse as `TIMECODE TRACK STRING`. There is no per-line mixing.
- **Disjoint by construction.** A line that satisfies the canonical grammar is not a valid fallback line. A canonical file with one typo'd token therefore never silently degrades to fallback with its flags swallowed as text: it fails the canonical pass (E08) and the fallback pass too, yielding E09 — implementations report the canonical-pass error as the primary diagnostic.
- Rationale: the fallback exists so a tracklist copied whole from a webpage just works. It is not there to salvage a doctored file that mixes styles. Scope note (decided 2026-09-28): the no-silent-degradation property holds only when at least one line is canonical-valid. A file in which *no* line is canonical-valid — including a single-line file like `0:00 S3 Banger - Title` — legally parses as fallback, and lookalike tokens (`S3`) are track text. This is intentional and follows from the verbatim rule.
- All file rules apply in fallback mode: strictly ascending timecodes, non-empty track strings, one cue per line.
- On write, a fallback file is rewritten to canonical CueDown (see §8).

### Track string

- Required. **Empty or whitespace-only track string is an error** (empty == broken).
- Preserved exactly, including internal whitespace. Leading/trailing whitespace of the *line* is stripped before parsing (`.strip()` semantics).

---

## 4. Tokens

### 4.1 Timecode (required)

Canonical write form:

- `MM:SS` when hours are zero; `HH:MM:SS` when nonzero.
- Every field zero-padded to 2 digits (`00:00`, `05:13`, `02:13:16`).
- Milliseconds: written **only if sub-second data exists**, as `.` + exactly 3 digits (`04:20.500`). Sub-second data is never stripped once present. A zero fraction still counts as sub-second data — the separator's presence, not its value, decides: `4:20.0` writes as `04:20.000`.

Accept grammar:

- 2 fields (`M:SS`) or 3 fields (`H:MM:SS`), each field 1+ digits.
- **Field overflow normalizes**: `133:16` → `02:13:16`, `90:00` → `01:30:00`.
- Fraction separator: **`.` only**, on input and on write. A `,` fraction separator is a malformed timecode (E05).
- Fraction is a **decimal fraction of a second**, 1–3 digits: `.5` = 500 ms, `.05` = 50 ms, `.055` = 55 ms.
- Bare integers (`313`) are **rejected** — minimum shape is `M:SS`.

### 4.2 Flag (optional): `<3` | `X`

- `<3` and `X` are **mutually exclusive**; both on one line is an error.
- Accept: `<3`, any of these heart emoji — ❤️ ♥️ 💙 💜 🖤 💛 💚 🧡 🤎 🤍 🩷 🩶 🩵 — with or without U+FE0F (variation selector-16 is ignored). Always written `<3`.
- `X` accepts `x` on input. **No emoji aliases for `X`** — deliberate: people go the distance for tracks they love; the never-play list gets the minimal product.

### 4.3 Speed (optional): `S0`–`S9`

- Single digit `0`–`9`. **Never zero-padded** (`S03` is an error).
- `s3` accepted on input; always written `S3`.
- **Default is `S0`** when no speed token is present. An explicit `S0` is **preserved on write** — never normalized away. A line with no speed token stays token-free on write.

---

## 5. Case & whitespace

- Token matching is **case-insensitive on input** (`x`, `s3`); tokens are always written uppercase (`X`, `S3`).
- Input: tokens separated by one or more spaces/tabs; lines stripped of leading/trailing whitespace before parsing.
- Write: exactly one space between tokens and around the delimiter.

---

## 6. Errors (strict — fail the file, stop early)

- E01 Duplicate token (timecode, flag, or speed appears twice)
- E02 `<3` and `X` on the same line
- E03 Missing or non-leading timecode (the timecode must be the first token on the line)
- E04 Empty or whitespace-only track string
- E05 Malformed timecode (bare integer, bad field shape, `,` fraction separator)
- E06 Zero-padded speed (`S03`) or out-of-range speed
- E07 Timecodes not strictly ascending / duplicate timecode
- E08 Unrecognized token before the delimiter (canonical grammar)
- E09 Mixed-grammar file — parses under neither the canonical nor the fallback grammar

---

## 7. Semantics

The format carries intent; interpretation is application-defined.

- **`<3`** — loved. The track the listener will go the distance for.
- **`X`** — never show me this again. Excluded from future play.
- **`S0`–`S9`** — relative intensity/speed of the set at this cue, `S0` lowest. Purely **advisory and optional**: it exists to show the shape of a set ("where's the fast part?"). Programs may interpret it however they like. muwav's intended use: map BPM across the set via Apple's music understanding framework, visualize intensity, and potentially skip the wind-down track at the end.

---

## 8. Examples

Canonical input (accepted):

```
0:00 ❤️ - Aalson – Reeds
6:56 - Alex Rusin – Ups and Down
15:50 s3 <3 - Nils Andreas – Rainbow Colors
1:04:25.5 - Koelle – Round & Round
133:16 x s2 - Some Track – Goodbye
```

Canonical output:

```
00:00 <3 - Aalson – Reeds
06:56 - Alex Rusin – Ups and Down
15:50 <3 S3 - Nils Andreas – Rainbow Colors
01:04:25.500 - Koelle – Round & Round
02:13:16 X S2 - Some Track – Goodbye
```

Fallback input (a forum tracklist — every line, or nothing):

```
0:00 Aalson - Reeds
6:56 Alex Rusin - Ups and Down
15:50 Nils Andreas - Rainbow Colors
```

Canonical output:

```
00:00 - Aalson - Reeds
06:56 - Alex Rusin - Ups and Down
15:50 - Nils Andreas - Rainbow Colors
```

---

## 9. Conformance checklist for implementations

1. `normalize(normalize(f)) == normalize(f)` byte-for-byte (idempotence).
2. Every canonical line round-trips unchanged.
3. Property test: generate random valid cues → serialize → parse → serialize → assert byte equality.
4. All E01–E09 cases rejected with the line number of first failure.
5. Grammar disjointness: a file valid under the canonical grammar is never parsed under the fallback grammar; when both passes fail, the canonical-pass error is the primary diagnostic.
