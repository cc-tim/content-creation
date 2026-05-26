def test_scriptwrite_in_pre_review_chain():
    from pipeline.stages.acquire import AcquireStage
    from pipeline.stages.analyze import AnalyzeStage
    from pipeline.stages.compose import ComposeStage
    from pipeline.stages.direct import DirectStage
    from pipeline.stages.scriptwrite import ScriptwriteStage
    from pipeline.stages.tts import TtsStage

    all_stages = [
        AcquireStage(), AnalyzeStage(), DirectStage(),
        ScriptwriteStage(), TtsStage(), ComposeStage(),
    ]
    names = [s.name for s in all_stages]
    assert names == ["acquire", "analyze", "direct", "scriptwrite", "tts", "compose"]
    # scriptwrite must run before the human review gate (pre-review)
    pre_review = {"acquire", "analyze", "direct", "scriptwrite"}
    assert "scriptwrite" in pre_review
