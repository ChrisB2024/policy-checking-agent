# pairgen

**Owner:** Claude (tooling — not learning budget) · **Chunk:** C1.3 · **Spec:** §3.2

## Purpose
Turn one real base policy into an expiring/renewal pair by applying a manifest of controlled
changes to the PDF. This is what produces ground truth and converts the demo corpus into an
eval set.

## Approach
Public sources yield single policies, not pairs. Rather than regenerating a synthetic policy
(which would lose real carrier layout, fonts, and scan artifacts — the things that make
extraction hard), **patch the real PDF in place**:

1. Locate the target value's bbox on its page via `raster.find_text`.
2. Cover it with an opaque rectangle matched to the page background.
3. Draw the replacement text at the same origin, in a font matched to the surrounding text.
4. For image-only pages: rasterize → edit the raster with Pillow → reinsert as an image page.

`pikepdf` handles document structure, `reportlab` draws the patch overlay, `pypdfium2` +
`Pillow` handle the scanned path.

## Surface
- `pc pairgen make <pair_id>` — reads `corpus/pairs/<pair_id>/manifest.json`, writes
  `corpus/renewal/<pair_id>-renewal.pdf`.
- `pc pairgen verify <pair_id>` — re-extracts text at each patched location and asserts the new
  value is present and the old one is gone. **Run this on every generated pair**; a patch that
  silently failed produces a manifest that lies, which poisons every eval run downstream.
- `pc pairgen list-targets` — the §3.2 injection-target checklist with per-target counts across
  the corpus, so no single pattern dominates.

## Injection targets
The full list is spec §3.2. Vary them across the corpus. Also inject the **decoys** — premium,
mailing address, agent of record, policy number, carrier name where coverage is unchanged —
these must not be flagged adverse.

## Invariants
- The manifest is the source of truth. The generator reads it; it never writes back to it.
- A change that cannot be applied cleanly fails loudly and produces no output file. A partial
  renewal PDF is worse than none.
- Endorsement removal means removing the form from the schedule **and** removing (or blanking)
  the endorsement page. Removing only the schedule line produces a document no carrier would
  issue and teaches the extractor the wrong thing.

## Failure modes
- Patched text that overlaps neighbouring content, or a covering rectangle that hides an
  adjacent value — `verify` should catch the second case, a human eyeball catches the first.
- Font mismatch making the patch obvious. Cosmetically ugly is fine for an eval set; it is not
  fine for the two cached demo pairs, which get shown to strangers.
- Treating the synthetic set as a realism claim. It is a correctness harness (spec §14).
