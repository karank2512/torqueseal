# SalesPatriot: Feature Proposal

- **Company:** SalesPatriot (YC W25), an AI-native platform for quoting and procurement in aerospace, electronics, industrial, and defense supply chains
- **Role:** Forward Deployed Engineer (San Francisco, onsite at customers on weekdays)
- **Posting:** https://jobs.ashbyhq.com/SalesPatriot/53626ad9-af69-4ee1-a947-ba2ef4a433a7 (published 2026-05-25)
- **Date researched:** 2026-10-21

## Pain points

SalesPatriot's customers are suppliers that quote on government RFQs (the YC profile says it helps them "find, review and bid on RFQ solicitations" with the Pentagon and as subcontractors: https://www.ycombinator.com/companies/salespatriot). I found no public G2, Capterra, Reddit, or Hacker News threads about SalesPatriot itself, and Reddit was not reachable from my research tools. So these pains come from DLA's own public material, a public vendor guide, and the company's posting.

1. **Quotes move through inboxes and spreadsheets.** The posting says billions of dollars in parts "still move through email threads, excel sheets, and disconnected ERPs." Source: SalesPatriot posting, May 2026. https://jobs.ashbyhq.com/SalesPatriot/53626ad9-af69-4ee1-a947-ba2ef4a433a7
2. **Small dealers quote an exact product and then can't trace it.** DLA's "Typical Product Substitution Scenario" says a small business dealer quotes "exact product," and when the contracting officer asks for traceability the dealer "gets tripped up." It also lists "no traceability to approved sources because purchased on Amazon, eBay, etc." Source: DLA Land and Maritime counsel briefing, DLA Supply Chain Alliance Conference, April 24, 2024 (slide 17). https://ndia.dtic.mil/wp-content/uploads/2024/dla/Wed_Breakout_CYA.pdf
3. **Fraudulent subcontractors target small dealers.** The same briefing says criminal organizations are "increasingly inserting themselves in DLA's supply chains as subcontractors." It says they approach "small business dealer/distributors" with very low prices and deliver parts that "may pass a kind, count, and condition visual inspection, but fail any sort of rigorous testing." Its warning signs include being "Unable to verify authenticity of various certificates." Source: same deck, April 24, 2024 (slides 11 to 14). https://ndia.dtic.mil/wp-content/uploads/2024/dla/Wed_Breakout_CYA.pdf
4. **DLA asks for traceability on the quotes that look risky.** DLA's small business training page says contracting officers must be able to confirm a documentation trail from the supplier back to the approved manufacturer. It says these requests usually come up when a non-OEM supplier quotes or a vendor has no DLA history. Source: DLA Small Business, "Supply Chain Traceability," August 2025 (paraphrased; the page blocked direct fetch, so I worked from the indexed excerpt). https://www.dla.mil/Small-Business/Resource-Center/Training-Resources/Details/Article/4181179/supply-chain-traceability/
5. **Avoidable quoting mistakes are common.** A public DIBBS guide lists first-timer mistakes, including "Quoting without reading packaging and marking requirements," "Ignoring sourcing restrictions," and lead time being "a guess instead of a quote." Source: NextPlus blog, August 10, 2026. https://nextplus.org/blog/how-to-quote-on-dla-dibbs

## Proposed feature: a traceability check before every quote goes out

**Trace-before-bid.** Before a quote leaves SP Studio, each RFQ line gets a traceability receipt and a pass, hold, or block decision.

- **Parse the requirement.** Read the approved source CAGE and part number from the solicitation, plus the exact or alternate product it asks for and any packaging or marking notes (pains 2 and 5).
- **Match the evidence.** Pull the supplier quote, dealer authorization letter, or invoice already in the customer's email or ERP and link it to the line (pain 1). Check that the CAGE and part number match, that the document comes from the approved source or an authorized dealer, and that the supplier quoted lead time and packaging.
- **Flag risk the way DLA does.** Raise a flag when a CAGE doesn't match, when a new subcontractor has no history, when a price falls far below past awards, or when a certificate can't be verified. These are the same signals DLA lists in pains 3 and 4.
- **Hold the line, don't guess.** Any line with weak evidence goes to a human with the reason and the documents attached. The quote can't go out until someone approves or overrides it, and that decision is logged.

Why this feature: one bad trace can cost a supplier the contract. The paperwork already lives in the inboxes SalesPatriot reads, so checking it before submission is a narrow add-on that protects the supplier's DLA standing.

## How Karan would build it

| Piece of the feature | What Karan has already built | Project |
| --- | --- | --- |
| Every decision links to the document behind it | Every score in tell links to its public-record receipt | tell (github.com/karank2512/tell-ai) |
| Reliable ingestion from messy sources (RFQs, inbox, ERP exports) | 6 idempotent collectors tracking 907 companies and 10,585 open postings at 97.8% run success over 321 runs, built solo | tell |
| Weak evidence goes to a human instead of auto-submitting | Holds low-confidence writes back for a human; exactly-once HubSpot writes | RelayIQ |
| Measuring match accuracy before trusting it | Went from 68% to 77% accuracy on a 495-case seeded benchmark | RelayIQ |
| Approve or override log for each line | Approve/deny traces tied to tool call IDs (fully tested MVP in simulated mode, no customers) | Foreman |
| Checking each LLM extraction (CAGE, part number, packaging) | Evals that score every LLM output 3 ways | Foreman |
| Retrieving the right document for a line | Retrieval assistant used daily by 60+ staff, cut manual lookup time 40%, evaluated against a golden set | Production AI at UW-Madison IT |

## Rough demo plan (3 to 4 days, public data only)

1. **Day 1:** Build about 30 synthetic RFQ lines that use the "exact product" fields from DLAD Procurement Note L04 (CAGE code, part number), as shown in the April 2024 DLA deck. Pair each line with a fake supplier quote, dealer letter, or marketplace-style invoice. Seed known failures: a mismatched CAGE, a missing dealer letter, a marketplace invoice, a price far below the usual range, and missing packaging details.
2. **Day 2:** Write an extractor in TypeScript and Postgres, the posting's stack. It pulls CAGE, part number, and lead time from each document. Then add rule checks and an LLM check that every extraction must pass.
3. **Day 3:** Build a React review queue. Each line shows pass, hold, or block, the reason, and the linked documents. Approving or overriding writes a log row.
4. **Day 4:** Score the run against the seeded labels: how many bad lines were caught and how many good lines were held by mistake. Record a short Loom walkthrough.

No DIBBS account or customer data is needed. The demo shows the workflow, not real performance numbers.

## LinkedIn note

> Hi, I'm Karan. I built tell solo: 6 collectors, 907 companies, 97.8% run success over 321 runs, every score linked to its receipt. I'd love to bring that to SalesPatriot as an FDE, starting with a traceability check on every quote. Open to a quick chat?
