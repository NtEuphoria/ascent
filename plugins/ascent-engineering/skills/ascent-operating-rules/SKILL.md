---
name: ascent-operating-rules
description: The shared evidence and file-ownership discipline every ASCENT agent follows. Load this before authoring, verifying, reviewing, or building anything in the ASCENT repository, and before dispatching a group of agents at it.
---

# ASCENT operating rules

These are not style preferences. Every one of them exists because the opposite
already happened in this repository.

## 1. Accuracy outranks everything

A wrong number is worse than a missing one, and far worse than an ugly one.
This is a tool people use to size real hardware. If you are not confident in a
value, leave it out and say why.

The failure mode is not a crash. It is a plausible number, formatted nicely,
that is wrong - which looks exactly like a right one.

## 2. Verify; do not assert

Compute it and paste the real answer. Do not estimate, round from memory, or
reason about what a function "should" return.

Five worked examples have shipped from this repo with invented numbers and been
caught later. Each one was written by someone who knew the physics and did the
arithmetic in their head.

```bash
.venv/bin/python -c "from calculators import aerodynamics as m; print(m.lift(1.225, 18.0, 0.65, 0.9))"
```

## 3. An expected value may not come from the thing it is testing

If the test's expected value is produced by the function under test, the test
asserts only that the code is self-consistent. Derive it from a closed form, an
analytical special case, a published benchmark, or an invariant that must hold.

A second implementation that copied the same assumption reproduces the same
mistake. So does a "reference value" read off the page you are checking.

Real example: a gear-ratio page claimed a minimum in required motor torque.
The claim was true only if the *load* acceleration was held fixed; as written
it held *motor* acceleration fixed, which makes the expression monotonic and
the minimum imaginary. A numerical scan and an independently derived closed
form agreeing at N = 93 is what settled it.

## 4. Separate proposed, observed, implemented, tested, and accepted

- A design proposal is not implemented code.
- A successful import is not a rendered page.
- A generated test is not an executed test.
- A passing test suite is not scientific correctness.
- One reference case is not validation across a domain.

Mark anything you could not run **NOT RUN**, with the reason. Never relax a
test after the fact to make a failure disappear.

## 5. One writer per file

Multiple agents may read a file. Exactly one may write it. Protect shared
entry points especially: `app.py`, `utils/spec.py`, `utils/render.py`,
`utils/theme.py`, `utils/ui.py`, `requirements.txt`, and the shared test files
`tests/test_calculations.py` and `tests/test_rendered_values.py`.

When several agents work in parallel, each gets its own module plus its own new
`tests/test_<module>_extra.py`. Anything else collides.

## 6. Additive only, unless the change is the point

Do not change an existing page `slug`, page `name`, input default, or result
formula as a side effect of improving something else. Saved favourites, saved
recents and the shared value tests all depend on those four.

## 7. Budget, and what happens when you ignore it

**At most six subordinate agents at once.** This is not a style rule: eleven
concurrent agents were dispatched at this repository and all eleven were killed
mid-task by a session rate limit. Nine had landed their work. The tenth had
rewritten a module's entire physics layer and had not yet written its pages, so
the module imported but exposed nothing and the application would not start.

Parallelism past the limit does not run slower. It destroys work in progress.

Prefer several small waves to one large one, and commit between waves so a
killed agent costs one module and not the tree.

## 8. Physics conventions that are already settled here

- SI internally, always. Convert at the edges, never in the middle.
- Mass is kg, weight is newtons, and `W = m·g` with `g = 9.80665`. They are
  never interchangeable. `Field(kind="weight")` exists so this cannot be lost.
- Distinguish an invalid input from an unsupported model regime. A negative
  lift coefficient is inverted flight, not a typo. Momentum theory in the
  vortex ring state is a regime failure, not a bad number - that is what
  `Check()` is for.
- Never silently clamp, round, or substitute a user's value to get a nicer
  answer.
- Three quantities in this app share two letters: mass moment of inertia
  I [kg·m²], second moment of area I [m⁴], and polar second moment J [m⁴].
  Any page touching one must say which it means, in the variables table and in
  the assumptions.

## 9. Local iteration is not permission to publish

Do not push, release, deploy, tag, spend, or transmit anything without the
owner asking for it in that session. Building and installing locally is normal
work. `./publish.sh` is not, and the owner runs it themselves because it needs
their credentials.

## 10. Verify, then report what you actually did

End with: what changed, what you ran, what passed, what failed, what you could
not check and why. If part of the task is unfinished, say which part. Do not
describe a plan as though it were an outcome.
