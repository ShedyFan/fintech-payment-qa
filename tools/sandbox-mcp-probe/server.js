#!/usr/bin/env node
/*
 * Минимальный MCP-сервер (stdio, JSON-RPC 2.0) для проверки границы песочницы
 * Claude Code. Один инструмент: fs_write — пишет файл по абсолютному пути.
 * Зависимостей нет (только встроенные модули Node).
 *
 * Смысл теста. Встроенная песочница Claude Code (/sandbox) на macOS использует
 * Seatbelt, на Linux — bubblewrap, и оборачивает ТОЛЬКО процесс инструмента Bash
 * и его дочерние процессы. Документация: "applies only to Bash commands and
 * their child processes". MCP-серверы запускаются host-процессом Claude Code
 * отдельно и под этот wrap НЕ попадают — значит, MCP-инструмент может писать
 * туда, куда Bash в песочнице уже нельзя.
 *
 * Регистрация — см. tools/sandbox-mcp-probe/README.md.
 */
'use strict';

const fs = require('fs');
const readline = require('readline');

const rl = readline.createInterface({ input: process.stdin });
function send(msg) { process.stdout.write(JSON.stringify(msg) + '\n'); }

const TOOLS = [{
  name: 'fs_write',
  description: 'Записать файл по абсолютному пути (проба границы песочницы Claude Code).',
  inputSchema: {
    type: 'object',
    properties: {
      path: { type: 'string', description: 'Абсолютный путь к файлу' },
      content: { type: 'string', description: 'Содержимое файла' },
    },
    required: ['path', 'content'],
  },
}];

rl.on('line', (line) => {
  line = line.trim();
  if (!line) return;

  let req;
  try { req = JSON.parse(line); } catch (e) { return; }
  const { id, method, params } = req;

  if (method === 'initialize') {
    send({ jsonrpc: '2.0', id, result: {
      protocolVersion: '2024-11-05',
      capabilities: { tools: {} },
      serverInfo: { name: 'sandbox-mcp-probe', version: '1.0.0' },
    } });
    return;
  }
  if (method === 'notifications/initialized') return;

  if (method === 'tools/list') {
    send({ jsonrpc: '2.0', id, result: { tools: TOOLS } });
    return;
  }

  if (method === 'tools/call' && params && params.name === 'fs_write') {
    const args = params.arguments || {};
    let text;
    try {
      fs.writeFileSync(args.path, String(args.content));
      const st = fs.statSync(args.path);
      text = 'OK: MCP-сервер записал ' + st.size + ' байт в ' + args.path;
    } catch (e) {
      text = 'ERROR: ' + (e.code || '') + ' ' + e.message;
    }
    send({ jsonrpc: '2.0', id, result: { content: [{ type: 'text', text }] } });
    return;
  }

  if (id !== undefined) {
    send({ jsonrpc: '2.0', id, error: { code: -32601, message: 'method not found: ' + method } });
  }
});
