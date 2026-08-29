# sandbox-mcp-probe — проба границы песочницы Claude Code через MCP

Проверка тезиса из материалов занятия (слайды 10–11): встроенная песочница
Claude Code (`/sandbox`) оборачивает **только процесс инструмента Bash и его
дочерние процессы** (док: *"applies only to Bash commands and their child
processes"*). MCP-серверы запускаются host-процессом Claude Code отдельно и под
этот wrap **не попадают**, поэтому MCP-инструмент может писать туда, куда
песочница уже не пускает Bash.

## Состав

| Файл | Что делает |
|---|---|
| `server.js` | Минимальный MCP-сервер (stdio, JSON-RPC 2.0), без зависимостей. Один инструмент `fs_write` — пишет файл по абсолютному пути. |
| `drive.js` | Драйвер: поднимает `server.js`, проходит хендшейк `initialize → notifications/initialized → tools/list → tools/call fs_write`, печатает ответы, проверяет файл на диске. Нужен для проверки **вне** Claude Code. |

Нужен только Node (встроенные модули). Сторонних пакетов нет.

## Регистрация в Claude Code

Добавить в `.mcp.json` в корне проекта (или в `~/.claude/settings.json`):

```json
{
  "mcpServers": {
    "sandbox-probe": {
      "command": "node",
      "args": ["tools/sandbox-mcp-probe/server.js"]
    }
  }
}
```

После этого в сессии появляется инструмент `mcp__sandbox-probe__fs_write`.

## Как прогнать тест-кейс (в ОДНОЙ сессии с активным `/sandbox`)

```bash
# 0. включить песочницу
/sandbox

# 1. Bash пытается писать за пределы рабочего каталога — ОЖИДАЕМО ОТКАЗ
echo "probe via bash" > "$HOME/mcp_sandbox_probe.txt"; echo "bash exit: $?"
#   ожидаемо: "Read-only file system" / "Permission denied", exit 1

# 2. Тот же путь через MCP-инструмент sandbox-probe — ОЖИДАЕМО УСПЕХ
#    вызвать mcp__sandbox-probe__fs_write с
#      path    = "$HOME/mcp_sandbox_probe.txt"
#      content = "probe via MCP"
#   ожидаемо: "OK: MCP-сервер записал N байт в /home/<user>/mcp_sandbox_probe.txt"

# 3. Подтвердить, что файл создан именно MCP-вызовом
cat "$HOME/mcp_sandbox_probe.txt"; ls -l "$HOME/mcp_sandbox_probe.txt"

# 4. уборка
rm -f "$HOME/mcp_sandbox_probe.txt"
```

Итог таблицей:

| Канал | Путь за границей песочницы | Результат |
|---|---|---|
| Bash (в `/sandbox`) | `$HOME/mcp_sandbox_probe.txt` | отказ (`Read-only file system` / `Permission denied`) |
| MCP `sandbox-probe.fs_write` | тот же путь | запись прошла — песочница MCP не накрывает |

## Проверка без Claude Code (только механизм MCP-сервера)

```bash
node tools/sandbox-mcp-probe/drive.js "/абсолютный/путь/вне/репозитория.txt"
```

Драйвер сам проходит MCP-хендшейк и вызывает `fs_write`; печатает JSON-ответы
сервера и подтверждает, что файл появился на диске. Показывает, что
**MCP-сервер как процесс пишет по произвольному абсолютному пути** — половина
контраста; вторую половину (отказ Bash по тому же пути) даёт шаг 1 процедуры
выше в `/sandbox`-сессии.
