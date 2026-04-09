from __future__ import annotations

from pipeline.storyboard import Scene


def test_scene_accepts_compartment():
    scene = Scene.from_dict(
        {
            "id": "s3",
            "section": "context",
            "narration": "脈絡焦慮",
            "narration_est_sec": 10,
            "facts_ref": ["f1"],
            "visual": {"type": "generated_image", "prompt": "brain"},
            "overlay": {"type": "text_left", "text": "上下文焦慮"},
            "compartment": {
                "type": "running_out",
                "position": "right",
                "size": {"width": 0.35, "height": 0.6},
                "loop": True,
                "animation": {
                    "label": "上下文",
                    "stages": [
                        {"value": "20%", "face": "neutral", "color": "#fbbf24"},
                        {"value": "10%", "face": "worried", "color": "#fb923c"},
                        {"value": "5%", "face": "panicked", "color": "#ef4444"},
                    ],
                    "stage_duration_sec": 1.5,
                    "shake": True,
                },
            },
        }
    )
    assert scene.compartment is not None
    assert scene.compartment["type"] == "running_out"
    assert scene.compartment["animation"]["shake"] is True


def test_scene_without_compartment_round_trips():
    data = {
        "id": "s1",
        "section": "hook",
        "narration": "開場",
        "narration_est_sec": 8,
        "facts_ref": [],
        "visual": {"type": "text_card", "text": "hi"},
        "overlay": None,
    }
    scene = Scene.from_dict(data)
    assert scene.compartment is None
    round_tripped = scene.to_dict()
    assert "compartment" not in round_tripped or round_tripped["compartment"] is None


def test_scene_with_compartment_round_trips():
    data = {
        "id": "s3",
        "section": "context",
        "narration": "N",
        "narration_est_sec": 5,
        "facts_ref": [],
        "visual": {"type": "generated_image", "prompt": "x"},
        "overlay": None,
        "compartment": {"type": "running_out"},
    }
    scene = Scene.from_dict(data)
    round_tripped = scene.to_dict()
    assert round_tripped["compartment"] == {"type": "running_out"}
