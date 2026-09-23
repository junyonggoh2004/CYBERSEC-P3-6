// Node unit tests of browser event/state logic with an isolated DOM/API double.
// No browser automation or external server is used here.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const { webcrypto } = require('node:crypto');

class Element {
  constructor() { this.hidden = false; this.disabled = false; this.value = '65536'; this.files = []; this.dataset = { pngOutput: 'true' }; this.children = []; this.events = {}; this.textContent = ''; }
  addEventListener(name, fn) { this.events[name] = fn; }
  appendChild(child) { this.children.push(child); }
  replaceChildren() { this.children = []; }
  reportValidity() { return true; }
  scrollIntoView() {}
  click() {}
  remove() {}
}
async function harness({ score = 2.36e-215, mismatch = false, fail = false } = {}) {
  const bytes = new Uint8Array([137, 80, 78, 71, 1, 2, 3]);
  const file = new File([bytes], 'actual-stego.png', { type: 'image/png' });
  const hash = Buffer.from(await webcrypto.subtle.digest('SHA-256', bytes)).toString('hex');
  const elements = new Map();
  const el = (id) => { if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id); };
  const requests = [];
  let exported;
  const context = { document: { getElementById: el, createElement: () => new Element(), body: new Element() }, window: {},
    crypto: webcrypto, FormData, Blob, File, Uint8Array, Date,
    URL: { createObjectURL(blob) { exported = blob; return 'blob:test'; }, revokeObjectURL() {} },
    setTimeout(fn) { fn(); },
    async fetch(url, options) {
      if (options) {
        requests.push(options.body);
        return { ok: !fail, json: async () => fail ? { error: 'Unreadable PNG' } : { job_id: 'job' } };
      }
      const window = Number(requests.at(-1).get('window_size'));
      const count = window === 65536 ? 1 : 2;
      const groups = { regular: 10, singular: 9, unusable: 3 };
      return { ok: true, json: async () => ({ status: 'done', result: {
        file_sha256: mismatch ? 'wrong-hash' : hash, image: { width: 64, height: 64, mode: 'RGB' },
        scores: { chi_square: score, rs: 0 }, combined: { category: 'Low indication', thresholds: { chi_square: .95, rs: .05 } },
        configuration: { requested_window_size: window }, limitations: ['Not proof of absence.'],
        channels: { R: { chi_square: { statistic: 1500, degrees_of_freedom: 127, score }, rs: { positive: groups, negative: groups, score: 0 },
          effective_window_size: window, windows: Array.from({ length: count }, (_, i) => ({ start: i * window, stop: (i + 1) * window, sample_count: window, statistic: 12, degrees_of_freedom: 10, score: i ? null : score })) } },
      } }) };
    },
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../frontend/analysis.js'), 'utf8'), context);
  return { context, el, file, bytes, requests, exportBlob: () => exported };
}
const info = { num_lsb: 1, start_unit: 24, container_bytes: 400, capacity_bytes: 1000, passphrase: 'must-not-export' };

test('exact encoder bytes, scientific score, context allowlist and JSON export', async () => {
  const h = await harness();
  await h.context.window.StegoAnalysis.analyseEncoded(h.file, info);
  assert.deepEqual(new Uint8Array(await h.requests[0].get('image_file').arrayBuffer()), h.bytes);
  assert.match(h.el('analysis-scores').textContent, /2\.3600e-215/);
  assert.match(h.el('analysis-encoding-details').textContent, /40\.00%/);
  assert.equal(h.el('analysis-result').hidden, false);
  await h.el('btn-export-analysis').events.click();
  const exported = JSON.parse(await h.exportBlob().text());
  assert.equal(exported.input.source, 'encoder_output');
  assert.equal(exported.input.encoding_context.passphrase, undefined);
  assert.equal(exported.input.sha256_matches_selected_file, true);
});
test('window rerun preserves input and changes table, manual upload drops encoder context', async () => {
  const h = await harness();
  await h.context.window.StegoAnalysis.analyseEncoded(h.file, info);
  const overall = h.el('analysis-scores').textContent;
  h.el('analysis-window').value = '1024';
  h.el('analysis-window').events.input();
  assert.equal(h.el('btn-export-analysis').disabled, true);
  await h.el('btn-analyse').events.click();
  assert.equal(h.el('analysis-window-rows').children.length, 2);
  assert.equal(h.el('analysis-scores').textContent, overall);
  h.el('analysis-file').files = [h.file];
  h.el('analysis-file').events.change();
  await h.el('btn-analyse').events.click();
  assert.equal(h.el('analysis-encoding').hidden, true);
  assert.match(h.el('analysis-source').textContent, /Manual upload/);
});
test('floating point zero is distinguished from a measured absence', async () => {
  const h = await harness({ score: 0 });
  await h.context.window.StegoAnalysis.analyseEncoded(h.file, info);
  assert.match(h.el('analysis-scores').textContent, /below numerical precision/);
  assert.match(h.el('analysis-interpretation').textContent, /Hidden data may still be present/);
});
test('mismatched bytes cannot display or export a report', async () => {
  const h = await harness({ mismatch: true });
  await h.context.window.StegoAnalysis.analyseEncoded(h.file, info);
  assert.equal(h.el('analysis-result').hidden, true);
  assert.equal(h.el('btn-export-analysis').disabled, true);
  assert.match(h.el('analysis-status').textContent, /hash did not match/);
  assert.equal(h.context.window.StegoAnalysis.isBusy(), false);
});
test('API errors reenable controls without a stale report', async () => {
  const h = await harness({ fail: true });
  await h.context.window.StegoAnalysis.analyseEncoded(h.file, info);
  assert.equal(h.el('analysis-result').hidden, true);
  assert.equal(h.el('btn-analyse').disabled, false);
  assert.match(h.el('analysis-status').textContent, /Unreadable PNG/);
});
