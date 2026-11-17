"""Temporary game-only bridge for a human observer of the isolated lab.

Forwards opaque encrypted traffic; never records payloads. No admin port. The
host side binds only the three existing Tailscale game ports, behind ak-firewall.
"""
import asyncio
import json
import os
from pathlib import Path
import signal
import sys

PORTS = (6543, 5567, 10020)
def _lab_address():
    if os.environ.get('AK_SERVER_IP'):
        return os.environ['AK_SERVER_IP']
    conf = Path('/etc/ak-server.conf')
    if conf.is_file():
        for line in conf.read_text().splitlines():
            if line.startswith('AK_SERVER_IP='):
                return line.split('=', 1)[1].strip().strip('"\'')
    return '100.64.0.10'
LAB_ADDRESS = _lab_address()
BASE = Path('/var/lib/ak-bot-lab/run/observer-relay')


async def copy(reader, writer):
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        writer.close()


async def bridge(reader, writer, port, inside):
    try:
        if inside:
            remote_reader, remote_writer = await asyncio.wait_for(asyncio.open_connection(
                LAB_ADDRESS if port != 6543 else '127.0.0.1', port, local_addr=('127.0.0.1', 0)), 5)
        else:
            remote_reader, remote_writer = await asyncio.wait_for(asyncio.open_unix_connection(str(BASE / f'{port}.sock')), 5)
        await asyncio.gather(copy(reader, remote_writer), copy(remote_reader, writer))
    except (OSError, asyncio.TimeoutError):
        writer.close()


async def main():
    inside = sys.argv[1] == 'inside'
    if inside:
        from lab import assert_inside
        assert_inside()
        BASE.mkdir(mode=0o700, exist_ok=True)
    else:
        # Refuse to occupy live game ports while production is active.
        proc = await asyncio.create_subprocess_exec('systemctl', 'is-active', '--quiet', 'aurakingdom')
        if await proc.wait() == 0:
            raise SystemExit('Production is active; refusing observer bridge')
    servers = []
    for port in PORTS:
        async def handler(reader, writer, selected=port):
            await bridge(reader, writer, selected, inside)
        if inside:
            path = BASE / f'{port}.sock'
            if path.exists():
                path.unlink()
            server = await asyncio.start_unix_server(handler, path=str(path))
            path.chmod(0o600)
        else:
            server = await asyncio.start_server(handler, host=LAB_ADDRESS, port=port)
        servers.append(server)
    print('Game-only observer bridge ready (' + ('isolated' if inside else 'Tailscale') + ').', flush=True)
    done = asyncio.Event()
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, done.set)
    await done.wait()
    for server in servers:
        server.close()
        await server.wait_closed()


if __name__ == '__main__':
    asyncio.run(main())
