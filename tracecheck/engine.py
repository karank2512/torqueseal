"""Match RFQ lines to supplier certs, run checks, and decide PASS / HOLD / BLOCK."""

import csv
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

PASS, HOLD, BLOCK = "PASS", "HOLD", "BLOCK"
SEVERITY = {PASS: 0, HOLD: 1, BLOCK: 2}

EXPIRY_WARNING_DAYS = 30
# Part numbers this similar to the RFQ part are shown as candidates (and rejected
# if they differ), so a reviewer can see the near-miss instead of just "missing".
CANDIDATE_SIMILARITY = 0.8


@dataclass
class RfqLine:
    line_id: str
    part_number: str
    description: str
    qty: int
    spec: str
    certs_required: list


@dataclass
class Check:
    name: str
    status: str
    detail: str
    doc_id: str = None


@dataclass
class LineResult:
    line_id: str
    part_number: str
    decision: str
    reason: str
    documents: list = field(default_factory=list)
    checks: list = field(default_factory=list)
    rejected_candidates: list = field(default_factory=list)
    override: dict = None


def worst(statuses):
    return max(statuses, key=SEVERITY.__getitem__, default=PASS)


def normalize(value):
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def load_rfq(path):
    with open(path, newline="") as f:
        return [
            RfqLine(
                line_id=row["line_id"],
                part_number=row["part_number"],
                description=row["description"],
                qty=int(row["qty"]),
                spec=row["spec"],
                certs_required=[c.strip() for c in row["certs_required"].split(";") if c.strip()],
            )
            for row in csv.DictReader(f)
        ]


def load_store(docs_dir):
    return [json.loads(p.read_text()) for p in sorted(Path(docs_dir).glob("*.json"))]


def check_part_number(line, doc):
    if doc["part_number"] == line.part_number:
        return Check("part_number_match", PASS, f"exact match {line.part_number}", doc["doc_id"])
    if normalize(doc["part_number"]) == normalize(line.part_number):
        return Check("part_number_match", HOLD,
                     f"partial match: cert says {doc['part_number']}, RFQ says {line.part_number}",
                     doc["doc_id"])
    return Check("part_number_match", BLOCK,
                 f"cert is for {doc['part_number']}, not {line.part_number}", doc["doc_id"])


def check_spec(line, doc):
    if normalize(doc["spec"]) == normalize(line.spec):
        return Check("spec_match", PASS, f"spec {line.spec}", doc["doc_id"])
    return Check("spec_match", BLOCK, f"cert spec {doc['spec']} does not meet {line.spec}", doc["doc_id"])


def check_expiry(doc, as_of):
    valid_until = date.fromisoformat(doc["valid_until"])
    days_left = (valid_until - as_of).days
    if days_left < 0:
        return Check("expiry", BLOCK, f"{doc['doc_id']} expired {valid_until}", doc["doc_id"])
    if days_left <= EXPIRY_WARNING_DAYS:
        return Check("expiry", HOLD, f"{doc['doc_id']} expires {valid_until} ({days_left} days)", doc["doc_id"])
    return Check("expiry", PASS, f"valid until {valid_until}", doc["doc_id"])


def check_lot_fields(doc):
    # A mill cert is traced by heat number; a CoC must name both its lot and the heat it came from.
    needed = ["heat"] if doc["doc_type"] == "MILL_CERT" else ["lot", "heat"]
    missing = [k for k in needed if not doc.get(k)]
    if missing:
        return Check("lot_traceability", BLOCK,
                     f"{doc['doc_id']} has no {' or '.join(missing)} number", doc["doc_id"])
    return Check("lot_traceability", PASS,
                 ", ".join(f"{k} {doc[k]}" for k in needed), doc["doc_id"])


def evaluate_doc(line, doc, as_of):
    pn = check_part_number(line, doc)
    if pn.status == BLOCK:
        return [pn]
    return [pn, check_spec(line, doc), check_expiry(doc, as_of), check_lot_fields(doc)]


