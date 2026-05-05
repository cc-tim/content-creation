// EditTokens: pure-logic token grammar for edit-mode composer.
(function () {
  'use strict';

  var SCENE_ELEMENTS = ['visual', 'subtitle', 'overlay', 'narration', 'transition'];
  var SCENE_RE = new RegExp('^@s(\\d+)(?:\\/(' + SCENE_ELEMENTS.join('|') + '))?$');
  var MANIFEST_RE = /^@manifest:([A-Za-z0-9_-]+)$/;

  function parseToken(raw) {
    if (typeof raw !== 'string') return null;
    var s = raw.trim();
    if (!s) return null;
    var m = s.match(SCENE_RE);
    if (m) {
      return { kind: 'scene', scene: 's' + m[1], element: m[2] || null, raw: s };
    }
    m = s.match(MANIFEST_RE);
    if (m) return { kind: 'manifest', item: m[1], raw: s };
    return null;
  }

  function parseTokenList(text) {
    if (!text) return [];
    var parts = String(text).split(/\s+/);
    var out = [];
    for (var i = 0; i < parts.length; i++) {
      if (!parts[i]) continue;
      var parsed = parseToken(parts[i]);
      if (parsed) out.push(parsed);
    }
    return out;
  }

  function mintTokenFromElement(el) {
    if (!el || !el.closest) return null;
    var match = el.closest('[data-edit-token]');
    return match ? match.getAttribute('data-edit-token') : null;
  }

  function tokenLabel(raw) {
    var t = parseToken(raw);
    if (!t) return raw;
    if (t.kind === 'manifest') return 'Manifest: ' + t.item;
    var sceneNum = t.scene.replace(/^s/, '');
    var elemLabels = {
      visual: 'image',
      subtitle: 'subtitle',
      overlay: 'overlay text',
      narration: 'narration',
      transition: 'transition out',
    };
    if (!t.element) return 'Scene ' + sceneNum;
    return 'Scene ' + sceneNum + ' ' + (elemLabels[t.element] || t.element);
  }

  function dedupeTokens(rawList) {
    var seen = {};
    var out = [];
    for (var i = 0; i < rawList.length; i++) {
      if (seen[rawList[i]]) continue;
      seen[rawList[i]] = true;
      out.push(rawList[i]);
    }
    return out;
  }

  function sceneIdsTouched(rawList) {
    var seen = {};
    var out = [];
    for (var i = 0; i < rawList.length; i++) {
      var t = parseToken(rawList[i]);
      if (t && t.kind === 'scene' && !seen[t.scene]) {
        seen[t.scene] = true;
        out.push(t.scene);
      }
    }
    return out;
  }

  window.EditTokens = {
    SCENE_ELEMENTS: SCENE_ELEMENTS.slice(),
    parseToken: parseToken,
    parseTokenList: parseTokenList,
    mintTokenFromElement: mintTokenFromElement,
    tokenLabel: tokenLabel,
    dedupeTokens: dedupeTokens,
    sceneIdsTouched: sceneIdsTouched,
  };

  function runSelfTests() {
    var pass = 0;
    var fail = 0;
    function eq(actual, expected, msg) {
      var ok = JSON.stringify(actual) === JSON.stringify(expected);
      if (ok) pass++;
      else {
        fail++;
        console.error('FAIL ' + msg + ' expected ' + JSON.stringify(expected) + ', got ' + JSON.stringify(actual));
      }
    }
    eq(parseToken('@s9'), { kind: 'scene', scene: 's9', element: null, raw: '@s9' }, 'parse scene');
    eq(parseToken('@s12/visual'), { kind: 'scene', scene: 's12', element: 'visual', raw: '@s12/visual' }, 'parse visual');
    eq(parseToken('@s9/transition'), { kind: 'scene', scene: 's9', element: 'transition', raw: '@s9/transition' }, 'parse transition');
    eq(parseToken('@manifest:verbatim_3'), { kind: 'manifest', item: 'verbatim_3', raw: '@manifest:verbatim_3' }, 'parse manifest');
    eq(parseToken('@s9/bogus'), null, 'reject unknown element');
    eq(parseToken('garbage'), null, 'reject garbage');
    eq(parseToken(''), null, 'reject empty');
    eq(parseToken(null), null, 'reject null');
    eq(parseTokenList('  @s9   @s11/subtitle  ').map(function (t) { return t.raw; }), ['@s9', '@s11/subtitle'], 'parse list');
    eq(parseTokenList('@s9 garbage @manifest:foo').length, 2, 'drop invalid list entries');
    eq(tokenLabel('@s9'), 'Scene 9', 'label scene');
    eq(tokenLabel('@s12/visual'), 'Scene 12 image', 'label visual');
    eq(tokenLabel('@s5/subtitle'), 'Scene 5 subtitle', 'label subtitle');
    eq(tokenLabel('@s5/overlay'), 'Scene 5 overlay text', 'label overlay');
    eq(tokenLabel('@s5/narration'), 'Scene 5 narration', 'label narration');
    eq(tokenLabel('@s5/transition'), 'Scene 5 transition out', 'label transition');
    eq(tokenLabel('@manifest:foo'), 'Manifest: foo', 'label manifest');
    eq(tokenLabel('garbage'), 'garbage', 'label passthrough');
    eq(dedupeTokens(['@s9', '@s9', '@s11/subtitle']), ['@s9', '@s11/subtitle'], 'dedupe');
    eq(sceneIdsTouched(['@s9', '@s9/visual', '@s11/subtitle', '@manifest:x']), ['s9', 's11'], 'scene ids touched');
    var div = document.createElement('div');
    div.setAttribute('data-edit-token', '@s7/visual');
    var inner = document.createElement('span');
    div.appendChild(inner);
    eq(mintTokenFromElement(inner), '@s7/visual', 'mint walks up');
    eq(mintTokenFromElement(document.createElement('div')), null, 'mint none');

    var summary = 'EditTokens self-tests: ' + pass + ' passed, ' + fail + ' failed';
    if (fail) console.error(summary);
    else console.log(summary);
    window.__EDIT_TOKENS_TEST_RESULT__ = { pass: pass, fail: fail };
  }

  if (typeof location !== 'undefined' && location.search.indexOf('test=1') >= 0) {
    runSelfTests();
  } else if (typeof window !== 'undefined' && window.__EDIT_TOKENS_TEST__) {
    runSelfTests();
  }
})();
