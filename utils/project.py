"""One project across seventy-eight calculators.

Every page in ASCENT has been an island: work out lift on one, then retype the
same mass on the drone page, the structures page and the motor page. Nothing
notices when those four values drift apart, which is the single most likely way
to get a confidently wrong answer out of a set of individually correct
calculators.

So a value is defined once here and bound to inputs. A bound input shows the
project value and cannot be edited on the page, because an input you can
override locally is a divergence waiting to happen - the consistency problem
solved by construction rather than detected afterwards.

Requirements sit on top: a target on a calculator's result, evaluated against
the current parameters. The important part is what happens when the evidence is
thin. A requirement whose inputs are not all pinned is reported as NOT
EVALUATED, never as met - missing information must not become a green tick.
And a calculator whose own regime Checks are firing reports OUTSIDE MODEL,
because a number the model cannot support is not a pass either.
"""
from __future__ import annotations

import json
import operator
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .settings import SUPPORT_DIR
from .spec import Calculator, Inputs
from .validation import ValidationError

PROJECT_PATH = os.path.join(SUPPORT_DIR, "project.json")

SOURCES = ("Measured", "Manufacturer spec", "Assumed", "Estimated")
"""Where a number came from. Kept with the value because "2.4 kg measured on a
scale" and "2.4 kg someone guessed" are not the same input, and only one of
them is worth designing around."""

OPERATORS: Dict[str, Any] = {
    "at most": operator.le,
    "at least": operator.ge,
    "greater than": operator.gt,
    "less than": operator.lt,
}

# Verdicts. The last two are the point of the whole exercise.
MET = "Meets"
NOT_MET = "Does not meet"
NOT_EVALUATED = "Not evaluated"
OUTSIDE_MODEL = "Outside model applicability"

_NUMERIC_KINDS = {"float", "int", "slider"}


@dataclass
class Parameter:
    key: str
    label: str
    value: float
    unit: str
    source: str = "Assumed"
    note: str = ""
    uncertainty: float = 0.0
    """The +/- on this value, in its own unit. Zero means "not stated",
    which is different from "exact" - the pages say so rather than quietly
    treating an unstated uncertainty as none."""


@dataclass
class Requirement:
    key: str
    label: str
    slug: str
    op: str
    target: float


@dataclass
class Verdict:
    status: str
    value: Optional[float] = None
    unit: str = ""
    detail: str = ""
    unpinned: List[str] = field(default_factory=list)
    sigma: float = 0.0
    marginal: bool = False
    """True when the uncertainty band crosses the target, so the verdict is
    real but not established: the same design could fall the other side of the
    line without anything about it changing."""

    @property
    def decided(self) -> bool:
        return self.status in (MET, NOT_MET)


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------
def _empty() -> Dict[str, Any]:
    return {"parameters": {}, "bindings": {}, "requirements": []}


def load() -> Dict[str, Any]:
    """The project, falling back to an empty one on any problem."""
    try:
        with open(PROJECT_PATH, encoding="utf-8") as handle:
            return _coerce(json.load(handle))
    except (OSError, ValueError):
        return _empty()


def _coerce(raw: Any) -> Dict[str, Any]:
    """Keep only well-formed entries. A malformed project file should cost the
    bad row, not the whole project."""
    out = _empty()
    if not isinstance(raw, dict):
        return out

    for key, entry in (raw.get("parameters") or {}).items():
        if not isinstance(entry, dict) or not isinstance(key, str):
            continue
        try:
            value = float(entry["value"])
        except (KeyError, TypeError, ValueError):
            continue
        try:
            # Negative is meaningless and would flip a variance term's sign
            # if it were ever used unsquared.
            spread = abs(float(entry.get("uncertainty", 0.0) or 0.0))
        except (TypeError, ValueError):
            spread = 0.0
        out["parameters"][key] = asdict(Parameter(
            key=key,
            label=str(entry.get("label") or key),
            value=value,
            unit=str(entry.get("unit") or ""),
            source=(entry.get("source") if entry.get("source") in SOURCES
                    else "Assumed"),
            note=str(entry.get("note") or ""),
            uncertainty=spread,
        ))

    for slot, param in (raw.get("bindings") or {}).items():
        # A binding to a parameter that no longer exists would silently feed a
        # default into a page that claims to be using the project.
        if isinstance(slot, str) and param in out["parameters"]:
            out["bindings"][slot] = param

    for entry in (raw.get("requirements") or []):
        if not isinstance(entry, dict):
            continue
        try:
            target = float(entry["target"])
        except (KeyError, TypeError, ValueError):
            continue
        if entry.get("op") not in OPERATORS or not entry.get("slug"):
            continue
        out["requirements"].append(asdict(Requirement(
            key=str(entry.get("key") or slugify(str(entry.get("label", "req")))),
            label=str(entry.get("label") or "Requirement"),
            slug=str(entry["slug"]),
            op=str(entry["op"]),
            target=target,
        )))
    return out


