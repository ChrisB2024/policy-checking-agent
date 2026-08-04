# Policy Check — Demo Build Spec

**Product:** Policy Check (wedge product, insurance vertical)
**Status:** Spec — not yet built
**Scope:** Demo-grade artifact for cold-start selling. Not production, not multi-tenant.
**Line of business:** Commercial package — General Liability + Commercial Property. Nothing else until eval gates are met.

---

## 1. Purpose

Produce a working policy comparison demo built entirely from publicly available documents, with no client dependency, that can be run on a laptop in front of a stranger at an industry event.

The demo exists to do three things, in this order:

1. Establish that the builder understands the account manager's actual job
2. Provoke correction — the findings taxonomy is the conversation piece, not the software
3. Produce a printable artifact (the renewal difference summary) that survives the conversation

Revenue is not a goal of this build. Credibility is.

### Non-goals

- Carrier portal integration
- AMS integration
- Any line of business beyond GL + property
- Multi-user accounts, billing, auth
- Retrieval / RAG / semantic search over policy language
- Coverage recommendations of any kind (see §11)

---

## 2. Invariants

These are locked. Changes to this list require an explicit decision, not drift.

1. **Materiality is decided by deterministic rules, never by a model.** The LLM extracts and narrates. It does not rule on whether a change matters.
2. **Every extracted field carries a page citation and a verbatim source snippet, or it does not appear in output.** No uncited claims.
3. **Uncertainty surfaces as `needs_review`, never as a guess.** Visible doubt on 5% of fields beats confident error on 2%.
4. **The eval set is authored before the extractor is written.** Ground truth first.
5. **Demo mode retains nothing.** Documents are processed in memory and discarded. This is stated to the prospect unprompted.
6. **The report describes changes. It never interprets them.** See §11.
7. **A human must be able to verify any single finding in under 90 seconds** by following the citation.

---

## 3. Corpus

### 3.1 Source policies (real, public)

Target: 15–20 complete commercial package policies including dec page, forms schedule, and endorsements.

| Source | What it yields | Notes |
|---|---|---|
| CourtListener / RECAP | Complete policies as litigation exhibits | Best source. Full-text searchable. Coverage disputes attach entire policies. |
| Public entity procurement (`site:.gov filetype:pdf`) | Dec pages, certificates, occasionally full policies | Search `"declarations" "commercial general liability"`, board packets, RFP attachments |
| State risk pools / JPAs | Full coverage documents | Published as a matter of policy |
| SERFF public filing access (state DOI) | Form filings | Availability varies by state |
| Carrier specimen policies | Clean, complete specimens | More common in professional liability, cyber, surplus lines |

**ISO forms are licensed by Verisk and are not a public library.** Individual ISO forms appear inside the documents above and processing them is fine. Do not build sourcing around obtaining a form catalog.

### 3.2 Synthetic renewal pairs

Public sources yield single policies, not expiring/renewal pairs. Pairs are authored.

For each base document, produce a renewal variant by applying a manifest of controlled changes. This yields ground truth and converts the demo corpus into an eval set.

**Manifest format** (`pairs/<pair_id>/manifest.json`):

```json
{
  "pair_id": "pkg-004",
  "base_document": "base/pkg-004-expiring.pdf",
  "renewal_document": "renewal/pkg-004-renewal.pdf",
  "line_of_business": "commercial_package",
  "injected_changes": [
    {
      "change_id": "c1",
      "field_path": "gl.each_occurrence_limit",
      "from": 1000000,
      "to": 500000,
      "expected_severity": "material_adverse",
      "expected_finding_type": "limit_decrease"
    },
    {
      "change_id": "c2",
      "field_path": "endorsements.CG2010",
      "from": "blanket_additional_insured",
      "to": null,
      "expected_severity": "material_adverse",
      "expected_finding_type": "endorsement_removed"
    },
    {
      "change_id": "c3",
      "field_path": "forms.CG0001.edition",
      "from": "04/13",
      "to": "12/07",
      "expected_severity": "review_required",
      "expected_finding_type": "form_edition_change"
    },
    {
      "change_id": "c4",
      "field_path": "property.locations[0].valuation",
      "from": "replacement_cost",
      "to": "actual_cash_value",
      "expected_severity": "material_adverse",
      "expected_finding_type": "valuation_downgrade"
    }
  ],
  "decoy_changes": [
    {
      "field_path": "premium.total",
      "from": 42150,
      "to": 46800,
      "expected_severity": "informational"
    }
  ]
}
```

**Injection targets — vary across the corpus so no single pattern dominates:**

