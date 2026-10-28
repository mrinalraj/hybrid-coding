"""Session bookkeeping for the hybrid-coding skill: init, config, status, transcript.

Called through hc.sh. Kept in one stdlib-only file so the skill installs anywhere
python3 exists.
"""
import glob
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLAUDE_MODELS = "sonnet haiku opus fable"


def sh(*args, cwd=None):
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def repo_root():
    return sh("git", "rev-parse", "--show-toplevel") or os.getcwd()


def resolve(s):
    return s if os.path.isabs(s) else os.path.join(repo_root(), ".hybrid", s)


def read_settings(d):
    out = {}
    try:
        for line in open(os.path.join(d, "session.md")):
            m = re.match(r"^([a-z_]+): (.*)$", line.rstrip("\n"))
            if m:
                out[m.group(1)] = m.group(2)
    except OSError:
        pass
    return out


def write_settings(d, settings):
    with open(os.path.join(d, "session.md"), "w") as f:
        f.write("".join(f"{k}: {v}\n" for k, v in settings.items()))


def render(d, sid):
    """Copy the worker/scribe instructions into the session with its paths filled in."""
    for name, target in (("worker.md", "WORKER.md"), ("scribe.md", "SCRIBE.md")):
        text = open(os.path.join(SKILL_DIR, "assets", name)).read()
        text = text.replace("{{SESSION}}", d).replace("{{SKILL}}", SKILL_DIR).replace("{{SID}}", sid)
        with open(os.path.join(d, target), "w") as f:
            f.write(text)


def http_json(url, method="GET", timeout=2.5):
    try:
        req = urllib.request.Request(url, method=method, data=b"" if method == "POST" else None)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except Exception:
        return None


def ollama_lines():
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    if not host.startswith("http"):
        host = "http://" + host
    tags = http_json(host + "/api/tags")
    if tags is None:
        return ["ollama: not running"]
    local = [m["name"] for m in tags.get("models", [])]
    lines = ["ollama local: " + (" ".join(local) if local else "none pulled")]
    me = http_json(host + "/api/me", method="POST")
    if not me or not me.get("plan"):
        lines.append("ollama cloud: not signed in (ollama signin)")
        return lines
    cloud = http_json("https://ollama.com/api/tags", timeout=3) or {}
    names = [m["name"] + ("-cloud" if ":" in m["name"] else ":cloud") for m in cloud.get("models", [])]
    lines.append(f"ollama cloud ({me['plan']} plan; sends code to ollama.com): " + (" ".join(names) or "catalogue unavailable"))
    return lines


