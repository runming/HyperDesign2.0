// HyperDesign Studio 2.0 —— 原生 ES Module，无构建、无框架、离线可用
import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';
import { STLLoader } from './vendor/STLLoader.js';

const API = '';
const $ = (s) => document.querySelector(s);
const state = { run: null, packs: [], skills: [], source: null, wire: false, bbox: true };

// ---------------------------------------------------------------- 三维视窗
const canvas = $('#view3d');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 5000);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.08;

scene.add(new THREE.HemisphereLight(0xdcefff, 0x203040, 1.05));
const key = new THREE.DirectionalLight(0xffffff, 1.35); key.position.set(220, 320, 260); scene.add(key);
const fill = new THREE.DirectionalLight(0x88bbff, 0.55); fill.position.set(-260, -120, -180); scene.add(fill);
const grid = new THREE.GridHelper(400, 20, 0x2a4a68, 0x1b3044); scene.add(grid);

let mesh = null;
let bboxHelper = null;
const bboxOf = new THREE.Box3();

function resize() {
  const w = canvas.clientWidth || 800, h = canvas.clientHeight || 600;
  renderer.setSize(w, h, false);
  camera.aspect = w / h; camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(canvas);
resize();

function frameObject(obj) {
  const box = new THREE.Box3().setFromObject(obj);
  bboxOf.copy(box);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  controls.target.copy(center);
  const d = Math.max(size.x, size.y, size.z) * 1.9;
  camera.position.set(center.x + d * 0.75, center.y + d * 0.55, center.z + d * 0.95);
  camera.near = d / 100; camera.far = d * 20; camera.updateProjectionMatrix();
  controls.update();
  updateHud(size, center);
}

function updateHud(size, center) {
  if (!size) {
    $('#hud').textContent = state.run ? '该运行无 CAD 产物' : '等待运行…';
    return;
  }
  $('#hud').textContent =
    `包络 (mm)  X ${size.x.toFixed(2)}   Y ${size.y.toFixed(2)}   Z ${size.z.toFixed(2)}\n` +
    `底面 Z = ${bboxOf.min.z.toFixed(3)}   质心 (${center.x.toFixed(1)}, ${center.y.toFixed(1)}, ${center.z.toFixed(1)})\n` +
    `单位 mm · 左键旋转 / 右键平移 / 滚轮缩放`;
}

function setBbox(show) {
  if (bboxHelper) { scene.remove(bboxHelper); bboxHelper.geometry.dispose(); bboxHelper = null; }
  if (show && mesh) {
    bboxHelper = new THREE.Box3Helper(bboxOf, new THREE.Color(0x00a8ff));
    scene.add(bboxHelper);
  }
}

function loadModel(runId) {
  const url = `${API}/api/runs/${runId}/artifacts/model.stl`;
  new STLLoader().load(url, (geo) => {
    if (mesh) { scene.remove(mesh); mesh.geometry.dispose(); mesh.material.dispose(); }
    geo.computeVertexNormals();
    const mat = new THREE.MeshStandardMaterial({
      color: 0xc9d6e2, metalness: 0.18, roughness: 0.62, flatShading: false,
      side: THREE.DoubleSide,
    });
    mesh = new THREE.Mesh(geo, mat);
    scene.add(mesh);
    frameObject(mesh);
    setBbox(state.bbox);
    state.source = url;
  }, undefined, (err) => {
    console.warn('STL 加载失败', err);
    $('#hud').textContent = '该运行没有可显示的 CAD 产物（可能在构建节点前就失败）';
    if (mesh) { scene.remove(mesh); mesh = null; }
    if (bboxHelper) { scene.remove(bboxHelper); bboxHelper = null; }
  });
}

(function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
})();

$('#toggle-wire').addEventListener('change', (e) => {
  state.wire = e.target.checked;
  if (mesh) mesh.material.wireframe = state.wire;
});
$('#toggle-bbox').addEventListener('change', (e) => { state.bbox = e.target.checked; setBbox(state.bbox); });
$('#btn-fit').addEventListener('click', () => { if (mesh) frameObject(mesh); });

