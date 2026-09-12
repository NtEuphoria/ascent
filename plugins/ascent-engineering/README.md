# ascent-engineering

Agents for working on ASCENT, distilled from a 208-role organization manual
into the six roles this repository's work actually generates.

## Install

From the repository root:

```
/plugin marketplace add ./
/plugin install ascent-engineering@ascent
```

## What you get

| Agent | Mode | Owns |
| --- | --- | --- |
| `calculator-author` | builder | One `calculators/*.py` plus its own test file |
| `physics-verifier` | tester | Nothing - computes independently and reports |
| `page-reviewer` | advisory | Nothing - reviews content and teaching quality |
| `design-reviewer` | advisory | Nothing - measures contrast, motion, chrome |
| `live-data-engineer` | builder | `utils/stream.py`, `utils/livesource.py`, `calculators/live.py` |
| `platform-builder` | builder | `macos/`, the build and packaging scripts |

Two skills: `ascent-operating-rules` (the evidence and file-ownership
discipline, loaded by every agent) and `ascent-role-catalogue` (the full manual,
loaded only when a brief outside the six is needed).

One command: `/ascent-expand <module>`, which runs an author and then an
independent verifier.

## Why six and not 208

Every installed agent's description is loaded into the main session on every
turn so routing can happen. 208 of them is a permanent context cost on every
message, and picking among 208 near-identical descriptions is harder than
picking among six distinct ones, not easier.

The manual agrees with this in its own text and sets a budget of six active
agents. The remaining 202 charters are still here, in
`skills/ascent-role-catalogue/reference/full-manual.md`, costing nothing until
something opens them.

## The rule that matters most

**An expected value may never come from the thing it is testing.** Author and
verifier are always different agents, and the verifier derives its own numbers
before reading the author's. Everything else in the operating rules exists
because the opposite already happened here.
