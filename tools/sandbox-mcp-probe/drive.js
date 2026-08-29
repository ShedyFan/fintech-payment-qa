#!/usr/bin/env node
/*
 * Драйвер: поднимает server.js, проходит MCP-хендшейк (initialize ->
 * notifications/initialized -> tools/list -> tools/call fs_write) и печатает
 * ответы. Путь для записи — из argv[2], по умолчанию файл в системном temp
 * (вне репозитория).
 *
 * Запуск:  node tools/sandbox-mcp-probe/drive.js [абсолютный/путь/файла]
 */
'use strict';

const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const target = process.argv[2] || path.join(os.tmpdir(), 'mcp_sandbox_probe.txt');
const server = path.join(__dirname, 'server.js');

const proc = spawn(process.execPath, [server], { stdio: ['pipe', 'pipe', 'inherit'] });

let buf = '';
const pending = [];
proc.stdout.on('data', (d) => {
  buf += d.toString();
  let nl;
  while ((nl = buf.indexOf('\n')) >= 0) {
    const line = buf.slice(0, nl).trim();
    buf = buf.slice(nl + 1);
    if (line) pending.push(JSON.parse(line));
  }
});

function sendMsg(obj) {
  proc.stdin.write(JSON.stringify(obj) + '\n');
}
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  console.log('target (вне репозитория): ' + target);
  try { fs.rmSync(target, { force: true }); } catch (e) {}

  sendMsg({ jsonrpc: '2.0', id: 1, method: 'initialize',
    params: { protocolVersion: '2024-11-05', capabilities: {},
      clientInfo: { name: 'drive', version: '1' } } });
  await wait(150);
  console.log('<- initialize: ' + JSON.stringify(pending.shift()));

  sendMsg({ jsonrpc: '2.0', method: 'notifications/initialized' });

  sendMsg({ jsonrpc: '2.0', id: 2, method: 'tools/list' });
  await wait(150);
  console.log('<- tools/list: ' + JSON.stringify(pending.shift()));

  sendMsg({ jsonrpc: '2.0', id: 3, method: 'tools/call',
    params: { name: 'fs_write',
      arguments: { path: target, content: 'записано MCP-инструментом fs_write, ' + new Date().toISOString() } } });
  await wait(200);
  console.log('<- tools/call fs_write: ' + JSON.stringify(pending.shift()));

  const exists = fs.existsSync(target);
  console.log('файл существует на диске: ' + exists);
  if (exists) console.log('содержимое: ' + JSON.stringify(fs.readFileSync(target, 'utf8')));

  proc.stdin.end();
  proc.kill();
  process.exit(exists ? 0 : 1);
})();