// ---------------------------------------------------------------- tabs
document.querySelectorAll('.tab').forEach((t) => t.addEventListener('click', () => {
  document.querySelectorAll('.tab').forEach((x) => x.classList.remove('active'));
  t.classList.add('active');
  const tab = t.dataset.tab;
  $('#view-wrap').classList.toggle('hidden', tab !== 'model');
  $('#rules-wrap').classList.toggle('hidden', tab !== 'rules');
  $('#kb-wrap').classList.toggle('hidden', tab !== 'kb');
  $('#ai-wrap').classList.toggle('hidden', tab !== 'ai');
  if (tab === 'kb') loadKbDocs();
}));

// ---------------------------------------------------------------- 知识库
async function loadKbDocs() {
  const role = $('#kb-role').value;
  const [{ documents }, stats] = await Promise.all([
    jget(`/api/kb/documents?role=${role}`), jget('/api/kb/stats')]);
  $('#kb-doc-count').textContent = `(${documents.length} 篇可见 / 共 ${stats.documents} 篇 · ${stats.chunks} 个条款块)`;
  $('#kb-docs').innerHTML = documents.map((d) =>
    `<div class="skill"><div class="k">${d.title}</div>
      <div class="d">${d.source_type.toUpperCase()} · ${d.version} · 可见角色 ${d.access_roles.join('/')} · ${d.chunks} 条款块</div></div>`
  ).join('');
}

async function doKbSearch() {
  const query = $('#kb-query').value.trim();
  if (!query) return;
  const role = $('#kb-role').value;
  const res = await jpost('/api/kb/search', { query, role, top_k: 5 });
  const meta = `检索「${query}」· 角色 ${role} · 向量后端 ${res.embedder}`
    + (res.found ? ` · 命中 ${res.hits.length} 条` : ` · **无证据**（${res.reason || ''}）`);
  $('#kb-meta').innerHTML = `<div class="chip">${meta}</div>`;
  if (!res.found) {
    $('#kb-results').innerHTML = `<div class="approval" style="margin-top:10px">
      <div style="color:var(--warn)">知识库没有通过证据门控的片段 —— Agent 此时应输出 <code>needs_input</code>，而不是编造答案。</div>
      <div class="muted" style="margin-top:6px">门控条件：BM25 必须命中 且 向量余弦 ≥ ${res.vec_min}${res.max_similarity !== undefined ? '（本查询最高 ' + res.max_similarity + '）' : ''}</div>
    </div>`;
    return;
  }
  $('#kb-results').innerHTML = res.hits.map((h) => `
    <div class="node" style="margin-bottom:8px">
      <div class="t">${h.doc_title} <span class="muted">› ${h.section}</span></div>
      <div class="cite" style="color:var(--fg);margin-top:6px">${h.quote}</div>
      <div class="m">通道 ${h.channels.join(' + ')} · RRF 分 ${h.score} · 关键条款
        ${h.clauses.map((c) => `<span class="pill ok" style="padding:1px 7px">${c}</span>`).join(' ')}</div>
    </div>`).join('');
}

$('#kb-search').addEventListener('click', doKbSearch);
$('#kb-query').addEventListener('keydown', (e) => { if (e.key === 'Enter') doKbSearch(); });
$('#kb-role').addEventListener('change', () => { loadKbDocs(); });

// ---------------------------------------------------------------- AI 助手
const AI_SESSION = 'studio-' + Math.random().toString(36).slice(2, 8);

function aiBubble(role, text, extra) {
  const div = document.createElement('div');
  div.className = 'ai-msg ' + role;
  div.innerHTML = `<div class="who">${role === 'user' ? '你' : 'HyperDesign 助手'}</div>
                   <div class="txt">${text.replace(/\n/g, '<br>')}</div>`
    + (extra ? `<div class="meta">${extra}</div>` : '');
  $('#ai-log').appendChild(div);
  $('#ai-log').scrollTop = $('#ai-log').scrollHeight;
}