def cmd_init(args):
    sid = args[0]
    resume = args[args.index("--resume") + 1] if "--resume" in args else None
    root = repo_root()
    common = sh("git", "-C", root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if common:
        exclude = os.path.join(common, "info", "exclude")
        os.makedirs(os.path.dirname(exclude), exist_ok=True)
        existing = open(exclude).read().splitlines() if os.path.exists(exclude) else []
        if ".hybrid/" not in existing:
            with open(exclude, "a") as f:
                f.write(".hybrid/\n")

    fresh = os.path.join(root, ".hybrid", sid)
    d = resolve(resume) if resume else fresh
    if resume and d != fresh and os.path.isdir(fresh) and not os.path.exists(os.path.join(fresh, "spec.md")) \
            and not os.path.isdir(os.path.join(fresh, "tasks")):
        subprocess.run(["rm", "-rf", fresh])  # untouched folder created at load; the resumed one replaces it
    state = "existing" if os.path.isdir(d) else "new"
    os.makedirs(d, exist_ok=True)
    settings = read_settings(d)
    if state == "new":
        settings = {"sid": sid, "started": time.strftime("%Y-%m-%d %H:%M"),
                    "repo": root, "branch": sh("git", "-C", root, "branch", "--show-current") or "-"}
    settings["main_session"] = sid
    write_settings(d, settings)
    render(d, sid)

    dirty = len([l for l in sh("git", "-C", root, "status", "--porcelain").splitlines() if l and not l.endswith(".hybrid/")])
    print(f"session: {d} ({state})")
    print(f"repo: {root} · branch {settings.get('branch', '-')} · {dirty} uncommitted path(s)")
    chosen = {k: settings[k] for k in ("title", "coder", "scout") if k in settings}
    print("settings: " + (" ".join(f"{k}={v}" for k, v in chosen.items()) if chosen else "none yet"))
    print("claude models: " + CLAUDE_MODELS)
    for line in ollama_lines():
        print(line)
    others = []
    for p in sorted(glob.glob(os.path.join(root, ".hybrid", "*", "session.md")), key=os.path.getmtime, reverse=True):
        od = os.path.dirname(p)
        if od == d:
            continue
        s = read_settings(od)
        done = "summarized" if os.path.exists(os.path.join(od, "SUMMARY.md")) else "open"
        others.append(f"  {od} — {s.get('title', 'untitled')} ({s.get('started', '?')}, {done})")
    if others:
        print("earlier sessions in this repo:")
        print("\n".join(others[:5]))


def cmd_config(args):
    d = resolve(args[0])
    settings = read_settings(d)
    for kv in args[1:]:
        k, _, v = kv.partition("=")
        settings[k.strip()] = v.strip()
    write_settings(d, settings)
    print("ok")


def cmd_status(args):
    d = resolve(args[0])
    rows = []
    for t in sorted(glob.glob(os.path.join(d, "tasks", "*"))):
        tid = os.path.basename(t)
        report = os.path.join(t, "report.md")
        status = "-"
        if os.path.exists(report):
            m = re.search(r"^status:\s*(\S+)", open(report).read(), re.M)
            status = m.group(1) if m else "report?"
        extra = ""
        result = os.path.join(t, "result.json")
        if os.path.exists(result):
            try:
                r = json.load(open(result))
                model = open(os.path.join(t, "model")).read().strip() if os.path.exists(os.path.join(t, "model")) else "?"
                cost = r.get("total_cost_usd")
                cost = f"${cost:.4f}" if isinstance(cost, (int, float)) and not model.startswith("ollama:") else "n/a"
                extra = f" model={model} turns={r.get('num_turns')} cost={cost} worker_session={r.get('session_id')}"
            except Exception:
                extra = " result=running-or-unparseable"
        rounds = len(glob.glob(os.path.join(t, "result.*.json")))
        rows.append(f"{tid}: report={status}{extra}" + (f" fix_rounds={rounds}" if rounds else ""))
    print("\n".join(rows) if rows else "no tasks yet")
    wts = sorted(glob.glob(os.path.join(d, "wt", "*")))
    if wts:
        print("open worktrees: " + " ".join(wts))
    for f in ("spec.md", "plan.md", "SUMMARY.md"):
        if os.path.exists(os.path.join(d, f)):
            print(f"has {f}")


def cmd_ready(args):
    """Gate for "done": anything still running, unverified or contradicted blocks it."""
    d = resolve(args[0])
    blockers = []
    wts = sorted(glob.glob(os.path.join(d, "wt", "*")))
    if wts:
        blockers.append("worktrees not integrated: " + " ".join(os.path.basename(w) for w in wts))
    newest = 0.0
    for t in sorted(glob.glob(os.path.join(d, "tasks", "*"))):
        tid = os.path.basename(t)
        report = os.path.join(t, "report.md")
        result = os.path.join(t, "result.json")
        if os.path.exists(os.path.join(t, "model")) and (not os.path.exists(result) or os.path.getsize(result) == 0):
            blockers.append(f"{tid}: CLI worker still running")
            continue
        if not os.path.exists(report):
            blockers.append(f"{tid}: no report yet (worker still running, or it failed)")
            continue
        newest = max(newest, os.path.getmtime(report))
        m = re.search(r"^status:\s*(\S+)", open(report).read(), re.M)
        if not m or m.group(1) != "done":
            blockers.append(f"{tid}: status {m.group(1) if m else 'missing'}")
    summary = os.path.join(d, "SUMMARY.md")
    if not os.path.exists(summary):
        blockers.append("no SUMMARY.md: run the scribe's summary job and wait for it")
    else:
        if os.path.getmtime(summary) < newest:
            blockers.append("SUMMARY.md is older than a task report: re-run the summary job")
        m = re.search(r"^## Discrepancies\s*\n(.*?)(?=^## |\Z)", open(summary).read(), re.M | re.S)
        body = (m.group(1).strip() if m else "").strip("-* \n")
        if body and body.lower() != "none":
            blockers.append("SUMMARY.md lists discrepancies: resolve them, then re-run the summary job")
    if blockers:
        print("NOT READY:\n" + "\n".join(f"  - {b}" for b in blockers))
        sys.exit(1)
    print("READY")


TAG_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)


