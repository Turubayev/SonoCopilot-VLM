'use strict';
// Regression tests of document lifecycle and async races; no patient data or model calls.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, 'app.js'), 'utf8');
const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
class Element {
  constructor(tag = 'div') { this.tagName = tag.toUpperCase(); this.children = []; this.events = {}; this._value = ''; this.checked = false; this.disabled = false; this.hidden = false; this.textContent = ''; this.valid = true; this.classes = new Set(); this.classList = {toggle:(name, force) => force ? this.classes.add(name) : this.classes.delete(name), add:name=>this.classes.add(name), remove:name=>this.classes.delete(name)}; }
  get value() { if (this.tagName === 'SELECT') return this.children[this._selectedIndex || 0]?.value || ''; return this._value; }
  set value(value) { if (this.tagName === 'SELECT') { const index = this.children.findIndex(option => option.value === value); this._selectedIndex = index < 0 ? 0 : index; } else this._value = value; }
  get options() { return this.children; }
  set selectedIndex(value) { this._selectedIndex = value; }
  append(...elements) { this.children.push(...elements); }
  replaceChildren(...elements) { this.children = elements; this._selectedIndex = 0; }
  addEventListener(name, callback) { this.events[name] = callback; }
  checkValidity() { return this.valid; }
  focus() {} remove() {} removeAttribute(name) { delete this[name]; }
}
async function createApp(fetchHook) {
  const elements = new Map();
  for (const match of html.matchAll(/<([a-z]+)[^>]*\bid="([^"]+)"[^>]*>/g)) elements.set(match[2], new Element(match[1]));
  for (const name of ['Щитовидная железа', 'Другое']) { const option = new Element('option'); option.value = name; elements.get('organ').append(option); }
  elements.get('frame-index').value = '0';
  const downloads = [], windowEvents = {};
  const response = data => ({ok:true, status:200, json:async()=>data, headers:{get:()=> 'application/json'}});
  const context = {
    document:{getElementById:id=>elements.get(id), querySelectorAll:()=>[...elements.values()].filter(el => ['BUTTON','INPUT','TEXTAREA','SELECT'].includes(el.tagName)), body:new Element('body'), createElement:tag=>{ const el = new Element(tag); if (tag === 'a') el.click = () => downloads.push(el.download); return el; }},
    window:{addEventListener:(name,callback)=>windowEvents[name]=callback},
    fetch:async (url, options) => { if (fetchHook) { const custom = fetchHook(url, options); if (custom !== undefined) return custom; } if (url === '/api/config') return response({token:'test-token', version:'1.0.0'}); if (url === '/api/models') return response({models:['vision-test'], ollama_available:true}); if (url === '/api/model-download') return response({state:'idle'}); if (url === '/api/convert') return response({image:'png-data',metadata:{frames:2,selected_frame:0}}); throw Error('Unexpected request '+url); },
    Blob, AbortController, Uint8Array, btoa:binary=>Buffer.from(binary,'binary').toString('base64'), URL:{createObjectURL:()=> 'blob:test',revokeObjectURL:()=>{}}, setTimeout:()=>1, clearTimeout:()=>{}, confirm:()=>true,
  };
  vm.createContext(context); vm.runInContext(source, context);
  for (let i = 0; i < 8; i++) await new Promise(resolve => setImmediate(resolve));
  return {context,elements,downloads,windowEvents,run:code=>vm.runInContext(code,context),response};
}
const reportFixture = () => ({schema_version:1, application:'SonoCopilot — исследовательская версия',created_at:'2026-10-09T10:00:00Z',status:'Проверено врачом',organ:'Другое',age:'37',indication:'Плановое исследование',measurements:'Размеры введены врачом',observations:'Наблюдения сохранены',description:'Описание врача',conclusion:'Заключение врача',limitations:'Ограничения',doctor:'Врач',provenance:{model:'vision-test',clinically_validated:true}});
const file = () => ({name:'ultrasound.png',type:'image/png',size:4,arrayBuffer:async()=>new Uint8Array([1,2,3,4]).buffer});
test('saving JSON uses a revision token: old downloads cannot clear later edits', async () => {
  const app = await createApp(); const description = app.elements.get('description');
  description.value = 'Первое описание'; description.events.input(); app.elements.get('export').onclick();
  const old = app.downloads.at(-1); description.value = 'Изменённое описание'; description.events.input();
  assert.equal(app.context.window.sonoMarkSaved(old), false); assert.equal(app.context.window.sonoHasUnsavedChanges, true);
  app.elements.get('export').onclick(); assert.equal(app.context.window.sonoMarkSaved(app.downloads.at(-1)), true); assert.equal(app.context.window.sonoHasUnsavedChanges, false);
});
test('restoring a confirmed JSON clears approval, privacy and images and retains observations', async () => {
  const app = await createApp(); await app.run('upload')( [file()] );
  app.elements.get('privacy').checked = true;
  const saved = reportFixture(); await app.elements.get('open-report').onchange({target:{files:[{size:1000,text:async()=>JSON.stringify(saved)}]}});
  assert.equal(app.run('approved'),false); assert.equal(app.elements.get('review').checked,false); assert.equal(app.elements.get('privacy').checked,false);
  assert.equal(app.run('images.length'),0); assert.equal(app.elements.get('observations').value,saved.observations);
  assert.equal(app.run('provenance.clinically_validated'),false); assert.equal(app.context.window.sonoHasUnsavedChanges,true);
});
test('report validator rejects malformed fields, future schema and noninteger ages', async () => {
  const app = await createApp(), validate = app.run('validateOpenedReport');
  for (const bad of [{...reportFixture(),doctor:{html:'bad'}},{...reportFixture(),age:'4.5'},{...reportFixture(),description:'x'.repeat(16001)},{...reportFixture(),schema_version:2},{...reportFixture(),provenance:[]}]) assert.throws(()=>validate(bad));
  const old = reportFixture(); delete old.schema_version; delete old.observations; assert.equal(validate(old).observations,'');
});
test('mixed upload keeps oversize error visible even after valid file succeeds', async () => {
  const app = await createApp();
  await app.run('upload')([{name:'large.dcm',size:21*1024*1024},file()]);
  assert.equal(app.run('images.length'),1); assert.match(app.elements.get('message').textContent,/20 МБ/); assert.match(app.elements.get('message').textContent,/Добавлено снимков: 1/);
  assert.equal(app.context.window.sonoIsBusy,false);
});
test('six-image limit remains visible and duplicate batches do not run', async () => {
  const app = await createApp(); await app.run('upload')(Array.from({length:7},file));
  assert.equal(app.run('images.length'),6); assert.match(app.elements.get('message').textContent,/максимум 6/);
});
test('cancelled AI response cannot overwrite a later manual report', async () => {
  let resolveAnalysis; let calls = 0;
  const app = await createApp((url) => { if (url === '/api/analyze') { calls++; return new Promise(resolve=>resolveAnalysis=resolve); } });
  await app.run('upload')([file()]); app.elements.get('privacy').checked=true;
  const task = app.elements.get('analyze').onclick(); await new Promise(resolve=>setImmediate(resolve));
  await app.elements.get('analyze').onclick(); assert.equal(calls,1);
  app.elements.get('cancel').onclick(); app.elements.get('observations').value='Новые данные врача'; app.elements.get('manual').onclick();
  resolveAnalysis(app.response({description:'Устаревший ответ',conclusion:'Устаревший ответ',limitations:'Устаревший ответ'})); await task;
  assert.equal(app.elements.get('description').value,'Новые данные врача'); assert.equal(app.context.window.sonoIsBusy,false);
});
test('new study restores valid frame zero, empty age and no approval', async () => {
  const app = await createApp(); app.elements.get('frame-index').value='3'; app.elements.get('age').value='45'; app.elements.get('description').events.input();
  app.elements.get('reset').onclick();
  assert.equal(app.elements.get('frame-index').value,'0'); assert.equal(app.elements.get('age').value,''); assert.equal(app.context.window.sonoHasUnsavedChanges,false); assert.equal(app.run('approved'),false);
});
test('editing an approved report invalidates review and native close bypass is explicit', async () => {
  const app = await createApp();
  for (const key of ['description','conclusion','doctor']) app.elements.get(key).value='Введено врачом';
  app.elements.get('review').checked=true; app.elements.get('approve').onclick(); assert.equal(app.run('approved'),true);
  app.elements.get('description').events.input(); assert.equal(app.run('approved'),false); assert.equal(app.elements.get('review').checked,false);
  let blocked = false; app.windowEvents.beforeunload({preventDefault:()=>blocked=true}); assert.equal(blocked,true);
  app.context.window.sonoAllowClose(); blocked=false; app.windowEvents.beforeunload({preventDefault:()=>blocked=true}); assert.equal(blocked,false);
});