async function aiSend() {
  const text = $('#ai-input').value.trim();
  if (!text) return;
  $('#ai-input').value = '';
  aiBubble('user', text);
  $('#ai-send').disabled = true;
  try {
    const r = await jpost('/api/assistant/message', { session: AI_SESSION, text });
    const extra = [`阶段 ${r.stage}`, r.kind];
    if (r.verdict) extra.push(`准入 ${r.verdict}`);
    if (r.build && r.build.metrics) extra.push(`实体 ${r.build.metrics.solids} · 体积 ${r.build.metrics.volume_mm3}mm³`);
    if (r.params) extra.push(`壁厚 ${r.params.WALL} · 拔模 ${r.params.DRAFT_DEG}° · 圆角 R${r.params.CORNER_R}`);
    aiBubble('assistant', r.reply, extra.join(' · '));
    $('#ai-meta').innerHTML = `<div class="chip">会话 ${AI_SESSION} · 阶段 <b>${r.stage}</b>
      · 包络 ${r.params.LENGTH_X}×${r.params.WIDTH_Y}×${r.params.HEIGHT_Z}mm
      · 立柱高 ${r.params.POST_H} · 导光窗 Z=${r.params.LED_Z}</div>`;
  } catch (e) {
    aiBubble('assistant', '调用失败：' + e.message, 'error');
  } finally {
    $('#ai-send').disabled = false;
  }
}

$('#ai-send').addEventListener('click', aiSend);
$('#ai-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') aiSend(); });
$('#ai-reset').addEventListener('click', async () => {
  await jpost('/api/assistant/reset', { session: AI_SESSION, text: '' });
  $('#ai-log').innerHTML = '';
  $('#ai-meta').innerHTML = '<div class="chip">会话已重置</div>';
});

