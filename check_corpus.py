#!/usr/bin/env python3
"""Structural checker for the CueDown conformance corpus and example files.

Needs no CueDown parser: it validates fixture *shape* and the machine-checkable
sides of each fixture triple, plus grammar-level sanity of example files.
Run from the corpus repo root:

	python3 check_corpus.py [tests-dir]     # default: tests

What it verifies:
  valid/    - every <name>.cd has <name>.json and <name>.canonical.cd
            - JSON matches the corpus schema (types, allowed values)
            - time_ms strictly ascending, speed in 0..9 or null, flag in {"<3","X",null}
            - .canonical.cd is lint-clean canonical form (regex-strict:
              zero-padding, 3-digit fractions, FLAG before SPEED, single
              spaces, LF-only, single trailing LF, no blank lines)
            - .canonical.cd AGREES with .json line-by-line: time arithmetic,
              fractional flag, flag/speed tokens, verbatim track
  invalid/  - every <name>.cd has <name>.json with a real error code (E01-E09)
              and a line number that exists in the .cd file
  examples  - every *.cd in the repo root and examples/ (if present):
              every line is parseable under at least one grammar, the file
              does not MIX canonical and fallback lines (the E09 trap),
              timecodes strictly ascend, and no track is empty

What it CANNOT verify: that parsing a messy input .cd yields its .json.
That is the parser's half of the contract - hold the corpus-v1.0.0 tag until
the first implementation harness goes green against the full set.
"""

import json
import re
import sys
from pathlib import Path

CANONICAL_LINE = re.compile(
	r"^(?:(\d{2}):)?(\d{2}):(\d{2})(?:\.(\d{3}))?( <3| X)?( S\d)? - (.+)$"
)
ERROR_CODES = {f"E0{n}" for n in range(1, 10)}
FLAGS = {"<3", "X", None}
HEARTS = set("\u2764\u2665\U0001F499\U0001F49C\U0001F5A4\U0001F49B\U0001F49A\U0001F9E1\U0001F90E\U0001F90D\U0001FA77\U0001FA76\U0001FA75")

failures = []


def fail(fixture, msg):
	failures.append(f"  {fixture}: {msg}")


def timecode_ms(tok):
	"""Loose input-side timecode: 2-3 colon fields, optional 1-3 digit fraction.
	Returns milliseconds, or None if the token is not timecode-shaped.
	Deliberately looser than the spec (overflow allowed, no padding rules):
	this is a pre-flight linter, not the parser."""
	m = re.fullmatch(r"(\d+(?::\d+){1,2})(?:\.(\d{1,3}))?", tok)
	if not m:
		return None
	fields = [int(f) for f in m.group(1).split(":")]
	hh, mm, ss = (0, *fields) if len(fields) == 2 else fields
	frac = int(m.group(2).ljust(3, "0")) if m.group(2) else 0
	return ((hh * 3600 + mm * 60 + ss) * 1000) + frac


def is_flag_or_speed(tok):
	t = tok.replace("\ufe0f", "")
	if t in ("<3", "x", "X") or t in HEARTS:
		return True
	return len(t) == 2 and t[0] in "sS" and t[1].isdigit()


def classify_line(line):
	"""Return (grammar, ms) where grammar is 'canonical', 'fallback', or None.
	Mirrors the spec's disjointness rule: a line is fallback only if it does
	not satisfy the canonical grammar."""
	if " - " in line:
		head, _, rest = line.partition(" - ")
		toks = head.split()
		if toks:
			ms = timecode_ms(toks[0])
			if ms is not None and all(is_flag_or_speed(t) for t in toks[1:]) and rest.strip():
				return "canonical", ms
	parts = line.split(None, 1)
	if parts:
		ms = timecode_ms(parts[0])
		if ms is not None and len(parts) == 2 and parts[1].strip():
			return "fallback", ms
	return None, None


