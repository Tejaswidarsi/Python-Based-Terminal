from flask import Flask, request, jsonify
import os, shutil, psutil, uuid, shlex
import re

app = Flask(__name__, static_folder='static', static_url_path='/')

SANDBOX_ROOT = os.path.abspath('sandbox')
os.makedirs(SANDBOX_ROOT, exist_ok=True)

sessions = {}

def ensure_within_sandbox(path):
    abs_path = os.path.abspath(path)
    if os.path.commonpath([abs_path, SANDBOX_ROOT]) != SANDBOX_ROOT:
        raise ValueError("Access denied")
    return abs_path

def get_cwd_rel(sid):
    cwd = sessions.get(sid, SANDBOX_ROOT)
    rel = os.path.relpath(cwd, SANDBOX_ROOT)
    return '/' if rel == '.' else '/' + rel

def make_response(output, sid, extra_data=None):
    response = {"output": output, "cwd": get_cwd_rel(sid)}
    if extra_data:
        response.update(extra_data)
    return jsonify(response)

def parse_natural_language(cmdline, cwd):
    cmdline = cmdline.lower().strip()
    if "create a folder" in cmdline and "move" in cmdline:
        match = re.search(r"create a folder (\w+).*move (\w+\.txt|\w+) into it", cmdline)
        if match:
            folder, file = match.groups()
            return f"mkdir {folder} && mv {file} {folder}"
    elif "create a file" in cmdline:
        match = re.search(r"create a file (\w+\.txt|\w+)", cmdline)
        if match:
            return f"touch {match.group(1)}"
    elif "copy" in cmdline and "from" in cmdline and "to" in cmdline:
        match = re.search(r"copy (\w+\.txt|\w+) from (\w+) ?(folder)? to (\w+) ?(folder)?", cmdline)
        if match:
            source_file, source_folder, _, dest_folder, _ = match.groups()
            return f"cp {source_folder}/{source_file} {dest_folder}"
    elif "write" in cmdline and "to" in cmdline:
        match = re.search(r"write ?(?:(.+) )?to (\w+\.txt|\w+)", cmdline)
        if match:
            content = match.group(1) if match.group(1) else ""
            filename = match.group(2)
            if content:
                return f"nano {filename} {content}"
            return f"nano {filename}"
    elif "move" in cmdline and "to" in cmdline:
        match = re.search(r"move (\w+\.txt|\w+) to (\w+)", cmdline)
        if match:
            file, dest = match.groups()
            return f"mv {file} {dest}"
    elif "delete" in cmdline or "remove" in cmdline:
        match = re.search(r"(delete|remove) ?(\w+\.txt|\w+)(?: folder)?", cmdline)
        if match:
            target = match.group(2)
            if "folder" in cmdline and os.path.isdir(os.path.join(cwd, target)):
                return f"rmdir {target}"
            return f"rm {target}"
    elif "show current directory" in cmdline or "where am i" in cmdline:
        return "pwd"
    elif "go to" in cmdline or "change to" in cmdline:
        match = re.search(r"(go to|change to) (\w+|..)", cmdline)
        if match:
            directory = match.group(2)
            return f"cd {directory}"
    elif "show cpu" in cmdline or "check cpu" in cmdline:
        return "cpu"
    elif "show memory" in cmdline or "check memory" in cmdline:
        return "mem"
    return cmdline

@app.route('/init', methods=['GET'])
def init():
    sid = uuid.uuid4().hex
    sessions[sid] = SANDBOX_ROOT
    return jsonify({"session_id": sid, "cwd": '/'})