def save(project: Dict[str, Any]) -> bool:
    """Atomic write, so an interrupted save cannot leave a half-written file."""
    try:
        os.makedirs(SUPPORT_DIR, exist_ok=True)
        temporary = PROJECT_PATH + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(_coerce(project), handle, indent=2)
        os.replace(temporary, PROJECT_PATH)
        return True
    except OSError:
        return False


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")
    return cleaned or "value"


# ---------------------------------------------------------------------------
# Parameters and bindings
# ---------------------------------------------------------------------------
def parameters(project: Dict[str, Any]) -> List[Parameter]:
    return [Parameter(**entry) for entry in project["parameters"].values()]


def add_parameter(project: Dict[str, Any], label: str, value: float,
                  unit: str, source: str = "Assumed", note: str = "",
                  uncertainty: float = 0.0) -> Parameter:
    key = slugify(label)
    suffix = 2
    while key in project["parameters"] and \
            project["parameters"][key]["label"] != label:
        key, suffix = f"{slugify(label)}_{suffix}", suffix + 1
    param = Parameter(key=key, label=label, value=float(value), unit=unit,
                      source=source, note=note,
                      uncertainty=abs(float(uncertainty or 0.0)))
    project["parameters"][key] = asdict(param)
    return param


def remove_parameter(project: Dict[str, Any], key: str) -> None:
    project["parameters"].pop(key, None)
    # Bindings to a removed parameter must go with it, or a page keeps
    # claiming to read from the project while quietly using a default.
    for slot in [s for s, p in project["bindings"].items() if p == key]:
        project["bindings"].pop(slot, None)


def slot(slug: str, field_key: str) -> str:
    return f"{slug}:{field_key}"


def bind(project: Dict[str, Any], slug: str, field_key: str,
         param_key: Optional[str]) -> None:
    where = slot(slug, field_key)
    if param_key and param_key in project["parameters"]:
        project["bindings"][where] = param_key
    else:
        project["bindings"].pop(where, None)


def bound_value(project: Dict[str, Any], slug: str,
                field_key: str) -> Optional[Parameter]:
    key = project["bindings"].get(slot(slug, field_key))
    entry = project["parameters"].get(key) if key else None
    return Parameter(**entry) if entry else None


def compatible(project: Dict[str, Any], unit: str) -> List[Parameter]:
    """Parameters that could fill an input measured in `unit`.

    Matched on the unit string rather than on a dimensional analysis, because
    the units here are already written in one canonical style throughout the
    app, and a real dimension system would be a large piece of machinery whose
    only job is to say what a string comparison already says.
    """
    wanted = (unit or "").strip()
    return [p for p in parameters(project) if p.unit.strip() == wanted]


def usage(project: Dict[str, Any], param_key: str) -> List[Tuple[str, str]]:
    """(slug, field) for every input this parameter feeds."""
    return [tuple(s.split(":", 1)) for s, p in project["bindings"].items()
            if p == param_key]


# ---------------------------------------------------------------------------
# Requirements
# ---------------------------------------------------------------------------
def add_requirement(project: Dict[str, Any], label: str, slug: str, op: str,
                    target: float) -> Requirement:
    requirement = Requirement(key=slugify(f"{label}_{slug}"), label=label,
                              slug=slug, op=op, target=float(target))
    project["requirements"].append(asdict(requirement))
    return requirement


def remove_requirement(project: Dict[str, Any], key: str) -> None:
    project["requirements"] = [r for r in project["requirements"]
                               if r["key"] != key]


def requirements(project: Dict[str, Any]) -> List[Requirement]:
    return [Requirement(**entry) for entry in project["requirements"]]


