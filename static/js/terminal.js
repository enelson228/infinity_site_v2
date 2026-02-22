/* INFINITY Terminal — terminal.js */

(function () {
    'use strict';

    const output = document.getElementById('terminal-output');
    const input = document.getElementById('terminal-input');
    const sendBtn = document.getElementById('terminal-send');
    const logoutBtn = document.getElementById('terminal-logout');

    // Conversation history (client-side, sent with every request)
    let messages = [];
    const MAX_HISTORY = 40; // 20 exchanges (user + assistant each)

    // ── Boot sequence ────────────────────────────────────────────────────────

    function boot() {
        const lines = [
            'INFINITY TERMINAL v1.0 — MJOLNIR ARMORY SYSTEMS',
            'CLEARANCE VERIFIED. SECURE CHANNEL ESTABLISHED.',
            'TYPE YOUR QUERY AND PRESS ENTER OR [SEND].',
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━',
        ];
        lines.forEach((line) => appendBootLine(line));
        scrollToBottom();
        input.focus();
    }

    function appendBootLine(text) {
        const el = document.createElement('div');
        el.className = 'terminal-msg-boot';
        el.textContent = text;
        output.appendChild(el);
    }

    // ── Message rendering ────────────────────────────────────────────────────

    function appendUserMessage(text) {
        const el = document.createElement('div');
        el.className = 'terminal-msg-user';
        el.textContent = 'YOU > ' + text;
        output.appendChild(el);
        scrollToBottom();
    }

    /**
     * Creates an empty AI message bubble with a blinking cursor.
     * Returns the element so the typewriter can fill it in.
     */
    function createAIBubble() {
        const el = document.createElement('div');
        el.className = 'terminal-msg-ai';

        const label = document.createElement('span');
        label.className = 'terminal-ai-label';
        label.textContent = 'INFINITY > ';
        el.appendChild(label);

        const content = document.createElement('span');
        content.className = 'terminal-ai-content';
        el.appendChild(content);

        const cursor = document.createElement('span');
        cursor.className = 'terminal-cursor';
        cursor.textContent = '█';
        el.appendChild(cursor);

        output.appendChild(el);
        scrollToBottom();
        return { el, content, cursor };
    }

    function appendErrorLine(text) {
        const el = document.createElement('div');
        el.className = 'terminal-msg-error';
        el.textContent = '[ ERROR ] ' + text;
        output.appendChild(el);
        scrollToBottom();
    }

    function appendInfoLine(text) {
        const el = document.createElement('div');
        el.className = 'terminal-msg-boot';
        el.textContent = text;
        output.appendChild(el);
        scrollToBottom();
    }

    // ── Typewriter ───────────────────────────────────────────────────────────

    function typewriter(contentEl, cursorEl, text, delayMs) {
        return new Promise((resolve) => {
            let i = 0;
            function tick() {
                if (i < text.length) {
                    contentEl.textContent += text[i];
                    i++;
                    scrollToBottom();
                    setTimeout(tick, delayMs);
                } else {
                    cursorEl.remove();
                    resolve();
                }
            }
            tick();
        });
    }

    // ── Scroll ───────────────────────────────────────────────────────────────

    function scrollToBottom() {
        output.scrollTop = output.scrollHeight;
    }

    // ── Send logic ───────────────────────────────────────────────────────────

    async function sendMessage() {
        const text = input.value.trim();
        if (!text) return;

        input.value = '';
        setInputEnabled(false);

        // Handle built-in commands
        if (text.toLowerCase() === 'clear') {
            output.innerHTML = '';
            messages = [];
            boot();
            setInputEnabled(true);
            return;
        }

        // Remember command (explicit)
        if (text.toLowerCase().startsWith('remember ') || text.toLowerCase().startsWith('remember:')) {
            const content = text.replace(/^remember:?\s*/i, '').trim();
            if (!content) {
                appendErrorLine('Provide memory text after REMEMBER.');
                setInputEnabled(true);
                return;
            }
            try {
                const res = await fetch('/api/memory', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ content }),
                });
                if (!res.ok) {
                    appendErrorLine('Failed to store memory.');
                } else {
                    appendInfoLine('MEMORY STORED.');
                }
            } catch (_) {
                appendErrorLine('Connection error. Try again.');
            }
            setInputEnabled(true);
            input.focus();
            return;
        }

        appendUserMessage(text);

        // Add to history
        messages.push({ role: 'user', content: text });

        // Trim to MAX_HISTORY (keep even number so pairs stay intact)
        while (messages.length > MAX_HISTORY) {
            messages.shift();
        }

        const { content, cursor } = createAIBubble();
        const includeMemory = text.toLowerCase().startsWith('recall ') || text.toLowerCase().startsWith('recall:');
        if (includeMemory) {
            const prompt = text.replace(/^recall:?\s*/i, '').trim();
            if (!prompt) {
                cursor.remove();
                appendErrorLine('Provide a prompt after RECALL.');
                setInputEnabled(true);
                return;
            }
            messages[messages.length - 1].content = prompt;
        }

        try {
            const res = await fetch('/api/claude/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ messages, include_memory: includeMemory }),
            });

            if (res.status === 401 || res.status === 302) {
                window.location.href = '/terminal/login';
                return;
            }

            if (!res.ok) {
                cursor.remove();
                const err = await res.json().catch(() => ({ error: 'Unknown error' }));
                appendErrorLine(err.error || 'Request failed');
                setInputEnabled(true);
                return;
            }

            const data = await res.json();
            const responseText = data.content || '';

            // Add assistant reply to history
            messages.push({ role: 'assistant', content: responseText });

            // Trim again after adding assistant message
            while (messages.length > MAX_HISTORY) {
                messages.shift();
            }

            await typewriter(content, cursor, responseText, 15);
        } catch (err) {
            cursor.remove();
            appendErrorLine('Connection error. Check network and try again.');
        }

        setInputEnabled(true);
        input.focus();
    }

    function setInputEnabled(enabled) {
        input.disabled = !enabled;
        sendBtn.disabled = !enabled;
        if (enabled) {
            sendBtn.classList.remove('loading');
        } else {
            sendBtn.classList.add('loading');
        }
    }

    // ── Event listeners ──────────────────────────────────────────────────────

    sendBtn.addEventListener('click', sendMessage);

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            sendMessage();
        }
    });

    logoutBtn.addEventListener('click', async () => {
        try {
            await fetch('/api/terminal/logout', { method: 'POST' });
        } finally {
            window.location.href = '/terminal/login';
        }
    });

    // ── Init ─────────────────────────────────────────────────────────────────

    boot();
})();
