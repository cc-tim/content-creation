import inspect

from pipeline.stages import direct


def test_prompt_includes_chart_taxonomy_and_examples():
    """The director taxonomy must teach `chart` and each chart_type's data schema
    by demonstration (worked examples with real numbers), not just by name."""
    src = inspect.getsource(direct)
    assert '"type": "chart"' in src
    for chart_type in ("stat_big_number", "proportion_blocks", "timeline", "bar", "comparison"):
        assert chart_type in src, f"missing chart_type {chart_type} in director prompt"
    # A worked example carrying a real number (teaches the data schema):
    assert "230,676" in src
    # The <=8-char guardrail is surfaced to the model:
    assert "8 chars" in src
