"""Declarative calculator specification.

A calculator page used to be written out as instructions: draw a header, lay out
four columns, build a result card, list assumptions. That was repeated 47 times,
so every change to how pages look was a 47-file edit.

Here a calculator is *data* instead, and one renderer turns that data into a
page. Motion, theming, keyboard handling and layout are implemented once.

Pages that genuinely need imperative control (the PID simulator, the unit
converter, the moment-of-inertia shape picker) pass `render=` and keep full
control - forcing those into a schema would cost more than it saves.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple


class Inputs:
    """Attribute access over the values the user typed: `i.rho`, `i.velocity`."""

    def __init__(self, values: Dict[str, Any]):
        self._values = values

    def __getattr__(self, name: str) -> Any:
        try:
            return self._values[name]
        except KeyError as exc:                     # pragma: no cover - a typo guard
            raise AttributeError(
                f"No input named '{name}'. Available: "
                f"{', '.join(sorted(self._values))}"
            ) from exc

    def __getitem__(self, name: str) -> Any:
        return self._values[name]

    def as_dict(self) -> Dict[str, Any]:
        return dict(self._values)


@dataclass
class Field:
    """One user input. `key` is how the compute function refers to it."""

    key: str
    label: str
    unit: str
    default: float
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    help: Optional[str] = None
    kind: str = "float"
    """"float" | "int" | "choice" | "slider" | "weight".

    "weight" draws the mass-or-weight pair and always yields newtons, so the
    mass/weight distinction can never be lost by a calculator author.
    """
    options: Optional[Sequence[str]] = None    # for kind="choice"
    width: int = 1                      # relative column width
    widget: Optional[Callable[[str, "Field"], Any]] = None
    """Escape valve for compound inputs: (widget_key, field) -> value.

    Used where one logical input needs several controls - a value plus a unit
    selector, say. Keeps such pages as data instead of forcing the whole page
    onto the imperative path.
    """


@dataclass
class Output:
    """The single large headline number."""

    label: str
    unit: str
    sig: int = 4


@dataclass
class Secondary:
    """A supporting value under the headline.

    `fn` receives the inputs and the primary result, so it can reuse work.
    If it raises, the value is skipped rather than breaking the page.
    """

    label: str
    unit: str
    fn: Callable[[Inputs, float], float]
    sig: int = 4


@dataclass
class Sweep:
    """An optional graph: vary one input, plot the result against it."""

    over: str                           # which Field.key to sweep
    y_label: str
    title: str
    x_label: Optional[str] = None       # defaults to the field's label [unit]
    lo: Optional[float] = None          # absolute lower bound; defaults to 0
    lo_factor: Optional[float] = None   # or a multiple of the current value
    hi_factor: float = 1.6              # sweep to this multiple of the value
    hi_min: Optional[float] = None      # never sweep a range narrower than this
    log_y: bool = False
    fn: Optional[Callable[[Inputs, Any], Any]] = None
    """Optional vectorised override: (inputs, x_array) -> y_array.

    Without it the renderer recomputes `compute` point by point, which is fine
    for cheap equations and always stays consistent with the headline number.
    """


@dataclass
class Reference:
    """A table of real values for a quantity the page asks the user to guess.

    Most of these equations need a coefficient the user does not know: a drag
    coefficient, a rolling resistance, a propeller figure of merit. Asking for
    it without saying what a plausible one looks like turns an accurate
    calculator into a precise way of producing a wrong answer.
    """

    title: str
    columns: Sequence[str]
    rows: Sequence[Sequence[str]]
    note: str = ""
    """Where the numbers came from, or what would make them not apply."""


@dataclass
class Check:
    """A regime test run against the user's inputs.

    `fn` returns (level, message) or None, with level one of
    "info" | "warning" | "danger". Use it where an equation stays happy to
    compute but has stopped being true - incompressible aerodynamics above
    Mach 0.3, momentum theory in the vortex ring state, a beam past yield.
    """

    fn: Callable[["Inputs", float], Optional[Tuple[str, str]]]


@dataclass
class Calculator:
    """Everything needed to render one calculator page."""

    slug: str                           # stable id, e.g. "aero.lift"
    name: str
    latex: str
    explanation: str
    inputs: List[Field] = field(default_factory=list)
    compute: Optional[Callable[[Inputs], float]] = None
    result: Optional[Output] = None
    secondary: List[Secondary] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    variables: List[Tuple[str, str, str]] = field(default_factory=list)
    example: str = ""
    graph: Optional[Sweep] = None
    """One graph. Prefer `graphs` for more than one; both end up in `graphs`."""
    graphs: List[Sweep] = field(default_factory=list)
    references: List[Reference] = field(default_factory=list)
    checks: List[Check] = field(default_factory=list)
    related: Sequence[str] = ()
    """Slugs of calculators that answer the next question this one raises."""
    sensitivity: bool = True
    """Show the derived influence table. Off only where it says nothing -
    a page whose result is a lookup rather than a function of its inputs."""
    note: Optional[Callable[[Inputs, float], Optional[str]]] = None
    """Optional caption under the result - return None for no caption."""
    render: Optional[Callable[[], None]] = None
    """Escape hatch: draw the whole page yourself and ignore everything above."""
    keywords: Sequence[str] = ()
    """Extra search terms for the command palette."""

    def __post_init__(self) -> None:
        # One code path downstream: `graph=` is the common single-graph case
        # and stays supported, but the renderer only ever reads `graphs`.
        if self.graph is not None and self.graph not in self.graphs:
            self.graphs = [self.graph] + list(self.graphs)

    @property
    def prefix(self) -> str:
        """Widget-key namespace. Reset clears every key with this prefix."""
        return self.slug.replace(".", "_")

    def search_text(self) -> str:
        """What the command palette matches against."""
        return " ".join([self.name, self.slug, " ".join(self.keywords)]).lower()


def normalise(entries, category: str) -> List[Calculator]:
    """Accept either a list of Calculator or a legacy {name: render_fn} dict.

    Lets modules be converted to specs one at a time while the app keeps
    working, rather than needing one enormous atomic change.
    """
    if isinstance(entries, dict):
        prefix = category.lower().replace(" ", "_").replace("/", "_")
        return [
            Calculator(
                slug=f"{prefix}.{name.lower().replace(' ', '_')}",
                name=name, latex="", explanation="", render=fn,
            )
            for name, fn in entries.items()
        ]
    return list(entries)
