'use strict';
const $ = id => document.getElementById(id), player = $('player');
let project, active = 0, previewOffset = null, previewEnd = null;
let busy = false, taskBusy = false, readingScript = false, playing = false, dirty = false;
let imagePosition = 0, imageStarted = 0, undoRevision = null;
let switchingVideo = false, activation = 0;
const time = seconds => `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
const current = () => project.scenes[active];
function status(text, error = false) { $('status').textContent = text; $('status').classList.toggle('error', error); }
function clock(value) { $('clock').textContent = `${time(Math.min(value, project.duration))} / ${time(project.duration)}`; $('scrub').value = value; }
function pending(scene) { return [scene.visual_status === 'draft' ? 'Draft visual' : '', scene.narration_status === 'pending' ? 'Narration pending' : ''].filter(Boolean).join(' · '); }
function updatePlayButton() { $('playTimeline').textContent = playing ? 'Pause timeline' : 'Play timeline'; }
function pause() {
  if (playing && player.hidden) imagePosition += (performance.now() - imageStarted) / 1000;
  playing = false; player.pause(); updatePlayButton();
}
function canLeave() { if (!dirty) return true; status('Save or discard your script changes first.', true); return false; }
function fillEditor() {
  const scene = current();
  $('editTitle').value = scene.title; $('editText').value = scene.text;
  $('editIn').value = scene.media_in; $('editDuration').value = scene.duration.toFixed(3);
  $('sceneNotes').textContent = scene.notes; $('scriptState').textContent = pending(scene) || 'CURRENT';
  $('moveEarlier').disabled = busy || active === 0 || !project.can_reorder;
  $('moveLater').disabled = busy || active === project.scenes.length - 1 || !project.can_reorder;
  $('moveEarlier').title = $('moveLater').title = project.can_reorder ? '' : 'Timed audio/graphics need explicit anchor edits before reordering.';
  $('undoEdit').disabled = busy || undoRevision === null; dirty = false;
}
function activate(index, { seek = true, autoplay = false, offset = 0, discard = false } = {}) {
  if (!project || (!discard && seek && !canLeave())) return;
  active = Math.max(0, Math.min(project.scenes.length - 1, index)); const scene = current();
  $('sceneTitle').textContent = scene.title; $('sceneCount').textContent = `${active + 1} / ${project.scenes.length}`; fillEditor();
  document.querySelectorAll('.scene-card').forEach((e, i) => e.classList.toggle('active', i === active));
  document.querySelectorAll('#pictureTrack button, #narrationTrack button').forEach(e => e.classList.toggle('active', Number(e.dataset.index) === active));
  $('previous').disabled = active === 0; $('next').disabled = active === project.scenes.length - 1;
  if (!seek) return;
  const generation = ++activation; switchingVideo = true;
  pause(); previewOffset = previewEnd = null; imagePosition = offset;
  const image = !project.master && scene.media_type === 'image';
  player.hidden = image; $('stillImage').hidden = !image; $('noMedia').hidden = true; player.onloadedmetadata = null;
  if (image) { player.removeAttribute('src'); player.load(); $('stillImage').src = scene.media; switchingVideo = false; }
  else {
    const source = project.master || scene.media;
    const setPosition = () => { if (generation !== activation) return; switchingVideo = false; player.currentTime = (project.master ? scene.start : scene.media_in) + offset; if (autoplay) play(); };
    player.muted = !project.master && scene.audio_mode !== 'preserve';
    if (player.getAttribute('src') !== source) { player.onloadedmetadata = setPosition; player.src = source; player.load(); } else setPosition();
  }
  if (image && autoplay) play();
  $('rangeIn').value = scene.start.toFixed(3); $('rangeOut').value = Math.min(project.duration, scene.start + Math.min(15, scene.duration)).toFixed(3);
  $('scrub').max = project.duration; clock(scene.start + offset); $('fullCut').hidden = true;
  $('viewerTag').textContent = project.master ? 'RENDER OF THIS EDIT' : `TIMELINE SOURCE${pending(scene) ? ' · ' + pending(scene).toUpperCase() : ''}`;
  status(project.master ? 'Playing an export bound to this timeline.' : 'Selected footage from this timeline. Build a range to review composed audio, graphics and cuts.');
}
function play() {
  if (readingScript || !canLeave()) return; playing = true; imageStarted = performance.now(); updatePlayButton();
  if (!player.hidden) player.play().catch(() => { pause(); status('Press play to continue.'); });
}
function advance() {
  if (active + 1 < project.scenes.length && canLeave()) activate(active + 1, { autoplay: true });
  else { pause(); clock(current().start + current().duration); }
}
function renderNavigation() {
  for (const id of ['scenes', 'pictureTrack', 'narrationTrack', 'sceneTicks']) $(id).replaceChildren();
  project.scenes.forEach((scene, index) => {
    const button = document.createElement('button'); button.className = 'scene-card'; button.setAttribute('aria-label', `Scene ${index + 1}: ${scene.title}`);
    for (const [tag, name, text] of [['span', 'number', String(index + 1).padStart(2, '0')], ['strong', '', scene.title], ['span', 'duration', time(scene.start)], ['span', 'kind', pending(scene) || `${scene.duration.toFixed(1)}s`]]) {
      const element = document.createElement(tag); element.className = name; element.textContent = text; button.append(element);
    }
    button.onclick = () => activate(index); $('scenes').append(button);
    for (const id of ['pictureTrack', 'narrationTrack']) {
      const clip = document.createElement('button'); clip.textContent = index + 1; clip.title = scene.title + (pending(scene) ? ' · ' + pending(scene) : '');
      clip.dataset.index = index; clip.style.flexGrow = scene.duration; clip.className = id === 'narrationTrack' && scene.narration_status === 'pending' ? 'pending' : '';
      clip.setAttribute('aria-label', `${id === 'pictureTrack' ? 'Picture' : 'Narration'}: ${scene.title}`); clip.onclick = () => activate(index); $(id).append(clip);
    }
    const tick = document.createElement('span'); tick.textContent = index % 2 === 0 ? String(index + 1).padStart(2, '0') : ''; tick.style.flexGrow = scene.duration; $('sceneTicks').append(tick);
  });
}
function applyProject(data, preferredId) {
  pause(); project = data; previewOffset = previewEnd = null;
  document.title = project.title + ' · Editing workspace'; $('projectTitle').textContent = $('projectCrumb').textContent = project.title;
  $('projectSubtitle').textContent = project.subtitle || 'One timeline for picture, narration and previews.';
  $('cutCount').textContent = `${project.scenes.length} scenes · revision ${project.revision}`;
  const drafts = project.scenes.filter(s => s.visual_status === 'draft').length, missing = project.scenes.filter(s => s.narration_status === 'pending').length;
  $('editState').textContent = `Current edit · ${drafts} draft visuals · ${missing} scenes awaiting narration${project.render_stale ? ' · Previous export is out of date and will not play as this edit.' : ''}`;
  $('rangeIn').max = $('rangeOut').max = project.duration; renderNavigation(); activate(Math.max(0, project.scenes.findIndex(s => s.id === preferredId)), { discard: true });
  if (readingScript) loadFullScript();
}
async function refresh(automatic = false) {
  if (busy || dirty) { if (!automatic) canLeave(); return; }
  try {
    const response = await fetch('/api/project'), data = await response.json(); if (!response.ok) throw Error(data.error || 'Project unavailable');
    // A finished export can become available after the timeline itself changed.
    // Refresh that binding too, even if its edit fingerprint is unchanged.
    if (!automatic || !project || data.timeline_sha256 !== project.timeline_sha256 || data.master !== project.master) applyProject(data, project && current().id);
  } catch (error) { status(error.message, true); }
}
async function save(operation) {
  if (busy) return; busy = true; pause(); const id = current().id, revision = project.revision;
  document.querySelectorAll('#sceneEditor button').forEach(b => b.disabled = true);
  try {
    const response = await fetch('/api/edit', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ expected_revision: revision, operation }) });
    const data = await response.json(); if (!response.ok) throw Error(data.error);
    undoRevision = revision; dirty = false; applyProject(data, id); status('Saved to the timeline. Older previews are no longer current.');
  } catch (error) { status('Edit was not saved: ' + error.message, true); }
  finally { busy = false; document.querySelectorAll('#sceneEditor button').forEach(b => b.disabled = false); $('moveEarlier').disabled = active === 0 || !project.can_reorder; $('moveLater').disabled = active === project.scenes.length - 1 || !project.can_reorder; $('undoEdit').disabled = undoRevision === null; }
}
$('sceneEditor').onsubmit = event => { event.preventDefault(); save({ op: 'editorial', clip_id: current().id, fields: { title: $('editTitle').value, text: $('editText').value } }); };
for (const id of ['editTitle', 'editText']) $(id).oninput = () => { dirty = true; status('Unsaved script changes.'); };
$('discardScene').onclick = fillEditor;
$('trimScene').onclick = () => { if (canLeave()) save({ op: 'trim', clip_id: current().id, in: Number($('editIn').value), duration: Number($('editDuration').value), ripple: true }); };
function move(delta) { if (!canLeave()) return; const ids = project.scenes.map(s => s.id), next = active + delta; [ids[active], ids[next]] = [ids[next], ids[active]]; save({ op: 'reorder', clip_ids: ids }); }
$('moveEarlier').onclick = () => move(-1); $('moveLater').onclick = () => move(1);
$('undoEdit').onclick = () => { if (canLeave() && undoRevision !== null) save({ op: 'undo', revision: undoRevision }); };
$('previous').onclick = () => activate(active - 1); $('next').onclick = () => activate(active + 1);
$('refreshProject').onclick = () => refresh(); $('playTimeline').onclick = () => playing ? pause() : play(); $('fullCut').onclick = () => activate(active);
player.addEventListener('play', () => { if (dirty) { pause(); canLeave(); return; } playing = true; updatePlayButton(); });
player.addEventListener('pause', () => { if (!player.ended) { playing = false; updatePlayButton(); } });
player.addEventListener('timeupdate', () => {
  if (!project || readingScript || player.hidden || switchingVideo) return;
  if (previewOffset !== null) { clock(Math.min(previewEnd, previewOffset + player.currentTime)); return; }
  const scene = current(), value = project.master ? player.currentTime : scene.start + Math.max(0, player.currentTime - scene.media_in);
  if (project.master) { const index = project.scenes.findIndex(s => value >= s.start && value < s.start + s.duration); if (index >= 0 && index !== active && !dirty) activate(index, { seek: false }); }
  else if (value >= scene.start + scene.duration - .015 && playing) { advance(); return; }
  clock(value);
});
player.addEventListener('ended', () => { if (switchingVideo) return; if (!readingScript && !project.master && previewOffset === null) advance(); else pause(); });
function imageTick(now) {
  if (project && playing && player.hidden && !readingScript) { const elapsed = imagePosition + (now - imageStarted) / 1000; clock(current().start + Math.min(elapsed, current().duration)); if (elapsed >= current().duration) advance(); }
  requestAnimationFrame(imageTick);
}
requestAnimationFrame(imageTick);
$('scrub').oninput = () => {
  if (!project || !canLeave()) return; const value = Number($('scrub').value), index = project.scenes.findIndex(s => value >= s.start && value < s.start + s.duration), chosen = index < 0 ? project.scenes.length - 1 : index;
  activate(chosen, { offset: Math.min(project.scenes[chosen].duration - .001, value - project.scenes[chosen].start) });
};
function loadFullScript() {
  const text = project.scenes.filter(s => s.text.trim()).map(s => `${s.title}\n\n${s.text}`).join('\n\n'); $('fullScriptText').textContent = text || 'No narration written yet.';
  $('fullScriptNote').textContent = 'Scene narration in this timeline’s order. Edit words in the scene editor; pending narration has not been recorded.';
  $('scriptFeedback').textContent = `${text.trim().split(/\s+/).filter(Boolean).length.toLocaleString()} words · timeline revision ${project.revision}`; $('copyScript').disabled = $('downloadScript').disabled = !text;
}
function scriptPanel(show) {
  if (!canLeave()) return; pause(); readingScript = show; $('fullScriptPanel').hidden = !show;
  document.querySelector('.workspace').hidden = show; document.querySelector('.scene-browser').hidden = show; $('timelineMode').classList.toggle('selected', !show);
  $('fullScriptMode').classList.toggle('selected', show); $('fullScriptMode').setAttribute('aria-pressed', String(show)); if (show) loadFullScript();
}
$('timelineMode').onclick = () => scriptPanel(false); $('fullScriptMode').onclick = () => scriptPanel(true);
$('copyScript').onclick = async () => { try { await navigator.clipboard.writeText($('fullScriptText').textContent); $('scriptFeedback').textContent = 'Timeline script copied.'; } catch { $('scriptFeedback').textContent = 'Select the text or download it to copy.'; } };
$('downloadScript').onclick = () => { const url = URL.createObjectURL(new Blob([$('fullScriptText').textContent], { type: 'text/plain;charset=utf-8' })); const link = document.createElement('a'); link.href = url; link.download = 'timeline-script.txt'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); };
$('renderPreview').onclick = async () => {
  if (!project || taskBusy || !canLeave()) return;
  const start = Number($('rangeIn').value), end = Number($('rangeOut').value), hash = project.timeline_sha256;
  if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end <= start || end > project.duration || end - start > 30) { status('Choose up to 30 seconds inside the timeline.', true); return; }
  taskBusy = true; $('renderPreview').disabled = true; status('Building a preview of this timeline…');
  try {
    const response = await fetch('/api/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ start, end, timeline_sha256: hash }) });
    const result = await response.json(); if (!response.ok) throw Error(result.error); const deadline = Date.now() + 210000;
    while (true) {
      await new Promise(resolve => setTimeout(resolve, 1200)); if (Date.now() > deadline) throw Error('Preview took too long.');
      const response = await fetch('/api/tasks/' + result.task), task = await response.json(); if (!response.ok || task.status === 'failed') throw Error(task.error || 'Preview unavailable');
      if (task.status === 'ready') {
        await refresh(true);
        if (task.timeline_sha256 !== project.timeline_sha256) { status('The timeline changed while rendering. Build a new preview for the current edit.'); break; }
        if (!readingScript && !dirty) { pause(); player.onloadedmetadata = null; previewOffset = start; previewEnd = end; player.hidden = false; $('stillImage').hidden = $('noMedia').hidden = true; player.src = task.media; player.muted = false; player.load(); $('viewerTag').textContent = 'COMPOSED PREVIEW · THIS TIMELINE'; $('fullCut').hidden = false; clock(start); }
        status('Preview ready for this edit. Pending narration or draft visuals remain unfinished.'); break;
      }
    }
  } catch (error) { status('Preview could not be built: ' + error.message, true); }
  finally { taskBusy = false; $('renderPreview').disabled = false; }
};
player.addEventListener('error', () => { if (player.error && !player.hidden) status('Footage could not be opened. Build a range preview or choose another scene.', true); });
window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
refresh(); setInterval(() => refresh(true), 5000);
