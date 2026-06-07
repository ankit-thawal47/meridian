"""Simple task inspector UI — one HTML page, no framework."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Meridian Task Inspector</title>
  <style>
    body { font-family: monospace; max-width: 900px; margin: 40px auto; padding: 0 20px; }
    input { width: 340px; padding: 6px; font-family: monospace; font-size: 14px; }
    button { padding: 6px 16px; font-family: monospace; font-size: 14px; cursor: pointer; }
    h2 { margin-top: 28px; margin-bottom: 6px; font-size: 15px; }
    pre { background: #f4f4f4; padding: 12px; overflow-x: auto; font-size: 13px; white-space: pre-wrap; word-break: break-all; }
    .error { color: red; }
    .label { font-weight: bold; }
    table { border-collapse: collapse; width: 100%; font-size: 13px; }
    td, th { border: 1px solid #ccc; padding: 6px 10px; text-align: left; vertical-align: top; }
    th { background: #eee; }
    #output { display: none; }
  </style>
</head>
<body>
  <h1 style="font-size:18px;">Meridian Task Inspector</h1>

  <div>
    <input id="taskId" type="text" placeholder="Enter task_id" />
    <button onclick="load()">Fetch</button>
  </div>

  <div id="error" class="error" style="margin-top:10px;"></div>

  <div id="output">
    <h2>Task</h2>
    <table id="taskTable"></table>

    <h2>State</h2>
    <pre id="stateBox"></pre>

    <h2>Trace (<span id="spanCount">0</span> spans)</h2>
    <table id="traceTable">
      <thead><tr><th>#</th><th>kind</th><th>name</th><th>outcome</th><th>cost_usd</th><th>summary</th></tr></thead>
      <tbody id="traceBody"></tbody>
    </table>
  </div>

  <script>
    async function load() {
      const id = document.getElementById('taskId').value.trim();
      const errEl = document.getElementById('error');
      const outEl = document.getElementById('output');
      errEl.textContent = '';
      outEl.style.display = 'none';

      if (!id) { errEl.textContent = 'Enter a task_id.'; return; }

      let task, trace;
      try {
        const [tr, tt] = await Promise.all([
          fetch(`/tasks/${id}`),
          fetch(`/tasks/${id}/trace`),
        ]);
        if (!tr.ok) { errEl.textContent = `Error ${tr.status}: ${await tr.text()}`; return; }
        if (!tt.ok) { errEl.textContent = `Trace error ${tt.status}: ${await tt.text()}`; return; }
        task  = await tr.json();
        trace = await tt.json();
      } catch (e) {
        errEl.textContent = `Fetch failed: ${e}`;
        return;
      }

      // Task table
      const taskFields = ['task_id','repo','issue_ref','status','turns','cost_usd'];
      const taskTable = document.getElementById('taskTable');
      taskTable.innerHTML = taskFields.map(f =>
        `<tr><td class="label">${f}</td><td>${task[f] ?? ''}</td></tr>`
      ).join('');

      // State box
      document.getElementById('stateBox').textContent =
        JSON.stringify(task.state, null, 2);

      // Trace table
      document.getElementById('spanCount').textContent = trace.length;
      const tbody = document.getElementById('traceBody');
      tbody.innerHTML = trace.map((s, i) =>
        `<tr>
          <td>${i + 1}</td>
          <td>${s.kind}</td>
          <td>${s.name}</td>
          <td>${s.outcome}</td>
          <td>${s.cost_usd?.toFixed(6) ?? ''}</td>
          <td>${s.summary}</td>
        </tr>`
      ).join('');

      outEl.style.display = 'block';
    }

    document.getElementById('taskId').addEventListener('keydown', e => {
      if (e.key === 'Enter') load();
    });
  </script>
</body>
</html>
"""


@router.get("/ui", response_class=HTMLResponse, include_in_schema=False)
async def ui() -> HTMLResponse:
    return HTMLResponse(_HTML)
