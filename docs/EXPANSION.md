# Expanding a calculator page

Every page in ASCENT is a `Calculator` dataclass in `calculators/<module>.py`,
rendered by `utils/render.py`. To deepen a page you add data, not layout.

Read `utils/spec.py` for the full vocabulary and
`calculators/aerodynamics.py` (`_LIFT`) for a page built to the current
standard. Copy its shape.

## The hard rules

1. **Accuracy beats everything.** A wrong number is worse than a missing one.
   If you are not confident in a value, leave it out and say why in a comment.
2. **Additive only.** Do not change an existing default, an existing result
   formula, an existing page `slug`, or an existing page `name`. Other tests
   and the user's saved favourites depend on all four. You may improve wording.
3. **Every worked example must be computed, not estimated.** Run the actual
   function with the actual numbers and paste the real answer. Examples with
   invented numbers have shipped from this repo before and been caught.
4. **Every new pure function needs hand-checked tests** with a known answer you
   can defend, in `tests/test_<module>_extra.py`. Do not edit
   `tests/test_calculations.py` or `tests/test_rendered_values.py` - other
   agents are working in this tree at the same time and those files are shared.
5. **`pytest tests/ -q` must be green when you finish.** Run it.
6. **Never start a Streamlit server.** One is already running on port 8501 and
   it will conflict. Verify with pytest, not a browser.
7. **Stay inside your assigned module** plus your own new test file.

## What "expand greatly" means, per page

Aim for every single one of these on every page:

- **`secondary=[...]`** — 3 to 6 supporting values. The quantities an engineer
  would work out next anyway: the same result in other units, the margin
  against a limit, the per-unit figure, the reciprocal.
- **`graphs=[Sweep(...), ...]`** — 2 to 4 graphs, each sweeping a *different*
  input. `graph=` (singular) still works and is folded into `graphs`.
- **`checks=[Check(fn), ...]`** — 1 to 3 regime tests. `fn(inputs, result)`
  returns `("info" | "warning" | "danger", message)` or `None`. Use these where
  the equation happily computes but has stopped being true: compressibility
  above Mach 0.3, a beam past yield, a motor past its thermal limit, a battery
  below its cutoff. **This is the highest-value thing you can add** and most
  pages have none yet.
- **`references=[Reference(...)]`** — 1 to 2 tables of real values for whatever
  coefficient the page asks the user to invent. Include a `note` saying where
  the range applies. Only numbers you are confident are standard.
- **`related=[...]`** — 3 to 5 slugs from `docs/SLUGS.md`. Pick the pages that
  answer the question this one raises next, not merely nearby topics.
- **`assumptions=[...]`** — 5 or more, each one a thing that could actually
  bite. Say what breaks when it is violated, not just that it is assumed.
- **`variables=[...]`** — every symbol in the LaTeX, with its unit.
- **`explanation`** — 2 to 4 sentences that teach the physics, not restate the
  formula. `<b>`, `<i>` and `<code>` are allowed.
- **`example`** — a real scenario with real numbers and the computed answer.
- **`keywords=(...)`** — search terms someone would actually type.

You do **not** need to write a sensitivity section: `utils/analysis.py` derives
it from `compute` automatically on every page.

## Adding whole new calculators

If your module is obviously missing something an engineer would reach for, add
it: new pure function at the top, tests, then a full `Calculator` and an entry
in `CALCULATORS`. Hold the same standard as the rest of the page.

## Checking your worked examples

```bash
.venv/bin/python -c "
from calculators import aerodynamics as m
print(m.lift(1.225, 18.0, 0.65, 0.9))
"
```