- Limit decrease (each occurrence, aggregate, products-completed ops)
- Deductible increase / SIR introduced
- Additional insured: blanket → scheduled
- Additional insured: ongoing operations only (completed ops dropped)
- Waiver of subrogation removed
- Primary & non-contributory removed
- Notice of cancellation days reduced
- New exclusion added
- Causes of loss: special → broad
- Valuation: replacement cost → ACV
- Coinsurance percentage increased
- Business income period of indemnity shortened
- Blanket property limit → scheduled per-location limits
- Form edition rollback
- Retro date advanced (if any claims-made component)

**Decoys** — changes that must NOT be flagged as adverse: premium change, mailing address change, agent of record change, policy number change, carrier name change where coverage is unchanged.

**Corpus targets:**
- 20 pairs minimum
- 3–5 distinct carriers represented
- At least 4 pairs where the only material finding is subtle (edition date, AI scope narrowing) — these are the demo moments
- At least 2 pairs with scanned/image-only pages
- At least 2 pairs with zero material findings (the tool must be able to say "nothing material changed")

---

## 4. Data contract

### 4.1 Field primitive

Every extracted value uses this envelope. No bare values anywhere in the pipeline.

```json
{
  "value": 1000000,
  "raw": "$1,000,000",
  "page": 3,
  "bbox": [122.4, 388.1, 244.9, 401.7],
  "source_text": "Each Occurrence Limit    $1,000,000",
  "confidence": "high",
  "extraction_passes_agreed": true
}
```

`confidence` ∈ `high` | `low` | `not_found`
- `high` — both extraction passes agreed
- `low` — passes disagreed, or value inferred rather than read directly → routes to `needs_review`
- `not_found` — field absent from document

### 4.2 PolicySnapshot

One per document. This is the object the comparison engine operates on — never raw text.

```
PolicySnapshot
├── document
│   ├── source_filename
│   ├── page_count
│   └── page_classifications[]        # dec_page | forms_schedule | endorsement | jacket | other
│
├── identity
│   ├── named_insured                 # Field<string>
│   ├── dba[]                         # Field<string>
│   ├── mailing_address               # Field<Address>
│   ├── policy_number                 # Field<string>
│   ├── carrier_name                  # Field<string>
│   ├── naic_code                     # Field<string>
│   ├── policy_period_start           # Field<date>
│   ├── policy_period_end             # Field<date>
│   ├── coverage_trigger              # Field<occurrence|claims_made>
│   └── retroactive_date              # Field<date|null>
│
├── general_liability
│   ├── each_occurrence               # Field<int|null>
│   ├── general_aggregate             # Field<int|null>
│   ├── aggregate_applies_per         # Field<policy|project|location>
│   ├── products_completed_ops_agg    # Field<int|null>
│   ├── personal_advertising_injury   # Field<int|null>
│   ├── damage_to_rented_premises     # Field<int|null>
│   ├── medical_expense               # Field<int|null>
│   ├── deductible_amount             # Field<int|null>
│   ├── deductible_basis              # Field<per_claim|per_occurrence|null>
│   └── sir_amount                    # Field<int|null>
│
├── property
│   ├── blanket_coverage              # Field<bool>
│   ├── blanket_limit                 # Field<int|null>
│   ├── causes_of_loss_form           # Field<special|broad|basic>
│   ├── locations[]
│   │   ├── location_number           # Field<string>
│   │   ├── address                   # Field<Address>
│   │   ├── building_limit            # Field<int|null>
│   │   ├── bpp_limit                 # Field<int|null>
│   │   ├── valuation                 # Field<replacement_cost|acv|functional>
│   │   ├── coinsurance_pct           # Field<int|null>
│   │   └── deductible                # Field<int|null>
│   ├── business_income_limit         # Field<int|null>
│   ├── business_income_basis         # Field<actual_loss|coinsurance|monthly_limit>
│   └── period_of_indemnity_months    # Field<int|null>
│
├── forms_schedule[]
│   ├── form_family                   # Field<string>   # normalized: "CG0001"
│   ├── edition                       # Field<string>   # normalized: "04/13"
│   ├── title                         # Field<string>
│   └── raw_form_number               # Field<string>   # as printed
│
├── risk_transfer                     # extracted separately, highest scrutiny
│   ├── additional_insured
│   │   ├── present                   # Field<bool>
│   │   ├── basis                     # Field<blanket|scheduled|none>
│   │   ├── scope                     # Field<ongoing_ops|completed_ops|both|none>
│   │   ├── scheduled_parties[]       # Field<string>
│   │   └── governing_forms[]         # Field<string>
│   ├── waiver_of_subrogation
│   │   ├── present                   # Field<bool>
│   │   └── basis                     # Field<blanket|scheduled|none>
│   ├── primary_noncontributory
│   │   └── present                   # Field<bool>
│   └── notice_of_cancellation_days   # Field<int|null>
│
├── exclusions[]                      # endorsements identified as coverage-restricting
│   ├── form_family
│   ├── title
│   └── subject                       # short normalized tag, e.g. "habitability"
│
└── premium
    ├── total                         # Field<int|null>
    ├── taxes_fees                    # Field<int|null>
    └── audit_basis                   # Field<auditable|non_auditable|null>
```