// ---------------------------------------------------------------- 后端交互
async function jget(path) {
  const r = await fetch(API + path);
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}
async function jpost(path, body) {
  const r = await fetch(API + path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error((await r.text()) || r.status);
  return r.json();
}

function pill(text, cls) {
  const el = $('#run-pill');
  el.textContent = text; el.className = `pill ${cls}`;
}

function renderNodes(run) {
  const box = $('#node-list');
  box.innerHTML = '';
  if (!run) { box.innerHTML = '<div class="muted">尚未运行</div>'; return; }
  run.nodes.forEach((n) => {
    const def = (n.output && n.output.__title) || '';
    const div = document.createElement('div');
    div.className = 'node';
    const ms = n.elapsed_ms != null ? `${n.elapsed_ms} ms` : '—';
    const err = n.error ? `<div class="m" style="color:var(--bad)">${n.error.code}: ${(n.error.message || '').slice(0, 60)}</div>` : '';
    div.innerHTML = `<div class="t"><span class="dot ${n.status}"></span> ${n.id}</div>
      <div class="m">${n.status} · ${ms}${def ? ' · ' + def : ''}</div>${err}`;
    box.appendChild(div);
  });
}

function renderSkills(skills) {
  $('#skill-list').innerHTML = skills.map((s) =>
    `<div class="skill"><div class="k">${s.key}@${s.version}</div><div class="d">${s.description}</div></div>`).join('');
}

function renderRules(run) {
  const summary = $('#rules-summary'), body = $('#rules-body');
  if (!run) { summary.innerHTML = ''; body.innerHTML = '<div class="muted">尚未运行</div>'; return; }
  const harnessNodes = run.nodes.filter((n) => n.output && n.output.verdict);
  const caeNode = run.nodes.find((n) => n.output && n.output.stress_concentration_kt !== undefined);
  let caeChip = '';
  if (caeNode) {
    const o = caeNode.output;
    caeChip = `<div class="chip"><b>CAE</b> 孔边 Kt = ${o.stress_concentration_kt}`
      + `（理论 ${o.analytic_kt}，误差 ${o.kt_error_pct}%）· σ_θθ,max = ${o.sigma_max_hoop_mpa} MPa`
      + ` · σ∞ = ${o.far_field_stress_mpa} MPa · ${o.mesh.elements} 单元</div>`;
  }
  if (!harnessNodes.length && !caeNode) {
    summary.innerHTML = '<div class="chip">本 run 未产生 Harness 裁决</div>';
    body.innerHTML = '';
    return;
  }
  summary.innerHTML = caeChip + harnessNodes.map((n) => {
    const v = n.output.verdict;
    const cls = v === 'passed' ? 'ok' : (v === 'failed' ? 'bad' : 'wait');
    return `<div class="chip"><b>${n.id}</b> 判定 <span class="pill ${cls}">${v}</span> · 规则 ${n.output.results.length} 条</div>`;
  }).join('');

  const rows = [];
  harnessNodes.forEach((n) => {
    n.output.results.forEach((r) => {
      rows.push(`<tr class="${r.verdict}">
        <td><span class="tag">${r.rule_id}</span>${r.title ? `<div class="muted">${r.title}</div>` : ''}</td>
        <td>${r.severity}${r.blocking ? ' · 阻断' : ''}</td>
        <td><span class="pill ${r.verdict === 'passed' ? 'ok' : (r.verdict === 'failed' ? 'bad' : 'wait')}">${r.verdict}</span></td>
        <td class="tag">${fmt(r.actual)} / ${fmt(r.limit)} ${r.unit || ''}</td>
        <td>${(r.citation && (r.citation.document
              ? r.citation.document + (r.citation.clause ? ' › ' + r.citation.clause : '')
              : r.citation.clause)) || ''}
            ${r.citation && r.citation.quote ? `<div class="cite">「${r.citation.quote.slice(0, 64)}…」</div>` : ''}
            ${r.suggested_action ? `<div class="act">建议：${r.suggested_action}</div>` : ''}</td>
      </tr>`);
    });
  });
  body.innerHTML = `<table><thead><tr><th>规则</th><th>级别</th><th>判定</th><th>实测 / 限值</th><th>引用与建议</th></tr></thead>
    <tbody>${rows.join('')}</tbody></table>`;
}

function fmt(v) {
  if (typeof v === 'number') return Number.isInteger(v) ? v : v.toFixed(3);
  if (Array.isArray(v)) return '[' + v.map((x) => (typeof x === 'number' ? +x.toFixed(3) : x)).join(', ') + ']';
  return v === null || v === undefined ? '—' : String(v);
}

function renderApproval(run) {
  const box = $('#approval-box');
  if (!run) { box.innerHTML = '<div class="muted">尚未运行</div>'; return; }
  const waiting = run.nodes.some((n) => n.status === 'waiting_approval');
  if (run.status === 'waiting_approval' && waiting) {
    box.innerHTML = `<div>运行已到达审批门，等待工程师签字。</div>
      <div class="muted" style="margin-top:6px">前置条件：CAD 几何 Harness 与网格物理 DFM Harness 均已通过。</div>
      <div class="row"><input type="text" id="approver" placeholder="审批人" value="工程师" style="flex:1" /></div>
      <div class="row"><input type="text" id="comment" placeholder="审批意见" style="flex:1" value="几何与工艺达标，放行" /></div>
      <div class="row"><button class="btn-ok" id="btn-ok">✓ 通过</button>
        <button class="btn-no" id="btn-no">✕ 驳回</button></div>`;
    $('#btn-ok').onclick = () => doApprove('approve');
    $('#btn-no').onclick = () => doApprove('reject');
  } else if (run.approval && run.approval.decision) {
    box.innerHTML = `<div>审批结论：<b>${run.approval.decision === 'approve' ? '通过' : '驳回'}</b>
       · 审批人 ${run.approval.approver}</div>
      <div class="muted" style="margin-top:6px">${run.approval.comment || ''}</div>`;
  } else if (run.status === 'failed') {
    box.innerHTML = `<div style="color:var(--bad)">运行失败：${run.error || ''}</div>
      <div class="muted" style="margin-top:6px">物理 Harness 未通过时审批门不会打开（一票否决）。</div>`;
  } else {
    box.innerHTML = `<div class="muted">当前状态：${run.status}</div>`;
  }
}

function renderEvents(events) {
  $('#event-count').textContent = `(${events.length})`;
  $('#event-list').innerHTML = events.map((e) => {
    const cls = e.type.includes('failed') ? 'failed'
      : e.type.includes('approval') || e.type.includes('approved') ? 'approval'
      : e.type.includes('finished') || e.type.includes('succeeded') ? 'ok' : '';
    return `<div class="ev ${cls}"><span class="s">#${e.seq}</span> <span class="n">${e.type}</span>
      ${e.node_id ? ' · ' + e.node_id : ''}</div>`;
  }).join('');
}

async function refresh(runId) {
  const { run } = await jget(`/api/runs/${runId}`);
  state.run = run;
  renderNodes(run);
  renderRules(run);
  renderApproval(run);
  const cls = run.status === 'succeeded' ? 'ok' : run.status === 'failed' ? 'bad'
    : run.status === 'waiting_approval' ? 'wait' : 'running';
  pill(run.status, cls);
  const { events } = await jget(`/api/runs/${runId}/events`);
  renderEvents(events);
  return run;
}

async function doApprove(decision) {
  const run = state.run;
  if (!run) return;
  const approver = ($('#approver') || {}).value || '工程师';
  const comment = ($('#comment') || {}).value || '';
  await jpost(`/api/runs/${run.run_id}/approve`, { approver, decision, comment });
  await refresh(run.run_id);
}

async function doRun() {
  const preset = $('#preset-select').value;
  pill('运行中…', 'running');
  $('#btn-run').disabled = true;
  try {
    const { run } = await jpost('/api/runs', { preset });
    state.run = run;
    const cls0 = run.status === 'succeeded' ? 'ok' : run.status === 'failed' ? 'bad'
      : run.status === 'waiting_approval' ? 'wait' : 'running';
    pill(run.status, cls0);
    renderNodes(run); renderRules(run); renderApproval(run);
    if (run.nodes.some((n) => n.id === 'n1_cad_build' && n.status === 'ok')) loadModel(run.run_id);
    else {
      $('#hud').textContent = '本次运行在 CAD 构建前/中被拒绝，无可显示几何';
      if (mesh) { scene.remove(mesh); mesh = null; }
      if (bboxHelper) { scene.remove(bboxHelper); bboxHelper = null; }
    }
    await refresh(run.run_id);
  } catch (e) {
    alert('运行失败：' + e.message);
    pill('失败', 'bad');
  } finally {
    $('#btn-run').disabled = false;
  }
}

async function boot() {
  try {
    const h = await jget('/api/health');
    $('#health-line').textContent =
      `后端在线 · v${h.version} · 工作流 ${h.workflow}@${h.workflow_version} · CAD 引擎 ${h.engine}`;
    $('#wf-id').textContent = `${h.workflow}@${h.workflow_version}`;
    const [{ skills }, { presets }] = await Promise.all([jget('/api/skills'), jget('/api/presets')]);
    state.skills = skills; renderSkills(skills);
    $('#preset-select').innerHTML = presets
      .map((p) => `<option value="${p.key}">${p.title}</option>`).join('');
    const { runs } = await jget('/api/runs');
    if (runs.length) await refresh(runs[runs.length - 1].run_id);
    else { renderNodes(null); renderRules(null); renderApproval(null); }
  } catch (e) {
    $('#health-line').textContent = '后端未连接：' + e.message;
  }
}

$('#btn-run').addEventListener('click', doRun);
boot();
