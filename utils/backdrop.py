"""Laminar: the generative backdrop behind first-run setup.

See docs/BACKDROP.md for what it is and why it is that. In short: particles
advected through analytic potential flow around a lifting body, projected in
perspective, with the pointer acting as a weak probe in the field.

Two constraints shape every technical decision here.

**It must run offline.** The app builds its own environment on first launch and
is expected to work on a machine that has never been online since. So there is
no three.js, no p5, no CDN of any kind - the projection, the field and the
integrator are about a hundred lines of arithmetic, which is less code than the
loader for a library would be.

**It must not compete with the text in front of it.** That is why it is drawn
at very low contrast, why the motion is slow, and why `prefers-reduced-motion`
collapses it to one static frame rather than a slower animation.

Streamlit sanitises `st.html`, stripping any script, so this goes through
`components.v1.html`, which renders a real iframe with its own document. The
iframe is then positioned as a fixed layer behind the page by CSS in the
parent - see `LAYER_CSS`.
"""
from __future__ import annotations

import streamlit.components.v1 as components

HEIGHT = 1
"""The iframe is taken out of flow and made full-screen by CSS, so the height
Streamlit reserves for it in the layout should be as close to nothing as it
will accept - otherwise it pushes the panel down by its own height."""

LAYER_CSS = """
/* The backdrop sits behind everything, full-viewport, out of the layout.
   Streamlit's own iframe wrapper keeps the space it was given, so the wrapper
   is collapsed as well as the iframe being repositioned. */
.st-key-backdrop{position:fixed;inset:0;z-index:0;pointer-events:none;
  height:0;margin:0;padding:0;overflow:visible;}
.st-key-backdrop iframe{position:fixed;inset:0;width:100vw;height:100vh;
  border:0;display:block;pointer-events:auto;}
.st-key-backdrop [data-testid="stElementContainer"]{height:0;margin:0;}

/* The main column must let the pointer through to the field on either side of
   the panel, while the panel itself keeps working normally. Without this the
   app container swallows every mouse event before the backdrop sees one. */
[data-testid="stMain"]{pointer-events:none;}
[data-testid="stMain"] .block-container{pointer-events:auto;}
"""


def _document(accent: str, ink: str, motion_still: bool) -> str:
    """The iframe's whole document. No external references of any kind."""
    still = "true" if motion_still else "false"
    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>
  html,body{{margin:0;height:100%;background:transparent;overflow:hidden;}}
  canvas{{display:block;width:100%;height:100%;}}