def inputs_for(project: Dict[str, Any], calc: Calculator
               ) -> Tuple[Dict[str, Any], List[str]]:
    """Input values for a calculator, plus the labels of anything unpinned.

    Unbound inputs fall back to the spec's own default so a number can still be
    shown - but they are reported, and their presence is what stops a
    requirement being called met.
    """
    values: Dict[str, Any] = {}
    unpinned: List[str] = []
    for spec_field in calc.inputs:
        param = bound_value(project, calc.slug, spec_field.key)
        if param is not None:
            values[spec_field.key] = param.value
            continue
        if spec_field.kind == "choice" and spec_field.options:
            values[spec_field.key] = spec_field.options[0]
        else:
            values[spec_field.key] = spec_field.default
            if spec_field.kind in _NUMERIC_KINDS or spec_field.kind == "weight":
                unpinned.append(spec_field.label)
    return values, unpinned


def uncertainties_for(project: Dict[str, Any], calc: Calculator
                      ) -> Dict[str, float]:
    """The +/- on each of a calculator's inputs, from the parameters bound to
    them. An input with no bound parameter, or one whose parameter states no
    uncertainty, contributes nothing."""
    out: Dict[str, float] = {}
    for spec_field in calc.inputs:
        param = bound_value(project, calc.slug, spec_field.key)
        if param is not None and param.uncertainty > 0:
            out[spec_field.key] = param.uncertainty
    return out


def evaluate(project: Dict[str, Any], requirement: Requirement,
             catalogue: Dict[str, Any]) -> Verdict:
    """Decide a requirement, or explain honestly why it cannot be decided."""
    entry = catalogue.get(requirement.slug)
    if entry is None:
        return Verdict(NOT_EVALUATED,
                       detail="That calculator is no longer in the app.")
    calc = entry[1] if isinstance(entry, tuple) else entry
    if calc.compute is None or calc.result is None:
        return Verdict(NOT_EVALUATED,
                       detail="That page does not produce a single result.")

    values, unpinned = inputs_for(project, calc)
    try:
        value = calc.compute(Inputs(values))
    except (ValidationError, ZeroDivisionError, ValueError, OverflowError) as exc:
        return Verdict(NOT_EVALUATED, detail=str(exc), unpinned=unpinned)
    if not isinstance(value, (int, float)):
        return Verdict(NOT_EVALUATED, detail="No numeric result.",
                       unpinned=unpinned)
    value = float(value)
    unit = calc.result.unit

    # The calculator's own regime checks outrank the comparison. A number the
    # model cannot support is not a pass, however it compares to the target.
    for check in calc.checks:
        try:
            verdict = check.fn(Inputs(values), value)
        except (ValidationError, ZeroDivisionError, ValueError):
            continue
        if verdict and verdict[0] in ("warning", "danger"):
            return Verdict(OUTSIDE_MODEL, value=value, unit=unit,
                           detail=verdict[1], unpinned=unpinned)

    if unpinned:
        return Verdict(
            NOT_EVALUATED, value=value, unit=unit, unpinned=unpinned,
            detail="Some inputs are still the page defaults rather than "
                   "project values, so this number is not a statement about "
                   "your design yet.")

    passed = OPERATORS[requirement.op](value, requirement.target)

    # If the answer's own uncertainty reaches across the target, the comparison
    # is decided by a difference the inputs cannot actually resolve. That is
    # not a failure, and it is not a clean pass either - it is a pass that
    # should be labelled as one you cannot yet rely on.
    from . import analysis

    spread = analysis.uncertainty(calc, Inputs(values), value,
                                  uncertainties_for(project, calc))
    marginal = bool(spread.known
                    and abs(value - requirement.target) < spread.sigma)
    return Verdict(MET if passed else NOT_MET, value=value, unit=unit,
                   sigma=spread.sigma, marginal=marginal,
                   detail=(f"within ± {spread.sigma:.4g} {unit} of the target, "
                           "so this is not established"
                           if marginal else ""))


def summary(project: Dict[str, Any], catalogue: Dict[str, Any]
            ) -> Dict[str, int]:
    counts = {MET: 0, NOT_MET: 0, NOT_EVALUATED: 0, OUTSIDE_MODEL: 0}
    for requirement in requirements(project):
        counts[evaluate(project, requirement, catalogue).status] += 1
    return counts
