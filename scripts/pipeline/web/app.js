'use strict';
const $ = id => document.getElementById(id);
const player = $('player');
let project, mode = 'cut', active = 0, previewOffset = null, previewEnd = null;
let taskBusy = false, readingScript = false, scriptRequest = 0, fullScriptText = '';
const time = seconds => `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
const list = () => mode === 'cut' ? project.scenes : project.storyboard;
const sourceFor = scene => mode === 'cut' && project.master ? project.master : scene.media;
const sourceIn = scene => mode === 'cut' && project.master ? scene.start : scene.media_in;
function status(text, error = false) {
  $('status').textContent = text;
  $('status').classList.toggle('error', error);
}
function narration(scene) {
  $('scriptBody').replaceChildren(...(scene.text || 'No scene narration supplied. Open Full script to read the project script.')
    .split(/\n\n/).filter(Boolean).map(text => {
      const paragraph = document.createElement('p'); paragraph.textContent = text; return paragraph;
    }));
}
function activate(index, seek = true, autoplay = false) {
  if (!project) return;
  active = Math.max(0, Math.min(list().length - 1, index));
  const scene = list()[active];
  $('sceneTitle').textContent = scene.title;
  $('sceneCount').textContent = `${String(active + 1).padStart(2, '0')} / ${list().length}`;
  narration(scene);
  document.querySelectorAll('.scene-card').forEach((element, i) => element.classList.toggle('active', i === active));
  document.querySelectorAll('#pictureTrack button').forEach((element, i) => element.classList.toggle('active', i === active));
  $('previous').disabled = active === 0; $('next').disabled = active === list().length - 1;
  if (!seek) return;
  previewOffset = previewEnd = null;
  const source = sourceFor(scene), image = !(mode === 'cut' && project.master) && scene.media_type === 'image';
  player.pause(); player.onloadedmetadata = null;
  player.hidden = !source || image; $('stillImage').hidden = !source || !image; $('noMedia').hidden = !!source;
  if (source && image) {
    $('stillImage').src = source;
  } else if (source) {
    const setPosition = () => {
      player.currentTime = sourceIn(scene);
      if (autoplay && !readingScript) player.play().catch(() => status('Press play to continue.'));
    };
    player.muted = mode === 'story';
    if (player.getAttribute('src') !== source) {
      player.onloadedmetadata = setPosition; player.src = source; player.load();
    } else setPosition();
  }
  $('rangeIn').value = scene.start.toFixed(3);
  $('rangeOut').value = Math.min(project.duration, scene.start + Math.min(15, scene.duration)).toFixed(3);
  $('scrub').max = mode === 'cut' ? project.duration : scene.duration;
  $('scrub').value = mode === 'cut' ? scene.start : 0;
  $('clock').textContent = mode === 'cut' ? `${time(scene.start)} / ${time(project.duration)}` : `00:00 / ${time(scene.duration)}`;
  $('viewerTag').textContent = mode === 'story' ? 'VISUAL REFERENCE · AUDIO MUTED' : project.master ? 'FULL CUT' : 'SOURCE REVIEW';
  status(mode === 'story' ? 'Storyboard references are separate from the assembled cut.' : project.master ?
    'Review the full cut, or build a short range from the timeline.' :
    'Source review follows individual clips. Build a range to check the composed picture and audio.');
}
function renderNavigation() {
  $('scenes').replaceChildren(); $('pictureTrack').replaceChildren(); $('sceneTicks').replaceChildren();
  list().forEach((scene, index) => {
    const button = document.createElement('button'); button.className = 'scene-card';
    button.setAttribute('aria-label', `Scene ${index + 1}: ${scene.title}`);
    const number = document.createElement('span'); number.className = 'number'; number.textContent = String(index + 1).padStart(2, '0');
    const title = document.createElement('strong'); title.textContent = scene.title;
    const duration = document.createElement('span'); duration.className = 'duration'; duration.textContent = mode === 'cut' ? time(scene.start) : 'DRAFT';
    const kind = document.createElement('span'); kind.className = 'kind'; kind.textContent = mode === 'cut' ? `${scene.duration.toFixed(1)}s` : 'Visual reference';
    button.append(number, title, duration, kind); button.onclick = () => activate(index); $('scenes').append(button);
    const clip = document.createElement('button'); clip.textContent = index + 1; clip.title = scene.title;
    clip.setAttribute('aria-label', `Jump to ${scene.title}`); clip.style.flexGrow = mode === 'cut' ? scene.duration : 1;
    clip.onclick = () => activate(index); $('pictureTrack').append(clip);
    const tick = document.createElement('span'); tick.textContent = index % 2 === 0 ? String(index + 1).padStart(2, '0') : '';
    tick.style.flexGrow = mode === 'cut' ? scene.duration : 1; $('sceneTicks').append(tick);
  });
}
function closeFullScript() {
  readingScript = false; $('fullScriptPanel').hidden = true;
  document.querySelector('.workspace').hidden = false; document.querySelector('.scene-browser').hidden = false;
  $('fullScriptMode').classList.remove('selected'); $('fullScriptMode').setAttribute('aria-pressed', 'false');
}
async function showFullScript() {
  if (!project) return;
  readingScript = true; player.pause(); $('fullScriptPanel').hidden = false;
  document.querySelector('.workspace').hidden = true; document.querySelector('.scene-browser').hidden = true;
  $('cutMode').classList.remove('selected'); $('storyMode').classList.remove('selected');
  $('fullScriptMode').classList.add('selected'); $('fullScriptMode').setAttribute('aria-pressed', 'true');
  await loadFullScript();
}
async function loadFullScript() {
  const request = ++scriptRequest, current = $('scriptVersion').value === 'revised';
  fullScriptText = ''; $('copyScript').disabled = true; $('downloadScript').disabled = true;
  $('fullScriptTitle').textContent = current ? 'Current script' : 'Cut narration';
  $('fullScriptNote').textContent = current ? 'Complete current script file, including any visual directions and production notes. Script revisions may differ from the recorded cut.' : 'All supplied scene narration in timeline order.';
  $('fullScriptText').textContent = ''; $('scriptFeedback').textContent = 'Loading complete script…';
  try {
    let text;
    if (current) {
      const response = await fetch('/api/script'); const data = await response.json();
      if (!response.ok) throw Error(data.error || 'Script unavailable'); text = data.text;
    } else {
      text = project.scenes.filter(scene => scene.text.trim()).map(scene => `${scene.title} (${time(scene.start)})\n\n${scene.text}`).join('\n\n');
    }
    if (request !== scriptRequest) return;
    fullScriptText = text; $('fullScriptText').textContent = text || 'No narration supplied for these scenes.';
    $('scriptFeedback').textContent = `${text.trim().split(/\s+/).filter(Boolean).length.toLocaleString()} words · complete text`;
    $('copyScript').disabled = !text; $('downloadScript').disabled = !text;
  } catch (error) {
    if (request === scriptRequest) $('scriptFeedback').textContent = 'Could not load the script: ' + error.message + ' Select a version to retry.';
  }
}
$('fullScriptMode').onclick = showFullScript;
$('scriptVersion').onchange = loadFullScript;
$('copyScript').onclick = async () => {
  try { await navigator.clipboard.writeText(fullScriptText); $('scriptFeedback').textContent = 'Complete script copied.'; }
  catch (error) { $('scriptFeedback').textContent = 'Copy unavailable. Select the text below or download the script.'; }
};
$('downloadScript').onclick = () => {
  const url = URL.createObjectURL(new Blob([fullScriptText], { type: 'text/plain;charset=utf-8' }));
  const link = document.createElement('a'); link.href = url;
  link.download = $('scriptVersion').value === 'revised' ? 'current-script.txt' : 'cut-narration.txt';
  document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
};
function setMode(next) {
  if (!project || (next === 'story' && !project.storyboard.length)) return;
  closeFullScript(); player.pause(); mode = next; document.body.classList.toggle('storyboard', mode === 'story');
  $('cutMode').classList.toggle('selected', mode === 'cut'); $('storyMode').classList.toggle('selected', mode === 'story');
  $('viewLabel').textContent = mode === 'cut' ? 'EXISTING CUT' : 'STORYBOARD';
  $('scriptLabel').textContent = mode === 'cut' ? 'SCENE NARRATION' : 'STORYBOARD TEXT';
  $('scriptState').textContent = mode === 'cut' ? 'CUT' : 'DRAFT';
  $('editorNote').textContent = mode === 'cut' ? 'Read every scene together under Full script. The current script may differ from this cut.' :
    'Storyboard visuals are references, played muted. They do not establish that a new script has been recorded or rendered.';
  $('timelineLabel').textContent = mode === 'cut' ? 'ASSEMBLED TIMELINE' : 'CURRENT CHAPTER · VISUAL REFERENCE';
  $('browserTitle').textContent = mode === 'cut' ? 'Scenes' : 'Storyboard';
  $('fullCut').hidden = mode === 'story'; document.querySelector('.range-panel').hidden = !project.can_preview;
  $('fullCut').textContent = project.master ? 'Return to full cut ↗' : 'Return to source ↗';
  renderNavigation(); activate(0);
}
function position() {
  if (previewOffset !== null) return Math.min(previewEnd, player.currentTime + previewOffset);
  const scene = list()[active];
  if (mode === 'cut' && project.master) return player.currentTime;
  return Math.max(0, player.currentTime - scene.media_in) + (mode === 'cut' ? scene.start : 0);
}
player.addEventListener('timeupdate', () => {
  if (!project || readingScript || player.hidden) return;
  const scene = list()[active], value = position();
  if (mode === 'cut') {
    if (project.master || previewOffset !== null) {
      const index = project.scenes.findIndex(item => value >= item.start && value < item.start + item.duration);
      if (index >= 0 && index !== active) activate(index, false);
    } else if (value >= scene.start + scene.duration - .01) {
      player.pause(); if (active + 1 < list().length) activate(active + 1, true, true);
    }
    $('clock').textContent = `${time(Math.min(value, project.duration))} / ${time(project.duration)}`; $('scrub').value = value;
  } else {
    if (value >= scene.duration) player.pause();
    $('clock').textContent = `${time(Math.min(value, scene.duration))} / ${time(scene.duration)}`;
    $('scrub').value = Math.min(value, scene.duration);
  }
});
player.addEventListener('ended', () => {
  if (!readingScript && mode === 'cut' && !project.master && previewOffset === null && active + 1 < list().length) activate(active + 1, true, true);
});
$('scrub').addEventListener('input', () => {
  if (!project) return;
  const value = Number($('scrub').value);
  if (mode === 'story') { if (!player.hidden) player.currentTime = list()[active].media_in + value; return; }
  const index = project.scenes.findIndex(scene => value >= scene.start && value < scene.start + scene.duration);
  const chosen = index < 0 ? project.scenes.length - 1 : index;
  if (previewOffset !== null || (!project.master && chosen !== active)) activate(chosen);
  if (!player.hidden) player.currentTime = project.master ? value : sourceIn(list()[active]) + value - list()[active].start;
  $('clock').textContent = `${time(value)} / ${time(project.duration)}`;
});
$('cutMode').onclick = () => setMode('cut'); $('storyMode').onclick = () => setMode('story');
$('previous').onclick = () => activate(active - 1); $('next').onclick = () => activate(active + 1);
$('fullCut').onclick = () => activate(active);
$('renderPreview').onclick = async () => {
  if (!project || taskBusy) return;
  const start = Number($('rangeIn').value), end = Number($('rangeOut').value);
  if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end <= start || end > project.duration || end - start > 30) {
    status('Choose a valid range of up to 30 seconds within the cut.', true); return;
  }
  taskBusy = true; $('renderPreview').disabled = true; status(`Building ${time(start)}–${time(end)} from the scene timeline…`);
  try {
    const response = await fetch('/api/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ start, end }) });
    const result = await response.json(); if (!response.ok) throw Error(result.error);
    const deadline = Date.now() + 210000;
    while (true) {
      await new Promise(resolve => setTimeout(resolve, 1200));
      if (Date.now() > deadline) throw Error('Preview took too long. Reload to reconnect.');
      const taskResponse = await fetch('/api/tasks/' + result.task), task = await taskResponse.json();
      if (!taskResponse.ok || task.status === 'failed') throw Error(task.error || 'Preview unavailable');
      if (task.status === 'ready') {
        if (mode === 'cut' && !readingScript) {
          player.pause(); player.onloadedmetadata = null;
          previewOffset = start; previewEnd = end; player.hidden = false; $('stillImage').hidden = true; $('noMedia').hidden = true;
          player.src = task.media; player.muted = false; player.load(); $('viewerTag').textContent = 'RANGE PREVIEW · PIPELINE COMPOSITION';
        }
        status(`Preview ready · ${time(start)}–${time(end)}. Picture and audio passed the pipeline’s preview checks.`); break;
      }
    }
  } catch (error) { status('Preview could not be built: ' + error.message, true); }
  finally { taskBusy = false; $('renderPreview').disabled = false; }
};
player.addEventListener('error', () => { if (player.error && !player.hidden) status('This video could not be opened. Build a range preview or select another scene.', true); });
fetch('/api/project').then(response => {
  if (!response.ok) throw Error('Project unavailable'); return response.json();
}).then(data => {
  project = data; project.storyboard ??= [];
  document.title = project.title + ' · Editing workspace'; $('projectTitle').textContent = project.title;
  $('projectCrumb').textContent = project.title; $('projectSubtitle').textContent = project.subtitle || 'Review the story before the next export.';
  $('cutCount').textContent = `${project.scenes.length} scenes`; $('storyCount').textContent = `${project.storyboard.length} chapters`;
  $('storyMode').hidden = !project.storyboard.length;
  $('scriptVersion').querySelector('[value="revised"]').disabled = !project.has_script;
  $('scriptVersion').value = project.has_script ? 'revised' : 'existing';
  $('rangeIn').max = project.duration; $('rangeOut').max = project.duration;
  setMode('cut');
}).catch(error => status(error.message, true));
