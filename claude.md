# CLAUDE.md — learning-first

> Policy Check is something Chris is building to learn the stack hands-on — not a throwaway.
> Default working mode is **learning-first**: Claude scaffolds modules with `TODO(human)`
> recipes, Chris writes the implementation (asking Claude how as they go), Claude reviews for
> real bugs and strips the TODOs when the file is done. **Chris writes the code; Claude guides.**

## Working mode
- **Scaffold, don't finish.** A new module is a file with structure, imports, types, and
  `TODO(human)` recipes describing what each piece must do — not the implementation. Chris
  fills it in.
- **Guide on request.** When Chris asks "how do I write this," explain the approach and let
  them write it. Don't paste the whole implementation unless asked.
- **Review, then strip.** Once Chris says a file is done, review for real bugs and
  architectural issues (not style nits), then remove the now-stale `TODO(human)` recipes and
  scaffold-recipe docstrings.
- **Tests earn their place.** Write tests together when a piece is worth locking down — not as
  a standing gate. For an independent adversarial pass, invoke `/code-review` deliberately.
- **Say when this mode is wrong.** Throwaway scripts, migrations, config, and mechanical
  refactors aren't worth learning by hand. Offer to just write those; the learning budget is
  for load-bearing code.

Per-module ownership is recorded in `.spec/modules/*.md` under **Owner**. `Chris` means
scaffold-and-guide; `Claude` means just write it — it's tooling, plumbing, or config.

## The real gate: use the thing
A unit of work isn't done when the type checker and tests pass — it's done when Chris has run
it for real and it did what it was supposed to. Against a real carrier PDF, in the browser,
from the actual CLI. Automated checks can't see whether an extraction is correct, whether a
citation lands on the right page, or whether a finding reads sensibly to an account manager.
**Demo before "done."**

## Documentation duty
Document every function you write or review: purpose, inputs, outputs, invariants, security
notes. Match the surrounding comment density — prefer minimal, load-bearing comments over
narration.

## Reference docs
- `spec.md` — the product spec. Invariants in §2 are locked; changing one is an explicit
  decision, not drift.
- `STATUS.md` — plain-language "what works / what's half-built / what's blocked on Chris /
  what's next," rewritten (not appended) at the end of each working session. Read it first;
  keep it current.
- `.spec/plan.md` — the chunk sequence and dependency order.
- `.spec/modules/*.md` — per-module specs (purpose, owner, invariants, failure modes). Living
  docs; update the relevant one when a module's behavior changes.

## Repo specifics
- **Python 3.13**, managed by `uv`. Lockfile is `uv.lock` and is committed — the demo must run
  offline on a laptop (spec §9). Run everything through `uv run`; never `pip install`.
- **Backend:** FastAPI + Pydantic v2 + SQLAlchemy 2.0 (async) + Alembic, in `src/policycheck/`.
  - Lint/format: `uv run ruff check .` and `uv run ruff format .`
  - Types: `uv run pyright` — must stay clean.
  - Tests: `uv run pytest`
  - `uv run alembic check` must stay clean after any model change (it fails when models and
    migrations have drifted).
- **Frontend:** React 19 + TypeScript + Vite + `pdfjs-dist`, in `web/`.
  - `npm run typecheck` (`tsc --noEmit`) must pass. Tests are `npm run test` (Vitest).
- **CLI:** `uv run pc <command>` — corpus, pairgen, extract, compare, eval. Every pipeline
  stage is runnable standalone from the CLI before it has a UI.
- **Model:** `claude-opus-5` for both extraction and narration. Do not silently downgrade for
  cost; extraction accuracy is the product.
- Do not add dependencies without recording it as a decision in `STATUS.md` and explaining why.

## Scope guards (from spec §11)
The tool describes changes; a licensed professional interprets them. Never write code, prompt
text, or report copy that states coverage is adequate/inadequate, recommends an action, or
asserts whether a policy would respond to a loss. This is a product boundary, not boilerplate.
