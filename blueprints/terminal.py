import time
import psutil
from flask import Blueprint, render_template, request, jsonify, session
import anthropic
import config
import database
from auth import login_required

terminal_bp = Blueprint('terminal', __name__)

TERMINAL_SYSTEM_PROMPT = (
    "You are INFINITY, a high-level A.I. construct integrated into the MJOLNIR GEN3 armor systems "
    "and this tactical homelab. You assist with system administration, networking, and security. "
    "Your tone is professional, efficient, and slightly detached, like Auntie Dot or Cortana. "
    "Respond with high-signal, technical clarity. Use military-style terminology where appropriate "
    "(e.g., 'Targeting parameters updated', 'Uplink established', 'Node synchronized')."
)

_anthropic_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

def get_system_context():
    """Gather current system state for AI context."""
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    load = psutil.getloadavg()
    uptime_sec = int(time.time() - psutil.boot_time())
    uptime_h = uptime_sec // 3600
    uptime_m = (uptime_sec % 3600) // 60
    
    projects = database.list_projects()
    status_summary = []
    for p in projects:
        status_summary.append(f"{p['name']}: {p['status']} ({p['response_time'] or '0'}ms)")
    
    context = (
        f"\n\nCURRENT SYSTEM STATUS:\n"
        f"- CPU_LOAD: {cpu}%\n"
        f"- RAM_ALLOC: {ram}%\n"
        f"- LOAD_AVG: {load[0]}, {load[1]}, {load[2]}\n"
        f"- UPTIME: {uptime_h}h {uptime_m}m\n"
        f"- ACTIVE_NODES:\n" + "\n".join(f"  * {s}" for s in status_summary)
    )
    return context

@terminal_bp.route('/terminal')
@login_required
def terminal():
    return render_template('terminal.html')

@terminal_bp.route('/api/memory', methods=['GET'])
@login_required
def api_memory_list():
    user_id = int(session.get('user_id'))
    return jsonify({'memories': database.list_memories(user_id)})

@terminal_bp.route('/api/memory', methods=['POST'])
@login_required
def api_memory_add():
    data = request.get_json(silent=True) or {}
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'error': 'Content required'}), 400
    user_id = int(session.get('user_id'))
    database.add_memory(user_id, content)
    from utils import client_ip
    database.append_audit('memory_add', client_ip(), actor_user_id=user_id, target_user_id=user_id)
    return jsonify({'success': True})

_CHAT_MAX_MESSAGES = 40
_CHAT_MAX_MESSAGE_CHARS = 8000

@terminal_bp.route('/api/claude/chat', methods=['POST'])
@login_required
def api_claude_chat():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Invalid request body'}), 400

    messages = data.get('messages', [])
    if not isinstance(messages, list) or len(messages) > _CHAT_MAX_MESSAGES:
        return jsonify({'error': 'Invalid messages'}), 400

    last_msg = messages[-1]['content'] if messages else ""
    
    # ── Command Interceptor ────────────────────────────────────────────────
    if last_msg.startswith('/'):
        cmd = last_msg[1:].lower().split()
        if not cmd:
            return jsonify({'content': 'INVALID COMMAND.'})
        
        if cmd[0] == 'sys':
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            uptime = int(time.time() - psutil.boot_time())
            return jsonify({'content': f"SYSTEM STATS:\nCPU: {cpu}%\nRAM: {ram}%\nUPTIME: {uptime}s"})
        
        if cmd[0] == 'whoami':
            username = session.get('username')
            role = session.get('role')
            return jsonify({'content': f"IDENTITY: {username}\nCLEARANCE: {role.upper()}"})
            
        if cmd[0] == 'ls':
            files = database.list_files()
            if not files:
                return jsonify({'content': "UPLINK CACHE EMPTY."})
            flist = "\n".join(f"- {f['name']} ({round(f['size']/1024/1024, 2)}MB)" for f in files[:10])
            return jsonify({'content': f"RECENT UPLINK FILES:\n{flist}"})

        if cmd[0] == 'status':
            projects = database.list_projects()
            plist = "\n".join(f"[{p['status'].upper()}] {p['name']} - {p['response_time'] or 0}ms" for p in projects)
            return jsonify({'content': f"INFRASTRUCTURE STATUS:\n{plist}"})

        if cmd[0] == 'nodes':
            projects = database.list_projects()
            output = "ACTIVE INFRASTRUCTURE NODES:\n"
            output += "ID" + " " * 18 + "STATUS" + " " * 10 + "LATENCY\n"
            output += "-" * 50 + "\n"
            for p in projects:
                name = p['name'][:18].ljust(20)
                status = f"[{p['status'].upper()}]".ljust(15)
                latency = f"{p['response_time'] or 0}ms"
                output += f"{name} {status} {latency}\n"
            return jsonify({'content': output})


    # ── AI Generation ──────────────────────────────────────────────────────
    sanitized = []
    for msg in messages:
        if not isinstance(msg, dict):
            return jsonify({'error': 'Invalid message format'}), 400
        role = msg.get('role', '')
        content = msg.get('content', '')
        if role not in ('user', 'assistant') or not isinstance(content, str):
            return jsonify({'error': 'Invalid message format'}), 400
        sanitized.append({'role': role, 'content': content[:_CHAT_MAX_MESSAGE_CHARS]})

    try:
        system_prompt = TERMINAL_SYSTEM_PROMPT + get_system_context()
        
        if data.get('include_memory'):
            user_id = int(session.get('user_id'))
            memories = database.list_memories(user_id)
            if memories:
                mem_lines = '\n'.join(f"- {m['content']}" for m in memories)
                system_prompt += (
                    "\n\nUSER MEMORY (explicitly requested):\n" +
                    mem_lines
                )
        
        response = _anthropic_client.messages.create(
            model='claude-3-5-sonnet-20241022',
            max_tokens=8096,
            system=system_prompt,
            messages=sanitized,
        )
        content_blocks = response.content
        if not content_blocks or not hasattr(content_blocks[0], 'text'):
            return jsonify({'error': 'Unexpected response format from AI'}), 502
        return jsonify({'content': content_blocks[0].text})
    except anthropic.APIStatusError as e:
        return jsonify({'error': f'AI service error: {e}'}), 502
    except Exception as e:
        return jsonify({'error': f'Internal error: {e}'}), 500