### 4.3 Normalization

Runs after extraction, before comparison. This step produces most of the accuracy.

| Input | Output |
|---|---|
| `"$1,000,000"`, `"1,000,000"`, `"1000M"`, `"1 Mil"` | `1000000` |
| `"Included"`, `"Incl."` | `INCLUDED` sentinel (not `0`, not `null`) |
| `"Excluded"`, `"None"`, `"N/A"` | `null` with `basis: excluded` |
| `"CG 00 01 04 13"`, `"CG0001 (04/13)"`, `"CG 00 01 (Ed. 04 13)"` | `{family: "CG0001", edition: "04/13"}` |
| `"04/01/2025"`, `"April 1, 2025"`, `"1 Apr 25"` | `2025-04-01` |
| `"Repl Cost"`, `"RC"`, `"Replacement Cost"` | `replacement_cost` |
| `"Spec"`, `"Special Form"`, `"Causes of Loss – Special"` | `special` |
| Address strings | USPS-normalized components for matching |

Form family canonicalization regex is the single highest-leverage piece of code in the build. Test it against every raw form number in the corpus before writing the comparison engine.

---

## 5. Comparison engine

Deterministic. No model calls in this stage.

### 5.1 Matching

Before comparing, entities on each side must be paired:

| Entity | Match key | Unmatched handling |
|---|---|---|
| Coverage limits | Field path (fixed schema) | `not_found` on one side → finding |
| Forms | `form_family` | Present on one side only → `form_added` / `form_removed` |
| Property locations | Normalized address, fallback to location number | Unmatched → `location_added` / `location_removed` |
| Scheduled AI parties | Normalized party name | Unmatched → `ai_party_added` / `ai_party_removed` |
| Exclusions | `form_family` | Present on renewal only → `exclusion_added` |

Location matching by address rather than location number matters — carriers renumber locations between terms.

### 5.2 Findings taxonomy

| Finding type | Trigger | Severity |
|---|---|---|
| `limit_decrease` | Any limit lower than prior | material_adverse |
| `aggregate_basis_narrowed` | per-project/per-location → per-policy | material_adverse |
| `deductible_increase` | Deductible higher | material_adverse |
| `sir_introduced` | SIR present where none prior | material_adverse |
| `exclusion_added` | Coverage-restricting form present on renewal only | material_adverse |
| `endorsement_removed` | AI, WOS, or P&NC present prior, absent now | material_adverse |
| `ai_basis_narrowed` | Blanket → scheduled | material_adverse |
| `ai_scope_narrowed` | Both → ongoing ops only | material_adverse |
| `valuation_downgrade` | Replacement cost → ACV or functional | material_adverse |
| `causes_of_loss_narrowed` | Special → broad → basic | material_adverse |
| `coinsurance_increase` | Coinsurance % higher | material_adverse |
| `blanket_to_scheduled` | Blanket property limit → per-location | material_adverse |
| `business_income_reduced` | Limit lower or period shortened | material_adverse |
| `notice_of_cancellation_reduced` | Fewer days | material_adverse |
| `retro_date_advanced` | Retro date later than prior | material_adverse |
| `form_edition_change` | Same family, different edition | **review_required** |
| `form_added_unclassified` | New form not in known taxonomy | **review_required** |
| `location_removed` | Location on prior only | review_required |
| `low_confidence_field` | Either side extracted at `low` | **needs_review** |
| `limit_increase` | Any limit higher | favorable |
| `exclusion_removed` | Restricting form dropped | favorable |
| `deductible_decrease` | Deductible lower | favorable |
| `carrier_change` | Different carrier | informational |
| `premium_change` | Premium delta | informational |
| `address_change` | Mailing address differs | informational |
| `policy_number_change` | Expected at renewal | suppressed |

**Form edition changes are `review_required`, never auto-classified.** Edition rollbacks frequently narrow coverage and edition advances frequently broaden it, but the direction is form-specific and cannot be inferred from the date. This finding says *"this changed, read it"* — which is the correct and defensible output.

