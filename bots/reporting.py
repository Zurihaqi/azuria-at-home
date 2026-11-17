"""Bounded, credential-free prototype telemetry for the owner dashboard."""
import json
import os
from pathlib import Path
import re
import time


class Reporter:
    def __init__(self, directory=Path('/run/pilot'), world='isolated'):
        self.directory = Path(directory)
        self.state = {'phase':'connecting', 'task':'Connecting to the isolated test world', 'updated_at':time.time()}
        self.update()
        self.emit('info', 'Bot session started in the ' + world + ' world')

    def update(self, **values):
        self.state.update(values, updated_at=time.time())
        temporary = self.directory / 'status-public.tmp'
        temporary.write_text(json.dumps(self.state), encoding='utf-8')
        temporary.chmod(0o600)
        temporary.replace(self.directory / 'status-public.json')

    def emit(self, level, message):
        # Do not record native payloads, credentials or opaque session objects.
        if not isinstance(message, str) or re.search(r'pass(?:word|wd|phrase)?|secret|ticket|token|credential|private.?key|hash|[a-f0-9]{32,}', message, re.I):
            if level == 'error':
                self.update(phase='failed',task='Bot paused after a failure',last_failure='Error details withheld by privacy filter')
            return
        message = message[:300]
        path = self.directory / 'events-public.jsonl'
        if path.exists() and path.stat().st_size > 2 * 1024 * 1024:
            path.replace(self.directory / 'events-public.previous.jsonl')
        row = {'time':time.time(), 'level':level, 'message':message, 'bot':self.state.get('name', 'Pilot')}
        with path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        path.chmod(0o600)
        if level == 'error':
            self.update(phase='failed', task='Test paused after a failure', last_failure=message)

    def message(self, message):
        prefixes = ('Native map entry:', 'Native player state:', 'Native character present:',
                    'Native quest UI:', 'Native quest update:', 'Native dialogue:',
                    'Native equipment transfer result:', 'Native movement endpoint confirmed',
                    'Native movement correction:', 'Native skill acknowledgement:',
                    'Requested ordinary', 'Requested normal', 'Requested one ordinary',
                    'Tutorial checkpoint:', 'Collision-checked route:',
                    'Quest objective:', 'Quest ', 'No supported authored quest',
                    'Melee landed', 'Killed ', 'Treasure ', 'Following ', 'Combat on ',
                    'Native system message:',
                    'Requesting a native revive', 'Sent the native revive request', 'Pilot died;',
                    'Native logout countdown', 'Native server closed', 'Protocol probe stopped:')
        if not message.startswith(prefixes):
            return
        level = 'error' if message.startswith('Protocol probe stopped:') else 'warning' if message.startswith('Native movement correction:') else 'info'
        self.emit(level, message)
