import os
import re
import subprocess
from flask import Blueprint, render_template, jsonify, request
from auth import login_required
import config

osint_bp = Blueprint('osint', __name__)

KALI_TOOLS = [
    {
        "id": "whois",
        "name": "WHOIS Lookup",
        "description": "Query WHOIS databases for domain registration information",
        "category": "Information Gathering",
        "icon": "🌐",
        "command": "whois",
        "params": ["domain"],
        "example": "google.com"
    },
    {
        "id": "dig",
        "name": "DNS Lookup (dig)",
        "description": "Query DNS servers for domain records",
        "category": "Network Reconnaissance",
        "icon": "📡",
        "command": "dig",
        "params": ["domain"],
        "example": "google.com"
    },
    {
        "id": "nslookup",
        "name": "NS Lookup",
        "description": "Query DNS name servers",
        "category": "Network Reconnaissance",
        "icon": "🔍",
        "command": "nslookup",
        "params": ["domain"],
        "example": "google.com"
    },
    {
        "id": "nmap",
        "name": "Nmap Scan",
        "description": "Network exploration and security auditing",
        "category": "Network Scanning",
        "icon": "🔎",
        "command": "nmap",
        "params": ["target", "ports"],
        "example": "-sV -p 1-1000 localhost"
    },
    {
        "id": "curl",
        "name": "cURL",
        "description": "Transfer data from or to a server",
        "category": "Web Analysis",
        "icon": "🌐",
        "command": "curl",
        "params": ["url"],
        "example": "-I https://google.com"
    },
    {
        "id": "host",
        "name": "Host Lookup",
        "description": "DNS lookup utility",
        "category": "Network Reconnaissance",
        "icon": "🏷️",
        "command": "host",
        "params": ["domain"],
        "example": "google.com"
    },
    {
        "id": "ping",
        "name": "Ping",
        "description": "Send ICMP ECHO_REQUEST packets to network hosts",
        "category": "Network Diagnostics",
        "icon": "📶",
        "command": "ping",
        "params": ["target", "count"],
        "example": "-c 4 localhost"
    },
    {
        "id": "traceroute",
        "name": "Traceroute",
        "description": "Print the route packets trace to network host",
        "category": "Network Diagnostics",
        "icon": "🛤️",
        "command": "traceroute",
        "params": ["target"],
        "example": "google.com"
    },
    {
        "id": "whatweb",
        "name": "WhatWeb",
        "description": "Next generation web scanner - identify websites",
        "category": "Web Analysis",
        "icon": "🕸️",
        "command": "whatweb",
        "params": ["url"],
        "example": "https://google.com"
    },
    {
        "id": "theharvester",
        "name": "theHarvester",
        "description": "Gather emails, subdomains, hosts, employee names from public sources",
        "category": "OSINT",
        "icon": "📧",
        "command": "theHarvester",
        "params": ["domain", "source"],
        "example": "-d google.com -b all"
    }
]

def is_safe_command(cmd: str, args: str) -> bool:
    dangerous_chars = [';', '|', '&', '$', '`', '>', '<', '\n', '\r']
    combined = f"{cmd} {args}"
    for char in dangerous_chars:
        if char in combined:
            return False
    if not re.match(r'^[a-zA-Z0-9\-_.\s/:\?=&%]+$', args):
        return False
    return True

def get_safe_command_args(tool_id: str, user_args: str) -> tuple:
    tool = next((t for t in KALI_TOOLS if t['id'] == tool_id), None)
    if not tool:
        return None, None
    
    cmd = tool['command']
    
    if not is_safe_command(cmd, user_args):
        return None, None
    
    return cmd, user_args

@osint_bp.route('/osint')
@login_required
def osint():
    return render_template('osint.html', tools=KALI_TOOLS)

@osint_bp.route('/api/osint/tools')
@login_required
def api_osint_tools():
    return jsonify({ 'tools': KALI_TOOLS })

@osint_bp.route('/api/osint/execute', methods=['POST'])
@login_required
def api_osint_execute():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        tool_id = data.get('tool_id', '').strip()
        args = data.get('args', '').strip()
        
        if not tool_id:
            return jsonify({'error': 'Tool ID required'}), 400
        
        cmd, safe_args = get_safe_command_args(tool_id, args)
        
        if not cmd:
            return jsonify({'error': 'Invalid tool or unsafe command'}), 400
        
        command_parts = [cmd] + safe_args.split()
        
        try:
            result = subprocess.run(
                command_parts,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            return jsonify({
                'success': True,
                'output': result.stdout,
                'error': result.stderr,
                'returncode': result.returncode
            })
        except subprocess.TimeoutExpired:
            return jsonify({'error': 'Command timed out (30s limit)'}), 408
        except FileNotFoundError:
            return jsonify({'error': f'Tool "{cmd}" not found on this system'}), 404
        except Exception as e:
            return jsonify({'error': f'Execution error: {str(e)}'}), 500
            
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@osint_bp.route('/api/osint/validate', methods=['POST'])
@login_required
def api_osint_validate():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    tool_id = data.get('tool_id', '')
    args = data.get('args', '')
    
    cmd, safe_args = get_safe_command_args(tool_id, args)
    
    if cmd:
        return jsonify({'valid': True, 'command': f"{cmd} {safe_args}"})
    else:
        return jsonify({'valid': False, 'error': 'Invalid or unsafe command'})
