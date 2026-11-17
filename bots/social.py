"""Sparse, contextual local chat. No external model and no player-text echo."""
import random
import re
import time
from wire import string

VOICE = {
    'Awan': {
        'idle': ('hmm', 'bentar'),
        'quest': ('otw', 'yang ini dulu deh', 'quest lagi'),
        'grind': ('coba yang ini', 'farm bentar', 'nyari drop dulu'),
        'party': ('ikut sini?', 'bentar nyusul', 'ok'),
        'combat': ('tebel juga', 'ini dulu', 'satu lagi'),
        'done': ('udah', 'beres', 'next'),
        'hello': ('yo', 'oi', 'halo'),
        'where': ('di sini', 'bentar, nyusul'),
        'help': ('invite aja', 'boleh, invite'),
        'reply': ('iya?', 'kenapa?', 'yo?'),
    },
    'Arden': {
        'idle': ('yo', 'hmm'),
        'quest': ('bentar quest dulu', 'otw npc', 'masih quest'),
        'grind': ('farm dulu deh', 'cari exp bentar', 'coba sini'),
        'party': ('otw', 'gw ikut', 'jangan ngebut wkwk'),
        'combat': ('gas', 'fokus yang ini', 'ok lanjut'),
        'done': ('done', 'aman', 'lanjut'),
        'hello': ('yo', 'sup', 'oi'),
        'where': ('otw', 'belakang lu'),
        'help': ('gas invite', 'invite gw'),
        'reply': ('ya?', 'apa?', 'kenapa bro'),
    },
}


class LocalChat:
    def __init__(self, clock=time.monotonic, name='Awan', rng=None):
        self.clock = clock
        self.rng = rng or random.Random()
        self.last = float('-inf')
        self.pending = None
        self.name = name
        self.mode = 'idle'
        self.lines = VOICE.get(name, VOICE['Awan'])
        self.last_line = None
        self.next_ambient = self.clock() + self.rng.uniform(60, 120)
        self.reply_at = 0

    def event(self, kind):
        if kind in self.lines and self.rng.random() < .25:
            self.pending = self.choose(kind)
            self.reply_at = self.clock() + self.rng.uniform(3, 9)

    def choose(self, kind):
        options = [line for line in self.lines[kind] if line != self.last_line]
        return self.rng.choice(options or self.lines[kind])

    def hear(self, sender, message):
        words = set(re.findall(r'[a-z]+', message.lower()[:500]))
        if sender in ('Awan', 'Arden') or self.name.lower() not in words:
            return
        kind = ('hello' if words & {'hi', 'hello', 'halo', 'hey', 'hai', 'yo', 'oi'} else
                'where' if words & {'where', 'mana', 'dimana'} else
                'help' if words & {'help', 'bantu', 'party', 'invite'} else 'reply')
        self.pending = self.choose(kind)
        self.reply_at = self.clock() + self.rng.uniform(3, 9)

    def next_payload(self):
        now = self.clock()
        if now - self.last < 90:
            return None
        if self.pending:
            if now < self.reply_at:
                return None
            line = self.pending
        else:
            if now < self.next_ambient:
                return None
            self.next_ambient = now + self.rng.uniform(180, 360)
            if self.mode == 'idle' or self.rng.random() < .5:
                return None
            line = self.choose(self.mode)
        self.pending = None
        self.last = now
        self.last_line = line
        self.next_ambient = now + self.rng.uniform(180, 360)
        return string('say ' + line)
