"""Build-specific Lapis transport prototype; no production-use claim.

Compatibility implementation of this legacy game's native handshake, not a
general-purpose security protocol. Frame bounds are enforced before allocation.
"""
import asyncio
import secrets
import struct


class ProtocolError(Exception):
    pass


class Reader:
    def __init__(self, data):
        self.data = memoryview(data)
        self.offset = 0

    def take(self, count):
        if count < 0 or self.offset + count > len(self.data):
            raise ProtocolError('Truncated message')
        result = bytes(self.data[self.offset:self.offset + count])
        self.offset += count
        return result

    def number(self, fmt):
        return struct.unpack('<' + fmt, self.take(struct.calcsize('<' + fmt)))[0]

    def text(self):
        return self.take(self.number('H')).decode('cp950', errors='replace')

    def end(self):
        if self.offset != len(self.data):
            raise ProtocolError('Unexpected trailing message data')


class RC4:
    def __init__(self, key):
        if not key:
            raise ValueError('Empty key')
        self.s = list(range(256))
        j = 0
        for i in range(256):
            j = (j + self.s[i] + key[i % len(key)]) & 255
            self.s[i], self.s[j] = self.s[j], self.s[i]
        self.i = self.j = 0

    def crypt(self, data):
        out = bytearray()
        for byte in data:
            self.i = (self.i + 1) & 255
            self.j = (self.j + self.s[self.i]) & 255
            self.s[self.i], self.s[self.j] = self.s[self.j], self.s[self.i]
            out.append(byte ^ self.s[(self.s[self.i] + self.s[self.j]) & 255])
        return bytes(out)


def string(value):
    raw = value.encode('ascii')
    if len(raw) > 65535:
        raise ValueError('String too large')
    return struct.pack('<H', len(raw)) + raw


def rsa_session(n, e, key):
    size = (n.bit_length() + 7) // 8
    if not 64 <= size <= 512 or e < 3 or e % 2 == 0:
        raise ProtocolError('Invalid RSA public key')
    padding = bytearray()
    while len(padding) < size - len(key) - 3:
        b = secrets.randbelow(255) + 1
        padding.append(b)
    message = b'\x00\x02' + bytes(padding) + b'\x00' + key
    return pow(int.from_bytes(message, 'big'), e, n).to_bytes(size, 'big')


class Connection:
    def __init__(self, reader, writer):
        self.reader, self.writer = reader, writer
        self.tx = self.rx = None
        self.idle_timeout = 8

    async def exact(self, count, timeout=8):
        try:
            return await asyncio.wait_for(self.reader.readexactly(count), timeout)
        except asyncio.IncompleteReadError:
            raise ProtocolError('Peer closed connection') from None
        except asyncio.TimeoutError:
            raise ProtocolError('Receive deadline exceeded') from None

    async def handshake(self):
        nlen, elen = struct.unpack('<II', await self.exact(8))
        if not 64 <= nlen <= 512 or not 1 <= elen <= 8:
            raise ProtocolError(f'Unexpected public-key sizes: {nlen}, {elen}')
        n = int.from_bytes(await self.exact(nlen), 'big')
        e = int.from_bytes(await self.exact(elen), 'big')
        key = secrets.token_bytes(5)
        self.writer.write(rsa_session(n, e, key))
        await self.writer.drain()
        self.tx, self.rx = RC4(key), RC4(key)
        return nlen * 8

    async def send(self, ncid, payload=b''):
        body = struct.pack('<H', ncid) + payload
        if not 2 <= len(body) <= 8192:
            raise ProtocolError('Invalid frame size')
        self.writer.write(struct.pack('<h', len(body)) + self.tx.crypt(body))
        await self.writer.drain()

    async def receive(self):
        size, = struct.unpack('<h', await self.exact(2, self.idle_timeout))
        if not 2 <= size <= 8192:
            raise ProtocolError(f'Invalid received frame size: {size}')
        body = self.rx.crypt(await self.exact(size))
        return struct.unpack_from('<H', body)[0], body[2:]

    async def close(self):
        self.writer.close()
        await self.writer.wait_closed()