def _is_skill_start(rec):
    m = rec.get("message") or {}
    c = m.get("content")
    if rec.get("type") == "assistant" and isinstance(c, list):
        return any(b.get("type") == "tool_use" and b.get("name") == "Skill"
                   and str(b.get("input", {}).get("skill", "")).split(":")[-1] == "hybrid-coding" for b in c)
    if rec.get("type") == "user" and isinstance(c, str):
        return bool(re.search(r"<command-name>/?(\S+:)?hybrid-coding</command-name>", c))
    return False


def cmd_transcript(args):
    sid = args[0]
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR", os.path.expanduser("~/.claude"))
    paths = glob.glob(os.path.join(config_dir, "projects", "*", sid + ".jsonl"))
    if not paths:
        sys.exit(f"no transcript for session {sid} under {config_dir}/projects")
    recs = []
    for line in open(paths[0]):
        try:
            recs.append(json.loads(line))
        except ValueError:
            pass

    start = 0
    if "--all" not in args:
        marks = [i for i, r in enumerate(recs) if _is_skill_start(r)]
        if marks:
            start = marks[-1]
            # A model-invoked skill follows the user's request; include that request.
            for i in range(start, -1, -1):
                r = recs[i]
                c = (r.get("message") or {}).get("content")
                if r.get("type") == "user" and not r.get("isMeta") and (
                        isinstance(c, str) or any(b.get("type") == "text" for b in c or [])):
                    start = i
                    break

    with_tools = "--tools" in args
    tools, out = {}, []

    def brief(name, inp):
        for key in ("command", "file_path", "description", "skill", "pattern", "url"):
            if key in inp:
                return f"{name}: {str(inp[key])[:200]}"
        return name

    def add(role, text):
        text = TAG_RE.sub("", text).strip()
        if not text:
            return
        if out and out[-1][0] == role:
            out[-1] = (role, out[-1][1] + "\n\n" + text)
        else:
            out.append((role, text))

    for r in recs[start:]:
        if r.get("isSidechain") or r.get("isMeta"):
            continue
        c = (r.get("message") or {}).get("content")
        if r.get("type") == "assistant" and isinstance(c, list):
            for b in c:
                if b.get("type") == "text":
                    add("ORCHESTRATOR", b["text"])
                elif b.get("type") == "tool_use":
                    tools[b["id"]] = b["name"]
                    if b["name"] == "AskUserQuestion":
                        qs = b.get("input", {}).get("questions", [])
                        add("ORCHESTRATOR", "\n".join(
                            f"[asked] {q.get('question')} options: " + ", ".join(o.get("label", "") for o in q.get("options", []))
                            for q in qs))
                    elif with_tools:
                        add("ORCHESTRATOR", f"[tool] {brief(b['name'], b.get('input', {}))}")
        elif r.get("type") == "user":
            if isinstance(c, str):
                add("USER", c)
            elif isinstance(c, list):
                for b in c:
                    if b.get("type") == "text":
                        add("USER", b["text"])
                    elif b.get("type") == "tool_result" and tools.get(b.get("tool_use_id")) == "AskUserQuestion":
                        content = b.get("content")
                        if isinstance(content, list):
                            content = " ".join(x.get("text", "") for x in content)
                        add("USER", f"[answered] {content}")
                    elif b.get("type") == "tool_result" and with_tools:
                        content = b.get("content")
                        if isinstance(content, list):
                            content = " ".join(x.get("text", "") for x in content if isinstance(x, dict))
                        add("ORCHESTRATOR", f"[result] {str(content).strip()[:300]}")
    for role, text in out:
        print(f"## {role}\n{text}\n")


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: hc.py init|config|status|ready|transcript <arg> …")
    {"init": cmd_init, "config": cmd_config, "status": cmd_status, "ready": cmd_ready,
     "transcript": cmd_transcript}[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
