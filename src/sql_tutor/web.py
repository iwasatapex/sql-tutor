from __future__ import annotations

import json
import logging
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from dataclasses import replace
from urllib.parse import urlparse

from sql_tutor.config import Settings
from sql_tutor.exercises.repository import ExerciseRepository
from sql_tutor.exercises.generator import ExerciseGenerator
from sql_tutor.learning.curriculum import Curriculum
from sql_tutor.learning.selector import ExerciseSelector
from sql_tutor.llm.base import LLMProviderError
from sql_tutor.llm.factory import create_provider
from sql_tutor.llm.ollama import list_models
from sql_tutor.storage.progress import ProgressStore
from sql_tutor.tutor.orchestrator import TutorOrchestrator
from sql_tutor.tutor.session import (
    ExerciseSetupError,
    LearningSession,
    NoActiveExerciseError,
    NoExercisesAvailableError,
)

logger = logging.getLogger(__name__)


class EmptySubmissionError(ValueError):
    """Raised when the learner submits empty SQL."""


HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SQL Tutor</title>
<style>
:root{color-scheme:dark;--bg:#0b1020;--panel:#121a2d;--panel2:#19243c;--text:#edf2ff;--muted:#9aa9c7;--accent:#7c9cff;--good:#5ee0a0;--bad:#ff8c9c;--border:#2b3a5c}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top right,#1d2d55 0,#0b1020 45%);color:var(--text);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;min-height:100vh}
.app{max-width:1440px;margin:auto;padding:28px}.top{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:24px}.brand{font-size:26px;font-weight:800;letter-spacing:-.8px}.brand span{color:var(--accent)}.sub{color:var(--muted);font-size:13px}.grid{display:grid;grid-template-columns:300px minmax(0,1fr) 360px;gap:20px;align-items:start}.panel{background:linear-gradient(180deg,rgba(18,26,45,.98),rgba(15,23,42,.96));border:1px solid var(--border);border-radius:18px;padding:20px;box-shadow:0 18px 60px #0003}.nav{display:flex;align-items:center;gap:28px;color:#b9c6e5;font-size:14px}.nav a{color:inherit;text-decoration:none;padding:10px 0}.nav a.active{color:var(--text);border-bottom:2px solid var(--accent)}.avatar{width:42px;height:42px;border-radius:50%;display:grid;place-items:center;background:#2a4b91;color:#fff;font-weight:800}.top-right{display:flex;align-items:center;gap:24px}.brand-mark{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--accent);margin-right:7px}.side{display:flex;flex-direction:column;gap:16px}.metric{display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--border)}.metric:last-child{border:0}.label{color:var(--muted)}.pill{display:inline-block;padding:4px 9px;border:1px solid var(--border);border-radius:999px;color:#c5d1f2;font-size:12px}.title{font-size:29px;font-weight:800;letter-spacing:-.8px;margin:12px 0}.exercise-topline{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}.desc{color:#c2cde4;margin-bottom:18px}.schema{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin:14px 0 20px}.table{background:var(--panel2);border:1px solid var(--border);border-radius:12px;padding:12px}.table b{display:block;margin-bottom:6px}.table div{color:var(--muted);font-size:13px}.selector{width:100%;background:var(--panel2);color:var(--text);border:1px solid var(--border);border-radius:10px;padding:10px;margin:8px 0 14px;font:inherit}.editor{width:100%;min-height:180px;resize:vertical;background:#0a0f1c;color:#e8efff;border:1px solid var(--border);border-radius:12px;padding:15px;font:14px/1.6 ui-monospace,SFMono-Regular,Consolas,monospace;outline:none}.editor:focus{border-color:var(--accent)}.actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:12px}button{cursor:pointer;border:1px solid var(--border);background:var(--panel2);color:var(--text);border-radius:10px;padding:10px 15px;font-weight:650}button.primary{background:var(--accent);color:#091024;border-color:transparent}button:hover{filter:brightness(1.12)}button:disabled{opacity:.5;cursor:not-allowed}.feedback{margin-top:18px;padding:15px;border-radius:12px;border:1px solid var(--border);background:#0d1526;white-space:pre-wrap}.feedback.good{border-color:#276d50}.feedback.bad{border-color:#75404c}.hint{margin-top:12px;color:#e8d99a}.result{overflow:auto;margin-top:12px}.result table{border-collapse:collapse;width:100%;font-size:13px}.result th,.result td{border:1px solid var(--border);padding:8px;text-align:left;white-space:nowrap}.result th{background:var(--panel2)}.progress-row{margin:12px 0}.bar{height:7px;background:#283552;border-radius:9px;overflow:hidden}.bar i{display:block;height:100%;background:var(--accent)}.empty{color:var(--muted);padding:24px;text-align:center}.footer{margin-top:20px;color:var(--muted);font-size:12px}.schema-flash{outline:2px solid var(--accent);outline-offset:3px;border-radius:12px}@media(max-width:1240px){.grid{grid-template-columns:260px minmax(0,1fr)}.right-column{grid-column:1 / -1;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}}@media(max-width:900px){.grid{grid-template-columns:1fr}.app{padding:16px}.top{align-items:flex-start;flex-direction:column}}
.debug-panel{margin:14px 0 18px;border:1px solid var(--border);border-radius:12px;background:var(--panel2);padding:14px}.debug-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}.debug-header h2{margin:0;font-size:16px;font-weight:700}.link-btn{background:none;border:none;color:var(--accent);cursor:pointer;font:inherit;font-size:13px;padding:4px 8px;border-radius:6px}.link-btn:hover{background:var(--panel)}.debug-panel pre{margin:0;background:#0b1020;border:1px solid var(--border);border-radius:8px;padding:12px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px;white-space:pre-wrap;word-break:break-word;color:var(--text);max-height:200px;overflow:auto}.predict-panel{margin:14px 0 18px;border:1px solid var(--border);border-radius:12px;background:var(--panel2);padding:14px}.predict-header{margin-bottom:12px}.predict-header h2{margin:0 0 4px;font-size:16px;font-weight:700}.query-display{background:#0b1020;border:1px solid var(--border);border-radius:8px;padding:12px;margin-bottom:14px}.query-display pre{margin:0;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px;white-space:pre-wrap;word-break:break-word;color:var(--text)}.predict-panel .editor{margin-bottom:12px}.explain-panel{margin:14px 0 18px;border:1px solid var(--border);border-radius:12px;background:var(--panel2);padding:14px}.explain-header{margin-bottom:12px}.explain-header h2{margin:0 0 4px;font-size:16px;font-weight:700}.explain-panel .editor{margin-bottom:12px}
</style>
</head>
<body><main class="app">
<header class="top"><div><div class="brand">SQL <span>Tutor</span></div><div class="sub">Adaptive practice • local-first • model agnostic</div></div><nav class="nav" aria-label="Primary"><a class="active" href="#practice">Practice</a><a href="#progress-panel">Progress</a><a href="#resources">Resources</a><a href="#settings">Settings</a></nav><div class="top-right"><div class="pill" id="status">Ready</div><div class="avatar">A</div></div></header>
<div class="grid" id="practice"><aside class="side"><section class="panel"><h2>Practice setup</h2><label class="label" for="topic">Topic</label><select id="topic" class="selector"><option value="">Adaptive (all topics)</option></select><div class="sub">Choose a SQL topic to practice.</div><label class="label" for="question-type">Question type</label><select id="question-type" class="selector"><option value="write">Write SQL</option><option value="debug">Debug SQL</option><option value="predict">Predict output</option><option value="explain">Explain SQL</option></select><div class="sub">Write SQL, fix buggy queries, predict output, or explain a query.</div><label class="label" for="difficulty">Difficulty</label><select id="difficulty" class="selector"><option value="adaptive">Adaptive</option><option value="beginner">Beginner</option><option value="intermediate">Intermediate</option><option value="advanced">Advanced</option></select><div class="sub">Adjust the challenge level.</div><button class="primary" id="generate">⟳ Generate new question</button></section><section class="panel"><h2>Session</h2><div class="metric"><span class="label">Attempts</span><strong id="attempts">0</strong></div><div class="metric"><span class="label">Correct</span><strong id="correct">0</strong></div><div class="metric"><span class="label">Accuracy</span><strong id="accuracy">0%</strong></div><div class="metric"><span class="label">Failed</span><strong id="failed">0</strong></div><div class="metric"><span class="label">Hints used</span><strong id="hints">0</strong></div><div class="actions"><button id="skip">Skip exercise</button><button id="next">Next exercise</button></div></section></aside><section class="panel"><div class="exercise-topline"><span class="pill">Practice workspace</span><span class="sub">Question-based learning</span></div><div id="exercise"><div class="empty">Loading exercise…</div></div><div id="debug-panel" class="debug-panel" style="display:none"><div class="debug-header"><h2>Broken query</h2><button id="copy-broken" class="link-btn">Copy to editor</button></div><pre><code id="broken-query-display"></code></pre><div class="sub">Find the bug and write the corrected query below.</div></div><div id="predict-panel" class="predict-panel" style="display:none"><div class="predict-header"><h2>Predict the output</h2><div class="sub">What does this query return? Write one line per row with columns separated by |; the first line is the column names.</div></div><div class="query-display"><pre id="predict-query-display"></pre></div><label for="prediction"><strong>Your predicted output</strong></label><textarea id="prediction" class="editor" spellcheck="false" placeholder="column1 | column2&#10;val1   | val2&#10;..."></textarea><div class="actions"><button class="primary" id="check-prediction">Check prediction</button></div></div><div id="explain-panel" class="explain-panel" style="display:none"><div class="explain-header"><h2>Explain this query</h2><div class="sub">Describe in your own words what the query returns and how it gets there. Mention the tables, columns and clauses it uses.</div></div><div class="query-display"><pre id="explain-query-display"></pre></div><label for="explanation"><strong>Your explanation</strong></label><textarea id="explanation" class="editor" spellcheck="true" placeholder="This query ..."></textarea><div class="actions"><button class="primary" id="check-explanation">Check explanation</button></div></div><label for="query"><strong>Your SQL</strong></label><textarea id="query" class="editor" spellcheck="false" placeholder="SELECT ...;"></textarea><div class="actions"><button class="primary" id="submit">Run & check</button><button id="hint">Get hint</button><button id="schema">Show schema</button></div><div id="feedback"></div><div class="footer">Your queries are evaluated locally. Use semicolon-terminated SELECT/WITH statements.</div></section><aside class="side right-column"><section class="panel" id="progress-panel"><h2>Learning progress</h2><div id="progress-content">Loading…</div></section><section class="panel"><h2>Recent performance</h2><div class="metric"><span class="label">Correct answers</span><strong id="recent-correct">0</strong></div><div class="metric"><span class="label">Incorrect answers</span><strong id="recent-failed">0</strong></div><div class="metric"><span class="label">Accuracy</span><strong id="recent-accuracy">0%</strong></div><div class="sub">Your session performance updates after each submission.</div></section></aside></div><section class="panel" id="resources"><h2>Resources</h2><div class="sub">Keyboard: Ctrl/Cmd+Enter submits the SQL in the editor, or checks the prediction or explanation. CLI commands: :hint, :schema, :skip, :help, :quit. Learner SQL must be a single SELECT/WITH statement; row order is only compared when the reference query uses ORDER BY.</div></section><section class="panel" id="settings"><h2>Settings</h2><label class="label" for="model">Local Ollama model</label><select id="model" class="selector"><option value="">Loading models…</option></select><div class="sub" id="provider-info">Local Ollama: loading…</div><div class="sub">Choose an installed Ollama model. Exercise generation and optional hints use it; SQL grading remains local.</div></section></main>
<script>
const $=id=>document.getElementById(id);let state=null;let submitInFlight=false;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,opts={}){const r=await fetch(path,{headers:{'Content-Type':'application/json'},...opts});let data=null;try{data=await r.json()}catch(e){throw Error('Request failed (status '+r.status+')')}if(!r.ok){const err=Error((data&&data.error)||'Request failed');err.status=r.status;err.payload=data;throw err}return data}
function renderProgress(items){$('progress-content').innerHTML=items.map(p=>`<div class="progress-row"><div class="metric"><span>${esc(p.title)}</span><span>${p.solved}/${p.total}</span></div><div class="bar"><i style="width:${Math.round(p.ratio*100)}%"></i></div><div class="sub">${esc(p.status)} · ${esc(p.accuracy)}</div></div>`).join('')||'<div class="sub">No progress yet.</div>'}
function renderExercise(e){if(!e){$('exercise').innerHTML='<div class="empty">No exercises available. Try another topic or difficulty.</div>';return}$('exercise').innerHTML=`<div><span class="pill">${esc(e.concept)}</span> <span class="pill">${esc(e.difficulty)}</span></div><div class="title">${esc(e.title)}</div><div class="desc">${esc(e.description)}</div><div class="schema">${e.schema.map(t=>`<div class="table"><b>${esc(t.name)}</b>${t.columns.map(c=>`<div>${esc(c.name)} · ${esc(c.type)}</div>`).join('')}</div>`).join('')}</div>`}
function renderStats(){if(!state)return;const attempts=Number(state.attempts||0),failed=Number(state.failed_attempts||0),correct=Math.max(0,attempts-failed),accuracy=attempts?Math.round(correct/attempts*100):0;$('attempts').textContent=attempts;$('correct').textContent=correct;$('accuracy').textContent=accuracy+'%';$('failed').textContent=failed;$('hints').textContent=state.hints_used;$('recent-correct').textContent=correct;$('recent-failed').textContent=failed;$('recent-accuracy').textContent=accuracy+'%'}
function renderFeedback(f,extra){if(!f){$('feedback').innerHTML='';return}const good=f.is_correct;$('feedback').innerHTML=`<div class="feedback ${good?'good':'bad'}"><strong>${esc(f.message)}</strong>${f.error?`\n\nError: ${esc(f.error)}`:(!good&&!f.error?`\n\n${esc(f.reason)}`:``)}${f.hint?`<div class="hint">Hint: ${esc(f.hint.message)}</div>`:''}${extra&&extra.actual?`<div class="actual-output">Actual output:<pre>${esc(extra.actual)}</pre></div>`:''}${extra&&extra.reference?`<div class="actual-output">Model answer:<pre>${esc(extra.reference)}</pre></div>`:''}</div>`}
async function refreshProgress(){renderProgress((await api('/api/progress')).items)}
function renderTopics(topics,selected){$('topic').innerHTML='<option value="">Adaptive (all topics)</option>'+topics.map(t=>`<option value="${esc(t)}" ${t===selected?'selected':''}>${esc(t)}</option>`).join('')}
function renderDifficulty(selected){const v=selected||'adaptive';if($('difficulty').value!==v)$('difficulty').value=v}
function renderQuestionType(selected){const v=selected||'write';if($('question-type').value!==v)$('question-type').value=v}
function renderDebugPanel(e){const panel=$('debug-panel');const display=$('broken-query-display');const copy=$('copy-broken');if(!panel||!e){if(panel)panel.style.display='none';return}if(e.question_type==='debug'&&e.broken_query){$('debug-panel').style.display='';$('broken-query-display').textContent=e.broken_query;if(copy){copy.onclick=()=>{$('query').value=e.broken_query;$('query').focus();$('status').textContent='Bug copied to editor'}}}else{if(panel)panel.style.display='none'}}
function renderPredictPanel(e){const panel=$('predict-panel');const queryDisplay=$('predict-query-display');const predictionInput=$('prediction');const checkBtn=$('check-prediction');if(!panel||!e){if(panel)panel.style.display='none';return}if(e.question_type==='predict'){$('predict-panel').style.display='';$('predict-query-display').textContent=e.query||'';$('query').value='';if(predictionInput)predictionInput.value='';if(checkBtn)checkBtn.onclick=checkPrediction}else{if(panel)panel.style.display='none'}}
function renderExplainPanel(e){const panel=$('explain-panel');const queryDisplay=$('explain-query-display');const explanationInput=$('explanation');if(!panel||!e){if(panel)panel.style.display='none';return}if(e.question_type==='explain'){panel.style.display='';if(queryDisplay)queryDisplay.textContent=e.query||'';$('query').value='';if(explanationInput)explanationInput.value=''}else{panel.style.display='none'}}
function renderState(payload){renderTopics(payload.topics,payload.selected_topic);renderDifficulty(payload.selected_difficulty);renderQuestionType(payload.question_type);renderExercise(payload.exercise);renderDebugPanel(payload.exercise);renderPredictPanel(payload.exercise);renderExplainPanel(payload.exercise);renderStats();renderFeedback(payload.feedback)}
function applyState(payload){state=payload;window.__sqlTutorState=payload;renderState(payload)}
async function chooseTopic(){if(requestBusy())return;setBusy(true);try{applyState(await api('/api/topic',{method:'POST',body:JSON.stringify({concept:$('topic').value})}));await refreshProgress();$('query').value='';$('status').textContent='Ready'}catch(e){$('status').textContent=e.message}finally{setBusy(false)}}
async function chooseDifficulty(){if(requestBusy())return;setBusy(true);try{applyState(await api('/api/difficulty',{method:'POST',body:JSON.stringify({difficulty:$('difficulty').value})}));await refreshProgress();$('query').value='';$('status').textContent='Ready'}catch(e){$('status').textContent=e.message}finally{setBusy(false)}}
async function chooseQuestionType(){if(requestBusy())return;setBusy(true);try{applyState(await api('/api/question-type',{method:'POST',body:JSON.stringify({question_type:$('question-type').value})}));await refreshProgress();$('query').value='';$('status').textContent='Ready'}catch(e){const prev=state&&state.question_type;if(prev)renderQuestionType(prev);$('status').textContent=e.message}finally{setBusy(false)}}
async function generate(){if(requestBusy())return;setBusy(true);try{applyState(await api('/api/generate',{method:'POST',body:JSON.stringify({concept:$('topic').value||null,difficulty:$('difficulty').value,question_type:$('question-type').value})}));await refreshProgress();$('query').value='';$('status').textContent='Ready'}catch(e){$('status').textContent=e.message}finally{setBusy(false)}}
async function load(){try{state=await api('/api/session');window.__sqlTutorState=state;renderState(state);await refreshProgress();await loadConfig();$('status').textContent=state.available===false?(state.message||state.error||'No exercises available'):'Ready'}catch(e){$('status').textContent=e.message;$('exercise').innerHTML=`<div class="empty">${esc(e.message)}</div>`}}
async function submit(){
const qt=state&&state.question_type||'write';
if(qt==='predict'){await checkPrediction();return}
if(qt==='explain'){await checkExplanation();return}
const query=$('query').value.trim();
if(!query||submitInFlight)return;

submitInFlight=true;
$('submit').disabled=true;
$('status').textContent='Checking…';

try{
state=await api('/api/submit',{
method:'POST',
body:JSON.stringify({query})
});
window.__sqlTutorState=state;
renderStats();
renderFeedback(state.feedback);
await refreshProgress();

if(!state.feedback||!state.feedback.is_correct){
$('status').textContent='Answer checked';
return;
}

$('status').textContent='Correct';
await new Promise(resolve=>setTimeout(resolve,700));

$('status').textContent='Loading next question…';
await action('/api/next',{throwOnError:true});
$('status').textContent='Ready';
}catch(e){
$('status').textContent=e.message;
}finally{
submitInFlight=false;
$('submit').disabled=false;
}
}
async function checkPrediction(){
const prediction=$('prediction').value.trim();
if(!prediction||submitInFlight)return;
submitInFlight=true;
$('check-prediction').disabled=true;
$('status').textContent='Checking…';
try{
state=await api('/api/predict',{method:'POST',body:JSON.stringify({prediction})});
window.__sqlTutorState=state;
renderPredictPanel(state.exercise);
renderStats();
renderFeedback(state.feedback,{actual:state.actual_output});
await refreshProgress();
if(!state.feedback||!state.feedback.is_correct){
$('status').textContent='Answer checked';
return;
}
$('status').textContent='Correct';
await new Promise(resolve=>setTimeout(resolve,700));
$('status').textContent='Loading next question…';
await action('/api/next',{throwOnError:true});
$('status').textContent='Ready';
}catch(e){
$('status').textContent=e.message;
}finally{
submitInFlight=false;
$('check-prediction').disabled=false;
}
}
async function checkExplanation(){
const explanation=$('explanation').value.trim();
if(!explanation||submitInFlight)return;
submitInFlight=true;
$('check-explanation').disabled=true;
$('status').textContent='Checking…';
try{
state=await api('/api/explain',{method:'POST',body:JSON.stringify({explanation})});
window.__sqlTutorState=state;
renderStats();
renderFeedback(state.feedback,{reference:state.reference_explanation});
await refreshProgress();
if(!state.feedback||!state.feedback.is_correct){
$('status').textContent='Answer checked';
return;
}
$('status').textContent='Correct';
await new Promise(resolve=>setTimeout(resolve,700));
$('status').textContent='Loading next question…';
await action('/api/next',{throwOnError:true});
$('status').textContent='Ready';
}catch(e){
$('status').textContent=e.message;
}finally{
submitInFlight=false;
$('check-explanation').disabled=false;
}
}
function setBusy(busy){['generate','skip','next','hint','schema','topic','question-type','difficulty','model'].forEach(id=>{const el=$(id);if(el)el.disabled=busy})}
function requestBusy(){return submitInFlight}
async function loadConfig(){try{const cfg=await api('/api/config');const model=$('model');model.innerHTML='';for(const name of cfg.models||[]){const option=document.createElement('option');option.value=name;option.textContent=name;model.appendChild(option)}if(cfg.model)model.value=cfg.model;$('provider-info').textContent='Local Ollama'+(cfg.model?' ('+cfg.model+')':' (choose a model)')+' · Question types: '+cfg.question_types.join(', ')}catch(e){$('provider-info').textContent='Local Ollama unavailable: '+e.message}}
async function action(path,opts={}){const throwOnError=!!opts.throwOnError;if(submitInFlight&&!throwOnError)return;setBusy(true);try{applyState(await api(path,{method:'POST'}));$('query').value='';await refreshProgress();$('status').textContent='Ready'}catch(e){$('status').textContent=e.message;if(throwOnError)throw e}finally{setBusy(false)}}
$('topic').onchange=chooseTopic;$('difficulty').onchange=chooseDifficulty;$('question-type').onchange=chooseQuestionType;$('generate').onclick=generate;$('submit').onclick=submit;$('hint').onclick=async()=>{try{const d=await api('/api/hint',{method:'POST'});$('feedback').innerHTML=`<div class="feedback"><div class="hint">Hint: ${esc(d.hint)}</div></div>`;state.hints_used=d.hints_used;renderStats()}catch(e){$('status').textContent=e.message}};$('schema').onclick=()=>{const panel=document.querySelector('.schema');if(!panel){$('status').textContent='No schema to show yet';return}panel.scrollIntoView({behavior:'smooth',block:'nearest'});panel.classList.remove('schema-flash');void panel.offsetWidth;panel.classList.add('schema-flash')};$('skip').onclick=()=>action('/api/skip');$('next').onclick=()=>action('/api/next');document.querySelectorAll('.nav a').forEach(a=>{a.addEventListener('click',()=>{document.querySelectorAll('.nav a').forEach(o=>o.classList.remove('active'));a.classList.add('active')})});$('query').addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter')submit()});$('check-explanation').onclick=checkExplanation;$('explanation').addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter')checkExplanation()});load();
 $('model').onchange=async()=>{if(!$('model').value)return;setBusy(true);try{applyState(await api('/api/model',{method:'POST',body:JSON.stringify({model:$('model').value})}));$('status').textContent='Using '+$('model').value;await loadConfig()}catch(e){$('status').textContent=e.message}finally{setBusy(false)}};
