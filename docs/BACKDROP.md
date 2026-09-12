# Laminar — the backdrop's algorithmic philosophy

## The movement

**Laminar** is the flow regime in which layers of fluid slide past one another
without mixing. It is the quiet regime: ordered, predictable, entirely legible.
Above a critical Reynolds number it breaks down into turbulence, and ASCENT has
a page about exactly that transition.

The backdrop lives permanently on the ordered side of that threshold. It is
never allowed to become turbulent, because turbulence is visually loud and this
surface exists underneath something a person is reading.

## The conceptual seed

The field is not decorative noise. It is **potential flow around a lifting
body** — the construction an aerodynamicist recognises immediately and nobody
else needs to: a uniform stream, a doublet, and a bound vortex, superposed.

```
w(z) = U(z + a²/z) + (iΓ/2π)·ln(z)
```

That is the Kutta–Joukowski setup, the oldest closed-form answer to the
question ASCENT's very first calculator asks. The app computes lift on one
page; the background is the thing being computed, made visible. Someone who
knows will see streamlines bending around an invisible cylinder with
circulation. Everyone else sees a calm drift.

## How it is expressed

Particles are advected through the field rather than animated along paths.
Nothing is keyframed: each point samples the analytic velocity at its own
position and moves. The streamlines that emerge were never drawn — they are
where the mathematics sends the particles, which is why they look inevitable
rather than designed.

Depth is real. Points occupy a volume and are projected through a perspective
divide, so radius, opacity and parallax all fall out of one distance term
instead of being faked per-layer. The doublet's strength varies with depth, so
near layers curve hard around the body and far layers barely notice it — the
structure resolves as you look into it.

## Interaction

The pointer is a probe in the flow, not a cursor over a picture. It introduces
a weak source that bends the local streamlines and then relaxes out, because a
probe in a wind tunnel perturbs the field it measures and the field recovers.
The perturbation is deliberately underpowered: it should be discoverable, never
demanding.

## The restraint

This runs behind a setup screen for an engineering instrument. Every parameter
is tuned against one requirement that outranks beauty: **it must never compete
with the text in front of it.** Contrast stays far below the foreground,
motion stays slow enough to sit below the threshold of attention, and the whole
field collapses to a single static frame when the system asks for reduced
motion. A backdrop that pulls the eye has failed, however good it looks alone.
