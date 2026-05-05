"""
Test SRT patching for zh-TW locale rewording.

Two patterns documented here from project 1776997800:
  s3: abstract compound noun → vivid concrete action (情感錯配 → 接偏了/落空)
  s6: clinical label → minimal felt truth (情感伸手是危險的 → 伸手，不安全)
      — also creates a deliberate echo with the scene's closing line "不伸，才安全"
"""
from __future__ import annotations

from pathlib import Path

from pipeline.utils.srt import SrtEntry, parse_srt, write_srt

S3_ORIGINAL = (
    "它通常來自日常的情感錯配，\n"
    "不是壞父母，而是反覆的小小失聯。"
)
S3_VIVID = (
    "它通常不是大傷害，而是反覆的小小落空——\n"
    "父母有愛、有回應，只是稍微接偏了。"
)

S6_ORIGINAL_BLK16 = "第一個模式：孩子學到，\n情感伸手是危險的。"
S6_VIVID_BLK16 = "第一個模式：孩子學到，\n哭了，也沒人接住。"

S6_ORIGINAL_BLK19 = "但孩子的神經系統只記錄了一件\n事：我把手伸出去，對方退縮了。"
S6_VIVID_BLK19 = "但孩子的神經系統只記錄了一件\n事：我伸手了，但沒人接住我。"


def _make_srt(entries: list[tuple[int, int, int, str]]) -> list[SrtEntry]:
    return [SrtEntry(index=i, start_ms=s, end_ms=e, text=t) for i, s, e, t in entries]


def patch_srt_entry(entries: list[SrtEntry], index: int, new_text: str) -> list[SrtEntry]:
    """Replace the text of the entry matching `index`, leave all others untouched."""
    return [
        SrtEntry(e.index, e.start_ms, e.end_ms, new_text) if e.index == index else e
        for e in entries
    ]


class TestSrtLocalePatching:
    def test_patch_preserves_timing(self):
        entries = _make_srt([
            (7, 29_976, 36_543, "大多數人以為迴避型依附來自嚴重的創傷——\n被拋棄、被忽視。"),
            (8, 36_543, 39_260, "但真相更隱微，也更普遍。"),
            (9, 39_260, 46_053, S3_ORIGINAL),
            (10, 46_055, 49_650, "關鍵，不是某一次大的衝突或傷害。"),
        ])
        patched = patch_srt_entry(entries, index=9, new_text=S3_VIVID)

        s3 = next(e for e in patched if e.index == 9)
        assert s3.start_ms == 39_260
        assert s3.end_ms == 46_053
        assert s3.text == S3_VIVID

    def test_patch_only_touches_target(self):
        entries = _make_srt([
            (7, 29_976, 36_543, "大多數人以為迴避型依附來自嚴重的創傷——\n被拋棄、被忽視。"),
            (8, 36_543, 39_260, "但真相更隱微，也更普遍。"),
            (9, 39_260, 46_053, S3_ORIGINAL),
            (10, 46_055, 49_650, "關鍵，不是某一次大的衝突或傷害。"),
        ])
        patched = patch_srt_entry(entries, index=9, new_text=S3_VIVID)

        for e in patched:
            if e.index != 9:
                original = next(o for o in entries if o.index == e.index)
                assert e.text == original.text
                assert e.start_ms == original.start_ms
                assert e.end_ms == original.end_ms

    def test_abstract_term_removed(self):
        entries = _make_srt([(9, 39_260, 46_053, S3_ORIGINAL)])
        patched = patch_srt_entry(entries, index=9, new_text=S3_VIVID)
        text = patched[0].text
        assert "情感錯配" not in text
        assert "小小失聯" not in text

    def test_vivid_terms_present(self):
        entries = _make_srt([(9, 39_260, 46_053, S3_ORIGINAL)])
        patched = patch_srt_entry(entries, index=9, new_text=S3_VIVID)
        text = patched[0].text
        assert "落空" in text
        assert "接偏了" in text

    def test_roundtrip_through_file(self, tmp_path: Path):
        entries = _make_srt([
            (8, 36_543, 39_260, "但真相更隱微，也更普遍。"),
            (9, 39_260, 46_053, S3_ORIGINAL),
            (10, 46_055, 49_650, "關鍵，不是某一次大的衝突或傷害。"),
        ])
        srt_path = tmp_path / "test.srt"
        write_srt(entries, srt_path)

        loaded = parse_srt(srt_path)
        patched = patch_srt_entry(loaded, index=9, new_text=S3_VIVID)
        write_srt(patched, srt_path)

        final = parse_srt(srt_path)
        s3 = next(e for e in final if e.index == 9)
        assert s3.text == S3_VIVID
        assert s3.start_ms == 39_260
        assert s3.end_ms == 46_053


class TestS6Pattern:
    """s6: clinical label → felt truth (two sentences changed to close an arc).

    Opening: 情感伸手是危險的 → 哭了，也沒人接住
    Mid-scene: 我把手伸出去，對方退縮了 → 我伸手了，但沒人接住我
    Both use 接住 — echoes s4 vocabulary (接偏了/沒接準) and closes the scene loop.
    """

    def test_blk16_clinical_label_removed(self):
        entries = _make_srt([(16, 84_407, 88_924, S6_ORIGINAL_BLK16)])
        patched = patch_srt_entry(entries, index=16, new_text=S6_VIVID_BLK16)
        assert "情感伸手" not in patched[0].text
        assert "哭了" in patched[0].text
        assert "沒人接住" in patched[0].text

    def test_blk19_parent_action_replaced_with_child_experience(self):
        entries = _make_srt([(19, 102_259, 108_712, S6_ORIGINAL_BLK19)])
        patched = patch_srt_entry(entries, index=19, new_text=S6_VIVID_BLK19)
        assert "對方退縮了" not in patched[0].text
        assert "沒人接住我" in patched[0].text

    def test_接住_vocabulary_thread_consistent(self):
        # Both changed blocks use 接住 — consistent with s3/s4 vocabulary
        assert "接住" in S6_VIVID_BLK16
        assert "接住" in S6_VIVID_BLK19

    def test_timings_preserved_both_blocks(self):
        e16 = _make_srt([(16, 84_407, 88_924, S6_ORIGINAL_BLK16)])
        e19 = _make_srt([(19, 102_259, 108_712, S6_ORIGINAL_BLK19)])
        p16 = patch_srt_entry(e16, 16, S6_VIVID_BLK16)
        p19 = patch_srt_entry(e19, 19, S6_VIVID_BLK19)
        assert p16[0].start_ms == 84_407 and p16[0].end_ms == 88_924
        assert p19[0].start_ms == 102_259 and p19[0].end_ms == 108_712