### 5.3 Finding object

```json
{
  "finding_id": "f-007",
  "type": "ai_basis_narrowed",
  "severity": "material_adverse",
  "field_path": "risk_transfer.additional_insured.basis",
  "prior": {
    "value": "blanket",
    "page": 14,
    "bbox": [88.0, 210.5, 402.1, 260.0],
    "source_text": "CG 20 33 – Additional Insured – Owners, Lessees or Contractors – Automatic Status"
  },
  "current": {
    "value": "scheduled",
    "page": 16,
    "bbox": [88.0, 198.2, 402.1, 268.4],
    "source_text": "CG 20 10 – Additional Insured – Owners, Lessees or Contractors – Scheduled Person or Organization"
  },
  "narrative": null,
  "confidence": "high"
}
```

`narrative` is populated by the LLM pass in §6. It is the only model-generated field in the object.

---

## 6. Narration

Single LLM call, runs last, receives the ruled findings list — never the raw documents.

**Constraints on the narration prompt:**

- May restate what changed in plain language
- May explain what a term means in general (e.g. what ACV means as a valuation basis)
- May NOT assess adequacy, recommend action, characterize risk, or say whether a change is acceptable
- May NOT introduce findings not present in the input list
- May NOT reorder or re-rank by its own judgment

Every sentence in the narration must trace to a finding object. If the model produces a sentence that doesn't, the prompt is wrong.

---

## 7. Outputs

Two artifacts per run.

### 7.1 Internal findings report

Audience: account manager / checker. Purpose: verification.

```
POLICY COMPARISON — INTERNAL
[Named Insured] · [Prior period] → [Renewal period]
Generated [timestamp] · [N] findings

NEEDS REVIEW — LOW CONFIDENCE EXTRACTION        [n]
  Fields where extraction was uncertain. Verify manually.

MATERIAL CHANGES — COVERAGE REDUCED             [n]
  ▸ Each Occurrence Limit: $1,000,000 → $500,000
    Prior: p.3  ·  Renewal: p.3                 [view]

REVIEW REQUIRED                                 [n]
  ▸ CG0001 edition changed: 04/13 → 12/07
    Prior: p.11 ·  Renewal: p.11                [view]

MATERIAL CHANGES — COVERAGE BROADENED           [n]

INFORMATIONAL                                   [n]

UNCHANGED — VERIFIED                            [n]
  Collapsed by default.
```

The `UNCHANGED — VERIFIED` count matters more than it looks. It's the difference between "the tool found four things" and "the tool checked ninety-one fields and four changed."

### 7.2 Client-facing renewal difference summary

Audience: the insured. Purpose: the broker forwards it without editing.

One page. No jargon without a plain-language gloss. No branding from the tool. Sections:

1. Policy identification and term
2. What changed in your coverage — plain language, adverse changes first
3. What stayed the same — summarized, not enumerated
4. Premium
5. Items your broker is reviewing — the `review_required` set, framed as in-progress not unresolved

**Copy invariants:**
- Never uses "gap," "deficient," "inadequate," "exposed," or "at risk"
- Never recommends an action
- Never states or implies whether coverage would respond to a hypothetical claim
- Attributes nothing to the tool — reads as the broker's document

This artifact is the thing to print and carry. It is more persuasive than the software.

---

## 8. Eval harness

Runs against the manifest set. Every extraction or prompt change re-runs the full suite.

### Metrics

| Metric | Definition | Gate |
|---|---|---|
| Material recall | Injected `material_adverse` changes detected | **100%** |
| Overall recall | All injected changes detected at any severity | ≥ 95% |
| Severity accuracy | Detected findings assigned expected severity | ≥ 95% |
| False positive rate | Findings not in manifest and not decoy-explained | ≤ 1 per pair |
| Decoy suppression | Decoy changes not classified adverse | 100% |
| Citation page accuracy | Cited page contains the cited value | 100% |
| Clean-pair precision | Zero-change pairs producing zero material findings | 100% |

Material recall at 100% is non-negotiable. A missed limit decrease is the failure mode that ends the product.

False positives are the second-order killer — a checker who finds two phantom findings stops trusting the other forty.

### Harness output

Per-run scorecard written to `evals/runs/<timestamp>.json`, plus a diff against the previous run so regressions are visible immediately.

---

## 9. Demo mechanics

**Flow:** drop two PDFs → progress indicator with named stages (extracting, normalizing, comparing) → findings list → click finding → split-pane PDF view, both sides scrolled to cited page with bbox highlighted.

