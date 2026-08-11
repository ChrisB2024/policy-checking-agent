# Policy Check — System Thinking Framework Applied

**Project:** Policy Check (renewal vs. expiring commercial policy comparison)
**Applied:** 2026-08-03
**Current scope per H2 plan:** demo-grade only through 2026
**Framework source:** System Thinking Framework, Phases 0–9

> **Headline finding:** This project is at Phase 5 architecturally and Phase 0 is unfinished. The spec depth — `PolicySnapshot`, `field_at` resolution, USPS Pub 28 normalization, `Unresolved` enum, confidence via two-pass agreement — is Phase 2 and Phase 5 work of real quality. But the Phase 0 test cannot be completed with observed facts, only assumed ones. Everything downstream inherits that gap.

---

## PHASE 0 — Problem Thinking

### 1. Who hurts and why

The framework demands one sentence with every blank filled by specifics. Here it is, with the unverified parts marked:

> A **commercial lines account manager** at a 5–25 person independent NJ agency currently **reads the expiring policy and the renewal side by side in two PDF windows, manually noting limit and endorsement changes** *(assumed, not observed)* because **carriers don't issue a diff and the AMS doesn't store coverage detail at field level** *(assumed)*, and Policy Check eliminates this by **extracting both documents to a common schema and applying deterministic rules that flag every material difference with a page-level citation.**

Two blanks are assumptions. That is the project's largest open risk and it is not a technical one.

**A structural problem the framework surfaces:** it asks for *a* specific person. Policy Check has two, and they want different things.

| | Account Manager | Principal |
|---|---|---|
| Relationship to product | User — runs it, reads the findings | Buyer — signs the check |
| Pain | Time, volume, renewal-season crush | E&O exposure, one missed endorsement |
| What makes them adopt | Fewer minutes per renewal | Defensible audit trail |
| What makes them abandon | Noise, false positives | A single missed material change |

A product that serves the AM's pain (speed) and one that serves the principal's pain (defensibility) pull in opposite directions — speed wants fewer flags, defensibility wants more. **Resolve this explicitly or the product will drift toward whichever one you spoke to most recently.**

Recommendation: build for the principal's invariant (never miss a material adverse change), then solve the AM's pain through severity ranking and ordering, not through suppression.

### 2. Product invariants

- Every flagged difference cites the source page and field in **both** documents. An uncited finding never renders — it is a bug, not a low-confidence result.
- The system reports that something **differs**; it never states whether the difference is good or bad for the insured. Materiality is a rules classification, not a coverage opinion.
- Missing data renders as *"not found in this document"* — **never** as absence of change. A null must never be silently read as "unchanged." This is the single most dangerous failure mode in the product.
- When extraction confidence falls below threshold, the field is surfaced as unverified and routed to human review, never guessed.
- No output reaches an insured without a human approving it.

**Adaptation of the framework's 2-second rule:** it doesn't apply here. Comparing two 40-page policies is a minutes-long job and users know it. The equivalent invariant is *the user always knows what stage the job is in and how much remains.* Silent processing is the trust violation, not slowness.

### 3. Product causality chains

Two chains run in opposite directions. Both matter.

**Chain A — the survival chain.**
Material change missed → AM relies on the report instead of reading → insured discovers the gap at claim time → E&O claim against the agency → agency terminates and talks → Hiclone loses the vertical, not just the client.

**Chain B — the retention chain.**
Report flags 60 differences on a routine renewal → AM stops reading past the first page → tool becomes shelfware → retainer churns at month three.

Chain A is fatal and Chain B is merely expensive. That asymmetry justifies the acceptance gate of 100% recall on material adverse changes with tolerance for lower precision — **and it means noise gets solved by ranking and grouping, never by dropping findings.**

Write this down as the reason, because in six months a noisy demo will create pressure to suppress, and the pressure will feel reasonable.

### 4. Security invariants — defined now, not later

**What the product touches:** complete commercial policies. Named insured and FEIN, all covered locations, loss history, premium and rating basis, and depending on line: driver schedules with license numbers, employee counts and payroll, equipment schedules with serial numbers.

This is non-public personal information under insurance regulation, not generic business data.

**Regulatory scope to confirm before the first client document:**
- Whether NJ has adopted the NAIC Insurance Data Security Model Law, and what it obligates of a third-party service provider
- NY DFS Part 500 (23 NYCRR 500) — likely in scope the moment you expand to the NYC metro, since NJ agencies commonly write NY risks
- Carrier and agency contractual vendor security terms, which frequently bind harder than statute

**Blast radius:** a compromised extraction store is not one agency's data. It is a corpus of complete commercial policies across every agency you serve — coverage limits, loss history, and locations, assembled and structured. That is a materially more attractive target than the source PDFs sitting in an AMS.

**The demo scope is itself the primary security control.** Running only on public specimen forms and public procurement filings through 2026 means there is no NPI to breach. Preserve that deliberately — the first client document is a regulatory threshold crossing, not just a milestone.

