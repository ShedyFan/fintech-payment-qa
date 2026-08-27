# Отчёт по ДЗ №2

## 1. Работающий результат

*(статус, ссылка на test-plan.md)*

## 2. Агенты параллельно

*(сколько субагентов, как разбита задача, что вернулось в главную сессию)*

## 3. Workflow

Файл: `workflows/qa-regression-workflow.md`. *(прогонялся ли на практике)*

## 4. Worktrees

*(три ветки, что в каждой, как прошёл merge, что почищено)*

## 5. Изоляция

Песочница Claude Code (`/sandbox`, обычные bash-права): всё вне рабочего каталога
`fintech-payment-qa` (и вне явно разрешённых путей вроде `/tmp/claude`, `$TMPDIR`)
смонтировано read-only; `/root` дополнительно закрыт правами доступа. Path
traversal не помогает — фильтр проверяет итоговый разрешённый путь.

### Попытки записи за пределы рабочей папки

| Путь | Результат | Код возврата |
|------|-----------|--------------|
| `/home/tester_qa/sandbox_escape_test.txt` | `Read-only file system` | 1 |
| `/tmp/../../etc/sandbox_escape_test.txt` | `Read-only file system` | 1 |
| `/tmp/sandbox_escape_test.txt` | `Read-only file system` | 1 |
| `/home/tester_qa/.bashrc_evil` | `Read-only file system` | 1 |
| `/var/tmp/escape.txt` | `Read-only file system` | 1 |
| `/root/escape.txt` | `Permission denied` | 1 |
| `../escape_outside_project.txt` | `Read-only file system` | 1 |

Команда:

```bash
for p in /tmp/sandbox_escape_test.txt "$HOME/.bashrc_evil" /var/tmp/escape.txt /root/escape.txt "../escape_outside_project.txt"; do
  echo "=== $p ==="; echo "data" > "$p" 2>&1; echo "exit code: $?";
done
```

Вывод:

```
=== /tmp/sandbox_escape_test.txt ===
/bin/bash: line 1: /tmp/sandbox_escape_test.txt: Read-only file system
exit code: 1
=== /home/tester_qa/.bashrc_evil ===
/bin/bash: line 1: /home/tester_qa/.bashrc_evil: Read-only file system
exit code: 1
=== /var/tmp/escape.txt ===
/bin/bash: line 1: /var/tmp/escape.txt: Read-only file system
exit code: 1
=== /root/escape.txt ===
/bin/bash: line 1: /root/escape.txt: Permission denied
exit code: 1
=== ../escape_outside_project.txt ===
/bin/bash: line 1: ../escape_outside_project.txt: Read-only file system
exit code: 1
```

### Контрольная запись внутри проекта

```bash
echo "control write inside project" > ./sandbox_control_test.txt
echo "exit code: $?"
ls -l ./sandbox_control_test.txt
rm ./sandbox_control_test.txt
```

Вывод:

```
exit code: 0
-rwxrwxrwx 1 nobody nogroup 29 Aug 27 17:32 ./sandbox_control_test.txt
```

Итог: запись за границу песочницы отклоняется во всех случаях, запись внутри
рабочего каталога проходит успешно. Ограничение не обходилось.

## 6. Недоверенный текст / инъекция

*(куда вшита инструкция, какая модель слабая/сильная, таблица результатов)*

## 7. Оптимизатор / индекс кодовой базы

*(пробовали ли — для текстового QA-проекта не обязательно)*

## 8. Замеры: параллельно против последовательно

*(время, контекст главной сессии, что получилось быстрее)*

## Честные тупики

*(что не сработало с первого раза — заполняется по ходу работы)*

## Инструменты

*(что использовалось: модели, CLI, дополнительные скиллы)*
