# Prototype: trace-before-bid

A small Python prototype of the feature in [README.md](README.md). Before a quote goes out, every RFQ line is matched to supplier certs, gets a traceability receipt, and gets a PASS, HOLD, or BLOCK decision. If any line is BLOCKed, the quote is not released.

All data is synthetic. No accounts, no API keys, no network. Python 3 stdlib only (pytest for tests).

## Run it (2 minutes)

```bash
python3 -m tracecheck run sample_data/rfq.csv --as-of 2026-10-21
```

`--as-of` pins the check date so the expiry results match the output below. Leave it off to check against today. The command prints the gate table and then the full JSON report. Exit code is 0 when released, 1 when waiting on human review, 2 when blocked.

Other options:

```bash
# a reviewer approves a HOLD line (logged in the report as an override)
python3 -m tracecheck run sample_data/rfq.csv --as-of 2026-10-21 --approve L03 --reviewer karan

# trying to approve a BLOCK line is refused
python3 -m tracecheck run sample_data/rfq.csv --approve L05

# also write the JSON report to a file
python3 -m tracecheck run sample_data/rfq.csv --json-out report.json
```

Tests:

```bash
python3 -m venv .venv && .venv/bin/pip install pytest
.venv/bin/pytest -q
```

## Sample gate table

```
LINE  PART NUMBER       DECISION  REASON
----  ----------------  --------  ------
L01   AN960C10L         PASS      all required certs present, matched, current, and lot-traceable
L02   MS20470AD4-6      PASS      all required certs present, matched, current, and lot-traceable
L03   NAS6204-12        HOLD      MILL-3001 expires 2026-11-05 (15 days)
L04   M83248/1-110      HOLD      partial match: cert says M83248-1-110, RFQ says M83248/1-110
L05   MS27039-1-08      BLOCK     COC-5001 expired 2026-08-01
L06   NAS1149F0363P     BLOCK     no COC on file for NAS1149F0363P (closest: NAS1149F0332P)
L07   BAR-7075T6-1.000  BLOCK     COC-7002 has no lot or heat number
L08   MS21042L4         BLOCK     CoC heat H-22817 does not match mill cert heat H-22871
L09   NAS1611-014       BLOCK     cert spec NAS1612 does not meet NAS1611

2 pass, 2 hold, 5 block (as of 2026-10-21)
QUOTE NOT RELEASED: fix the BLOCK lines; blocks cannot be overridden.
```

Each line in the JSON report carries its receipt: the documents used (doc id, type, issuer, source file), every check that ran with its status and the doc it ran against, any near-miss candidates that were rejected, and the reviewer override if there was one.

## What's in the repo

| Path | What it is |
| --- | --- |
| `sample_data/rfq.csv` | 9 RFQ lines: part number, qty, spec, required certs (`COC`, `MILL_CERT`) |
| `sample_data/docs/*.json` | Mock supplier document store: 13 mill certs and CoCs, each pointing at a fake inbox or ERP file. Seeded with an expired cert, one about to expire, a part number written differently, a cert for the wrong part, a CoC with no lot or heat, a heat number that does not match the mill cert, and a wrong spec |
| `tracecheck/engine.py` | Matching, checks, decisions, and the release gate |
| `tracecheck/cli.py` | `run` command, gate table, JSON report, approvals |
| `tests/test_tracecheck.py` | Each PASS, HOLD, and BLOCK path, the release gate, and an end-to-end run on the sample data |

## How decisions are made

For each required cert type on a line, the engine looks for docs of that type whose part number is close to the RFQ part number, runs the checks below on each, and keeps the best one.

| Check | PASS | HOLD | BLOCK |
| --- | --- | --- | --- |
| Document present | a usable cert of the required type is on file | | none on file |
| Part number match | exact | same characters, different formatting (`M83248-1-110` vs `M83248/1-110`) | cert is for a different part |
| Spec match | same spec | | different spec |
| Expiry | valid more than 30 days | expires within 30 days | expired |
| Lot traceability | mill cert has heat; CoC has lot and heat | | missing lot or heat |
| Lot continuity | CoC heat matches mill cert heat | | heats differ |

The line decision is the worst check result, and the reason is the first check that produced it. The quote is `BLOCKED` if any line is BLOCK, `AWAITING_REVIEW` if any HOLD is not yet approved, otherwise `RELEASED`. A human can approve a HOLD, which is logged with their name. A BLOCK cannot be approved, because the evidence itself failed.

## Mapping to the proposal

| Proposal (README) | In this prototype |
| --- | --- |
| "each RFQ line gets a traceability receipt and a pass, hold, or block decision" | Per-line `documents` and `checks` in the JSON report, with a decision and one-line reason |
| Match the evidence: link the supplier doc to the line and check the part number matches | Candidate matching against the doc store, `part_number_match`, rejected near-miss candidates listed in the receipt |
| Flag risk the way DLA does: "certificate can't be verified" (pains 3, 4) | Expired certs, wrong spec, missing lot or heat, and heat breaks between mill cert and CoC all BLOCK |
| Small dealer "gets tripped up" on traceability (pain 2) | Lot continuity check proves the CoC traces back to the mill heat |
| "Hold the line, don't guess": weak evidence goes to a human, quote can't go out until approved, decision is logged | HOLD sets status `AWAITING_REVIEW`; `--approve` with `--reviewer` writes an override entry; BLOCK refuses release |
| Every decision links to the document behind it (tell) | Every check records the `doc_id` it ran on, and each doc carries its `source_file` |

## Not in this prototype

The proposal also covers CAGE codes, dealer authorization letters, price far below past awards, new subcontractors with no history, packaging and marking notes, and LLM extraction from real PDFs and email. Here the docs are already structured JSON, so the focus is the gate logic and the receipt. Those signals would slot in as more checks in `evaluate_doc` or `evaluate_line`.