**Shutdown answer, decided now:** client documents are deleted on engagement termination within a stated window; extracted structured data is deleted with them; only anonymized rule-performance statistics survive.

---

## PHASE 1 — Mental Models

### Inputs → Processing → Outputs

**In:** expiring policy PDF, renewal policy PDF, agency materiality configuration.
**Processing:** classify pages → extract to schema → normalize → compare by rules → narrate findings.
**Out (product):** internal findings report, client-facing renewal summary.
**Out (plumbing):** extraction JSON, normalizer version, page classifications.

One output sits on the boundary: **confidence scores.** Internally they're plumbing. Surfaced to the AM as *"these three fields need your eyes"*, they become one of the most valuable parts of the product — it converts the system's uncertainty into a directed task rather than a hedge. Promote it.

### State machines

**Document lifecycle:** uploaded → classified → extracted → normalized → compared → narrated → under review → approved → delivered.

**Finding lifecycle:** detected → classified material/immaterial → confirmed or dismissed by reviewer → included or excluded from output.

The reviewer's dismiss action is the highest-value state transition in the system. It is simultaneously rule-tuning signal and E&O audit trail. **Log it with the reviewer, timestamp, finding, and reason — from day one.**

An undesigned reachable state is a bug: *"extracted under normalizer v1, compared against a snapshot normalized under v2."* Your `normalizer_version` field on `DocumentMeta` already anticipates exactly this. The framework's point is that the check must be enforced at the comparator boundary, not merely recorded.

### Trust boundaries

The one that gets missed: **the uploaded PDF is untrusted input to a language model.** A document can contain text — visible or not — crafted to manipulate extraction. This is not hypothetical for a product whose corpus includes documents sourced from public court filings and procurement portals.

Your architecture already mitigates it structurally, which is worth recognizing explicitly:
- Extraction output is schema-constrained, so injected text cannot introduce fields
- The comparator is deterministic and never interprets free text as instruction
- The narrator receives **structured findings only**, never raw document text

Make that third one an enforced contract, not a convention. The narrator must be architecturally incapable of seeing document text.

---

## PHASE 2 — Decomposition

| Module | Promise | Must never |
|---|---|---|
| **Ingest** | Accepts a PDF, emits pages with stable indices | Modify page content or reorder |
| **Classifier** | Labels each page by document section | Discard an unclassifiable page silently |
| **Extractor** | Page → typed fields with citations and confidence | Emit a field without a page citation |
| **Normalizer** | Raw values → canonical form, versioned | Normalize away a semantic difference |
| **Comparator** | Two snapshots → findings with materiality | Consult a model for any decision |
| **Narrator** | Findings → plain language | Receive raw document text; add a judgment |
| **Reporter** | Findings + narration → two artifacts | Render an uncited finding |
| **Review gate** | Human approval, logged | Be bypassable by any code path |

### Failure mode analysis

- **Extractor receives a scanned page with no text layer.** Must emit an explicit unextractable marker. Silent empty extraction becomes phantom "no change" — the fatal null bug.
- **Normalizer encounters an address format outside the Pub 28 pipeline.** Must preserve raw and mark unnormalized rather than produce a wrong `match_key`, which creates a phantom diff or, worse, a phantom match.
- **Comparator finds a form on the renewal absent from expiring, with no matching rule.** Must classify as unknown-material and surface, never drop. Unknown defaults to visible.
- **Extraction confidence disagrees across the two passes.** `agreement()` low → route to review, don't average.
- **Extractor is compromised or manipulated.** Blast radius must stop at the schema. Nothing downstream trusts extractor output as instruction.

### System evolution test

Adding a new line of business — Property after GL, then Auto, then WC — should require a schema extension and a rules file. **If it requires touching the comparator, the comparator is coupled to a line of business and the decomposition is wrong.** Test this on paper before building the second line.

---

## PHASE 3 — Math, honestly scoped

Most of this phase doesn't apply. Naming what doesn't is as useful as naming what does.

**Applies:**
- **Statistics.** Your eval harness makes a recall claim. With ~20 synthetic renewal pairs, "100% recall on material adverse changes" is a statement about 20 pairs, not about the product. Know the confidence interval before you say the number to a principal — a small-sample claim stated as a general one is the kind of thing that ends badly in a regulated vertical.
- **Graph traversal.** `field_at` with `Unresolved` and `_match_in` is tree traversal over keyed collections. The `NO_SUCH_PATH` / `NO_SUCH_ROW` / `AMBIGUOUS` distinction is correct and worth preserving — collapsing them into a single "not found" destroys the information the review gate needs.

**Does not apply, and reaching for it would be a mistake:**
- **Embeddings and vector similarity.** The temptation will be to match forms or clauses by semantic similarity. Don't. Form matching is exact-match on form number and edition date — a deterministic problem with a deterministic answer. Semantic similarity introduces exactly the model-decides-materiality failure your architecture exists to prevent.
- Differential equations, queuing theory — not at this scale.

---

## PHASE 4 — Research, Plan, Implement, Validate