def check_lot_continuity(chosen):
    mill, coc = chosen.get("MILL_CERT"), chosen.get("COC")
    if not (mill and coc and mill.get("heat") and coc.get("heat")):
        return None
    if mill["heat"] == coc["heat"]:
        return Check("lot_continuity", PASS, f"CoC heat {coc['heat']} matches mill cert")
    return Check("lot_continuity", BLOCK,
                 f"CoC heat {coc['heat']} does not match mill cert heat {mill['heat']}")


def evaluate_line(line, store, as_of):
    result = LineResult(line.line_id, line.part_number, PASS, "")
    chosen = {}
    for doc_type in line.certs_required:
        similarity = {
            d["doc_id"]: SequenceMatcher(None, normalize(d["part_number"]), normalize(line.part_number)).ratio()
            for d in store if d["doc_type"] == doc_type
        }
        candidates = sorted(
            (d for d in store if similarity.get(d["doc_id"], 0) >= CANDIDATE_SIMILARITY),
            key=lambda d: -similarity[d["doc_id"]],
        )
        scored = [(d, evaluate_doc(line, d, as_of)) for d in candidates]
        usable = [(d, checks) for d, checks in scored if checks[0].status != BLOCK]
        for d, checks in scored:
            if checks[0].status == BLOCK:
                result.rejected_candidates.append({"doc_id": d["doc_id"], "reason": checks[0].detail})
        if not usable:
            near = f" (closest: {scored[0][0]['part_number']})" if scored else ""
            result.checks.append(Check("document_present", BLOCK,
                                       f"no {doc_type} on file for {line.part_number}{near}"))
            if scored:
                result.checks.extend(scored[0][1])
            continue
        doc, checks = min(usable, key=lambda dc: SEVERITY[worst(c.status for c in dc[1])])
        chosen[doc_type] = doc
        result.documents.append({"doc_id": doc["doc_id"], "doc_type": doc_type,
                                 "issuer": doc["issuer"], "source_file": doc["source_file"]})
        result.checks.append(Check("document_present", PASS, f"{doc_type} {doc['doc_id']}", doc["doc_id"]))
        result.checks.extend(checks)

    continuity = check_lot_continuity(chosen)
    if continuity:
        result.checks.append(continuity)

    result.decision = worst(c.status for c in result.checks)
    if result.decision == PASS:
        result.reason = "all required certs present, matched, current, and lot-traceable"
    else:
        result.reason = next(c.detail for c in result.checks if c.status == result.decision)
    return result


@dataclass
class GateReport:
    as_of: str
    status: str
    released: bool
    summary: dict
    lines: list

    def to_dict(self):
        return asdict(self)


def run_gate(rfq_lines, store, as_of, approvals=None, reviewer=None):
    """Evaluate every line and decide whether the quote may be released.

    approvals: line_ids a human has reviewed and approved. Only HOLD lines can be
    approved; a BLOCK cannot be overridden because the evidence itself failed.
    """
    approvals = set(approvals or [])
    results = [evaluate_line(line, store, as_of) for line in rfq_lines]
    unknown = approvals - {r.line_id for r in results}
    if unknown:
        raise ValueError(f"unknown line ids in approvals: {', '.join(sorted(unknown))}")
    for r in results:
        if r.line_id not in approvals:
            continue
        if r.decision != HOLD:
            raise ValueError(f"{r.line_id} is {r.decision}; only HOLD lines can be approved")
        r.override = {"reviewer": reviewer or "unknown", "action": "approved", "on": as_of.isoformat(),
                      "original_reason": r.reason}

    decisions = [r.decision for r in results]
    summary = {s: decisions.count(s) for s in (PASS, HOLD, BLOCK)}
    open_holds = [r for r in results if r.decision == HOLD and not r.override]
    if summary[BLOCK]:
        status = "BLOCKED"
    elif open_holds:
        status = "AWAITING_REVIEW"
    else:
        status = "RELEASED"
    return GateReport(as_of.isoformat(), status, status == "RELEASED", summary,
                      [asdict(r) for r in results])
