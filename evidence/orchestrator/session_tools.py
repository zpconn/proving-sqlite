#!/usr/bin/env python3
"""Check every ended campaign session's tool calls against Zach's allowlist (2026-11-10, after T-011).

  Claude: Bash, Read, Write, Edit, Glob, Grep, Monitor, TaskStop, ToolSearch (tool_use names in the stream-json log;
          campaign.py's --tools gives Claude sessions exactly these once B2 lands)
  Codex:  exec, wait, apply_patch and exec's shell tools                    (function calls in the rollout, and the
          tools.exec_command, tools.write_stdin, tools.apply_patch            tools a code-mode cell calls)

Usage:
  session_tools.py check [<job> ...]   check the named jobs, or every ended job; exit 1 if any call is off the list
  session_tools.py watch               check each job as it ends; print one line per job to the log, and exit 1 on the
                                       first call off the list (run in the background, so its exit is the alarm)
A job has ended when its runner wrote exit.json (tools/campaign.py's _job). Read-only: it never touches a session.
"""
import glob
import json
import os
import re
import sys
import time

STATE = '/home/zpconn/code/proving-sqlite-wt/state'
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'session-tools.log')
CLAUDE_OK = {'Bash', 'Read', 'Write', 'Edit', 'Glob', 'Grep', 'Monitor', 'TaskStop', 'ToolSearch'}   # TaskStop: Zach and the auditor, 2026-11-11
CODEX_CALLS_OK = {'exec', 'wait', 'apply_patch', 'exec_command', 'write_stdin'}
CODEX_CELL_OK = {'tools.exec_command', 'tools.write_stdin', 'tools.apply_patch'}
CELL_CALL = re.compile(r'\b(tools|collaboration|clock|functions|web|browser|image|mcp)\.([A-Za-z_][A-Za-z0-9_]*)\s*\(')


def jsonl(path):
    out = []
    try:
        with open(path, errors='replace') as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return out


def check_job(d):
    """(vendor, calls counter, problems)."""
    events = jsonl(os.path.join(d, 'out.jsonl'))
    calls, probs = {}, []
    if any(e.get('type') == 'system' and e.get('subtype') == 'init' for e in events):
        for e in events:
            if e.get('type') == 'assistant':
                for x in (e.get('message') or {}).get('content') or []:
                    if x.get('type') == 'tool_use':
                        calls[x['name']] = calls.get(x['name'], 0) + 1
        probs = ['%s x%d' % (n, k) for n, k in sorted(calls.items()) if n not in CLAUDE_OK]
        return 'claude', calls, probs
    thread = next((e.get('thread_id') for e in events if e.get('type') == 'thread.started'), None)
    for e in events:                       # codex --json items that are tools in their own right
        it = e.get('item') or {}
        if it.get('type') in ('mcp_tool_call', 'web_search', 'collab_tool_call'):
            probs.append('item %s' % it.get('type'))
    if not thread:
        return 'codex?', calls, probs + ([] if events else ['no events'])
    rollouts = glob.glob(os.path.expanduser('~/.codex/sessions/*/*/*/rollout-*%s*.jsonl' % thread))
    if not rollouts:
        return 'codex', calls, probs + ['no rollout for thread %s' % thread]
    for e in jsonl(rollouts[0]):
        p = e.get('payload') or {}
        if p.get('type') in ('function_call', 'custom_tool_call'):
            n = p.get('name') or '?'
            calls[n] = calls.get(n, 0) + 1
            if n not in CODEX_CALLS_OK:
                probs.append('call %s' % n)
            for m in CELL_CALL.finditer(str(p.get('arguments') or p.get('input') or '')):
                name = '%s.%s' % m.groups()
                calls[name] = calls.get(name, 0) + 1
                if name not in CODEX_CELL_OK:
                    probs.append('cell %s' % name)
    return 'codex', calls, sorted(set(probs))


def ended_jobs():
    return sorted(os.path.basename(os.path.dirname(x)) for x in glob.glob(os.path.join(STATE, 'jobs', '*', 'exit.json'))
                  if re.search(r'-(builder|reviewer|oneoff)$', os.path.basename(os.path.dirname(x))))


def line(job):
    vendor, calls, probs = check_job(os.path.join(STATE, 'jobs', job))
    ok = not probs
    text = '%s %s %s %s | %s' % (time.strftime('%Y-%m-%dT%H:%M:%S'), job, vendor, 'OK' if ok else 'OFF-LIST: ' + ', '.join(probs),
                                 ' '.join('%s=%d' % kv for kv in sorted(calls.items())))
    return ok, text


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'check'
    if cmd == 'check':
        jobs = sys.argv[2:] or ended_jobs()
        bad = 0
        for j in jobs:
            ok, text = line(j)
            print(text)
            bad += not ok
        print('RESULT session-tools %s %d jobs, %d off the list' % ('PASS' if not bad else 'FAIL', len(jobs), bad))
        return 1 if bad else 0
    if cmd == 'watch':
        seen = set(ended_jobs())
        while True:
            for j in ended_jobs():
                if j in seen:
                    continue
                seen.add(j)
                ok, text = line(j)
                with open(LOG, 'a') as f:
                    f.write(text + '\n')
                print(text, flush=True)
                if not ok:
                    return 1
            time.sleep(30)
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main())