def check_json_model(fixture, data):
	if not isinstance(data, dict):
		return fail(fixture, "expected JSON object at top level")
	if data.get("grammar") not in ("canonical", "fallback"):
		fail(fixture, f"grammar must be 'canonical' or 'fallback', got {data.get('grammar')!r}")
	cues = data.get("cues")
	if not isinstance(cues, list) or not cues:
		return fail(fixture, "cues must be a non-empty array")
	prev_ms = -1
	for i, cue in enumerate(cues):
		where = f"cues[{i}]"
		if not isinstance(cue, dict):
			fail(fixture, f"{where} is not an object")
			continue
		extra = set(cue) - {"time_ms", "fractional", "flag", "speed", "track"}
		if extra:
			fail(fixture, f"{where} has unknown keys {sorted(extra)}")
		if not isinstance(cue.get("time_ms"), int) or cue["time_ms"] < 0:
			fail(fixture, f"{where}.time_ms must be a non-negative integer")
		elif cue["time_ms"] <= prev_ms:
			fail(fixture, f"{where}.time_ms {cue['time_ms']} not strictly ascending")
		else:
			prev_ms = cue["time_ms"]
		if not isinstance(cue.get("fractional"), bool):
			fail(fixture, f"{where}.fractional must be a boolean")
		if cue.get("flag") not in FLAGS:
			fail(fixture, f"{where}.flag must be '<3', 'X', or null")
		speed = cue.get("speed")
		if speed is not None and (not isinstance(speed, int) or not 0 <= speed <= 9):
			fail(fixture, f"{where}.speed must be null or an integer 0-9")
		track = cue.get("track")
		if not isinstance(track, str) or not track.strip():
			fail(fixture, f"{where}.track must be a non-empty string")
	return cues


def check_canonical_file(fixture, text, cues):
	if "\r" in text:
		fail(fixture, "canonical file must be LF-only")
	if not text.endswith("\n") or text.endswith("\n\n"):
		fail(fixture, "canonical file must end with exactly one trailing LF")
	lines = text.split("\n")[:-1]
	if any(not line for line in lines):
		fail(fixture, "canonical file must not contain blank lines")
	if cues is not None and len(lines) != len(cues):
		fail(fixture, f"canonical has {len(lines)} lines but JSON has {len(cues)} cues")
		return
	for i, line in enumerate(lines):
		m = CANONICAL_LINE.match(line)
		if not m:
			fail(fixture, f"canonical line {i + 1} is not lint-clean canonical form: {line!r}")
			continue
		if cues is None:
			continue
		hh, mm, ss, frac, flag_tok, speed_tok, track = m.groups()
		cue = cues[i]
		if int(mm) > 59 or int(ss) > 59:
			fail(fixture, f"canonical line {i + 1}: minutes/seconds must be < 60 after overflow normalization")
		ms = ((int(hh or 0) * 3600 + int(mm) * 60 + int(ss)) * 1000) + int(frac or 0)
		if ms != cue.get("time_ms"):
			fail(fixture, f"canonical line {i + 1}: time {ms}ms != JSON time_ms {cue.get('time_ms')}")
		if (frac is not None) != bool(cue.get("fractional")):
			fail(fixture, f"canonical line {i + 1}: fraction presence disagrees with JSON fractional")
		flag = flag_tok.strip() if flag_tok else None
		if flag != cue.get("flag"):
			fail(fixture, f"canonical line {i + 1}: flag token disagrees with JSON flag")
		speed = int(speed_tok.strip()[1]) if speed_tok else None
		if speed != cue.get("speed"):
			fail(fixture, f"canonical line {i + 1}: speed token disagrees with JSON speed")
		if track != cue.get("track"):
			fail(fixture, f"canonical line {i + 1}: track {track!r} != JSON track {cue.get('track')!r}")


