"""Shared parameters and the requirements board.

The behaviour worth defending here is not that a comparison works. It is that
the board refuses to say "met" when it does not know - a requirements view that
turns missing information into a green tick is worse than no requirements view,
because it manufactures confidence.
"""
from __future__ import annotations

import pytest

from utils import project as store
from utils.spec import Calculator, Check, Field, Output


@pytest.fixture
def empty(real_settings_file):
    fresh = store._empty()
    store.save(fresh)
    return store.load()


def _calc(**kw):
    base = dict(slug="t.beam", name="Beam", latex="", explanation="",
                inputs=[Field("load", "Load", "N", 500.0),
                        Field("length", "Length", "m", 2.0)],
                compute=lambda i: i.load * i.length,
                result=Output("Moment", "N·m"))
    base.update(kw)
    return Calculator(**base)


def _catalogue(calc):
    return {calc.slug: ("Structures", calc)}


# --------------------------------------------------------------------------
# Parameters
# --------------------------------------------------------------------------
def test_a_parameter_round_trips(empty):
    store.add_parameter(empty, "Vehicle mass", 2.4, "kg", "Measured", "on a scale")
    store.save(empty)
    again = store.load()
    param = store.parameters(again)[0]
    assert (param.label, param.value, param.unit) == ("Vehicle mass", 2.4, "kg")
    assert param.source == "Measured" and param.note == "on a scale"


def test_an_unknown_source_falls_back_rather_than_being_trusted(empty):
    empty["parameters"]["x"] = {"key": "x", "label": "X", "value": 1.0,
                                "unit": "kg", "source": "Divinely revealed",
                                "note": ""}
    assert store._coerce(empty)["parameters"]["x"]["source"] == "Assumed"


def test_a_malformed_entry_costs_only_itself(empty):
    """A broken project file should lose the bad row, not the project."""
    store.add_parameter(empty, "Good", 1.0, "kg")
    empty["parameters"]["bad"] = {"label": "Bad", "value": "not a number"}
    recovered = store._coerce(empty)
    assert "bad" not in recovered["parameters"]
    assert "good" in recovered["parameters"]


def test_parameters_are_matched_to_inputs_by_unit(empty):
    store.add_parameter(empty, "Mass", 2.4, "kg")
    store.add_parameter(empty, "Voltage", 14.8, "V")
    assert [p.label for p in store.compatible(empty, "kg")] == ["Mass"]
    assert [p.label for p in store.compatible(empty, "V")] == ["Voltage"]
    assert store.compatible(empty, "m²") == []


def test_removing_a_parameter_removes_its_bindings(empty):
    """A binding left pointing at nothing would let a page keep claiming it
    reads from the project while quietly using a default."""
    store.add_parameter(empty, "Mass", 2.4, "kg")
    store.bind(empty, "t.beam", "load", "mass")
    store.remove_parameter(empty, "mass")
    assert empty["bindings"] == {}
    assert store.bound_value(empty, "t.beam", "load") is None


def test_a_binding_to_a_missing_parameter_is_dropped_on_load(empty):
    empty["bindings"]["t.beam:load"] = "never_existed"
    assert store._coerce(empty)["bindings"] == {}


def test_usage_reports_every_input_a_parameter_feeds(empty):
    store.add_parameter(empty, "Mass", 2.4, "kg")
    store.bind(empty, "a.one", "m", "mass")
    store.bind(empty, "b.two", "mass", "mass")
    assert sorted(store.usage(empty, "mass")) == [("a.one", "m"),
                                                  ("b.two", "mass")]


# --------------------------------------------------------------------------
# The verdict - the part that must never lie
# --------------------------------------------------------------------------
def test_an_unpinned_input_is_never_a_pass(empty):
    """The whole point. 500 x 2 = 1000, which is under the target of 5000, but
    neither input came from the project - so this says nothing about the
    user's design and must not be reported as met."""
    calc = _calc()
    requirement = store.add_requirement(empty, "Moment limit", "t.beam",
                                        "at most", 5000.0)
    verdict = store.evaluate(empty, store.Requirement(**requirement.__dict__),
                             _catalogue(calc))
    assert verdict.status == store.NOT_EVALUATED
    assert verdict.value == 1000.0          # the number is still shown
    assert sorted(verdict.unpinned) == ["Length", "Load"]


def test_pinning_every_input_produces_a_verdict(empty):
    calc = _calc()
    store.add_parameter(empty, "Load", 500.0, "N")
    store.add_parameter(empty, "Length", 2.0, "m")
    store.bind(empty, "t.beam", "load", "load")
    store.bind(empty, "t.beam", "length", "length")
    requirement = store.add_requirement(empty, "Moment limit", "t.beam",
                                        "at most", 5000.0)
    verdict = store.evaluate(empty, requirement, _catalogue(calc))
    assert verdict.status == store.MET and verdict.value == 1000.0


def test_a_failing_requirement_says_so(empty):
    calc = _calc()
    store.add_parameter(empty, "Load", 5000.0, "N")
    store.add_parameter(empty, "Length", 2.0, "m")
    store.bind(empty, "t.beam", "load", "load")
    store.bind(empty, "t.beam", "length", "length")
    requirement = store.add_requirement(empty, "Moment limit", "t.beam",
                                        "at most", 5000.0)
    assert store.evaluate(empty, requirement,
                          _catalogue(calc)).status == store.NOT_MET