@app.route('/run', methods=['POST'])
def run_command():
    data = request.json or {}
    sid = data.get('session_id')
    cmdline = data.get('command', '')
    filename = data.get('filename')
    content = data.get('content')
    if not sid or sid not in sessions:
        return jsonify({"output": "Invalid session. Reload page."}), 400

    cwd = sessions[sid]
    if not any(cmdline.startswith(c) for c in ['pwd', 'ls', 'cd', 'mkdir', 'touch', 'cat', 'rm', 'rmdir', 'mv', 'cp', 'cpu', 'mem', 'ps', 'nano', 'clear', 'cls']):
        cmdline = parse_natural_language(cmdline, cwd)
    parts = shlex.split(cmdline)
    if not parts:
        return make_response('', sid)
    cmd, args = parts[0], parts[1:]

    try:
        if cmd == 'pwd':
            return make_response(get_cwd_rel(sid), sid)

        if cmd == 'ls':
            target = cwd if not args else ensure_within_sandbox(os.path.join(cwd, args[0]))
            items = os.listdir(target)
            return make_response('\n'.join(items) if items else 'Directory is empty', sid)

        if cmd == 'cd':
            if not args or args[0] in ['~', '/']:
                target = SANDBOX_ROOT
                sessions[sid] = target
                return make_response(f"Changed to {get_cwd_rel(sid)}", sid)
            target = ensure_within_sandbox(os.path.join(cwd, args[0]))
            if os.path.isdir(target):
                sessions[sid] = target
                return make_response(f"Changed to {get_cwd_rel(sid)}", sid)
            return make_response(f"No such directory: {args[0]}", sid)

        if cmd == 'mkdir':
            if not args: return make_response("Usage: mkdir NAME", sid)
            target = ensure_within_sandbox(os.path.join(cwd, args[0]))
            os.mkdir(target)
            return make_response(f"Created directory {args[0]}", sid)

        if cmd == 'touch':
            if not args: return make_response("Usage: touch FILENAME", sid)
            target = ensure_within_sandbox(os.path.join(cwd, args[0]))
            with open(target, 'a') as f:
                pass
            return make_response(f"Created file {args[0]}", sid)

        if cmd == 'cat':
            if not args: return make_response("Usage: cat FILE", sid)
            target = ensure_within_sandbox(os.path.join(cwd, args[0]))
            try:
                with open(target, 'r') as f:
                    content = f.read()
                    return make_response(content or 'File is empty', sid)
            except FileNotFoundError:
                return make_response(f"Error: File {args[0]} not found", sid)

        if cmd == 'rm':
            if not args: return make_response("Usage: rm FILE", sid)
            target_rel = args[0]
            target = ensure_within_sandbox(os.path.join(cwd, target_rel))
            print(f"Debug: Attempting to rm '{target}' (rel: {target_rel})")
            if os.path.isdir(target):
                return make_response("Use rmdir DIR to remove directories", sid)
            if not os.path.exists(target):
                return make_response(f"Error: File '{target_rel}' not found", sid)
            os.remove(target)
            return make_response(f"Removed {target_rel}", sid)

        if cmd == 'rmdir':
            if not args: return make_response("Usage: rmdir DIR", sid)
            target_rel = args[0]
            target = ensure_within_sandbox(os.path.join(cwd, target_rel))
            print(f"Debug: Attempting to rmdir '{target}' (rel: {target_rel})")
            if not os.path.isdir(target):
                return make_response(f"Error: '{target_rel}' is not a directory", sid)
            if not os.path.exists(target):
                return make_response(f"Error: Directory '{target_rel}' not found", sid)
            shutil.rmtree(target)
            return make_response(f"Removed directory {target_rel}", sid)

        if cmd == 'mv':
            if len(args) != 2: return make_response("Usage: mv SRC DEST", sid)
            src = ensure_within_sandbox(os.path.join(cwd, args[0])); dst = ensure_within_sandbox(os.path.join(cwd, args[1]))
            shutil.move(src, dst)
            return make_response("Moved", sid)

        if cmd == 'cp':
            if len(args) != 2: return make_response("Usage: cp SRC DEST", sid)
            src = ensure_within_sandbox(os.path.join(cwd, args[0])); dst = ensure_within_sandbox(os.path.join(cwd, args[1]))
            if os.path.isdir(src): shutil.copytree(src, dst)
            else: shutil.copy2(src, dst)
            return make_response("Copied", sid)

        if cmd == 'cpu':
            cpu_percent = psutil.cpu_percent(interval=0.3)
            return make_response(f"{cpu_percent}%", sid, {"cpu": cpu_percent})

        if cmd == 'mem':
            vm = psutil.virtual_memory()
            mem_percent = vm.percent
            mem_total = vm.total // (1024 * 1024)
            return make_response(f"{mem_percent}% used ({mem_total}MB total)", sid, {"memory": {"percent": mem_percent, "total": mem_total}})

        if cmd == 'ps':
            procs = []
            for pid in psutil.pids()[:50]:
                try:
                    p = psutil.Process(pid)
                    procs.append(f"{pid}\t{p.name()}\t{p.status()}")
                except: pass
            return make_response('\n'.join(procs), sid)

        if cmd == 'nano':
            if not args:
                return make_response("Usage: nano FILE", sid)
            filename = args[0]
            target = ensure_within_sandbox(os.path.join(cwd, filename))
            if content is not None:
                try:
                    with open(target, 'w') as f:
                        f.write(content)
                    return make_response(f"Wrote to {filename}", sid)
                except Exception as e:
                    return make_response(f"Error: Unable to write to {filename} - {str(e)}", sid)
            return jsonify({"editor": filename, "output": "", "cwd": get_cwd_rel(sid)})
        if cmd in ('clear', 'cls'):
            return make_response("", sid)

        return make_response(f"Command not found: {cmd}", sid)

    except Exception as e:
        print(f"Debug Exception: {e} for command '{cmdline}' in cwd '{cwd}'")
        return make_response("Error: " + str(e), sid)

@app.route('/')
def index():
    return app.send_static_file('index.html')

if __name__ == '__main__':
    app.run(debug=True)