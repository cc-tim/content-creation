"""E11 never-silent, on the real browser (Phase 2 review I5, M1): a hung page call times out and
takes its browser down; a lost WebGL context and a page console error fail the render, naming it."""
import json
import subprocess
import time

import pytest

pytestmark = pytest.mark.integration


def _ours(tag):
    """Processes whose command line carries this page's tag: its browser."""
    out = subprocess.run(["pgrep", "-f", f"toy3d-page={tag}"], capture_output=True, text=True)
    return out.stdout.split()


def test_a_hung_page_call_times_out_and_leaves_no_browser(monkeypatch):
    from toy3d import runtime

    monkeypatch.setattr(runtime, "CALL_TIMEOUT", 2.0)
    t0 = time.monotonic()
    tag = None
    with pytest.raises(runtime.Toy3DRenderError, match=r"evaluate timed out after 2 s"), \
            runtime.open_page(64, 36, "render") as page:
        tag = page.tag
        assert _ours(tag)                                          # its browser is up
        page.evaluate("() => { while (true) {} }")
    assert time.monotonic() - t0 < 30
    time.sleep(1.0)
    assert not _ours(tag)                                          # and gone: no orphan left spinning


@pytest.fixture
def page(bank):
    from toy3d import runtime

    with runtime.open_page(160, 90, "render") as p:
        p.init(runtime.bank_payload(bank), 160, 90, "render")
        yield p


def _spec(worked, bank, t):
    from toy3d.acting import resolve

    return json.loads(json.dumps(resolve(worked, bank, t)))


def test_a_lost_webgl_context_fails_the_render(page, worked, bank):
    from toy3d.runtime import Toy3DRenderError

    page.render_state(_spec(worked, bank, 1.0))
    page.evaluate("() => document.querySelector('canvas').getContext('webgl2')"
                  ".getExtension('WEBGL_lose_context').loseContext()")
    with pytest.raises(Toy3DRenderError, match="WebGL context was lost"):
        page.render_state(_spec(worked, bank, 1.1))


def test_a_console_error_fails_the_render(page, worked, bank):
    from toy3d.runtime import Toy3DRenderError

    with pytest.raises(Toy3DRenderError, match="Shader Error 1282"):      # at the first call that sees it
        page.evaluate("() => console.error('THREE.WebGLProgram: Shader Error 1282 - VALIDATE_STATUS false')")
        page.render_state(_spec(worked, bank, 1.0))
