# Fixture cases — hard layouts found in real documents

Cases the pipeline has to survive, taken from actual corpus documents rather than invented.
Each one belongs in the eval harness as a named case, not just as a note here.

Add to this file whenever a real document breaks an assumption. The synthetic manifest set
tests whether the rules are right; this file tests whether the *reading* is right, which is
where extraction actually fails.

---

## `cl-2742056` — monoline cover note ahead of the real declarations

**Document:** Tapco Underwriters / Alea London, policy ALTE003493, 2004–2005, 39pp, scanned.
Certified on p1 as a true and complete copy. Sourced from CourtListener (dcd 1:06-cv-00157,
doc 41-2).

**Not usable as a package pair** — monoline surplus-lines CGL with no commercial property
coverage part, so `valuation_downgrade`, `coinsurance_increase`, `causes_of_loss_narrowed`,
`blanket_to_scheduled`, `business_income_reduced`, and `location_removed` are all
unexercisable. That is spec §1 scope and it is disqualifying for a package fixture.

**Usable as a GL-only pair, and valuable as an extraction fixture.** On the GL side it is
dense: seven of the ten `general_liability` fields are populated, plus class code, payroll
exposure, and split premises/ops and products rates.

### Why it earns a place in the harness

**1. Two schedules at different document levels; neither is complete alone.**
- p2 (cover note, "Special Conditions"): `IL0017 (11-85), IL0021 (11-85), TAPCO1998,
  MOLD EXCL (10-01), CL150`
- p9 (CGL Supplemental Declarations, Item 3): `CL150-EX, ALEA-GL-01 (01/04), EZ-EXCL-01
  (06/03), CG0001 (1-96), CG2136 (11/85), CG2139 (10-93), CG 2160 (4-98), CG2175 (12-02),
  UTS-128g (10-94)`

`MOLD EXCL (10-01)` appears in the first and not the second. `CG0001` appears in the second
and not the first. An extractor that finds one schedule and stops produces a `forms_schedule`
that is wrong in both directions — missing forms, and missing the fact that forms are missing.

**2. Limits are not where the first dec page suggests.** p2 shows a single blended
`$1,000,000 COMMERCIAL GENERAL LIABILITY`. p9 Item 1 breaks out all six: general aggregate
$2M, products/completed-ops aggregate $1M, personal & advertising injury $1M, each occurrence
$1M, damage to premises rented $50K, medical expense $5K. Reading only the front dec yields
one limit and five spurious `not_found`s — each of which would produce a phantom finding at
renewal.

**3. An orphaned coverage part.** p8 is a *Commercial Property* Total Mold Exclusion attached
to a policy with no property coverage part. Real `form_added_unclassified` test data.

**4. An internal conflict in a matched field.** Named insured's address is
`5614 5TH STREET, NE` on p2 and `5614 5TH STREET, NW` on p9. Both are cited, both are
verbatim, and they disagree. Property locations match on normalized address (spec §5.1), so
whichever the extractor picks silently changes matching behavior. This is the case that says
`Field[T]` needs a conflict path, not just a confidence level — the dual-pass merge catches
*extraction* disagreement, not *document* disagreement.

**5. Rates that do not reconcile.** p10: class 91340, payroll exposure 16,000, premises/ops
rate 10.16 → 162.56, but the premium reads $563, flagged `MP`. Minimum premium governs, and
563 + 187 = 750 = the coverage part premium on p9. Anything that validates or recomputes
premium from rate × exposure trips here. Premium is extracted, never derived.

### Process lesson

`pc corpus screen` correctly reported *scanned — needs manual review*. On a scanned document
the text-layer screen is blind, so page sampling is unsafe: the reviewer must page through
the whole document. The first review of this file sampled seven pages, missed p9, and
concluded there was no forms schedule and no limit breakout. Both were on the page in the gap.