</script></body></html>'''


def _exercise_payload(exercise):
    payload = {
        "id": exercise.exercise_id,
        "title": exercise.title,
        "description": exercise.description,
        "concept": exercise.concept,
        "difficulty": exercise.difficulty.value,
        "question_type": exercise.question_type.value,
        "broken_query": exercise.broken_query,
        "schema": [
            {"name": table.name, "columns": [{"name": c.name, "type": c.data_type} for c in table.columns]}
            for table in exercise.schema
        ],
    }

    # Predict and Explain questions are about a query the learner reads
    # instead of writes, so only those types receive it: for Write and
    # Debug questions the reference query is the answer.
    if exercise.question_type.value in _READ_ONLY_QUESTION_TYPES:
        payload["query"] = exercise.expected_query

    return payload


def _session_topics(curriculum):
    return [topic.title for topic in curriculum.topics]


_SUPPORTED_QUESTION_TYPES = ("write", "debug", "predict", "explain")

#: Question types whose question text *is* the reference query.
_READ_ONLY_QUESTION_TYPES = ("predict", "explain")


class TutorWebApp:
    def __init__(self, settings: Settings):
        self.settings = settings
        if settings.llm_provider not in {"ollama", "mock"}:
            raise LLMProviderError(
                "The web UI supports local Ollama only."
            )
        if settings.llm_base_url and urlparse(settings.llm_base_url).hostname not in {
            "localhost", "127.0.0.1", "::1"
        }:
            raise LLMProviderError(
                "Ollama must use a local base URL (localhost, 127.0.0.1, or ::1)."
            )
        self.repository = ExerciseRepository.from_directory(settings.data_dir)
        self.store = ProgressStore(str(settings.database_path))
        provider = create_provider(settings) if settings.llm_model else None
        self.curriculum = Curriculum.default()
        self.session = LearningSession(
            repository=self.repository,
            selector=ExerciseSelector(self.curriculum, self.repository),
            progress_store=self.store,
            orchestrator=TutorOrchestrator(progress_store=self.store, llm_provider=provider),
            generator=(ExerciseGenerator(provider, max_attempts=2, verify=True)
                       if provider is not None else None),
        )
        self.lock = threading.RLock()
        try:
            self.session.start()
        except NoExercisesAvailableError as error:
            logger.warning("Web session started without an exercise: %s", error)
        except ExerciseSetupError as error:
            logger.warning("Web session started without an exercise: %s", error)

    def close(self):
        self.session.close()
        self.store.close()

    def describe(self):
        models = (
            list_models(
                self.settings.llm_base_url or "http://127.0.0.1:11434"
            )
            if self.settings.llm_provider == "ollama"
            else ()
        )
        return {
            "provider": self.settings.llm_provider,
            "model": self.settings.llm_model,
            "models": models,
            "question_types": list(_SUPPORTED_QUESTION_TYPES),
        }

    def choose_model(self, model: str):
        models = list_models(
            self.settings.llm_base_url or "http://127.0.0.1:11434"
        )
        if model not in models:
            raise ValueError(f"Ollama model is not installed: {model}")
        self.settings = replace(self.settings, llm_model=model)
        provider = create_provider(self.settings)
        self.session.orchestrator = TutorOrchestrator(
            progress_store=self.store,
            llm_provider=provider,
        )
        self.session.generator = ExerciseGenerator(
            provider, max_attempts=2, verify=True
        )
        exercise = self.session.next_exercise()
        if exercise is None:
            raise NoExercisesAvailableError("No exercises available")
        return self._state_or_raise()

    def state(self):
        with self.lock:
            current = self.session.current
            if current is None:
                try:
                    self.session.start()
                except (NoExercisesAvailableError, ExerciseSetupError) as error:
                    return self._empty_state(str(error))
                current = self.session.current
                if current is None:
                    return self._empty_state("No exercises available")
            feedback = self.session.state.last_feedback if self.session.state else None
            return {
                "available": True,
                "exercise": _exercise_payload(current),
                "attempts": self.session.state.attempts if self.session.state else 0,
                "failed_attempts": self.session.failed_attempts,
                "hints_used": self.session.hints_used,
                "feedback": _feedback_payload(feedback),
                "selected_topic": self.session.selected_concept,
                "selected_difficulty": self._difficulty_label(),
                "question_type": self.session.selected_question_type,
                "supported_question_types": list(_SUPPORTED_QUESTION_TYPES),
                "topics": _session_topics(self.curriculum),
            }

    def _empty_state(self, message):
        return {
            "available": False,
            "error": "No exercises available",
            "message": message,
            "exercise": None,
            "attempts": 0,
            "failed_attempts": self.session.failed_attempts,
            "hints_used": self.session.hints_used,
            "feedback": None,
            "selected_topic": self.session.selected_concept,
            "selected_difficulty": self._difficulty_label(),
            "question_type": self.session.selected_question_type,
            "supported_question_types": list(_SUPPORTED_QUESTION_TYPES),
            "topics": _session_topics(self.curriculum),
        }

    def _difficulty_label(self):
        selected = self.session.selected_difficulty
        return selected.value if selected is not None else "adaptive"

    def _state_or_raise(self):
        payload = self.state()
        if not payload.get("available"):
            raise NoExercisesAvailableError(
                payload.get("message") or "No exercises available"
            )
        return payload

    def submit(self, query):
        with self.lock:
            if not str(query or "").strip():
                raise EmptySubmissionError("SQL query cannot be empty")
            outcome = self.session.submit(query)
            payload = self._state_or_raise()
            return {**payload, "feedback": _feedback_payload(outcome.feedback)}

    def predict(self, prediction: str) -> dict:
        with self.lock:
            if not str(prediction or "").strip():
                raise EmptySubmissionError("Prediction cannot be empty")
            outcome = self.session.submit_prediction(prediction)
            payload = self._state_or_raise()
            return {
                **payload,
                "feedback": _feedback_payload(outcome.feedback),
                "actual_output": outcome.actual_output,
            }

    def explain(self, explanation: str) -> dict:
        with self.lock:
            if not str(explanation or "").strip():
                raise EmptySubmissionError("Explanation cannot be empty")
            outcome = self.session.submit_explanation(explanation)
            payload = self._state_or_raise()
            return {
                **payload,
                "feedback": _feedback_payload(outcome.feedback),
                "reference_explanation": outcome.reference_explanation,
                "matched_terms": list(outcome.grade.matched),
                "missing_terms": list(outcome.grade.missing),
                "coverage": round(outcome.grade.coverage, 2),
            }

    def _next_payload(self, loader):
        with self.lock:
            exercise = loader()
            if exercise is None:
                raise NoExercisesAvailableError("No exercises available")
            return self._state_or_raise()

    def choose_topic(self, concept: str | None):
        with self.lock:
            self._set_topic_value(concept)
            exercise = self.session.next_exercise()
            if exercise is None:
                if concept:
                    raise NoExercisesAvailableError(
                        f"No exercises available for topic {concept!r}"
                    )
                raise NoExercisesAvailableError("No exercises available")
            return self._state_or_raise()

    def choose_difficulty(self, difficulty: str | None):
        with self.lock:
            self._set_difficulty_value(difficulty)
            exercise = self.session.next_exercise()
            if exercise is None:
                raise NoExercisesAvailableError(
                    "No exercises available for the selected difficulty"
                )
            return self._state_or_raise()

    def choose_question_type(self, question_type: str | None):
        with self.lock:
            self.session.set_question_type(question_type or "write")
            exercise = self.session.next_exercise()
            if exercise is None:
                raise NoExercisesAvailableError("No exercises available")
            return self._state_or_raise()

    def generate(self, concept=None, difficulty=None, question_type=None):
        with self.lock:
            self._set_topic_value(concept)
            self._set_difficulty_value(difficulty)
            if question_type is not None:
                self.session.set_question_type(question_type)
            exercise = self.session.next_exercise()
            if exercise is None:
                raise NoExercisesAvailableError(
                    "No exercises available for the selected options"
                )
            return self._state_or_raise()

    def _set_topic_value(self, concept):
        if concept is None:
            self.session.set_topic(None)
            return
        text = str(concept).strip()
        self.session.set_topic(text or None)

    def _set_difficulty_value(self, difficulty):
        if difficulty is None:
            self.session.set_difficulty(None)
            return
        text = str(difficulty).strip().lower()
        if text in {"", "adaptive", "auto"}:
            self.session.set_difficulty(None)
            return
        self.session.set_difficulty(text)

    def hint(self):
        with self.lock:
            hint = self.session.request_hint()
            return {"hint": hint.message, "hints_used": self.session.hints_used}

    def next(self):
        return self._next_payload(self.session.next)

    def skip(self):
        def _skip_and_advance():
            self.session.skip()
            return self.session.next_exercise()
        return self._next_payload(_skip_and_advance)

    def progress(self):
        items = []
        for progress in self.session.topic_progress():
            items.append({
                "title": progress.topic.title,
                "solved": progress.solved,
                "total": progress.total_exercises,
                "ratio": progress.solved / progress.total_exercises if progress.total_exercises else 0,
                "status": "done" if progress.is_complete else ("in progress" if progress.attempts else "not started"),
                "accuracy": f"{progress.mastery.accuracy:.0%} recent accuracy" if progress.attempts else "No attempts",
            })
        return {"items": items}


def _feedback_payload(feedback):
    if feedback is None:
        return None
    return {
        "is_correct": feedback.is_correct,
        "message": feedback.message,
        "reason": feedback.reason,
        "error": feedback.error,
        "hint": {"message": feedback.hint.message} if feedback.hint else None,
    }


def serve(settings: Settings, host="127.0.0.1", port=8765, open_browser=False):
    if host not in {"127.0.0.1", "localhost", "::1"} and not os.environ.get("SQL_TUTOR_ALLOW_EXTERNAL_WEB"):
        raise ValueError(
            "Refusing to bind the web UI to a non-loopback host. "
            "Set SQL_TUTOR_ALLOW_EXTERNAL_WEB=1 to opt in explicitly."
        )
    app = TutorWebApp(settings)

    class Handler(BaseHTTPRequestHandler):
        server_version = "SQLTutor/1.0"

        def _send(self, status, payload, content_type="application/json"):
            try:
                body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            except (TypeError, ValueError) as error:
                status = 500
                body = json.dumps({"error": f"Could not encode response: {error}"}).encode()
                content_type = "application/json"
            try:
                self.send_response(status)
                self.send_header("Content-Type", f"{content_type}; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _read_json_payload(self):
            raw_length = self.headers.get("Content-Length", "0")
            try:
                length = int(raw_length or "0")
            except (TypeError, ValueError):
                raise EmptySubmissionError(
                    "Request must include a valid Content-Length header"
                )
            if length < 0 or length > 1_000_000:
                raise EmptySubmissionError("Request body has an invalid length")
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw or b"{}")
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                raise EmptySubmissionError(f"Request body must be JSON: {error}")
            if not isinstance(payload, dict):
                raise EmptySubmissionError("Request body must be a JSON object")
            return payload

        def _status_for(self, error):
            if isinstance(error, NoExercisesAvailableError):
                return 409
            if isinstance(error, (NoActiveExerciseError, EmptySubmissionError, ValueError)):
                return 400
            if isinstance(error, ExerciseSetupError):
                return 500
            if isinstance(error, LLMProviderError):
                return 502
            return 500

        def _error_payload(self, error):
            return {
                "available": isinstance(error, NoExercisesAvailableError),
                "error": str(error) or type(error).__name__,
                "type": type(error).__name__,
            }

        def do_GET(self):
            path = urlparse(self.path).path
            try:
                if path == "/":
                    self._send(200, HTML.encode(), "text/html")
                elif path == "/api/session":
                    self._send(200, app.state())
                elif path == "/api/progress":
                    self._send(200, app.progress())
                elif path == "/api/config":
                    self._send(200, app.describe())
                else:
                    self._send(404, {"error": "Not found"})
            except BrokenPipeError:
                pass
            except ConnectionResetError:
                pass
            except Exception as error:  # keep every GET a valid JSON reply
                logger.exception("GET %s failed", path)
                self._send(self._status_for(error), self._error_payload(error))

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                payload = self._read_json_payload()
                if path == "/api/submit":
                    result = app.submit(str(payload.get("query", "")))
                elif path == "/api/topic":
                    result = app.choose_topic(payload.get("concept") or None)
                elif path == "/api/difficulty":
                    result = app.choose_difficulty(payload.get("difficulty"))
                elif path == "/api/question-type":
                    result = app.choose_question_type(payload.get("question_type"))
                elif path == "/api/generate":
                    result = app.generate(
                        payload.get("concept"),
                        payload.get("difficulty"),
                        payload.get("question_type"),
                    )
                elif path == "/api/model":
                    result = app.choose_model(str(payload.get("model", "")))
                elif path == "/api/hint":
                    result = app.hint()
                elif path == "/api/next":
                    result = app.next()
                elif path == "/api/skip":
                    result = app.skip()
                elif path == "/api/predict":
                    result = app.predict(str(payload.get("prediction", "")))
                elif path == "/api/explain":
                    result = app.explain(str(payload.get("explanation", "")))
                else:
                    self._send(404, {"error": "Not found"})
                    return
                self._send(200, result)
            except BrokenPipeError:
                pass
            except ConnectionResetError:
                pass
            except Exception as error:  # keep every POST a valid JSON reply
                logger.exception("POST %s failed", path)
                self._send(self._status_for(error), self._error_payload(error))

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"
    print(f"SQL Tutor UI: {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.close()
