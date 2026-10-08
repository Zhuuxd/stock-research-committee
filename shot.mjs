// 用 Node 内置 WebSocket 直连 Edge(CDP) 截图：导航 → 等待 window.__shotDone → 截图。无第三方依赖。
// 用法: node shot.mjs <url> <out.png> [waitFlag] [extraWaitMs] [width] [height]
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const [, , url, out, waitFlag = 'committee', extraWait = '1500', W = '1500', H = '1080', scrollSel = ''] = process.argv;
const PORT = 9200 + Math.floor(Math.random() * 300);

const sleep = ms => new Promise(r => setTimeout(r, ms));

const edge = spawn(EDGE, [
  '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
  '--remote-debugging-port=' + PORT,
  '--user-data-dir=' + path.join(process.cwd(), '.edgeprofile'),
  `--window-size=${W},${H}`,
  url,
], { stdio: 'ignore' });

async function getTarget() {
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/json`);
      const list = await r.json();
      const page = list.find(t => t.type === 'page' && t.webSocketDebuggerUrl);
      if (page) return page.webSocketDebuggerUrl;
    } catch (e) { /* retry */ }
    await sleep(300);
  }
  throw new Error('CDP target not found');
}

function cdp(ws) {
  let id = 0; const pend = new Map(); const events = [];
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); }
    else if (m.method === 'Runtime.exceptionThrown') {
      const d = m.params?.exceptionDetails;
      events.push('EXC: ' + (d?.exception?.description || d?.text || JSON.stringify(d)));
    } else if (m.method === 'Runtime.consoleAPICalled' && ['error','warning'].includes(m.params?.type)) {
      events.push('CONSOLE.' + m.params.type + ': ' + (m.params.args||[]).map(a=>a.value||a.description).join(' '));
    }
  };
  const send = (method, params = {}) => new Promise(res => {
    const i = ++id; pend.set(i, res);
    ws.send(JSON.stringify({ id: i, method, params }));
  });
  send._events = events;
  return send;
}

try {
  const wsUrl = await getTarget();
  const ws = new WebSocket(wsUrl);
  await new Promise(res => { ws.onopen = res; });
  const send = cdp(ws);
  await send('Page.enable');
  await send('Runtime.enable');
  await send('Page.navigate', { url });

  // 轮询等待渲染完成标志
  let done = false;
  for (let i = 0; i < 80; i++) {
    await sleep(300);
    const r = await send('Runtime.evaluate', { expression: 'window.__shotDone || ""', returnByValue: true });
    const v = r?.result?.result?.value;
    if (v && (v === waitFlag || waitFlag === 'any')) { done = true; break; }
  }
  if (!done) {
    const dbg = await send('Runtime.evaluate', {
      expression: `(function(){ try{ return JSON.stringify({done:window.__shotDone, hasFn: typeof runCommittee, hasShot: !!document.querySelector('#committeeBox .toolbox'), chamber: !!document.querySelector('#chamber'), err: (window.__err||'')}); }catch(e){ return 'DBGERR:'+e.message; } })()`,
      returnByValue: true });
    console.error('DIAG:', dbg?.result?.result?.value);
  }
  for (const e of send._events.slice(0, 12)) console.error(e);
  await sleep(parseInt(extraWait, 10));
  if (scrollSel) {
    await send('Runtime.evaluate', { expression: `try{ document.querySelector('${scrollSel}').scrollIntoView({block:'center'}) }catch(e){}`, returnByValue: true });
    await sleep(600);
  }

  const shot = await send('Page.captureScreenshot', { format: 'png' });
  const data = shot?.result?.data;
  if (!data) throw new Error('no screenshot data');
  fs.writeFileSync(out, Buffer.from(data, 'base64'));
  console.log('saved', out, fs.statSync(out).size, 'bytes', done ? '(done)' : '(timeout)');
  ws.close();
} catch (e) {
  console.error('ERR', e.message);
  process.exitCode = 1;
} finally {
  try { edge.kill(); } catch (e) {}
  process.exit(process.exitCode || 0);
}