def test_a_firing_regime_check_outranks_the_comparison(empty):
    """A number the model cannot support is not a pass, however well it
    compares to the target. This reuses the same Check objects the calculator
    pages already show."""
    calc = _calc(checks=[Check(lambda i, r: ("danger", "Past yield."))])
    store.add_parameter(empty, "Load", 500.0, "N")
    store.add_parameter(empty, "Length", 2.0, "m")
    store.bind(empty, "t.beam", "load", "load")
    store.bind(empty, "t.beam", "length", "length")
    requirement = store.add_requirement(empty, "Moment limit", "t.beam",
                                        "at most", 5000.0)
    verdict = store.evaluate(empty, requirement, _catalogue(calc))
    assert verdict.status == store.OUTSIDE_MODEL
    assert verdict.detail == "Past yield."


def test_an_info_check_does_not_block_a_verdict(empty):
    """Only warning and danger mean the model is out of its range; info is a
    remark."""
    calc = _calc(checks=[Check(lambda i, r: ("info", "Just so you know."))])
    store.add_parameter(empty, "Load", 500.0, "N")
    store.add_parameter(empty, "Length", 2.0, "m")
    store.bind(empty, "t.beam", "load", "load")
    store.bind(empty, "t.beam", "length", "length")
    requirement = store.add_requirement(empty, "Moment limit", "t.beam",
                                        "at most", 5000.0)
    assert store.evaluate(empty, requirement,
                          _catalogue(calc)).status == store.MET


def test_a_calculation_that_raises_is_not_evaluated(empty):
    def boom(i):
        raise ValueError("negative under the root")
    calc = _calc(compute=boom)
    requirement = store.add_requirement(empty, "R", "t.beam", "at most", 1.0)
    verdict = store.evaluate(empty, requirement, _catalogue(calc))
    assert verdict.status == store.NOT_EVALUATED
    assert "negative under the root" in verdict.detail


def test_a_requirement_pointing_at_a_removed_calculator_is_not_evaluated(empty):
    requirement = store.add_requirement(empty, "R", "gone.away", "at most", 1.0)
    verdict = store.evaluate(empty, requirement, {})
    assert verdict.status == store.NOT_EVALUATED
    assert "no longer in the app" in verdict.detail


def test_a_choice_input_does_not_count_as_unpinned(empty):
    """A dropdown has no project parameter to link to and always has a value,
    so requiring it to be pinned would make a verdict unreachable."""
    calc = _calc(inputs=[Field("mode", "Mode", "", 0, kind="choice",
                               options=["a", "b"]),
                         Field("load", "Load", "N", 2.0)],
                 compute=lambda i: i.load)
    store.add_parameter(empty, "Load", 2.0, "N")
    store.bind(empty, "t.beam", "load", "load")
    requirement = store.add_requirement(empty, "R", "t.beam", "at least", 1.0)
    assert store.evaluate(empty, requirement,
                          _catalogue(calc)).status == store.MET


@pytest.mark.parametrize("op,target,expected", [
    ("at most", 1000.0, store.MET),
    ("at most", 999.0, store.NOT_MET),
    ("at least", 1000.0, store.MET),
    ("at least", 1001.0, store.NOT_MET),
    ("greater than", 1000.0, store.NOT_MET),
    ("less than", 1000.0, store.NOT_MET),
])
def test_every_comparison_behaves_at_the_boundary(empty, op, target, expected):
    calc = _calc()
    store.add_parameter(empty, "Load", 500.0, "N")
    store.add_parameter(empty, "Length", 2.0, "m")
    store.bind(empty, "t.beam", "load", "load")
    store.bind(empty, "t.beam", "length", "length")
    requirement = store.add_requirement(empty, "R", "t.beam", op, target)
    assert store.evaluate(empty, requirement,
                          _catalogue(calc)).status == expected


# --------------------------------------------------------------------------
# Live values reach the calculators
# --------------------------------------------------------------------------
def test_changing_a_parameter_changes_the_verdict_with_no_other_edit(empty):
    """The reason the whole thing exists: one edit, every dependent result."""
    calc = _calc()
    store.add_parameter(empty, "Load", 500.0, "N")
    store.add_parameter(empty, "Length", 2.0, "m")
    store.bind(empty, "t.beam", "load", "load")
    store.bind(empty, "t.beam", "length", "length")
    requirement = store.add_requirement(empty, "R", "t.beam", "at most", 2000.0)
    assert store.evaluate(empty, requirement,
                          _catalogue(calc)).status == store.MET

    empty["parameters"]["load"]["value"] = 2000.0
    assert store.evaluate(empty, requirement,
                          _catalogue(calc)).status == store.NOT_MET


def test_the_summary_counts_all_four_states(empty):
    assert set(store.summary(empty, {})) == {
        store.MET, store.NOT_MET, store.NOT_EVALUATED, store.OUTSIDE_MODEL}


def test_importing_the_app_does_not_draw_it():
    """app.py called main() at import. That was always wrong and never bit,
    until a form appeared on the landing page: running main() in bare mode
    left Streamlit's global form state open, and every widget in the next real
    run raised "st.button() can't be used in an st.form()"."""
    source = open("app.py", encoding="utf-8").read()
    assert 'if __name__ == "__main__":' in source
    tail = source.rsplit('if __name__ == "__main__":', 1)[1]
    assert tail.strip() == "main()"


def test_the_project_page_is_the_first_thing_in_the_catalogue():
    """A value defined there is the value every other page can link, so it is
    where someone should land rather than something to go hunting for."""
    import app
    assert list(app.CATEGORIES)[0] == "Project"
