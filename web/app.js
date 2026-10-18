/* QueryPilot local UI. Text from users, models, or databases is always rendered
 * as textContent, never interpreted as HTML. No external dependencies. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  let currentRun = null;
  let busy = false;
  let reports = [];
  let selectedReport = null;
  let selectedCaseIndex = -1;
  let evaluationPolling = null;
  const historyKey = 'querypilot-local-runs-v1';

  function element(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }
  function empty(node) { node.replaceChildren(); }
  function show(id, visible = true) { $(id).classList.toggle('hidden', !visible); }
  async function api(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: {'Accept': 'application/json', ...(options.body ? {'Content-Type': 'application/json'} : {}), ...options.headers}
    });
    let data;
    try { data = await response.json(); } catch { data = {}; }
    if (!response.ok) throw new Error(data.detail || `${response.status} ${response.statusText}`);
    return data;
  }
  function setBusy(next) {
    busy = next;
    $('ask-button').disabled = next;
    document.querySelectorAll('.action-approve').forEach(x => x.disabled = next);
  }
  function notice(message, type = 'good') {
    const box = $('workspace-notice');
    box.textContent = message;
    box.className = `notice ${type}`;
  }
  function savedRuns() {
    try { return JSON.parse(localStorage.getItem(historyKey) || '[]'); }
    catch { return []; }
  }
  function rememberRun(run) {
    const entries = savedRuns().filter(x => x.id !== run.run_id);
    entries.unshift({id:run.run_id,question:run.question});
    localStorage.setItem(historyKey, JSON.stringify(entries.slice(0, 12)));
    renderRecents();
  }
  function renderRecents() {
    const root = $('recent-runs'); empty(root);
    const items = savedRuns();
    if (!items.length) {root.append(element('span','muted tiny','Your recent runs appear here.'));return;}
    items.forEach(x => {
      const button = element('button', 'recent', x.question || 'Untitled question');
      button.title = x.question || x.id;
      button.addEventListener('click', () => loadRun(x.id));
      root.append(button);
    });
  }
  function codeCard(sql) {
    const root = element('div', 'code-container');
    const code = element('pre', '', sql || 'No SQL available');
    const copy = element('button', 'code-copy', 'Copy SQL');
    copy.type = 'button';
    copy.onclick = async () => {
      try { await navigator.clipboard.writeText(sql || '');copy.textContent = 'Copied'; }
      catch {copy.textContent = 'Copy unavailable';}
    };
    root.append(code,copy);
    return root;
  }
  function eventTimeline(events, compact = false) {
    const root = element('div', compact ? 'timeline compact-timeline' : 'timeline');
    if (!events || events.length === 0) return element('div', 'timeline-placeholder', 'No checkpoints recorded for this run.');
    events.forEach((ev) => {
      const item = element('div', 'timeline-event');
      const name = ev.node || ev.status || 'checkpoint';
      item.append(element('strong', '', name.replaceAll('_', ' ')));
      item.append(element('span', '', `Attempt ${ev.attempts || 0} · ${ev.status || '—'} · ${ev.rows_returned || 0} rows`));
      if (ev.error) item.append(element('code', '', `Error: ${ev.error}`));
      if (ev.sql && (name.includes('draft') || name.includes('execute'))) item.append(element('code', '', ev.sql));
      if (ev.tool_calls && ev.tool_calls.length) item.append(element('span', '', `  Tools: ${ev.tool_calls.join(' → ')}`));
      root.append(item);
    });
    return root;
  }
  async function liveTrace(id) {
    const root = $('live-timeline');
    try {
      const trace = await api(`/api/ui/runs/${encodeURIComponent(id)}/trace`);
      const newRoot = eventTimeline(trace.events);
      newRoot.id = 'live-timeline';
      root.replaceWith(newRoot);
    } catch {
      root.textContent = 'Checkpoint history is unavailable for this run.';
    }
  }
  function renderTable(rows) {
    const wrapper = element('div','table-scroll');
    const table = element('table','result-table');
    const keys = [...new Set(rows.flatMap(r => Object.keys(r)))];
    const head = element('thead');
    const hrow = element('tr');
    keys.forEach(k => hrow.append(element('th','',k)));
    head.append(hrow);
    const body = element('tbody');
    rows.forEach(row => {
      const tr = element('tr');
      keys.forEach(k => tr.append(element('td','',row[k] === null || row[k] === undefined ? '—' : row[k])));
      body.append(tr);
    });
    table.append(head,body);
    wrapper.append(table);
    return wrapper;
  }
  async function renderRun(run) {
    currentRun = run;
    $('question').value = run.question || '';
    $('current-status').textContent = run.status || 'unknown';
    $('current-attempts').textContent = String(run.attempts ?? 0);
    $('current-tools').textContent = String((run.tool_calls || []).length);
    $('current-id').textContent = run.run_id || '—';
    $('attempt-pill').textContent = `Attempt ${run.attempts || 0} · ${run.status || '—'}`;
    const sql = $('sql-content'); empty(sql);
    if (run.proposed_sql) sql.append(codeCard(run.proposed_sql));
    else sql.append(element('div','timeline-placeholder','No SQL proposal has been generated.'));
    if (run.previous_error) {
      const err = element('div','notice danger',`Previous attempt: ${run.previous_error}`);
      err.style.margin = '0 19px 14px';sql.append(err);
    }
    if (run.status === 'awaiting_approval') {
      const approval = element('div','approval');
      approval.append(element('p','',`Review attempt ${run.attempts}. Nothing is executed until you approve.`));
      const feedback = element('input','feedback');
      feedback.placeholder = 'Optional rejection feedback to guide the next attempt';
      feedback.maxLength = 1000;
      approval.append(feedback);
      const buttons = element('div','approval-buttons');
      const approve = element('button','primary action-approve','Approve & execute ↗');
      const reject = element('button','outline action-approve','Reject & revise');
      approve.onclick = () => resumeRun(true,'');
      reject.onclick = () => resumeRun(false, feedback.value || 'Please revise the SQL proposal.');
      buttons.append(approve,reject);
      approval.append(buttons);sql.append(approval);
      notice('Waiting for your approval. Review the generated SQL before execution.','good');
    } else if (run.status === 'completed') notice('Query completed successfully. Database-backed results are shown below.', 'good');
    else if (run.status === 'failed' || run.status === 'stopped') notice(run.answer || run.previous_error || 'Workflow stopped.', 'danger');
    else show('workspace-notice', false);
    const out = $('results-content');empty(out);
    const rows = run.rows || [];
    $('result-count').textContent = `${rows.length} row${rows.length === 1 ? '' : 's'}`;
    if (run.status === 'completed') {
      const wrapper = element('div','result-wrap');
      wrapper.append(element('p','result-answer',run.answer || 'Query completed.'));
      if (rows.length) wrapper.append(renderTable(rows));
      else wrapper.append(element('div','muted tiny','The query returned zero rows.'));
      out.append(wrapper);
    } else out.append(element('div','timeline-placeholder','Results are only available after approved SQL execution.'));
    await liveTrace(run.run_id);
  }
  async function loadRun(id) {
    location.hash = 'workspace';
    if (busy) return;
    try { setBusy(true); await renderRun(await api(`/runs/${encodeURIComponent(id)}`)); }
    catch (err) {notice(`Cannot load run: ${err.message}`,'danger');}
    finally {setBusy(false);}
  }
  async function resumeRun(approved, feedback) {
    if (!currentRun || busy) return;
    try {
      setBusy(true);
      notice(approved ? 'Executing approved SQL. Please wait…' : 'Generating revised SQL. Please wait…','good');
      const run = await api(`/runs/${encodeURIComponent(currentRun.run_id)}/resume`, {
        method:'POST',body:JSON.stringify({approved,feedback})
      });
      await renderRun(run);
    } catch(err) { notice(`Cannot resume workflow: ${err.message}`,'danger'); }
    finally {setBusy(false);}
  }
  $('question-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (busy) return;
    const question = $('question').value.trim();
    if (question.length < 3) return;
    try {
      setBusy(true);
      notice('Inspecting schema and generating SQL with the agent…','good');
      const run = await api('/runs',{method:'POST',body:JSON.stringify({question})});
      rememberRun(run);
      await renderRun(run);
    } catch(err) {notice(`Could not generate SQL: ${err.message}`,'danger');}
    finally {setBusy(false);}
  });
  document.querySelectorAll('[data-example]').forEach(button => {
    button.addEventListener('click',() => {$('question').value = button.dataset.example;$('question').focus();});
  });
  $('clear-history').onclick = () => {localStorage.removeItem(historyKey);renderRecents();};

  function togglePage() {
    const evaluations = location.hash.replace('#','') === 'evaluations';
    show('workspace-page',!evaluations);show('evaluations-page',evaluations);
    $('nav-workspace').classList.toggle('selected',!evaluations);
    $('nav-evaluations').classList.toggle('selected',evaluations);
    $('page-eyebrow').textContent = evaluations ? 'WORKSPACE / EVALUATIONS' : 'WORKSPACE / QUERY AGENT';
    if (evaluations) refreshReports();
  }
  window.addEventListener('hashchange',togglePage);

  function formatPercent(val) {return typeof val === 'number' ? `${val.toFixed(1)}%` : '—';}
  function formatValue(value) {return value == null ? '—' : String(value);}
  async function refreshReports() {
    try {
      reports = await api('/api/ui/reports');
      const select = $('report-selector');
      const old = select.value;empty(select);
      if (!reports.length) {select.append(new Option('No reports yet',''));show('report-data',false);show('report-empty');return;}
      reports.forEach(r => select.append(new Option(`${r.name} · ${r.summary.passed}/${r.summary.total}`,r.id)));
      select.value = reports.some(r => r.id === old) ? old : reports[0].id;
      await openReport(select.value);
      refreshJudge();
    } catch(err) { $('report-empty').textContent = `Could not load reports: ${err.message}`;show('report-empty');show('report-data',false); }
  }
  async function openReport(id) {
    if (!id) return;
    try {
      selectedReport = await api(`/api/ui/reports/${encodeURIComponent(id)}`);
      show('report-empty',false);show('report-data');
      const s = selectedReport.summary;
      $('m-accuracy').textContent = formatPercent(s.accuracy);
      $('m-passed').textContent = `${s.passed} / ${s.total} correct`;
      $('m-completed').textContent = `${s.completed} / ${s.total}`;
      $('m-first').textContent = `${s.first_try} / ${s.total}`;
      $('m-attempts').textContent = formatValue(s.average_attempts);
      $('m-tools').textContent = `Tool score: ${formatValue(s.tool_correctness)}`;
      $('report-name').textContent = selectedReport.name;
      const root = $('evaluation-rows');empty(root);
      selectedReport.cases.forEach((r,i) => {
        const row = element('tr');row.dataset.caseIndex = i;
        row.append(element('td','',r.question));
        row.append(element('td',r.passed ? 'ok' : 'bad',r.passed ? '✓ Pass' : '✕ Fail'));
        row.append(element('td','',r.attempts ?? '—'));
        row.append(element('td','',Array.isArray(r.trace) && r.trace.length ? `${r.trace.length} steps ↗` : 'Summary ↗'));
        row.addEventListener('click',() => selectCase(i));
        root.append(row);
      });
      selectCase(Math.min(Math.max(0,selectedCaseIndex),selectedReport.cases.length-1));
    } catch(err) {show('report-data',false);show('report-empty');$('report-empty').textContent = `Could not open report: ${err.message}`;}
  }
  function selectCase(index) {
    if (!selectedReport || index < 0) return;
    selectedCaseIndex = index;
    document.querySelectorAll('.eval-table tr[data-case-index]').forEach(row => row.classList.toggle('is-selected',Number(row.dataset.caseIndex) === index));
    const r = selectedReport.cases[index];
    const panel = $('case-detail');empty(panel);panel.className = 'case-detail-wrap';
    panel.append(element('div',r.passed ? 'ok' : 'bad',r.passed ? '✓ Passed' : '✕ Failed'));
    panel.append(element('h3','',r.question));
    const meta = element('div','muted tiny',`Status: ${r.status || '—'} · Attempts: ${r.attempts ?? '—'} · Schema verified once: ${r.schema_verified_once === undefined ? 'not recorded' : String(r.schema_verified_once)}`);panel.append(meta);
    panel.append(element('div','subsection-title','Actual database output'));
    panel.append(element('pre','json-pre',JSON.stringify(r.actual_rows || [],null,2)));
    panel.append(element('div','subsection-title','Reference answer'));
    panel.append(element('pre','json-pre',JSON.stringify(r.expected_rows || [],null,2)));
    panel.append(element('div','subsection-title','Graph execution history'));
    if (r.trace && r.trace.length) panel.append(eventTimeline(r.trace,true));
    else panel.append(element('div','muted tiny','No trace recorded for this run.'));
  }
  async function refreshJudge() {
    try {
      const info = await api('/api/ui/judge-summary');
      const root = $('judge-metrics');empty(root);
      if (!info.available) {root.className = 'judge-placeholder';root.textContent = 'No judge scores yet.';return;}
      root.className = 'judge-grid';
      for (const [key,label] of [['task_completion','Task Completion'],['step_efficiency','Step Efficiency']]) {
        const card = element('div','judge-tile');card.append(element('span','',label));card.append(element('strong','',typeof info[key] === 'number' ? info[key].toFixed(2) : 'Not available'));root.append(card);
      }
      const note = element('p','judge-note',`Policy: ${info.judge_policy || '—'} · Suite: ${info.suite || '—'}`);
      note.style.gridColumn = '1 / -1';root.append(note);
    } catch { /* Optional panel; raw SQL report remains usable. */ }
  }
  $('report-selector').addEventListener('change',e => {selectedCaseIndex=-1;openReport(e.target.value);});
  $('refresh-reports').addEventListener('click',refreshReports);
  $('eval-mode').addEventListener('change',() => {
    const advanced = $('eval-mode').value === 'advanced';
    show('judge-limit-label',advanced);show('judge-policy-label',advanced);
  });
  async function refreshJob() {
    let job;
    try {job = await api('/api/ui/evaluation-job');}catch{return;}
    if (job.state === 'idle') {show('job-status',false);return;}
    show('job-status');
    $('job-title').textContent = `${job.suite || 'SQL'} · ${job.mode || 'standard'} evaluation`;
    $('job-pill').textContent = job.state;
    $('job-log').textContent = job.log || 'Starting…';
    $('job-log').scrollTop = $('job-log').scrollHeight;
    $('start-evaluation').disabled = job.state === 'running';
    if (job.state === 'running' && !evaluationPolling) evaluationPolling = setInterval(refreshJob,2400);
    if (job.state !== 'running') {
      if (evaluationPolling) clearInterval(evaluationPolling);evaluationPolling=null;
      refreshReports();refreshJudge();
    }
  }
  $('start-evaluation').addEventListener('click',async () => {
    const mode = $('eval-mode').value;
    const spec = {suite:$('suite').value,mode,judge_limit:Number($('judge-limit').value),judge_policy:$('judge-policy').value};
    try {
      const result = await api('/api/ui/evaluation-job',{method:'POST',body:JSON.stringify(spec)});
      show('job-status');$('job-title').textContent = 'Evaluation running';$('job-pill').textContent = result.state;
      $('job-log').textContent = 'Starting evaluation…';
      $('start-evaluation').disabled = true;
      if (!evaluationPolling) evaluationPolling=setInterval(refreshJob,2400);
    } catch(err) {alert(`Cannot start evaluation: ${err.message}`);}
  });
  async function checkHealth() {
    try {
      await api('/health');$('server-dot').classList.add('online');$('server-status').textContent='FastAPI online';
    }catch{$('server-status').textContent='FastAPI unavailable';}
  }
  renderRecents();togglePage();checkHealth();refreshJob();
})();