</style></head><body><canvas id="c"></canvas>
<script>
(function(){{
  // Streamlit names this iframe "st.iframe", and the backdrop covers the whole
  // viewport with pointer-events enabled - so hovering anywhere outside the
  // panel pops a native tooltip reading "st.iframe" over the first screen
  // anyone ever sees. The frame is decorative, so the fix is to drop the title
  // rather than reword it, and to hide it from assistive technology instead.
  // components.v1.html uses a same-origin srcdoc frame, so frameElement is
  // reachable from in here; wrapped anyway, because a cross-origin frame would
  // throw and take the whole backdrop down with it.
  try {{
    var host = window.frameElement;
    if (host) {{
      host.removeAttribute('title');
      host.setAttribute('aria-hidden', 'true');
      host.setAttribute('tabindex', '-1');
    }}
  }} catch (e) {{}}

  var canvas = document.getElementById('c');
  var ctx = canvas.getContext('2d', {{alpha: true}});
  var ACCENT = {accent!r}, INK = {ink!r}, STILL = {still};

  // --- the field -----------------------------------------------------------
  // Potential flow past a cylinder of radius A with circulation GAMMA:
  //   w(z) = U(z + A^2/z) + i*GAMMA/(2*pi) * ln(z)
  // Differentiated and split into real components below. The body radius
  // shrinks with depth so near layers curve hard and far ones barely notice,
  // which is what makes the volume read as a volume.
  var U = 0.62, A = 0.34, GAMMA = 0.95;
  var DEPTH = 2.6, FOCAL = 1.9, COUNT = 640, TRAIL = 18;

  var particles = [], w = 0, h = 0, dpr = 1;
  var probe = {{x: 0, y: 0, strength: 0}};

  function reseed(p, fresh) {{
    p.x = fresh ? (Math.random() * 3.2 - 1.6) : -1.68;
    // Concentrated toward the centre line rather than uniform across the
    // height. A streamline that passes a body length away barely deflects, so
    // spreading evenly spends most of the particles on straight lines and
    // leaves the interesting region sparse.
    var t = Math.random() * 2 - 1;
    p.y = Math.sign(t) * Math.pow(Math.abs(t), 1.7) * 1.15;
    p.z = Math.random() * DEPTH + 0.25;
    p.life = fresh ? Math.random() : 0;
    // A streamline is a path, not a point, so each particle carries its own
    // recent history. One frame of displacement renders as a speck; sixteen
    // renders as the line the mathematics actually traced.
    p.trail = [p.x, p.y];
  }}

  function build() {{
    particles = [];
    for (var i = 0; i < COUNT; i++) {{ var p = {{}}; reseed(p, true); particles.push(p); }}
  }}

  function velocity(x, y, z, out) {{
    // Radius falls off with depth: a body seen further away disturbs less.
    var a = A * (1.0 - 0.22 * z / DEPTH);
    var r2 = x * x + y * y;
    // Floored at the body's own radius, not at some tiny epsilon. Inside the
    // body the potential has no physical meaning and 1/r^2 runs away: a
    // particle that strayed in took one enormous step before the reseed check
    // could catch it, drawing a straight line clean across the screen.
    var floor = a * a;
    if (r2 < floor) r2 = floor;
    var inv = 1.0 / r2;
    var a2 = a * a;
    // Uniform stream + doublet.
    var ux = U * (1 - a2 * (x * x - y * y) * inv * inv);
    var uy = U * (-a2 * 2 * x * y * inv * inv);
    // Bound vortex: circulation is what makes it a LIFTING body rather than
    // just an obstacle, and it is the term the lift page is about.
    // The coefficient is GAMMA/(2*pi), straight from the potential. It was
    // written as GAMMA/2 first, which is pi times too strong - circulation
    // then overwhelmed the free stream and the whole field read as a vortex
    // rather than as flow past a body.
    var swirl = GAMMA * 0.1591549 * inv;
    ux += swirl * y;
    uy += -swirl * x;
    // The pointer as a weak source, relaxing out over time.
    if (probe.strength > 0.001) {{
      var dx = x - probe.x, dy = y - probe.y;
      var d2 = dx * dx + dy * dy + 0.02;
      var s = probe.strength * 0.10 / d2;
      ux += dx * s; uy += dy * s;
    }}
    out[0] = ux; out[1] = uy;
  }}

  // --- rendering -----------------------------------------------------------
  function resize() {{
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = canvas.clientWidth; h = canvas.clientHeight;
    canvas.width = Math.max(1, Math.floor(w * dpr));
    canvas.height = Math.max(1, Math.floor(h * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }}

  function project(x, y, z) {{
    var s = FOCAL / (FOCAL + z);
    var span = Math.max(w, h) * 0.62;
    return [w * 0.5 + x * span * s, h * 0.5 + y * span * s, s];
  }}

  var vel = [0, 0];

  function step(dt) {{
    probe.strength *= 0.965;          // the field recovers after a disturbance
    for (var i = 0; i < particles.length; i++) {{
      var p = particles[i];
      velocity(p.x, p.y, p.z, vel);
      // A second belt to the floor's braces: however the field is tuned, no
      // particle may move further in one frame than a trail segment can
      // sensibly represent.
      var speed = Math.sqrt(vel[0] * vel[0] + vel[1] * vel[1]);
      var cap = 2.2 * U;
      if (speed > cap) {{ vel[0] *= cap / speed; vel[1] *= cap / speed; }}
      p.x += vel[0] * dt;
      p.y += vel[1] * dt;
      p.trail.push(p.x, p.y);
      if (p.trail.length > TRAIL * 2) p.trail.splice(0, 2);
      p.life += dt * 0.22;
      // Nothing may sit inside the body. Potential flow has no solution there
      // and a particle that strays in gets flung out at absurd speed.
      var rr = p.x * p.x + p.y * p.y;
      var bodyR = A * (1.0 - 0.22 * p.z / DEPTH);
      if (p.x > 1.65 || p.life > 1.0 || Math.abs(p.y) > 1.25 ||
          rr < bodyR * bodyR) reseed(p, false);
    }}
  }}

  function draw() {{
    ctx.clearRect(0, 0, w, h);
    ctx.lineCap = 'round';
    for (var i = 0; i < particles.length; i++) {{
      var p = particles[i];
      var n = p.trail.length / 2;
      if (n < 2) continue;
      var s = FOCAL / (FOCAL + p.z);
      // Everything fades at the ends of a particle's life so nothing ever
      // pops into or out of existence.
      var fade = Math.min(1, p.life * 6) * Math.min(1, (1 - p.life) * 6);
      var alpha = 0.50 * fade * (s * s);
      if (alpha < 0.004) continue;
      ctx.strokeStyle = (i % 7 === 0 ? INK : ACCENT);
      ctx.globalAlpha = (i % 7 === 0) ? alpha * 0.5 : alpha;
      ctx.lineWidth = Math.max(0.45, 1.6 * s);
      ctx.beginPath();
      for (var k = 0; k < n; k++) {{
        var q = project(p.trail[k * 2], p.trail[k * 2 + 1], p.z);
        if (k === 0) ctx.moveTo(q[0], q[1]); else ctx.lineTo(q[0], q[1]);
      }}
      ctx.stroke();
    }}
    ctx.globalAlpha = 1;
  }}

  var last = 0;
  function frame(now) {{
    var dt = Math.min(0.05, (now - last) / 1000 || 0.016);
    last = now;
    step(dt);
    draw();
    requestAnimationFrame(frame);
  }}

  window.addEventListener('resize', function(){{ resize(); }});
  canvas.addEventListener('pointermove', function(e){{
    var span = Math.max(w, h) * 0.62;
    probe.x = (e.clientX - w * 0.5) / span;
    probe.y = (e.clientY - h * 0.5) / span;
    probe.strength = 1.0;
  }});

  resize();
  build();

  // The system preference wins outright. A slower drift is still drift; the
  // honest response to "reduce motion" is to stop.
  var reduce = STILL ||
    (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  if (reduce) {{
    for (var k = 0; k < 90; k++) step(0.016);   // settle into streamlines
    draw();
  }} else {{
    requestAnimationFrame(frame);
  }}
}})();
</script></body></html>"""


def render(accent: str, ink: str, motion: str = "Full") -> None:
    """Draw the backdrop. Call inside a container keyed `backdrop`."""
    components.html(_document(accent, ink, motion == "None"), height=HEIGHT,
                    scrolling=False)
