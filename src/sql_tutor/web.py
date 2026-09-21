from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from sql_tutor.config import Settings
from sql_tutor.exercises.repository import ExerciseRepository
from sql_tutor.exercises.generator import ExerciseGenerator
from sql_tutor.learning.curriculum import Curriculum
from sql_tutor.learning.selector import ExerciseSelector
from sql_tutor.llm.base import LLMProviderError
from sql_tutor.llm.factory import create_provider
from sql_tutor.storage.progress import ProgressStore
from sql_tutor.tutor.orchestrator import TutorOrchestrator
from sql_tutor.tutor.session import LearningSession, NoExercisesAvailableError


HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SQL Tutor</title>
<style>
:root{color-scheme:dark;--bg:#0b1020;--panel:#121a2d;--panel2:#19243c;--text:#edf2ff;--muted:#9aa9c7;--accent:#7c9cff;--good:#5ee0a0;--bad:#ff8c9c;--border:#2b3a5c}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top right,#1d2d55 0,#0b1020 45%);color:var(--text);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;min-height:100vh}
.app{max-width:1440px;margin:auto;padding:28px}.top{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:24px}.brand{font-size:26px;font-weight:800;letter-spacing:-.8px}.brand span{color:var(--accent)}.sub{color:var(--muted);font-size:13px}.grid{display:grid;grid-template-columns:300px minmax(0,1fr) 360px;gap:20px;align-items:start}.panel{background:linear-gradient(180deg,rgba(18,26,45,.98),rgba(15,23,42,.96));border:1px solid var(--border);border-radius:18px;padding:20px;box-shadow:0 18px 60px #0003}.nav{display:flex;align-items:center;gap:28px;color:#b9c6e5;font-size:14px}.nav a{color:inherit;text-decoration:none;padding:10px 0}.nav a.active{color:var(--text);border-bottom:2px solid var(--accent)}.avatar{width:42px;height:42px;border-radius:50%;display:grid;place-items:center;background:#2a4b91;color:#fff;font-weight:800}.top-right{display:flex;align-items:center;gap:24px}.brand-mark{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--accent);margin-right:7px}.side{display:flex;flex-direction:column;gap:16px}.metric{display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--border)}.metric:last-child{border:0}.label{color:var(--muted)}.pill{display:inline-block;padding:4px 9px;border:1px solid var(--border);border-radius:999px;color:#c5d1f2;font-size:12px}.title{font-size:29px;font-weight:800;letter-spacing:-.8px;margin:12px 0}.exercise-topline{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}.desc{color:#c2cde4;margin-bottom:18px}.schema{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin:14px 0 20px}.table{background:var(--panel2);border:1px solid var(--border);border-radius:12px;padding:12px}.table b{display:block;margin-bottom:6px}.table div{color:var(--muted);font-size:13px}.selector{width:100%;background:var(--panel2);color:var(--text);border:1px solid var(--border);border-radius:10px;padding:10px;margin:8px 0 14px;font:inherit}.editor{width:100%;min-height:180px;resize:vertical;background:#0a0f1c;color:#e8efff;border:1px solid var(--border);border-radius:12px;padding:15px;font:14px/1.6 ui-monospace,SFMono-Regular,Consolas,monospace;outline:none}.editor:focus{border-color:var(--accent)}.actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:12px}button{cursor:pointer;border:1px solid var(--border);background:var(--panel2);color:var(--text);border-radius:10px;padding:10px 15px;font-weight:650}button.primary{background:var(--accent);color:#091024;border-color:transparent}button:hover{filter:brightness(1.12)}button:disabled{opacity:.5;cursor:not-allowed}.feedback{margin-top:18px;padding:15px;border-radius:12px;border:1px solid var(--border);background:#0d1526;white-space:pre-wrap}.feedback.good{border-color:#276d50}.feedback.bad{border-color:#75404c}.hint{margin-top:12px;color:#e8d99a}.result{overflow:auto;margin-top:12px}.result table{border-collapse:collapse;width:100%;font-size:13px}.result th,.result td{border:1px solid var(--border);padding:8px;text-align:left;white-space:nowrap}.result th{background:var(--panel2)}.progress-row{margin:12px 0}.bar{height:7px;background:#283552;border-radius:9px;overflow:hidden}.bar i{display:block;height:100%;background:var(--accent)}.empty{color:var(--muted);padding:24px;text-align:center}.footer{margin-top:20px;color:var(--muted);font-size:12px}@media(max-width:1240px){.grid{grid-template-columns:260px minmax(0,1fr)}.right-column{grid-column:1 / -1;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}}@media(max-width:900px){.grid{grid-template-columns:1fr}.app{padding:16px}.top{align-items:flex-start;flex-direction:column}}
</style>
</head>
<body><main class="app">
<header class="top"><div><div class="brand">SQL <span>Tutor</span></div><div class="sub">Adaptive practice • local-first • model agnostic</div></div><nav class="nav" aria-label="Primary"><a class="active" href="#practice">Practice</a><a href="#progress">Progress</a><a href="#resources">Resources</a><a href="#settings">Settings</a></nav><div class="top-right"><div class="pill" id="status">Ready</div><div class="avatar">A</div></div></header>
<div class="grid" id="practice"><aside class="side"><section class="panel"><h2>Practice setup</h2><label class="label" for="topic">Topic</label><select id="topic" class="selector"><option value="">Adaptive (all topics)</option></select><div class="sub">Choose a SQL topic to practice.</div><label class="label" for="question-type">Question type</label><select id="question-type" class="selector"><option>Write SQL</option><option>Debug SQL</option><option>Predict output</option><option>Explain SQL</option></select><div class="sub">Choose how you want to practice.</div><label class="label" for="difficulty">Difficulty</label><select id="difficulty" class="selector"><option value="adaptive">Adaptive</option><option value="beginner">Beginner</option><option value="intermediate">Intermediate</option><option value="advanced">Advanced</option></select><div class="sub">Adjust the challenge level.</div><button class="primary" id="generate">⟳ Generate new question</button></section><section class="panel"><h2>Session</h2><div class="metric"><span class="label">Attempts</span><strong id="attempts">0</strong></div><div class="metric"><span class="label">Correct</span><strong id="correct">0</strong></div><div class="metric"><span class="label">Accuracy</span><strong id="accuracy">0%</strong></div><div class="metric"><span class="label">Failed</span><strong id="failed">0</strong></div><div class="metric"><span class="label">Hints used</span><strong id="hints">0</strong></div><div class="actions"><button id="skip">Skip exercise</button><button id="next">Next exercise</button></div></section></aside><section class="panel"><div class="exercise-topline"><span class="pill">Practice workspace</span><span class="sub">Question-based learning</span></div><div id="exercise"><div class="empty">Loading exercise…</div></div><label for="query"><strong>Your SQL</strong></label><textarea id="query" class="editor" spellcheck="false" placeholder="SELECT ...;"></textarea><div class="actions"><button class="primary" id="submit">Run & check</button><button id="hint">Get hint</button><button id="schema">Show schema</button></div><div id="feedback"></div><div class="footer">Your queries are evaluated locally. Use semicolon-terminated SELECT/WITH statements.</div></section><aside class="side right-column"><section class="panel" id="progress"><h2>Learning progress</h2><div id="progress">Loading…</div></section><section class="panel"><h2>Recent performance</h2><div class="metric"><span class="label">Correct answers</span><strong id="recent-correct">0</strong></div><div class="metric"><span class="label">Incorrect answers</span><strong id="recent-failed">0</strong></div><div class="metric"><span class="label">Accuracy</span><strong id="recent-accuracy">0%</strong></div><div class="sub">Your session performance updates after each submission.</div></section></aside></div></main>
<script>
const $=id=>document.getElementById(id);let state=null;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,opts={}){const r=await fetch(path,{headers:{'Content-Type':'application/json'},...opts});const data=await r.json();if(!r.ok)throw Error(data.error||'Request failed');return data}
function renderProgress(items){$('progress').innerHTML=items.map(p=>`<div class="progress-row"><div class="metric"><span>${esc(p.title)}</span><span>${p.solved}/${p.total}</span></div><div class="bar"><i style="width:${Math.round(p.ratio*100)}%"></i></div><div class="sub">${esc(p.status)} · ${esc(p.accuracy)}</div></div>`).join('')||'<div class="sub">No progress yet.</div>'}
function renderExercise(e){$('exercise').innerHTML=`<div><span class="pill">${esc(e.concept)}</span> <span class="pill">${esc(e.difficulty)}</span></div><div class="title">${esc(e.title)}</div><div class="desc">${esc(e.description)}</div><div class="schema">${e.schema.map(t=>`<div class="table"><b>${esc(t.name)}</b>${t.columns.map(c=>`<div>${esc(c.name)} · ${esc(c.type)}</div>`).join('')}</div>`).join('')}</div>`}
function renderStats(){if(!state)return;const attempts=Number(state.attempts||0),failed=Number(state.failed_attempts||0),correct=Math.max(0,attempts-failed),accuracy=attempts?Math.round(correct/attempts*100):0;$('attempts').textContent=attempts;$('correct').textContent=correct;$('accuracy').textContent=accuracy+'%';$('failed').textContent=failed;$('hints').textContent=state.hints_used;$('recent-correct').textContent=correct;$('recent-failed').textContent=failed;$('recent-accuracy').textContent=accuracy+'%'}
function renderFeedback(f){if(!f){$('feedback').innerHTML='';return}const good=f.is_correct;$('feedback').innerHTML=`<div class="feedback ${good?'good':'bad'}"><strong>${esc(f.message)}</strong>${f.error?`\n\nError: ${esc(f.error)}`:''}${!good&&!f.error?`\n\n${esc(f.reason)}`:''}${f.hint?`<div class="hint">Hint: ${esc(f.hint.message)}</div>`:''}</div>`}
async function refreshProgress(){renderProgress((await api('/api/progress')).items)}
function renderTopics(topics,selected){$('topic').innerHTML='<option value="">Adaptive (all topics)</option>'+topics.map(t=>`<option value="${esc(t)}" ${t===selected?'selected':''}>${esc(t)}</option>`).join('')}
async function chooseTopic(){try{state=await api('/api/topic',{method:'POST',body:JSON.stringify({concept:$('topic').value})});renderTopics(state.topics,state.selected_topic);renderExercise(state.exercise);renderStats();renderFeedback(state.feedback);await refreshProgress();$('query').value='';$('status').textContent='Ready'}catch(e){$('status').textContent=e.message}}
async function load(){try{state=await api('/api/session');renderTopics(state.topics,state.selected_topic);renderExercise(state.exercise);renderStats();renderFeedback(state.feedback);await refreshProgress();$('status').textContent='Ready'}catch(e){$('status').textContent=e.message;$('exercise').innerHTML=`<div class="empty">${esc(e.message)}</div>`}}
async function submit(){const query=$('query').value.trim();if(!query)return;$('submit').disabled=true;try{state=await api('/api/submit',{method:'POST',body:JSON.stringify({query})});renderStats();renderFeedback(state.feedback);await refreshProgress();if(state.feedback?.is_correct){$('status').textContent='Correct';}}catch(e){$('status').textContent=e.message}finally{$('submit').disabled=false}}
async function action(path){try{state=await api(path,{method:'POST'});renderExercise(state.exercise);renderStats();renderFeedback(state.feedback);$('query').value='';await refreshProgress();$('status').textContent='Ready'}catch(e){$('status').textContent=e.message}}
$('topic').onchange=chooseTopic;$('generate').onclick=()=>action('/api/next');$('submit').onclick=submit;$('hint').onclick=async()=>{try{const d=await api('/api/hint',{method:'POST'});$('feedback').innerHTML=`<div class="feedback"><div class="hint">Hint: ${esc(d.hint)}</div></div>`;state.hints_used=d.hints_used;renderStats()}catch(e){$('status').textContent=e.message}};$('schema').onclick=()=>document.querySelector('.schema').scrollIntoView({behavior:'smooth'});$('skip').onclick=()=>action('/api/skip');$('next').onclick=()=>action('/api/next');$('query').addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter')submit()});load();
</script></body></html>'''


def _exercise_payload(exercise):
    return {
        "id": exercise.exercise_id,
        "title": exercise.title,
        "description": exercise.description,
        "concept": exercise.concept,
        "difficulty": exercise.difficulty.value,
        "schema": [
            {"name": table.name, "columns": [{"name": c.name, "type": c.data_type} for c in table.columns]}
            for table in exercise.schema
        ],
    }


class TutorWebApp:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.repository = ExerciseRepository.from_directory(settings.data_dir)
        self.store = ProgressStore(str(settings.database_path))
        provider = None
        if settings.llm_provider != "mock":
            provider = create_provider(settings)
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
        self.session.start()

    def close(self):
        self.session.close()
        self.store.close()

    def state(self):
        with self.lock:
            current = self.session.current
            if current is None:
                raise NoExercisesAvailableError("No exercises available")
            feedback = self.session.state.last_feedback if self.session.state else None
            return {
                "exercise": _exercise_payload(current),
                "attempts": self.session.state.attempts if self.session.state else 0,
                "failed_attempts": self.session.failed_attempts,
                "hints_used": self.session.hints_used,
                "feedback": _feedback_payload(feedback),
                "selected_topic": self.session.selected_concept,
                "topics": [topic.title for topic in self.curriculum.topics],
            }

    def submit(self, query):
        with self.lock:
            outcome = self.session.submit(query)
            return {**self.state(), "feedback": _feedback_payload(outcome.feedback)}

    def choose_topic(self, concept: str | None):
        with self.lock:
            self.session.set_topic(concept)
            self.session.next_exercise()
            return self.state()

    def hint(self):
        with self.lock:
            hint = self.session.request_hint()
            return {"hint": hint.message, "hints_used": self.session.hints_used}

    def next(self):
        with self.lock:
            self.session.next()
            return self.state()

    def skip(self):
        with self.lock:
            self.session.skip()
            self.session.next()
            return self.state()

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
    app = TutorWebApp(settings)

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status, payload, content_type="application/json"):
            body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            try:
                if path == "/":
                    self._send(200, HTML.encode(), "text/html")
                elif path == "/api/session":
                    self._send(200, app.state())
                elif path == "/api/progress":
                    self._send(200, app.progress())
                else:
                    self._send(404, {"error": "Not found"})
            except Exception as error:
                self._send(500, {"error": str(error)})

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                if path == "/api/submit":
                    result = app.submit(str(payload.get("query", "")))
                elif path == "/api/topic":
                    result = app.choose_topic(payload.get("concept") or None)
                elif path == "/api/hint":
                    result = app.hint()
                elif path == "/api/next":
                    result = app.next()
                elif path == "/api/skip":
                    result = app.skip()
                else:
                    self._send(404, {"error": "Not found"})
                    return
                self._send(200, result)
            except Exception as error:
                self._send(400, {"error": str(error)})

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
