'use strict';
const $ = id => document.getElementById(id);
const reportKeys = ['description', 'conclusion', 'limitations'];
const studyKeys = ['organ', 'age', 'indication', 'measurements', 'observations'];
const textLimits = {organ:200, indication:4000, measurements:6000, observations:8000, doctor:200, description:16000, conclusion:16000, limitations:16000};
let token = '', images = [], approved = false, provenance = null;
let busy = false, revision = 0, jobSerial = 0, activeJob = null;
let studyCreatedAt = new Date().toISOString();
let ollamaAvailable = false, modelsBusy = false, downloadBusy = false, downloadTimer = null;
const pendingDownloads = new Map();
window.sonoHasUnsavedChanges = false;
window.sonoIsBusy = false;
let nativeCloseApproved = false;
window.sonoAllowClose = () => { nativeCloseApproved = true; };
function message(text, isError = false) {
  $('message').textContent = text;
  $('message').hidden = !text;
  $('message').classList.toggle('error', isError);
}
function setDirty(value) {
  window.sonoHasUnsavedChanges = value;
  $('save-state').textContent = value ? 'Есть несохранённые изменения' : 'Нет несохранённых изменений';
  $('save-state').classList.toggle('dirty', value);
}
function invalidate(markChanged = true) {
  approved = false;
  $('review').checked = false;
  $('report-state').textContent = 'Черновик';
  $('report-state').classList.remove('approved');
  if (markChanged) {
    if (provenance) provenance.modified_after_generation = true;
    revision++;
    setDirty(true);
  }
}
function refreshProvenance() {
  const p = provenance;
  $('provenance-state').textContent = !p ? '' : p.provider === 'manual'
    ? 'Источник: данные врача. Анализ изображений моделью не выполнялся.'
    : 'Источник: ' + (typeof p.model === 'string' ? p.model : 'открытый протокол') + (p.restored_from_file ? ' · восстановлено из файла; требуется повторная проверка.' : ' · ИИ-черновик, клиническая точность не подтверждена.');
}
async function responseError(response) {
  let detail = '';
  try { const body = await response.json(); if (typeof body.error === 'string') detail = body.error; } catch (_) {}
  return Error(detail || (response.status === 413 ? 'Снимки вместе слишком велики. Удалите часть изображений и повторите.' : 'Ошибка локального сервера (' + response.status + '). Повторите действие.'));
}
async function api(path, data, signal) {
  const options = {method:data === undefined ? 'GET' : 'POST', headers:{'X-Local-Token':token}, signal};
  if (data !== undefined) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(data);
    if (new Blob([options.body]).size > 32 * 1024 * 1024) throw Error('Снимки вместе слишком велики для одного анализа. Удалите часть изображений и повторите.');
  }
  let response;
  try { response = await fetch(path, options); }
  catch (error) { if (error.name === 'AbortError') throw error; throw Error('Нет связи с локальным сервером. Перезапустите SonoCopilot, предварительно сохранив протокол.'); }
  if (!response.ok) throw await responseError(response);
  try { return await response.json(); }
  catch (_) { throw Error('Сервер вернул неполный ответ. Повторите действие.'); }
}
function renderImages() {
  const gallery = $('gallery');
  gallery.replaceChildren();
  images.forEach((item, index) => {
    const tile = document.createElement('div'); tile.className = 'tile';
    const img = document.createElement('img'); img.src = 'data:image/png;base64,' + item.image; img.alt = 'Снимок УЗИ ' + (index + 1);
    const caption = document.createElement('span');
    caption.textContent = 'Снимок ' + (index + 1) + (item.metadata.frames > 1 ? ' · кадр ' + item.metadata.selected_frame + ' из 0–' + (item.metadata.frames - 1) : '');
    const button = document.createElement('button'); button.textContent = 'Удалить'; button.disabled = busy;
    button.onclick = () => { if (busy) return; images.splice(index, 1); $('privacy').checked = false; invalidate(); renderImages(); };
    tile.append(img, caption, button); gallery.append(tile);
  });
  $('count').textContent = images.length + ' / 6';
}
function updateControls() {
  document.querySelectorAll('button,input,textarea,select').forEach(control => { control.disabled = busy; });
  $('cancel').disabled = !busy;
  $('refresh').disabled = busy || modelsBusy;
  $('model').disabled = busy || modelsBusy;
  $('analyze').disabled = busy || !token || !$('model').value;
  $('download-model').disabled = busy || downloadBusy || !token || !ollamaAvailable;
  $('working').hidden = !busy;
  window.sonoIsBusy = busy || downloadBusy;
  renderImages();
}
function beginJob(label) {
  if (busy) return null;
  const job = {id:++jobSerial, controller:new AbortController()};
  activeJob = job; busy = true;
  $('working-text').textContent = label;
  updateControls();
  return job;
}
function current(job) { return activeJob === job && !job.controller.signal.aborted; }
function finishJob(job) { if (activeJob === job) { activeJob = null; busy = false; updateControls(); } }
$('cancel').onclick = () => {
  if (!activeJob) return;
  activeJob.controller.abort(); activeJob = null; busy = false; ++jobSerial; updateControls();
  message('Ожидание отменено. Уже загруженные снимки сохранены. Если ИИ начал анализ, Ollama может ещё некоторое время завершать его в фоне.');
};
async function upload(files) {
  if (busy || !files.length) return;
  if (!$('frame-index').checkValidity() || $('frame-index').value === '') return message('Проверьте номер кадра: целое число от 0 до 1023.', true);
  const frame = Number($('frame-index').value);
  const job = beginJob('Подготавливаем изображения…');
  if (!job) return;
  const errors = []; let added = 0;
  message('');
  try {
    for (const file of Array.from(files)) {
      if (!current(job)) break;
      if (images.length >= 6) { errors.push('Добавлено максимум 6 снимков. Остальные файлы пропущены.'); break; }
      if (file.size > 20 * 1024 * 1024) { errors.push('Файл «' + file.name + '» превышает 20 МБ и пропущен.'); continue; }
      if (file.size === 0) { errors.push('Файл «' + file.name + '» пуст и пропущен.'); continue; }
      try {
        const bytes = new Uint8Array(await file.arrayBuffer());
        if (!current(job)) break;
        let binary = '';
        for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
        const raw = btoa(binary);
        const raster = file.type === 'image/png' || file.type === 'image/jpeg' || /\.(?:png|jpe?g)$/i.test(file.name);
        const selectedFrame = raster ? 0 : frame;
        const result = await api('/api/convert', {image:raw, frame_index:selectedFrame}, job.controller.signal);
        if (!current(job)) break;
        images.push({...result, raw, frame_index:selectedFrame}); added++;
        $('privacy').checked = false; invalidate();
      } catch (error) { if (error.name === 'AbortError') break; errors.push('«' + file.name + '»: ' + error.message); }
    }
    if (current(job)) {
      if (added) $('status').textContent = 'Исследование загружено';
      const note = added ? 'Добавлено снимков: ' + added + '. Проверьте отсутствие персональных данных на изображениях.' : '';
      message([note, ...errors].filter(Boolean).join('\n'), errors.length > 0);
    }
  } finally { finishJob(job); $('upload').value = ''; }
}
async function models() {
  if (modelsBusy) return;
  modelsBusy = true; updateControls();
  const previous = $('model').value;
  try {
    const result = await api('/api/models');
    const names = Array.isArray(result.models) ? result.models.filter(name => typeof name === 'string') : [];
    ollamaAvailable = result.ollama_available === true || (result.ollama_available === undefined && !result.error);
    $('model').replaceChildren();
    for (const name of names) { const option = document.createElement('option'); option.value = name; option.textContent = name; $('model').append(option); }
    if (!names.length) { const option = document.createElement('option'); option.value = ''; option.textContent = ollamaAvailable ? 'Нет подходящей модели' : 'Ollama не подключена'; $('model').append(option); }
    else if (names.includes(previous)) $('model').value = previous;
    $('model-state').textContent = result.error || (names.length ? 'Локальная модель готова. Поддержка изображений проверена; клиническая точность для УЗИ не подтверждена.' : 'Ollama запущена. Установите модель с поддержкой изображений.');
    if (!names.length) $('setup').open = true;
  } catch (error) {
    ollamaAvailable = false;
    $('model').replaceChildren(); const option = document.createElement('option'); option.value = ''; option.textContent = 'Нет подключения'; $('model').append(option);
    $('model-state').textContent = error.message; $('setup').open = true;
  } finally { modelsBusy = false; updateControls(); }
}
function updateDownload(state) {
  downloadBusy = state.state === 'downloading';
  $('download-state').textContent = state.error || state.status || (state.state === 'complete' ? 'Модель установлена.' : '');
  $('download-progress').hidden = !downloadBusy;
  if (downloadBusy && Number(state.total) > 0) $('download-progress').value = Math.min(100, Math.max(0, Number(state.completed || 0) / Number(state.total) * 100));
  else $('download-progress').removeAttribute('value');
  updateControls();
}
async function pollDownload() {
  clearTimeout(downloadTimer);
  try {
    const state = await api('/api/model-download'); updateDownload(state);
    if (state.state === 'downloading') downloadTimer = setTimeout(pollDownload, 2000);
    else if (state.state === 'complete') await models();
  } catch (error) { downloadBusy = false; $('download-state').textContent = error.message; updateControls(); }
}
$('download-model').onclick = async () => {
  if (busy || downloadBusy || !ollamaAvailable) return;
  downloadBusy = true; updateControls();
  $('download-state').textContent = 'Запускаем загрузку модели…';
  try { const state = await api('/api/model-download', {model:'gemma3:4b'}); updateDownload(state); if (state.state === 'downloading') downloadTimer = setTimeout(pollDownload, 2000); else if (state.state === 'complete') await models(); }
  catch (error) { downloadBusy = false; $('download-state').textContent = error.message; updateControls(); }
};
$('upload').onchange = event => upload(event.target.files);
$('drop').ondragover = event => { event.preventDefault(); if (!busy) $('drop').classList.add('dragover'); };
$('drop').ondragleave = () => $('drop').classList.remove('dragover');
$('drop').ondrop = event => { event.preventDefault(); $('drop').classList.remove('dragover'); upload(event.dataTransfer.files); };
// A file dropped outside the upload target must never navigate away from a report.
window.addEventListener('dragover', event => event.preventDefault());
window.addEventListener('drop', event => event.preventDefault());
$('refresh').onclick = models;
$('model').onchange = updateControls;
$('analyze').onclick = async () => {
  if (busy) return;
  if (!images.length) return message('Добавьте хотя бы один снимок.', true);
  if (!$('privacy').checked) return message('Проверьте все снимки и подтвердите отсутствие персональных данных.', true);
  if (!$('model').value) return message('Сначала подключите локальную модель Ollama.', true);
  if (!$('age').checkValidity()) return message('Проверьте возраст: целое число от 0 до 120 лет или пустое поле.', true);
  if (reportKeys.some(key => $(key).value.trim()) && !confirm('Создать новый ИИ-черновик вместо текущих описания, заключения и ограничений?')) return;
  const job = beginJob('ИИ анализирует снимки. На этом компьютере это может занять несколько минут…');
  if (!job) return;
  invalidate(); message('');
  try {
    const data = {images:images.map(item => ({image:item.raw, frame_index:item.frame_index})), privacy_confirmed:true, model:$('model').value};
    for (const key of studyKeys) data[key] = $(key).value;
    const result = await api('/api/analyze', data, job.controller.signal);
    if (!current(job)) return;
    if (!reportKeys.every(key => typeof result[key] === 'string' && result[key].length <= 16000)) throw Error('Модель вернула неполный протокол. Выберите другую модель.');
    reportKeys.forEach(key => { $(key).value = result[key]; });
    provenance = result.provenance || {model:data.model, clinically_validated:false, human_review_required:true};
    refreshProvenance(); $('status').textContent = 'Черновик готов';
    message('Черновик сформирован. Проверьте каждый раздел по исходным изображениям.');
  } catch (error) { if (current(job) && error.name !== 'AbortError') message(error.message, true); }
  finally { finishJob(job); }
};
$('manual').onclick = () => {
  if (busy) return;
  if (reportKeys.some(key => $(key).value.trim()) && !confirm('Заменить текущий протокол данными врача? Описание и ограничения будут заполнены заново, заключение очищено.')) return;
  invalidate();
  provenance = {provider:'manual', images:[], clinically_validated:false, human_review_required:true};
  $('description').value = [$('observations').value, $('measurements').value].filter(Boolean).join('\n');
  $('conclusion').value = '';
  $('limitations').value = 'Составлено по введённым данным врача. ИИ-анализ изображений не выполнялся.';
  refreshProvenance(); $('status').textContent = 'Ручной протокол';
  message('Наблюдения и измерения перенесены в описание. Заполните заключение и проверьте протокол.');
  $('description').focus();
};
for (const key of [...studyKeys, ...reportKeys, 'doctor']) $(key).addEventListener('input', () => invalidate());
$('privacy').addEventListener('change', () => { if (approved) invalidate(); });
$('review').addEventListener('change', () => { if (approved && !$('review').checked) invalidate(); });
$('approve').onclick = () => {
  if (busy) return;
  if (!reportKeys.slice(0, 2).every(key => $(key).value.trim())) return message('Заполните описание и заключение.', true);
  if (!$('age').checkValidity()) return message('Проверьте возраст: целое число от 0 до 120 лет или пустое поле.', true);
  if (!$('doctor').value.trim() || !$('review').checked) return message('Укажите врача и подтвердите проверку протокола.', true);
  approved = true; revision++; setDirty(true);
  $('report-state').textContent = 'Проверено врачом'; $('report-state').classList.add('approved');
  message('Протокол подтверждён. Сохраните JSON для дальнейшего редактирования или PDF для печати.');
};
function report() {
  return {schema_version:1, application:'SonoCopilot — исследовательская версия', created_at:studyCreatedAt, updated_at:new Date().toISOString(), status:approved ? 'Проверено врачом' : 'Черновик, не подтверждён', ...Object.fromEntries([...studyKeys, ...reportKeys, 'doctor'].map(key => [key, $(key).value])), provenance};
}
function startDownload(blob, extension) {
  const filename = 'sonocopilot-report-' + revision + '-' + Date.now() + '.' + extension;
  if (extension === 'json') pendingDownloads.set(filename, revision);
  const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = filename; document.body.append(link); link.click(); link.remove();
  // Native dialog can stay open for a while. Revoke only once the download has had time to start.
  setTimeout(() => URL.revokeObjectURL(link.href), 60000);
  return filename;
}
window.sonoMarkSaved = filename => {
  const savedRevision = pendingDownloads.get(filename);
  pendingDownloads.delete(filename);
  if (savedRevision === undefined || savedRevision !== revision) return false;
  setDirty(false);
  $('save-state').textContent = 'Протокол сохранён в JSON · оригиналы снимков сохраняйте отдельно';
  return true;
};
$('export').onclick = () => {
  if (busy) return;
  if (!$('age').checkValidity()) return message('Проверьте возраст перед сохранением.', true);
  startDownload(new Blob([JSON.stringify(report(), null, 2)], {type:'application/json'}), 'json');
  message('Выберите место сохранения JSON. Файл содержит текст протокола и происхождение черновика; изображения в него не включаются.');
};
$('print').onclick = async () => {
  if (busy) return;
  if (!$('age').checkValidity()) return message('Проверьте возраст перед сохранением.', true);
  const job = beginJob('Подготавливаем PDF…'); if (!job) return;
  try {
    const response = await fetch('/api/export/pdf', {method:'POST', headers:{'Content-Type':'application/json', 'X-Local-Token':token}, body:JSON.stringify(report()), signal:job.controller.signal});
    if (!response.ok) throw await responseError(response);
    if (!(response.headers.get('Content-Type') || '').includes('application/pdf')) throw Error('Не удалось получить PDF. Сохраните JSON и повторите.');
    const blob = await response.blob(); if (!current(job)) return;
    startDownload(blob, 'pdf'); message('Выберите место сохранения PDF. Для продолжения редактирования также сохраните JSON.');
  } catch (error) { if (current(job) && error.name !== 'AbortError') message(error.message || 'Не удалось сохранить PDF.', true); }
  finally { finishJob(job); }
};
function validateOpenedReport(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || typeof value.application !== 'string' || !value.application.startsWith('SonoCopilot')) throw Error('Выберите JSON-протокол, сохранённый в SonoCopilot.');
  if (value.schema_version !== undefined && value.schema_version !== 1) throw Error('Файл создан в другой версии формата. Обновите SonoCopilot.');
  const result = {};
  for (const [key, max] of Object.entries(textLimits)) {
    const text = value[key] === undefined && key === 'observations' ? '' : value[key];
    if (typeof text !== 'string' || text.length > max) throw Error('Некорректное или слишком длинное поле протокола: ' + key + '.');
    result[key] = text;
  }
  if (typeof value.age !== 'string' || (value.age !== '' && (!/^\d{1,3}$/.test(value.age) || Number(value.age) > 120))) throw Error('Некорректный возраст в протоколе.');
  result.age = value.age;
  result.created_at = typeof value.created_at === 'string' && Number.isFinite(Date.parse(value.created_at)) ? new Date(value.created_at).toISOString() : new Date().toISOString();
  if (value.provenance !== null && value.provenance !== undefined && (typeof value.provenance !== 'object' || Array.isArray(value.provenance) || JSON.stringify(value.provenance).length > 65536)) throw Error('Некорректные сведения о происхождении протокола.');
  result.provenance = value.provenance ? {...value.provenance, restored_from_file:true, clinically_validated:false, human_review_required:true} : {provider:'restored', restored_from_file:true, clinically_validated:false, human_review_required:true};
  return result;
}
$('open-report').onchange = async event => {
  const file = event.target.files[0]; if (!file || busy) return;
  const job = beginJob('Открываем протокол…'); if (!job) return;
  try {
    if (file.size > 1024 * 1024) throw Error('JSON-протокол превышает 1 МБ. Выберите файл протокола SonoCopilot.');
    let parsed; try { parsed = JSON.parse(await file.text()); } catch (_) { throw Error('Не удалось прочитать JSON. Файл повреждён или имеет другой формат.'); }
    const restored = validateOpenedReport(parsed); if (!current(job)) return;
    if (window.sonoHasUnsavedChanges && !confirm('Открыть сохранённый протокол вместо текущего исследования? Несохранённые изменения и загруженные снимки будут удалены.')) return;
    images = []; $('privacy').checked = false; $('frame-index').value = '0';
    if (!Array.from($('organ').options).some(option => option.value === restored.organ)) { const option = document.createElement('option'); option.value = restored.organ; option.textContent = restored.organ; $('organ').append(option); }
    for (const key of [...studyKeys, ...reportKeys, 'doctor']) $(key).value = restored[key];
    studyCreatedAt = restored.created_at; provenance = restored.provenance; invalidate(); refreshProvenance();
    $('status').textContent = 'Протокол открыт';
    message('Протокол открыт как черновик. Повторно проверьте содержание и подтвердите его. Изображения не включены в JSON — при необходимости загрузите исходные снимки.');
  } catch (error) { if (current(job)) message(error.message, true); }
  finally { finishJob(job); $('open-report').value = ''; }
};
$('reset').onclick = () => {
  if (busy) return;
  if ((window.sonoHasUnsavedChanges || images.length) && !confirm('Начать новое исследование? Текущий протокол и снимки будут удалены из памяти.')) return;
  images = []; provenance = null; pendingDownloads.clear();
  for (const key of [...reportKeys, 'age', 'indication', 'measurements', 'observations', 'doctor']) $(key).value = '';
  $('organ').selectedIndex = 0; $('frame-index').value = '0'; $('privacy').checked = false; $('upload').value = ''; $('open-report').value = '';
  studyCreatedAt = new Date().toISOString(); revision++; invalidate(false); setDirty(false); refreshProvenance(); renderImages();
  $('status').textContent = 'Новое исследование'; message('');
};
window.addEventListener('beforeunload', event => {
  if (!nativeCloseApproved && (window.sonoHasUnsavedChanges || window.sonoIsBusy)) { event.preventDefault(); event.returnValue = ''; }
});
(async () => {
  try {
    const config = await api('/api/config'); token = config.token; $('version').textContent = config.version ? '· ' + config.version : '';
    await models();
    // Reconnect to an existing model download if the window was reopened.
    try { const state = await api('/api/model-download'); updateDownload(state); if (state.state === 'downloading') downloadTimer = setTimeout(pollDownload, 2000); } catch (_) {}
  } catch (error) { message('Не удалось запустить локальный сервис: ' + error.message, true); updateControls(); }
})();