def check_valid_dir(valid_dir):
	count = 0
	for cd in sorted(valid_dir.glob("*.cd")):
		if cd.name.endswith(".canonical.cd"):
			continue
		count += 1
		name = cd.name[:-3]
		fixture = f"valid/{name}"
		json_path = valid_dir / f"{name}.json"
		canon_path = valid_dir / f"{name}.canonical.cd"
		cues = None
		if not json_path.exists():
			fail(fixture, "missing expected-output .json")
		else:
			try:
				cues = check_json_model(fixture, json.loads(json_path.read_text(encoding="utf-8")))
			except (json.JSONDecodeError, UnicodeDecodeError) as e:
				fail(fixture, f"unreadable JSON: {e}")
		if not canon_path.exists():
			fail(fixture, "missing .canonical.cd")
		else:
			check_canonical_file(fixture, canon_path.read_text(encoding="utf-8"), cues)
	return count


def check_invalid_dir(invalid_dir):
	count = 0
	for cd in sorted(invalid_dir.glob("*.cd")):
		count += 1
		fixture = f"invalid/{cd.stem}"
		json_path = invalid_dir / f"{cd.stem}.json"
		if not json_path.exists():
			fail(fixture, "missing expected-error .json")
			continue
		try:
			data = json.loads(json_path.read_text(encoding="utf-8"))
		except (json.JSONDecodeError, UnicodeDecodeError) as e:
			fail(fixture, f"unreadable JSON: {e}")
			continue
		if set(data) != {"error", "line"}:
			fail(fixture, f"expected exactly {{'error', 'line'}}, got {sorted(data)}")
			continue
		if data["error"] not in ERROR_CODES:
			fail(fixture, f"unknown error code {data['error']!r}")
		n_lines = len(cd.read_text(encoding="utf-8").splitlines())
		if not isinstance(data["line"], int) or not 1 <= data["line"] <= max(n_lines, 1):
			fail(fixture, f"line {data['line']!r} out of range for a {n_lines}-line file")
	return count


def check_example(path):
	name = path.name
	try:
		text = path.read_text(encoding="utf-8")
	except UnicodeDecodeError as e:
		fail(name, f"not valid UTF-8: {e}")
		return
	kinds = {}
	prev_ms = -1
	ok = True
	for lineno, raw in enumerate(text.splitlines(), start=1):
		line = raw.strip()
		if not line:
			continue
		kind, ms = classify_line(line)
		if kind is None:
			fail(name, f"line {lineno} unparseable under both grammars: {line!r}")
			ok = False
			continue
		kinds.setdefault(kind, lineno)
		if ms <= prev_ms:
			fail(name, f"line {lineno} timecode not strictly ascending")
			ok = False
		prev_ms = max(prev_ms, ms)
	if not kinds:
		fail(name, "no cue lines found")
		return
	if len(kinds) > 1:
		fail(name, f"MIXED GRAMMAR (E09 trap): first canonical line {kinds['canonical']}, first fallback line {kinds['fallback']}")
		ok = False
	n = sum(1 for l in text.splitlines() if l.strip())
	verdict = next(iter(kinds)) if len(kinds) == 1 else "mixed"
	print(f"  {name}: {verdict}, {n} cues {'OK' if ok else 'FAILED'}")


def main():
	tests = Path(sys.argv[1] if len(sys.argv) > 1 else "tests")
	if not tests.is_dir():
		sys.exit(f"no such directory: {tests}")
	repo_root = tests.parent
	n_valid = check_valid_dir(tests / "valid") if (tests / "valid").is_dir() else 0
	n_invalid = check_invalid_dir(tests / "invalid") if (tests / "invalid").is_dir() else 0
	examples = sorted(repo_root.glob("*.cd")) + sorted((repo_root / "examples").glob("*.cd"))
	if examples:
		print(f"examples ({len(examples)}):")
		for path in examples:
			check_example(path)
	print(f"checked {n_valid} valid + {n_invalid} invalid fixtures + {len(examples)} example file(s)")
	if failures:
		print(f"\n{len(failures)} problem(s):")
		print("\n".join(failures))
		sys.exit(1)
	print("corpus is structurally sound ✅")


if __name__ == "__main__":
	main()