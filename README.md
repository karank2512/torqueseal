# Torqueseal

**The quote says every part is traceable. Torqueseal checks the certs before it ships.**

[![Torqueseal demo](docs/demo.gif)](docs/demo.mp4)

*15 second demo: [docs/demo.mp4](docs/demo.mp4)*

One idea: a small dealer quotes the exact product on a government RFQ, the contracting officer asks for traceability, and the dealer gets tripped up. Torqueseal is a trace-before-bid check: before a quote goes out, every RFQ line is matched against the certs on file, gets a traceability receipt, and earns a PASS, HOLD, or BLOCK decision. If any line is BLOCKed, the quote is not released. One command: `python3 -m tracecheck run`.

## What this is (and what it is not)

Torqueseal is a working prototype of a quote-release gate for defense quoting tools: pass, hold, or block every RFQ line on the evidence behind it, before the quote ships. It runs entirely on synthetic data: no accounts, no API keys, no network, Python 3 standard library only (pytest for the tests).

It is a prototype, not a product. It is not affiliated with SalesPatriot or DLA. The sample RFQ, certs, and inboxes are all invented, and every seeded failure is reproduced for real by the engine, not faked in the output.

## The problem

These pains are documented, not hypothetical:

- DLA's own briefing describes the "typical product substitution scenario": a small business dealer quotes an exact product, and when the contracting officer asks for traceability, the dealer "gets tripped up" - including "no traceability to approved sources because purchased on Amazon, eBay, etc." [DLA Land and Maritime, April 2024 (slide 17)](https://ndia.dtic.mil/wp-content/uploads/2024/dla/Wed_Breakout_CYA.pdf)
- The same briefing says criminal organizations are "increasingly inserting themselves in DLA's supply chains as subcontractors," approaching small dealers with very low prices and parts that "may pass a kind, count, and condition visual inspection, but fail any sort of rigorous testing." [Same deck (slides 11-14)](https://ndia.dtic.mil/wp-content/uploads/2024/dla/Wed_Breakout_CYA.pdf)
- DLA's small business training tells suppliers that contracting officers must be able to confirm a documentation trail from the supplier back to the approved manufacturer, and that these requests come up exactly when a non-OEM supplier quotes. [DLA Small Business, "Supply Chain Traceability"](https://www.dla.mil/Small-Business/Resource-Center/Training-Resources/Details/Article/4181179/supply-chain-traceability/)

One bad trace can cost a supplier the contract and its DLA standing. The paperwork already lives in the supplier's inbox and ERP; checking it before submission is the narrow place to catch it.

## What Torqueseal does

```
$ python3 -m tracecheck run sample_data/rfq.csv --as-of 2026-10-21
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

- **Good lines pass only on evidence.** Exact part number, matching spec, certs current and lot-traceable, and the CoC heat number matching the mill cert heat.
- **Weak lines wait for a human, not a guess.** A cert expiring within 30 days or a part number written differently earns a HOLD. A reviewer approves it by name, and the override is logged in the report.
- **Bad lines block, and blocks cannot be overridden.** An expired cert, a missing CoC, no lot or heat number, a heat mismatch, or the wrong spec stops the quote. Exit code 2.

## Every line carries its receipt

After the gate table, the run prints a full JSON report. Each line links the documents it used (doc id, type, issuer, source file), every check that ran with its status and the doc it ran against, the near-miss candidates that were rejected, and any reviewer override. The receipt is the point: when the contracting officer asks, the answer is a document trail, not a memory.

## Quickstart

You need Python 3 (tested on 3.13). There are no runtime dependencies, no API keys, and no network traffic.

```bash
git clone https://github.com/karank2512/torqueseal.git
cd torqueseal
python3 -m tracecheck run sample_data/rfq.csv --as-of 2026-10-21
```

`--as-of` pins the check date so the expiry results match the output above; leave it off to check against today. Exit code is 0 when released, 1 when waiting on human review, 2 when blocked.

```bash
# a reviewer approves a HOLD line, logged in the report as an override
python3 -m tracecheck run sample_data/rfq.csv --as-of 2026-10-21 --approve L03 --reviewer karan

# trying to approve a BLOCK line is refused
python3 -m tracecheck run sample_data/rfq.csv --approve L05

# write the JSON report to a file
python3 -m tracecheck run sample_data/rfq.csv --json-out report.json
```

Tests: 18 of them cover every PASS, HOLD, and BLOCK path, the release gate, and an end-to-end run on the sample data.

```bash
python3 -m venv .venv && .venv/bin/pip install pytest
.venv/bin/pytest -q
```

## How decisions are made

For each required cert type on a line, the engine looks for docs of that type whose part number is close to the RFQ part number, runs these checks on each, and keeps the best one.

| Check | PASS | HOLD | BLOCK |
| --- | --- | --- | --- |
| Document present | a usable cert of the required type is on file | | none on file |
| Part number match | exact | same characters, different formatting (`M83248-1-110` vs `M83248/1-110`) | cert is for a different part |
| Spec match | same spec | | different spec |
| Expiry | valid more than 30 days | expires within 30 days | expired |
| Lot traceability | mill cert has heat; CoC has lot and heat | | missing lot or heat |
| Lot continuity | CoC heat matches mill cert heat | | heats differ |

The line decision is the worst check result, and the reason is the first check that produced it. The quote is `BLOCKED` if any line is BLOCK, `AWAITING_REVIEW` if any HOLD is not yet approved, otherwise `RELEASED`. A human can approve a HOLD, logged with their name. A BLOCK cannot be approved, because the evidence itself failed.

## Project layout

| Path | What it is |
| --- | --- |
| `sample_data/rfq.csv` | 9 RFQ lines: part number, qty, spec, required certs (`COC`, `MILL_CERT`) |
| `sample_data/docs/*.json` | 13 mock supplier documents (mill certs and CoCs), seeded with an expired cert, one about to expire, a differently formatted part number, a cert for the wrong part, a CoC with no lot or heat, a heat mismatch, and a wrong spec |
| `tracecheck/engine.py` | matching, checks, decisions, and the release gate |
| `tracecheck/cli.py` | the `run` command, gate table, JSON report, approvals |
| `tests/test_tracecheck.py` | 18 tests: every decision path, the gate, and an end-to-end run |
