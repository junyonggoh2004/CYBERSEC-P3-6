/* DOM integration test, not a visual browser test.
 * Requires jsdom (NODE_PATH or local install) and the local Flask server.
 * Browser file, canvas and download APIs are adapters; app event handlers and
 * HTTP endpoints run unchanged. Run python tests/make_ui_fixtures.py first.
 */
const { JSDOM, VirtualConsole } = require('jsdom');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const origin = process.env.STEGO_TEST_URL || 'http://127.0.0.1:5010';
const errors = [];
const vc = new VirtualConsole();
vc.on('jsdomError', error => errors.push(error.message));
const dom = new JSDOM(fs.readFileSync(path.join(root, 'frontend/index.html'), 'utf8'), {
  url: origin, runScripts: 'outside-only', pretendToBeVisual: true, virtualConsole: vc,
});
const w = dom.window, $ = id => w.document.getElementById(id);
const downloads = [];
w.URL.createObjectURL = () => 'blob:test';
w.URL.revokeObjectURL = () => {};
w.HTMLAnchorElement.prototype.click = function () { downloads.push(this.download); };
w.HTMLCanvasElement.prototype.getContext = () => ({beginPath(){},moveTo(){},lineTo(){},stroke(){},fillText(){},setLineDash(){}});
function readBlob(blob) {
  return new Promise((resolve,reject)=>{const r=new w.FileReader();r.onload=()=>resolve(r.result);r.onerror=reject;r.readAsArrayBuffer(blob);});
}
w.Blob.prototype.text = async function () { return Buffer.from(await readBlob(this)).toString('utf8'); };
w.Blob.prototype.arrayBuffer = async function () { return new Uint8Array(await readBlob(this)).slice().buffer; };
// jsdom has no SubtleCrypto; analysis checks the returned SHA-256 against the selected file.
const nodeSubtle = require('node:crypto').webcrypto.subtle;
Object.defineProperty(w.crypto, 'subtle', { configurable: true, value: { digest: (alg, data) => nodeSubtle.digest(alg, new Uint8Array(data)) } });
// File inputs in jsdom have no OS picker. This adapter reads the File list used
// by the test instead of creating an empty placeholder upload.
class BrowserFormData {
  constructor(form) {
    this.items=new Map();
    if(form) for(const el of form.elements) {
      if(!el.name || el.disabled)continue;
      if(el.type==='file') { if(el.files[0])this.set(el.name,el.files[0]); }
      else this.set(el.name,el.value);
    }
  }
  append(k,v){this.items.set(k,v);}
  set(k,v){this.items.set(k,v);}
  delete(k){this.items.delete(k);}
}
w.FormData=BrowserFormData;
w.fetch=async(url, options={})=>{
  if(options.body instanceof BrowserFormData) {
    const body=new FormData();
    for(const [key,value] of options.body.items) {
      if(value instanceof w.Blob)body.append(key,new Blob([await readBlob(value)],{type:value.type}),value.name||'upload');
      else body.append(key,String(value));
    }
    options={...options,body};
  }
  return fetch(new URL(url,origin),options);
};
function event(id, type='change') { $(id).dispatchEvent(new w.Event(type,{bubbles:true,cancelable:true})); }
function set(id,value) { $(id).value=value;event(id,'input');event(id); }
function file(id,name,type) {
  const input=$(id), content=fs.readFileSync(path.join(root,'test_evidence',name));
  Object.defineProperty(input,'files',{configurable:true,value:[new w.File([content],name,{type})]});event(id);
}
function click(id) { $(id).click(); }
function submit(id) { event(id,'submit'); }
async function wait(check,label) {
  const deadline=Date.now()+15000;
  while(Date.now()<deadline) { if(check())return;await new Promise(r=>setTimeout(r,35)); }
  throw new Error('Timed out: '+label+'; notice='+$('notice').textContent+'; status='+$('prepare-status').textContent);
}
async function verify(verdict) {
  submit('verify-form');await wait(()=>!$('verdict-card').hidden && !$('verify-button').disabled,'verify');
  assert.equal($('verdict-title').textContent,verdict);
}
(async()=>{
  const ids=[...w.document.querySelectorAll('[id]')].map(x=>x.id);
  assert.equal(ids.length,new Set(ids).size,'unique HTML IDs');
  w.eval(fs.readFileSync(path.join(root,'frontend/app.js'),'utf8'));
  await wait(()=>$('signing-key').options.length>0,'keys');
  assert.equal($('hash-algorithm').value,'SHA-256');
  assert.equal($('page-protect').hidden,false);
  file('cover-file','frontend-cover.png','image/png');
  set('payload-text','Hello Bob from the frontend integration test.');
  set('lsb','3');set('hash-algorithm','SHA-512');
  await wait(()=>!$('protect-button').disabled,'exact capacity');
  assert.match($('record-preview').textContent,/SHA-512/);
  assert.match($('embedding-details').textContent,/Field padding/);
  submit('protect-form');await wait(()=>!$('created').hidden && !$('protect-button').disabled,'encode');
  assert.match($('created-info').textContent,/SHA-512/);
  click('use-for-verify');click('use-public');
  await verify('Authentic');
  assert.equal($('check-list').children.length,6);
  assert.match($('verify-record').textContent,/recomputed_payload_hash/);
  click('download-report');assert.ok(downloads.includes('verification-report.json'));
  click('decoy-public');await wait(()=>$('notice').textContent.includes('Wrong public key'),'decoy');
  assert.equal($('verdict-card').hidden,true);
  await verify('Signature Invalid');
  click('use-public');click('tamper-content');
  await wait(()=>$('tamper-status').textContent.includes('Changed a content bit'),'tamper');
  await verify('Tampered');
  click('restore-stego');set('verify-offset','2000');await verify('Payload Missing');
  w.location.hash='compare';await wait(()=>!$('page-compare').hidden,'compare page');
  click('compare-button');await wait(()=>!$('comparison-results').hidden && !$('compare-button').disabled,'comparison');
  assert.equal($('histogram-charts').querySelectorAll('canvas').length,3);
  assert.equal($('waveforms').hidden,true);
  click('analyse-created');submit('analysis-form');
  await wait(()=>!$('analysis-export').disabled,'analysis');
  assert.match($('chi-results').textContent,/Summary tail score/);
  assert.match($('rs-results').textContent,/Estimated LSB-replacement fraction/);
  assert.match($('window-results').textContent,/Requested window size/);
  assert.match($('analysis-status').textContent,/file match verified/);
  assert.equal($('analysis-encoding').hidden,false,'encoder settings shown for encoder output');
  assert.match($('analysis-file-info').textContent,/Encoder output/);
  assert.equal($('page-analysis').querySelectorAll('canvas').length,0,'histograms belong to Compare');
  set('window-size','1024');assert.equal($('analysis-export').disabled,true,'invalidate stale analysis');
  // Audio cover with an image payload uses the same user journey.
  w.location.hash='protect';file('cover-file','frontend-cover.wav','audio/wav');
  set('payload-type','image');file('payload-file','frontend-payload.png','image/png');
  set('hash-algorithm','SHA-256');
  await wait(()=>!$('protect-button').disabled,'audio capacity');
  submit('protect-form');await wait(()=>$('created-info').textContent.includes('SHA-256') && !$('protect-button').disabled,'audio encode');
  click('use-for-verify');click('use-public');await verify('Authentic');
  assert.match($('verdict-metadata').textContent,/PCM sample/);
  w.location.hash='compare';click('compare-button');
  await wait(()=>!$('waveforms').hidden && !$('compare-button').disabled,'waveforms');
  assert.equal($('waveform-charts').querySelectorAll('canvas').length,3);
  assert.equal($('histograms').hidden,true);
  assert.deepEqual(errors,[]);
  console.log('PASS: Protect, SHA-512, exact capacity, Verify, wrong key, tampering, missing payload, Compare histograms, separate analysis, stale-state reset, WAV/image round trip and waveforms.');
  dom.window.close();
})().catch(error=>{console.error(error);dom.window.close();process.exitCode=1;});