**Research.** Technical research is done. User research is not. The September screen shares in the H2 plan are not a sales activity that happens to be scheduled — **they are the Phase 0 dependency for this build.** Treat them as blocking.

**Plan.** Spec-first is already your practice and it shows. Add an explicit threat model document alongside it — currently absent.

**Implement.** The Feynman rule applies hardest to two places: the `field_at` resolution semantics and the Pub 28 normalization pipeline. If you can't explain in plain speech why zip5-only avoids phantom diffs, you can't defend a false negative that traces to it.

**Validate — three layers:**

1. *Technical* — eval harness with synthetic pairs and JSON manifests as ground truth. **Exists.**
2. *Security* — threat model run against implementation, including document-borne injection. **Does not exist.**
3. *Product* — put it in front of a real account manager and watch. **Has not happened.**

Two of three layers are missing, and the missing two are the ones that can't be fixed by writing more code.

---

## PHASE 5 — Architecture

**Data flow.** PDF → object storage → extraction service → structured store → comparator → report artifact. Every arrow crosses a boundary where a copy of client data now exists. Enumerate the copies; each one is a deletion obligation.

**Lifecycle.** Documents, snapshots, findings, and reports each need a retention answer. Ghost data in a system holding insurance NPI is not a performance problem, it's a disclosure problem.

**Communication.** ARQ background jobs with visible stage progression satisfies the Phase 0 progress invariant. Good fit.

**Least privilege.** The extraction service needs write access to the extraction store and nothing else. It should not be able to read other clients' snapshots or write reports. Set this up now while there's one service; retrofitting privilege separation onto a working system rarely happens.

**Defense in depth — deferred, deliberately.** Encryption at rest, audit logging, secret rotation, and access controls are not needed for a public-document demo. They are required before the first client PDF. Mark the boundary in the repo so it's a decision, not an oversight.

---

## PHASE 6 — Build a Real Product

**Three subsystems.** For most products the trust infrastructure supports the value engine. Here, **the trust infrastructure *is* the value engine** — citations, the review gate, and the audit trail are what an agency is buying. A comparison without citations is worthless to a principal defending an E&O claim. Don't treat them as a hardening layer to add later.

**Smallest useful thing.** Not a full `PolicySnapshot`. One line of business, declarations page plus schedule of forms only, comparing limits, named insured, locations, and form additions/removals. That single output is enough for an account manager to say "yes, that's the thing I do by hand." Ship that to a screen share before extending the schema.

**Instrument.** Every reviewer dismissal, every low-confidence route, every unextractable page. Attribution cannot be backfilled — your own operating principle, applied to your own build.

---

## PHASE 7 — Feedback Loops

- **User feedback:** what the AM says they want. Signal, not direction.
- **Behavioral data:** which findings get dismissed and which get acted on. This is the rule-tuning corpus and it is the most valuable data the product generates. It is also, note, the only path to reducing Chain B noise without violating Chain A.
- **System feedback:** extraction confidence distributions, unextractable page rates by carrier.

The correction to write down and check later: *you currently believe manual renewal comparison is a significant time cost for a commercial lines AM.* After the first three screen shares, compare that expectation to what you actually saw. If it turns out AMs spend twenty minutes rather than two hours, the product isn't dead — but the pitch moves entirely from time savings to E&O defensibility, and the pricing follows it.

---

## PHASE 8 — Meta-Skills

**Naming.** "Material" carries the entire product on its back and is currently undefined in writing. Define it as an enumerated rule set, not a concept.

And the harder one: **"Policy Check" implies checking, and checking implies a verdict.** The name flirts with the exact claim your E&O positioning depends on not making. Consider whether something in the diff/comparison family is safer to say in a room full of principals.

**Tradeoff thinking.** Recall over precision, chosen consciously, for the reason in Chain A. Written down so it survives contact with a noisy demo.

**Information boundaries.** The comparator must not know a model exists. The narrator must not know a document exists. Both are enforceable in code — enforce them.

**Communication.** You need one sentence that explains deterministic materiality to a principal who does not care about architecture. Something in the shape of: *the software finds the differences and a rulebook you can read decides which ones matter — no model gets a vote.* Refine it, then use it identically every time.

---

## PHASE 9 — Founder Layer

The framework's verdict on this project, plainly:

**Strong:** decomposition, invariants, architecture. Unusually strong for a pre-revenue product. The deterministic-materiality decision is genuinely defensible and most competitors can't say it.

**Weak:** Phase 0, and only Phase 0 — but it's the phase everything else is built on. Two blanks in the pain sentence are assumptions. The user research step was skipped because the architecture was more interesting than the interview, which is the most common and most expensive way for a well-built product to miss.

**The one thing to change:** stop treating the September screen shares as sales activity. They are the missing input to a build that is otherwise ahead of schedule. Do three of them before writing another line of extraction code, and bring the smallest-useful-thing demo to them rather than a finished system.

Your H2 plan already caps this project at demo-grade. The framework agrees, for a different reason than the plan gives: not because demo-grade is enough to sell, but because you don't yet know enough about the user to earn the right to build more.