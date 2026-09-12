---
description: Expand one ASCENT calculator module to the project standard, then verify it independently
---

Expand the calculator module the user named: **$ARGUMENTS**

Run this as two sequential agents, not one, and not in parallel with other
modules unless the user explicitly asks for a wave:

1. **`calculator-author`** on `calculators/$ARGUMENTS.py`, owning that file plus
   a new `tests/test_$ARGUMENTS_extra.py` and nothing else.
2. **`physics-verifier`** on the result, once the author has finished. It must
   derive its expected values independently rather than reading the author's.

Author and reviewer are always different agents. That is the point of the
second step; skipping it leaves the module checked only against itself.

If the user asks for several modules at once, dispatch at most six agents
concurrently and commit between waves. Eleven were dispatched at this repository
once and all eleven were killed mid-task by a session rate limit, leaving one
module unable to import.

Report what changed per page, the test count before and after, and any finding
the verifier raised that has not been fixed.
