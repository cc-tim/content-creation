// EditCostEstimate: heuristic cost and wide-rebuild estimate for edit jobs.
(function () {
  'use strict';

  var COST_PER_TOKEN_USD = {
    visual: 0.04,
    subtitle: 0,
    overlay: 0,
    narration: 0,
    transition: 0,
    manifest: 0.04,
    sceneOnly: 0.04,
  };
  var WIDE_REBUILD_THRESHOLD = 0.5;

  function estimateJobCost(rawTokens, totalScenes) {
    if (!window.EditTokens) {
      throw new Error('EditTokens not loaded; load tokens.js before cost_estimate.js');
    }
    var usd = 0;
    var sceneSet = {};
    for (var i = 0; i < rawTokens.length; i++) {
      var t = window.EditTokens.parseToken(rawTokens[i]);
      if (!t) continue;
      if (t.kind === 'manifest') {
        usd += COST_PER_TOKEN_USD.manifest;
        continue;
      }
      sceneSet[t.scene] = true;
      var key = t.element || 'sceneOnly';
      if (typeof COST_PER_TOKEN_USD[key] === 'number') {
        usd += COST_PER_TOKEN_USD[key];
      }
    }
    var scenesTouched = 0;
    for (var k in sceneSet) if (Object.prototype.hasOwnProperty.call(sceneSet, k)) scenesTouched++;
    var wideRebuild = totalScenes > 0 && scenesTouched / totalScenes > WIDE_REBUILD_THRESHOLD;
    return {
      usd: Math.round(usd * 1000) / 1000,
      wideRebuild: wideRebuild,
      scenesTouched: scenesTouched,
      needsConfirm: usd > 0 || wideRebuild,
    };
  }

  function formatSummaryLine(rawTokens, totalScenes) {
    var est = estimateJobCost(rawTokens, totalScenes);
    var n = rawTokens.length;
    return n + ' token' + (n === 1 ? '' : 's')
      + ' · ' + est.scenesTouched + ' scene' + (est.scenesTouched === 1 ? '' : 's')
      + ' · est. $' + est.usd.toFixed(3);
  }

  window.EditCostEstimate = {
    COST_PER_TOKEN_USD: COST_PER_TOKEN_USD,
    WIDE_REBUILD_THRESHOLD: WIDE_REBUILD_THRESHOLD,
    estimateJobCost: estimateJobCost,
    formatSummaryLine: formatSummaryLine,
  };

  function runSelfTests() {
    var pass = 0;
    var fail = 0;
    function eq(actual, expected, msg) {
      var ok = JSON.stringify(actual) === JSON.stringify(expected);
      if (ok) pass++;
      else {
        fail++;
        console.error('FAIL ' + msg + ' got ' + JSON.stringify(actual) + ', expected ' + JSON.stringify(expected));
      }
    }
    eq(estimateJobCost(['@s1/subtitle'], 10), { usd: 0, wideRebuild: false, scenesTouched: 1, needsConfirm: false }, 'subtitle free');
    eq(estimateJobCost(['@s1/visual'], 10), { usd: 0.04, wideRebuild: false, scenesTouched: 1, needsConfirm: true }, 'visual costs');
    eq(estimateJobCost(['@s1', '@s2', '@s3', '@s4', '@s5', '@s6'], 10), { usd: 0.24, wideRebuild: true, scenesTouched: 6, needsConfirm: true }, 'wide scene edits');
    eq(estimateJobCost(['@s1/subtitle', '@s2/subtitle'], 10), { usd: 0, wideRebuild: false, scenesTouched: 2, needsConfirm: false }, 'two subtitles');
    eq(estimateJobCost(['@s1/subtitle', '@s2/subtitle', '@s3/subtitle', '@s4/subtitle', '@s5/subtitle', '@s6/subtitle'], 10), { usd: 0, wideRebuild: true, scenesTouched: 6, needsConfirm: true }, 'wide free confirms');
    eq(estimateJobCost(['@manifest:verbatim_3'], 10), { usd: 0.04, wideRebuild: false, scenesTouched: 0, needsConfirm: true }, 'manifest costs');
    eq(estimateJobCost([], 10), { usd: 0, wideRebuild: false, scenesTouched: 0, needsConfirm: false }, 'empty');
    eq(formatSummaryLine(['@s1/visual', '@s2/subtitle'], 10), '2 tokens · 2 scenes · est. $0.040', 'summary plural');
    eq(formatSummaryLine(['@s1'], 10), '1 token · 1 scene · est. $0.040', 'summary singular');

    var summary = 'EditCostEstimate self-tests: ' + pass + ' passed, ' + fail + ' failed';
    if (fail) console.error(summary);
    else console.log(summary);
    window.__EDIT_COST_TEST_RESULT__ = { pass: pass, fail: fail };
  }

  if (typeof location !== 'undefined' && location.search.indexOf('test=1') >= 0) {
    runSelfTests();
  } else if (typeof window !== 'undefined' && window.__EDIT_COST_TEST__) {
    runSelfTests();
  }
})();
