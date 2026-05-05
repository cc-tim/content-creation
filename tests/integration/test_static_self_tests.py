"""Run the edit-mode JS self-tests with node."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

_STATIC = Path(__file__).resolve().parents[2] / "src" / "pipeline" / "dashboard" / "static"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_tokens_self_tests_pass():
    shim = (
        "global.window = global;\n"
        "global.location = { search: '?test=1' };\n"
        "global.console = console;\n"
        "global.document = {\n"
        "  createElement: function(tag) {\n"
        "    var el = { _tag: tag, _attrs: {}, _children: [], _parent: null,\n"
        "      setAttribute: function(k,v){this._attrs[k]=v;},\n"
        "      getAttribute: function(k){return this._attrs[k]||null;},\n"
        "      appendChild: function(c){c._parent=this;this._children.push(c);return c;},\n"
        "      closest: function(sel){\n"
        "        var m = sel.match(/^\\[([^=]+)(=\".*\")?\\]$/);\n"
        "        var key = m && m[1];\n"
        "        for (var n=this; n; n=n._parent) {\n"
        "          if (n._attrs && n._attrs[key]!==undefined) return n;\n"
        "        }\n"
        "        return null;\n"
        "      }\n"
        "    };\n"
        "    return el;\n"
        "  }\n"
        "};\n"
        f"var src = require('fs').readFileSync('{_STATIC / 'tokens.js'}', 'utf8');\n"
        "eval(src);\n"
        "var r = global.__EDIT_TOKENS_TEST_RESULT__ || {pass:0,fail:1};\n"
        "if (r.fail > 0) { process.exit(2); }\n"
        "console.log('tokens.js: ' + r.pass + ' passed');\n"
    )
    result = subprocess.run(["node", "-e", shim], capture_output=True, text=True)
    assert result.returncode == 0, (
        f"tokens.js self-tests failed.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_cost_estimate_self_tests_pass():
    shim = (
        "global.window = global;\n"
        "global.location = { search: '?test=1' };\n"
        "global.console = console;\n"
        "global.document = { createElement: function(){ return {\n"
        "  setAttribute:function(){},\n"
        "  appendChild:function(c){return c;},\n"
        "  closest:function(){return null;}\n"
        "}; } };\n"
        f"var t = require('fs').readFileSync('{_STATIC / 'tokens.js'}', 'utf8');\n"
        "eval(t);\n"
        f"var c = require('fs').readFileSync('{_STATIC / 'cost_estimate.js'}', 'utf8');\n"
        "eval(c);\n"
        "var r = global.__EDIT_COST_TEST_RESULT__ || {pass:0,fail:1};\n"
        "if (r.fail > 0) { process.exit(2); }\n"
        "console.log('cost_estimate.js: ' + r.pass + ' passed');\n"
    )
    result = subprocess.run(["node", "-e", shim], capture_output=True, text=True)
    assert result.returncode == 0, (
        f"cost_estimate.js self-tests failed.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
