from pipeline.constraints import ProjectConstraints


def test_default_clip_pct():
    c = ProjectConstraints()
    assert c.max_source_clip_pct == 0.60


def test_clip_budget_instruction_counts():
    c = ProjectConstraints(max_source_clip_pct=0.60)
    instr = c.clip_budget_instruction(scene_count=20)
    assert "12" in instr          # 60% of 20
    assert "20" in instr
    assert "clip" in instr.lower()


def test_check_clip_budget_ok():
    c = ProjectConstraints(max_source_clip_pct=0.60)
    scenes = [{"visual": {"type": "clip"}} for _ in range(10)] + \
             [{"visual": {"type": "generated_image"}} for _ in range(10)]
    assert c.check_clip_budget(scenes) == []


def test_check_clip_budget_exceeded():
    c = ProjectConstraints(max_source_clip_pct=0.60)
    scenes = [{"visual": {"type": "clip"}} for _ in range(18)] + \
             [{"visual": {"type": "generated_image"}} for _ in range(2)]
    violations = c.check_clip_budget(scenes)
    assert len(violations) == 1
    assert "18" in violations[0]


def test_still_frame_counts_against_budget():
    c = ProjectConstraints(max_source_clip_pct=0.60)
    scenes = [{"visual": {"type": "still_frame"}} for _ in range(18)] + \
             [{"visual": {"type": "generated_image"}} for _ in range(2)]
    violations = c.check_clip_budget(scenes)
    assert violations  # still_frame counts as source usage


def test_round_trip_json(tmp_path):
    c = ProjectConstraints(max_source_clip_pct=0.40, source_suitability="low")
    c.save(tmp_path)
    loaded = ProjectConstraints.load(tmp_path)
    assert loaded.max_source_clip_pct == 0.40
    assert loaded.source_suitability == "low"
