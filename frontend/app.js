"use strict";
const $ = id => document.getElementById(id);
const state = { keys: [], prepared: null, latest: null, received: null, pair: null, report: null, analysis: null, analysisFile: null, analysisContext: null, revision: 0, verifyRevision: 0, analysisRevision: 0, busy: false };
const urls = new Map();
const esc = value => String(value ?? "Unavailable").replace(/[&<>"']/g, c => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));
const pretty = value => JSON.stringify(value, null, 2);
const bytes = value => value < 1024 ? value + " B" : value < 1048576 ? (value / 1024).toFixed(1) + " KiB" : (value / 1048576).toFixed(1) + " MiB";
const kindOf = file => file && (/\.png$/i.test(file.name) ? "image" : /\.wav$/i.test(file.name) ? "audio" : null);
const fileLabel = file => file ? file.name + " · " + bytes(file.size) : "No file selected";
function notice(message, error = false) { $("notice").textContent = message; $("notice").classList.toggle("error", error); $("notice").hidden = !message; }
async function api(path, data) {
  const response = await fetch(path, data ? { method: "POST", body: data } : {});
  let result;
  try { result = await response.json(); } catch (_) { throw new Error("The server did not return a readable response."); }
  if (!response.ok || result.error) throw new Error(result.error || "Request failed (" + response.status + ").");
  return result;
}
function run(handler) { return async event => { try { await handler(event); } catch (error) { notice(error.message, true); } }; }
function table(headers, rows) { return '<table><thead><tr>' + headers.map(x => "<th>" + esc(x) + "</th>").join("") + "</tr></thead><tbody>" + rows.map(row => "<tr>" + row.map(x => "<td>" + esc(x) + "</td>").join("") + "</tr>").join("") + "</tbody></table>"; }
function detailsTable(rows) { return '<table class="detail-table"><tbody>' + rows.map(([key,value]) => "<tr><th>" + esc(key) + "</th><td>" + esc(value) + "</td></tr>").join("") + "</tbody></table>"; }
function metrics(id, items) { $(id).innerHTML = items.map(([name,value]) => '<div class="metric"><span>' + esc(name) + "</span><strong>" + esc(value) + "</strong></div>").join(""); }
function objectURL(id, blob) { if (urls.has(id)) URL.revokeObjectURL(urls.get(id)); const url = URL.createObjectURL(blob); urls.set(id,url); return url; }
function download(blob, filename) { const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = filename; a.click(); setTimeout(() => URL.revokeObjectURL(a.href),1000); }
function exportJSON(value, filename) { download(new Blob([pretty(value)],{type:"application/json"}),filename); }
function fromBase64(data, type, name) { const raw = atob(data); const buffer = Uint8Array.from(raw,c=>c.charCodeAt(0)); return new File([buffer],name,{type}); }
async function preview(id, file, text) {
  const el = $(id); el.replaceChildren();
  if (text !== undefined) { const p = document.createElement("div"); p.className="content-text"; p.textContent=text; el.append(p); return; }
  if (!file) { const p = document.createElement("p"); p.className="empty"; p.textContent="No object selected."; el.append(p); return; }
  const mime = file.type || "";
  if (/^image\/(png|jpeg|gif|webp)$/.test(mime) || /\.(png|jpe?g)$/i.test(file.name)) {
    const img = document.createElement("img"); img.alt = file.name; img.src = objectURL(id,file); el.append(img);
  } else if (mime.startsWith("audio/") || /\.(wav|mp3|ogg|flac|m4a)$/i.test(file.name)) {
    const audio = document.createElement("audio"); audio.controls=true; audio.preload="metadata"; audio.src=objectURL(id,file); el.append(audio);
  } else if (mime.startsWith("text/") && file.size < 100000) {
    const p = document.createElement("div"); p.className="content-text"; p.textContent=await file.text(); el.append(p);
  }
  const caption = document.createElement("p"); caption.textContent=fileLabel(file); el.append(caption);
}
function navigate() {
  const name = location.hash.slice(1) || "protect";
  const page = $( "page-" + name ) ? name : "protect";
  document.querySelectorAll(".page").forEach(el=>el.hidden=el.id!=="page-"+page);
  document.querySelectorAll("[data-page]").forEach(el=>{ if(el.dataset.page===page)el.setAttribute("aria-current","page"); else el.removeAttribute("aria-current"); });
  if(page==="compare") renderComparison();
}
document.querySelectorAll("[data-go]").forEach(el=>el.onclick=()=>location.hash=el.dataset.go);
window.addEventListener("hashchange",navigate);
navigate();
$("theme").onclick=()=>{
  const theme=document.documentElement.dataset.theme==="dark"?"light":"dark";
  document.documentElement.dataset.theme=theme;
  $("theme").textContent=theme==="dark"?"Light theme":"Dark theme";
  try { localStorage.setItem("stego-theme",theme); } catch (_) {}
  if(state.pair?.measurements) drawComparison(state.pair.measurements);
};
$("theme").textContent=document.documentElement.dataset.theme==="dark"?"Light theme":"Dark theme";

function selectedKey() { return state.keys.find(x=>x.key_id===$("signing-key").value); }
function renderKey() {
  const key=selectedKey(); if(!key)return;
  $("selected-public").value=key.public_key_pem;
  $("selected-fingerprint").textContent="SHA-256 public-key fingerprint: "+key.fingerprint;
  $("key-status").textContent="Alice · RSA "+key.bits+" · "+key.fingerprint.slice(0,12)+"…";
}
async function loadKeys(preferred) {
  const result=await api("/api/keys"); state.keys=result.keys;
  const selected=preferred || $("signing-key").value;
  $("signing-key").replaceChildren(...state.keys.map((key,i)=>new Option((i===0?"Saved demo pair":"Additional pair")+" · "+key.fingerprint.slice(0,12),key.key_id)));
  if(state.keys.some(key=>key.key_id===selected)) $("signing-key").value=selected;
  $("key-list").innerHTML=table(["Pair","RSA size","SHA-256 public fingerprint"],state.keys.map((key,i)=>[i===0?"Saved demo": "Additional",key.bits,key.fingerprint]));
  renderKey(); invalidate();
}
$("signing-key").addEventListener("change",renderKey);
$("generate-key").onclick=run(async()=>{
  $("generate-key").disabled=true;
  try { const key=await api("/api/keys/generate",new FormData()); await loadKeys(key.key_id); notice("Additional Alice key pair saved. Previous pairs remain available."); }
  finally { $("generate-key").disabled=false; }
});
$("export-public").onclick=()=>{const key=selectedKey(); if(key)download(new Blob([key.public_key_pem],{type:"text/plain"}),"alice-"+key.fingerprint.slice(0,12)+".pem");};
$("key-import-form").onsubmit=run(async e=>{
  e.preventDefault(); const data=new FormData(); data.append("key_file",$("private-file").files[0]); data.append("password",$("key-password").value);
  const key=await api("/api/keys/import",data); $("key-password").value=""; $("private-file").value=""; await loadKeys(key.key_id); notice("Signing pair imported and retained.");
});

function updateBits() {
  const depth=Number($("lsb").value);
  $("bits").innerHTML=Array.from("10110110",(bit,i)=>'<span class="bit '+(i>=8-depth?"selected":"")+'">'+bit+"</span>").join("");
  $("bit-explanation").textContent=depth+" lowest bit"+(depth===1?"":"s")+" replaced per value. Example: 100 available values × "+depth+" = "+(100*depth)+" bits. A 240-bit package "+(100*depth>=240?"fits.":"does not fit.");
  $("scope-note").textContent="Stable-cover hashing excludes these low bits. Start-location derivation uses SHA-256 regardless of the content-hash selection."+ (depth===8&&kindOf($("cover-file").files[0])!=="audio"?" At 8 LSBs, no image-channel value bits remain protected by the stable hash.":"");
}
function updateContent() {
  const cover=kindOf($("cover-file").files[0]) || "image";
  const old=$("payload-type").value;
  const other=cover==="image"?"audio":"image";
  $("payload-type").replaceChildren(new Option("Text message","text"),new Option(other==="audio"?"Audio file inside image":"Image file inside audio",other));
  if(old===other)$("payload-type").value=old;
  updatePayloadMode(); updateBits();
}
function updatePayloadMode() {
  const text=$("payload-type").value==="text";
  $("text-content").hidden=!text; $("file-content").hidden=text; $("payload-preview").hidden=text;
  $("payload-text").required=text; $("payload-file").required=!text;
  $("payload-file").accept=$("payload-type").value==="audio"?"audio/*":"image/png,image/jpeg,image/webp";
}
function updateStart(prefix="") {
  const mode=$(prefix?"verify-mode":"start-mode").value;
  $(prefix?"verify-offset-field":"offset-field").hidden=mode!=="manual";
  $(prefix?"verify-secret-field":"secret-field").hidden=mode!=="passphrase";
  if(!prefix) { $("secret").required=mode==="passphrase"; $("offset").required=mode==="manual"; }
}
$("cover-file").addEventListener("change",run(async()=>{
  const file=$("cover-file").files[0];
  if(file&&!kindOf(file))throw new Error("Choose a PNG image or WAV audio cover.");
  updateContent(); await preview("cover-preview",file);
}));
$("payload-type").addEventListener("change",updatePayloadMode);
$("payload-file").addEventListener("change",()=>preview("payload-preview",$("payload-file").files[0]));
$("lsb").addEventListener("change",updateBits);
$("start-mode").addEventListener("change",()=>updateStart());
$("verify-mode").addEventListener("change",()=>updateStart("verify"));
$("short-text").onclick=()=>{ $("payload-text").value="Explain how steganography can be used to embed hidden verification data in image and audio cover objects."; invalidate(); };
$("long-text").onclick=()=>{ $("payload-text").value="This undergraduate project requires student teams to design, implement and demonstrate a GUI-based LSB Replacement steganography program (window-based or web-based) that protects and verifies both image and audio cover objects using steganography, hashing and digital signatures. The project focuses on practical cybersecurity concepts: hiding a verification payload inside an image and an audio file, signing relevant verification data, extracting the hidden payload, checking the digital signature, and demonstrating positive and negative verification cases. Video as a cover object is not required for the main assignment, but may be attempted as an optional challenge."; invalidate(); };
function protectData() {
  const form=new FormData($("protect-form"));
  const kind=kindOf($("cover-file").files[0]);
  if(!kind) throw new Error("Choose a PNG or WAV cover.");
  form.set("cover_type",kind);
  if($("start-mode").value==="manual") form.delete("passphrase");
  else form.delete("manual_offset");
  return form;
}
function ready() { return $("cover-file").files[0] && selectedKey() && ($("payload-type").value==="text"?$("payload-text").value:$("payload-file").files[0]) && ($("start-mode").value!=="passphrase"||$("secret").value); }
let reviewTimer;
function invalidate() {
  state.revision++; state.prepared=null; $("protect-button").disabled=true;
  $("record-preview").textContent="Settings changed. Review again to create a current draft.";
  $("capacity-metrics").replaceChildren(); $("capacity-bar").value=0; $("embedding-details").textContent="No current measurements.";
  $("prepare-status").textContent=ready()?"Calculating capacity…":"Choose a cover and content to calculate the complete package size.";
  clearTimeout(reviewTimer);
  if(ready())reviewTimer=setTimeout(()=>prepare().catch(error=>{$("prepare-status").textContent=error.message;}),500);
}
$("protect-form").addEventListener("input",invalidate);
$("protect-form").addEventListener("change",invalidate);
async function prepare() {
  clearTimeout(reviewTimer);
  const revision=state.revision;
  const result=await api("/api/prepare",protectData());
  if(revision!==state.revision)return;
  state.prepared=result;
  $("protect-button").disabled=!result.fits||state.busy;
  $("prepare-status").textContent=result.fits?"The complete signed package fits. Your LSB selection will be used unchanged.":"The complete package does not fit. Increase depth, reduce content, change cover or adjust the start location.";
  metrics("capacity-metrics",[["Content",bytes(result.content_size_bytes)],["Complete package",bytes(result.container_size_bytes)],["Available",bytes(result.capacity_bytes)],["Space used",result.utilisation_percent+"%"],["Minimum sufficient depth",result.minimum_sufficient_depth ?? "Does not fit at 1–8"]]);
  $("capacity-bar").value=Math.min(100,result.utilisation_percent);
  $("cover-properties").textContent=Object.entries(result.cover_info).map(([k,v])=>k.replaceAll("_"," ")+": "+v).join(" · ");
  $("record-preview").textContent=pretty({record:result.metadata,payload_hash:result.payload_hash_hex,signature:result.signature_hex});
  $("embedding-details").innerHTML=detailsTable([["Start index",result.start_index],["Carrier unit",kindOf($("cover-file").files[0])==="image"?"Image channel value (row-major)":"PCM sample (interleaved)"],["Metadata/signature/header overhead",bytes(result.overhead_bytes)],["Field padding",result.padding_bits+" bits"],["Location security","An offset can be searched. A passphrase derives an offset; it does not encrypt the content."]])+table(["LSBs","Start","Available bytes","Required units","Fit"],result.choices.map(c=>[c.num_lsb,c.start_index,c.capacity_bytes,c.required_units,c.fits?"Yes":"No"]));
}
$("review").onclick=run(prepare);
$("protect-form").onsubmit=run(async e=>{
  e.preventDefault(); if(!state.prepared?.fits)throw new Error("Review capacity before creating the stego file.");
  const data=protectData(), cover=$("cover-file").files[0], content=$("payload-type").value==="text"?new File([$("payload-text").value],"message.txt",{type:"text/plain"}):$("payload-file").files[0];
  const settings={num_lsb:$("lsb").value,start_mode:$("start-mode").value,manual_offset:$("offset").value,passphrase:$("secret").value,cover_type:kindOf(cover)};
  state.busy=true; $("protect-button").disabled=true; $("prepare-status").textContent="Hashing, signing and embedding…";
  try {
    const result=await api("/api/encode",data);
    const file=fromBase64(result.stego_base64,result.mime,result.stego_filename);
    state.latest={file,cover,content,result,settings};
    $("created").hidden=false; await preview("stego-preview",file);
    $("created-info").textContent=bytes(result.container_size_bytes)+" signed package · "+result.num_lsb+" LSBs · "+result.metadata.hash_algorithm+" · Start "+result.start_index;
    $("final-record").textContent=pretty({record:result.metadata,payload_hash:result.payload_hash_hex,signature:result.signature_hex});
    $("analyse-created").disabled=settings.cover_type!=="image";
    $("prepare-status").textContent="Stego file created. Review or download the output below.";
    notice("Created the stego object. Alice's private key was used for signing only.");
    setLatestPair();
  } finally { state.busy=false; $("protect-button").disabled=!state.prepared?.fits; }
});
$("download-stego").onclick=()=>{if(state.latest)download(state.latest.file,state.latest.file.name);};
function useForVerify(file) {
  if(!state.latest)throw new Error("Protect a file first.");
  state.received=file||state.latest.file; $("received-file").required=false;
  $("received-file").value=""; const settings=state.latest.settings;
  $("verify-lsb").value=settings.num_lsb; $("verify-mode").value=settings.start_mode;
  $("verify-offset").value=settings.manual_offset; $("verify-secret").value=settings.passphrase;
  updateStart("verify"); preview("received-preview",state.received); invalidateVerification();
  location.hash="verify";
  notice("Local demo file loaded. Select Alice's trusted public key, then verify.");
}
function invalidateVerification() { state.verifyRevision++; $("verdict-card").hidden=true; state.report=null; $("verify-status").textContent="Inputs changed. Run verification for a current result."; }
$("verify-form").addEventListener("input",invalidateVerification);
$("verify-form").addEventListener("change",invalidateVerification);
$("use-for-verify").onclick=run(()=>useForVerify());
$("restore-stego").onclick=run(()=>{useForVerify(); $("tamper-status").textContent="Restored the original stego output.";});
$("received-file").addEventListener("change",()=>{state.received=$("received-file").files[0]; preview("received-preview",state.received); $("verdict-card").hidden=true;});
$("use-public").onclick=()=>{const key=selectedKey();if(key){$("verify-public").value=key.public_key_pem;invalidateVerification();notice("Selected demo public key loaded: "+key.fingerprint.slice(0,16)+"…");}};
$("public-file").onchange=run(async()=>{if($("public-file").files[0]){$("verify-public").value=await $("public-file").files[0].text();invalidateVerification();}});
$("decoy-public").onclick=run(async()=>{$("verify-public").value=(await api("/api/keys/decoy",new FormData())).public_key_pem;invalidateVerification();notice("Wrong public key loaded for a negative verification case.");});
function renderVerdict(result) {
  state.report=result; const ev=result.evidence;
  $("verdict-card").hidden=false; $("verdict-title").textContent=result.verdict;
  $("verdict-title").className=result.verdict==="Authentic"?"passed":"failed";
  $("reason-code").textContent=ev.reason_code; $("verdict-explanation").textContent=result.detail;
  $("check-list").innerHTML=Object.entries(ev.checks).map(([name,status])=>'<div class="check"><span>'+esc(name.replaceAll("_"," "))+'</span><strong class="'+(status==="Passed"?"passed":status==="Failed"?"failed":"")+'">'+esc(status)+"</strong></div>").join("");
  const meta=result.metadata||{};
  $("verdict-metadata").innerHTML=detailsTable([["File",ev.filename||state.received?.name],["Media type / file size",ev.cover_type+" / "+bytes(ev.file_size_bytes)],["Verification time",ev.verified_at],["Elapsed",ev.elapsed_ms+" ms"],["LSB depth / start method",ev.num_lsb+" / "+ev.start_mode],["Start index",ev.start_index],["Carrier unit / traversal",ev.carrier_unit+" / "+ev.traversal],["Media ID",meta.media_id],["Record timestamp",meta.timestamp],["Nonce",meta.nonce],["Content type / size",meta.mime?meta.mime+" / "+(meta.content_size_bytes??"Unavailable")+" bytes":null],["Hash algorithm",ev.hash_algorithm],["Signature algorithm",ev.signature_algorithm],["Supplied key fingerprint",ev.key_fingerprint],["Record trust",ev.record_trust]]);
  $("verdict-scope").textContent=ev.scope; $("verdict-next").textContent=ev.next_step;
  $("record-trust").textContent="Record: "+ev.record_trust+". Hash equality alone does not authenticate an unverified reference.";
  $("verify-record").textContent=pretty({record:result.metadata,expected_payload_hash:ev.expected_payload_hash,recomputed_payload_hash:ev.actual_payload_hash,expected_cover_hash:ev.expected_cover_hash,recomputed_cover_hash:ev.actual_cover_hash,signature:ev.signature_hex});
  $("download-content").disabled=!result.data_base64;
  if(result.data_base64) {
    state.recovered=fromBase64(result.data_base64,result.data_mime||"application/octet-stream",result.data_filename||"recovered-message.txt");
    preview("recovered-preview",state.recovered);
  } else {state.recovered=null; $("recovered-preview").textContent="Recovered content unavailable: extraction or verification could not complete.";}
}
$("verify-form").onsubmit=run(async e=>{
  e.preventDefault(); if(!state.received)throw new Error("Choose a received PNG or WAV file.");
  const kind=kindOf(state.received); if(!kind)throw new Error("Choose a PNG or WAV.");
  const data=new FormData(); data.append("stego_file",state.received); data.append("cover_type",kind);
  data.append("num_lsb",$("verify-lsb").value); data.append("start_mode",$("verify-mode").value);
  data.append("manual_offset",$("verify-offset").value); data.append("passphrase",$("verify-secret").value);
  data.append("public_key_pem",$("verify-public").value);
  const revision=state.verifyRevision;
  $("verify-button").disabled=true; $("verdict-card").hidden=true;
  $("verify-status").textContent="Extracting the package, checking the signature and comparing hashes…";
  try { const result=await api("/api/decode",data); if(revision!==state.verifyRevision)return; renderVerdict(result); $("verify-status").textContent="Verification completed. See the evidence for each check below."; }
  catch(error){$("verify-status").textContent="Verification request failed: "+error.message;throw error;}
  finally{$("verify-button").disabled=false;}
});
$("download-content").onclick=()=>{if(state.recovered)download(state.recovered,state.recovered.name);};
$("download-report").onclick=()=>{if(state.report){const {data_base64,...report}=state.report;exportJSON(report,"verification-report.json");}};
async function tamper(mode) {
  if(!state.latest)throw new Error("Protect a file first.");
  const data=new FormData(); data.append("stego_file",state.latest.file);
  Object.entries(state.latest.settings).forEach(([key,value])=>data.append(key,value));
  data.append("tamper_mode",mode);
  const result=await api("/api/demo/tamper",data);
  useForVerify(fromBase64(result.stego_base64,state.latest.file.type,"modified-"+state.latest.file.name));
  $("tamper-status").textContent=result.detail;
}
$("tamper-content").onclick=run(()=>tamper("payload"));
$("tamper-cover").onclick=run(()=>tamper("cover"));

function setLatestPair() {
  if(!state.latest)return;
  state.pair={before:state.latest.cover,after:state.latest.file,content:state.latest.content,measurements:null};
}
async function renderComparison() {
  if(!state.pair)return;
  await Promise.all([preview("compare-before",state.pair.before),preview("compare-after",state.pair.after),preview("compare-payload",state.pair.content)]);
  if(!state.pair.content)$("compare-payload").textContent="Hidden content is unknown for an independently uploaded pair. Extract it on Verify.";
  $("comparison-results").hidden=!state.pair.measurements;
  if(state.pair.measurements)drawComparison(state.pair.measurements);
}
$("compare-latest").onclick=run(async()=>{if(!state.latest)throw new Error("Protect a file first.");setLatestPair();$("compare-original").value="";$("compare-stego").value="";await renderComparison();await compare();});
$("compare-original").onchange=()=>{state.pair={before:$("compare-original").files[0],after:$("compare-stego").files[0],content:null};renderComparison();};
$("compare-stego").onchange=$("compare-original").onchange;
async function compare() {
  if(!state.pair?.before||!state.pair?.after)throw new Error("Choose both the original and stego object, or load the last protected pair.");
  const pair=state.pair, kind=kindOf(pair.before);
  if(!kind||kind!==kindOf(pair.after))throw new Error("Both objects must be PNGs, or both WAVs.");
  const data=new FormData();data.append("cover_type",kind);data.append("original_file",pair.before);data.append("stego_file",pair.after);
  $("compare-button").disabled=true; $("compare-status").textContent="Measuring changes…";
  try {pair.measurements=await api("/api/compare",data);if(state.pair!==pair)return;await renderComparison();$("compare-status").textContent=fileLabel(pair.before)+" → "+fileLabel(pair.after);}
  catch(error){$("compare-status").textContent=error.message;throw error;}
  finally{$("compare-button").disabled=false;}
}
$("compare-button").onclick=run(compare);
$("compare-zoom").oninput=()=>document.querySelectorAll("#compare-before img,#compare-after img").forEach(img=>img.style.transform="scale("+$("compare-zoom").value+")");
function chart(parent,title,series,labels,maxY=null,minY=0) {
  const container=document.createElement("div");container.className="chart-container";
  const heading=document.createElement("p");heading.textContent=title;container.append(heading);
  const canvas=document.createElement("canvas");canvas.width=760;canvas.height=260;canvas.setAttribute("role","img");canvas.setAttribute("aria-label",title+". "+labels);container.append(canvas);parent.append(container);
  const c=canvas.getContext("2d"), left=65, top=24, width=670, height=190;
  const ink=getComputedStyle(document.documentElement).getPropertyValue("--text-dim").trim();
  c.font="16px Segoe UI";c.fillStyle=ink;c.strokeStyle=ink;c.lineWidth=1;
  const values=series.flatMap(s=>s.values), max=maxY??Math.max(1,...values), span=max-minY||1;
  c.beginPath();c.moveTo(left,top);c.lineTo(left,top+height);c.lineTo(left+width,top+height);c.stroke();
  c.fillText(max.toFixed(max>10?0:2),4,top+8);c.fillText(String(minY),8,top+height);c.fillText(labels,left,250);
  for(const [index,s] of series.entries()) {
    c.strokeStyle=s.color||["#365ccc","#d46a12"][index%2];c.lineWidth=2;c.setLineDash(index%2?[8,5]:[]);
    c.beginPath();s.values.forEach((v,i)=>{const x=left+i/(s.values.length-1||1)*width,y=top+height-(v-minY)/span*height;if(i)c.lineTo(x,y);else c.moveTo(x,y);});c.stroke();
  }
}
function drawComparison(result) {
  $("comparison-results").hidden=false;
  metrics("comparison-metrics",[["Changed values",result.changed_percent+"%"],["Max difference",result.max_absolute_difference],["Mean squared error",result.mse.toPrecision(4)],["PSNR",result.psnr_db===null?"Identical":result.psnr_db.toFixed(2)+" dB"]].concat(result.audio_metrics?[["SNR",result.audio_metrics.snr_display]]:[]));
  $("histograms").hidden=!result.histograms; $("waveforms").hidden=!result.waveforms;
  $("difference-panel").hidden=!result.histograms; $("zoom-field").hidden=!result.histograms;
  $("histogram-charts").replaceChildren();$("waveform-charts").replaceChildren();
  if(result.histograms) {
    Object.entries(result.histograms).forEach(([name,h])=>chart($("histogram-charts"),name+" channel",[{values:h.before},{values:h.after}],"Intensity 0 → 255 · y = value count"));
    state.differenceViews={
      difference:{image:result.difference_png_base64,caption:"Absolute RGB differences amplified "+result.difference_gain.toFixed(1)+"× for visibility; this is not the actual stego appearance."},
      mask:{image:result.change_mask_png_base64,caption:"White marks a pixel whose R/G/B value differs between the two objects; black is unchanged. A carrier value that already matched the bit being written stays unchanged and will not be marked here."},
      highlighted:{image:result.highlighted_difference_png_base64,caption:"Same amplified difference, blended onto the cover in magenta so changed areas can be located in context."+(result.alpha_note?" "+result.alpha_note:"")},
    };
    renderDifferenceView();
  }
  if(result.waveforms) {
    for(const [key,label] of [["before","Original"],["after","Stego"],["difference","Sample difference"]]) {
      const values=result.waveforms[key].flat();
      chart($("waveform-charts"),label,[{values}], "Time 0 → "+result.cover_info.duration_seconds+" seconds · channel 1",1,-1);
    }
    $("channel-metrics").innerHTML=table(["Channel","Changed samples","Total samples","Max difference","RMS difference"],
      result.per_channel.map(c=>[c.channel,c.changed_samples,c.total_samples,c.max_absolute_difference,c.rms_difference.toPrecision(4)]));
  }
  const {difference_png_base64,change_mask_png_base64,highlighted_difference_png_base64,...readable}=result;$("comparison-data").textContent=pretty(readable);
}
function renderDifferenceView() {
  const view=state.differenceViews?.[$("difference-view").value]; if(!view)return;
  $("difference-view-image").src="data:image/png;base64,"+view.image; $("difference-view-caption").textContent=view.caption;
}
$("difference-view").onchange=renderDifferenceView;

$("analysis-file").onchange=()=>{state.analysisFile=$("analysis-file").files[0];state.analysisContext=null;preview("analysis-preview",state.analysisFile);clearAnalysis();};
// Encoding context describes the file; it never feeds the blind classifier.
function analysisSource() {
  const file=state.analysisFile;
  $("analysis-encoding").hidden=true;
  if(!file){$("analysis-file-info").innerHTML='<p class="empty">Select a PNG, or use “Analyse stego PNG” after protecting a file.</p>';return;}
  $("analysis-file-info").innerHTML=detailsTable([["Source",state.analysisContext?"Encoder output":"Manual upload"],["File",fileLabel(file)]]);
}
function clearAnalysis() {
  state.analysisRevision++;
  state.analysis=null;$("analysis-export").disabled=true;
  for(const id of ["chi-results","rs-results","window-results"])$(id).textContent="Run analysis to see measurements.";
  $("analysis-conclusion").textContent="No current results.";$("analysis-data").textContent="No report yet.";
  analysisSource();
}
$("window-size").addEventListener("input",clearAnalysis);
$("analyse-created").onclick=run(()=>{
  if(!state.latest||state.latest.settings.cover_type!=="image")throw new Error("Protect a PNG first.");
  // Allowlist non-secret explanatory settings; no payloads, keys or passwords.
  const r=state.latest.result;
  state.analysisContext={num_lsb:r.num_lsb,start_unit:r.start_index,container_bytes:r.container_size_bytes,capacity_bytes:r.capacity_bytes};
  state.analysisFile=state.latest.file;$("analysis-file").value="";$("analysis-file").required=false;
  preview("analysis-preview",state.analysisFile);clearAnalysis();location.hash="analysis";
});
// WebCrypto exists only in secure contexts (HTTPS or localhost); elsewhere the
// local hash comparison is skipped and reported rather than blocking analysis.
async function sha256Hex(file) {
  if(!globalThis.crypto?.subtle)return null;
  const digest=await crypto.subtle.digest("SHA-256",await file.arrayBuffer());
  return Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,"0")).join("");
}
function renderAnalysis(job) {
  const fmt=(v,tail=false)=>{
    if(v==null||!Number.isFinite(v))return "Insufficient data";
    if(tail&&v===0)return "Below numerical precision (returned 0)";
    return v>0&&v<0.0001?v.toExponential(4):Number(v).toFixed(5);
  };
  const counts=c=>c.regular+" / "+c.singular+" / "+c.unusable;
  const thresholds=job.combined.thresholds;
  const indication=(score,threshold)=>score==null?"Insufficient data":score>=threshold?"Indicators detected":"No strong indicators";
  const channels=Object.entries(job.channels);
  $("analysis-file-info").innerHTML=detailsTable([["Source",job.input.encoding_context?"Encoder output":"Manual upload"],["File",job.input.filename+" · "+bytes(job.input.byte_length)],["Image",job.image.width+" × "+job.image.height+" · "+job.image.mode],["SHA-256 of analysed PNG",job.file_sha256]]);
  const context=job.input.encoding_context;
  $("analysis-encoding").hidden=!context;
  if(context) {
    const usage=context.capacity_bytes>0?(100*context.container_bytes/context.capacity_bytes).toFixed(2)+"%":"Unavailable";
    $("analysis-encoding-details").innerHTML=detailsTable([["LSB depth",context.num_lsb],["Start",context.start_unit+" carrier units"],["Signed container",bytes(context.container_bytes)],["Capacity from start",bytes(context.capacity_bytes)],["Capacity used",usage]]);
  }
  const chiNote=job.scores.chi_square==null?"Insufficient data for the chi-square summary score."
    :job.scores.chi_square<thresholds.chi_square?"Weak chi-square evidence of pair equalisation. Hidden data may still be present, especially when payload bits are structured rather than approximately balanced."
    :"Value-pair equalisation is compatible with LSB replacement; other causes are possible.";
  $("chi-results").innerHTML=detailsTable([["Summary tail score",fmt(job.scores.chi_square,true)],["Threshold (provisional)",thresholds.chi_square],["Interpretation",indication(job.scores.chi_square,thresholds.chi_square)],["Note",chiNote]])
    +'<div class="table-wrap">'+table(["Channel","χ²","df","Whole-channel tail","Window median tail","Channel summary"],channels.map(([name,c])=>[name,fmt(c.chi_square.statistic),c.chi_square.degrees_of_freedom,fmt(c.chi_square.score,true),fmt(c.chi_square_regional_median_score,true),fmt(c.chi_square_summary_score,true)]))+"</div>";
  $("rs-results").innerHTML=detailsTable([["Estimated LSB-replacement fraction",fmt(job.scores.rs)],["Threshold (provisional)",thresholds.rs],["Interpretation",indication(job.scores.rs,thresholds.rs)],["Masks","[0,1,1,0] / [0,-1,-1,0]"]])
    +'<div class="table-wrap">'+table(["Channel","Groups","+mask R / S / U","Inverse R / S / U","Estimated fraction"],channels.map(([name,c])=>[name,c.rs.groups,counts(c.rs.positive),counts(c.rs.negative),fmt(c.rs.score)]))+"</div>";
  const summaries=[], rows=[];
  for(const [name,c] of channels) {
    const valid=c.windows.filter(w=>w.score!=null);
    const high=valid.filter(w=>w.score>=thresholds.chi_square).length;
    const peak=valid.length?Math.max(...valid.map(w=>w.score)):null;
    summaries.push([name,c.windows.length+" windows of "+c.effective_window_size+" values · "+valid.length+" usable · "+high+" at/above threshold · peak "+fmt(peak,true)]);
    c.windows.forEach((w,i)=>rows.push([name,i+1,w.start+"–"+w.stop,w.sample_count,fmt(w.statistic)+" / "+w.degrees_of_freedom,fmt(w.score,true),w.score==null?"Insufficient data":w.score>=thresholds.chi_square?"At/above threshold":"Below threshold"]));
  }
  $("window-results").innerHTML=detailsTable([["Requested window size",job.configuration.requested_window_size+" (may increase to limit each channel to 128 windows)"],...summaries])
    +'<details><summary>All windows</summary><div class="table-wrap analysis-windows">'+table(["Channel","Window","Start–end","Values","Statistic / df","Tail score","Observation"],rows)+"</div></details>";
  $("analysis-conclusion").textContent=({"High indication":"High indication: at least one method crossed its threshold. This is statistical evidence compatible with LSB replacement, not proof of hidden data.","Low indication":"Low indication: both methods are below their thresholds. This does not establish absence of hidden data.","Inconclusive":"Inconclusive: neither method crossed its threshold and at least one had insufficient data."})[job.combined.category];
  $("analysis-limitations").replaceChildren(...job.limitations.map(text=>{const li=document.createElement("li");li.textContent=text;return li;}));
  $("analysis-data").textContent=pretty(job);
}
$("analysis-form").onsubmit=run(async e=>{
  e.preventDefault();if(!state.analysisFile)throw new Error("Choose a PNG to analyse.");
  if(state.analysisFile.size>32*1024*1024)throw new Error("Analysis supports PNG files up to 32 MiB.");
  const file=state.analysisFile, context=state.analysisContext?{...state.analysisContext}:null, data=new FormData();data.append("image_file",file);data.append("window_size",$("window-size").value);
  clearAnalysis();const revision=state.analysisRevision;$("analysis-button").disabled=true;$("analysis-status").textContent="Analysing exact PNG bytes…";
  try {
    const expectedHash=await sha256Hex(file);
    let job=await api("/api/analyse?mode=async",data);
    while(job.job_id) {
      const id=job.job_id;await new Promise(resolve=>setTimeout(resolve,400));
      const progress=await api("/api/jobs/"+id);
      if(progress.status==="pending")continue;
      if(progress.status==="error")throw new Error(progress.error);
      job=progress.result;
    }
    if(file!==state.analysisFile||revision!==state.analysisRevision)return;
    if(expectedHash&&job.file_sha256!==expectedHash)throw new Error("Analysed file hash did not match the selected PNG. No result displayed.");
    job.input={filename:file.name,byte_length:file.size,source:context?"encoder_output":"manual_upload",sha256_matches_selected_file:expectedHash?true:null,
      encoding_context:context,context_origin:context?"Browser snapshot of encoder response; not inferred or independently verified":null};
    renderAnalysis(job);
    state.analysis=job;$("analysis-export").disabled=false;
    $("analysis-status").textContent="Completed · "+(expectedHash?"file match verified":"file match not checked (WebCrypto unavailable)")+" · "+fileLabel(file)+" · "+job.image.width+" × "+job.image.height+" · "+job.image.mode;
  } catch(error){$("analysis-status").textContent=error.message;throw error;}
  finally{$("analysis-button").disabled=false;}
});
$("analysis-export").onclick=()=>{if(state.analysis)exportJSON(state.analysis,"steganalysis-report.json");};
updateBits();updateStart();updateStart("verify");
loadKeys().catch(error=>notice("Could not load Alice's keys: "+error.message,true));