The click-to-citation jump is the moment that earns a follow-up meeting. Build it before building anything cosmetic.

**Event-day setup:**
- Two pairs pre-run and cached for instant display
- Live path functional — someone will ask to see it actually run; the 40 seconds is worth more than a cached result
- Runs offline or on phone hotspot; do not depend on venue wifi
- Printed renewal difference summary in hand
- Opening line is a request for critique, not a pitch: *"here's the checklist I built this against — what's missing?"*

**Retention statement, delivered unprompted:** documents are processed in memory and not stored. Expect this question first from anyone senior.

---

## 10. Stack

| Layer | Choice | Note |
|---|---|---|
| Extraction | Claude API, PDF as document block | Handles scanned pages. No separate OCR layer. |
| Page rasters | pypdfium2, cached | Needed for citation highlighting |
| API | FastAPI | Synchronous run is fine at demo scale |
| Storage | Postgres (Railway) — runs, findings, eval results | Demo-mode document processing stays in memory |
| Front end | React + pdf.js | Split pane, bbox overlay |
| Jobs | ARQ — **deferred** | Add only when batch processing 60-page documents |
| pgvector / embeddings | **Not used** | This is extraction + rules, not retrieval. Adding it is scope creep. |

**Dual-pass extraction:** run each document through extraction twice independently, compare field by field, mark disagreements `low` confidence. Cost is ~2× on the cheapest part of the pipeline and it's what makes the `needs_review` bucket honest.

---

## 11. Scope guards

The tool describes changes. A licensed professional interprets them.

**The system must never:**
- State that coverage is adequate, inadequate, or sufficient
- Recommend binding, declining, or renegotiating
- Assert whether a policy would or would not respond to a described loss
- Compare against an industry standard or "typical" limit
- Characterize the insured's risk profile
- Produce anything resembling a coverage opinion

This is not defensive boilerplate. It is the correct product boundary and it is a selling point: the checker keeps the judgment call, which is the part they're licensed and paid for. Say this explicitly in the demo. It converts an objection into a differentiator.

---

## 12. Open questions — resolve with a working account manager

Bring the findings taxonomy in §5.2 to the LinkedIn conversations. These are the questions that make the ask real.

1. What's on your actual policy check checklist that isn't in §5.2?
2. Which findings do you check first, and why that order?
3. Which changes are so routine you'd want them suppressed entirely?
4. Where does a checker most often get burned — what's the miss that caused a claim problem?
5. Is the renewal difference summary something you'd actually send an insured, or does that go out in a different format?
6. Quote-to-binder checking vs. expiring-to-renewal — which is more painful and more frequent?
7. What do you currently pay per policy if this is outsourced, and what's the turnaround?
8. What does the checker do with the result — email, AMS activity note, something else?

Question 4 is the one that reshapes the taxonomy. Ask it early.

---

## 13. Build sequence

**Phase 1 — Ground truth (weekend 1)**
- Assemble 15–20 public base documents
- Author 20 renewal variants with manifests
- Freeze the schema in §4.2
- Extraction working end-to-end on 3 documents
- Exit: manifests complete, schema stable, one document extracts with citations

**Phase 2 — Engine (weekend 2)**
- Form family normalizer, tested against every raw form number in corpus
- Full normalization layer
- Matching + comparison + severity rules
- Eval harness and first scorecard
- Exit: material recall 100% across the manifest set

**Phase 3 — Surface (weekend 3)**
- Both report outputs
- React UI with split-pane citation view
- Two cached demo pairs
- Exit: a stranger can be handed the laptop and understand the output without narration

**Phase 4 — Correction (ongoing, starts during phase 2)**
- 10 LinkedIn conversations framed as critique requests
- One state association event (NABIP-NJ / NAIFA-NJ, Big "I" or PIA chapter)
- Taxonomy revised against what comes back
- Exit: a working account manager says the checklist matches their job

Phase 4 does not wait for phase 3. The taxonomy is the conversation piece and it exists at the end of phase 2.

---

## 14. Known risks

**Extraction on scanned carrier PDFs is the technical risk.** Two pairs in the corpus must be image-only specifically to force this early rather than discovering it at an event.

**The synthetic pairs may not reflect how renewals actually differ.** Real renewals cluster changes in ways an author wouldn't guess. Treat the manifest set as a correctness harness, not as a realism claim — and replace it with real pairs as soon as one agency shares them.

**Timeline discipline.** Learning the domain is necessary and it is also the most comfortable available substitute for standing in a room full of strangers. Phase 4 has a date or it doesn't happen.