"""Start or stop the activity bots with the parameters of the last deployment.

Only two verbs exist and no flag may be invented at start time: launching a bot
replays the exact `launch` record the newest successful deploy_activity run
wrote to /var/backups/ak-bots/*/deployment.json, so a dashboard Start can never
run flags that were never reviewed or tested. Starting additionally requires
the game service to be active and normal-world access to be enabled for the
profile; stopping merely stops the bot unit and leaves the game, VM, and
databases untouched.

Run as root on the VM: bot_control.py start|stop awan|arden
Prints one JSON object; exit 1 with {"error": ...} on refusal.
"""
import json
from pathlib import Path
import subprocess as sp
import sys

ROOT = Path('/opt/ak-bot-prototype')
PROFILES = {'awan': 'pilot', 'arden': 'arden'}
UNIT = 'ak-bot-{}'


def unit(profile):
    return UNIT.format(profile)


def running(profile):
    return sp.run(['systemctl', 'is-active', '--quiet', unit(profile)]).returncode == 0


def launch_record(profile):
    if running(profile):
        raise RuntimeError(f'Bot {profile} is already running')
    for record in sorted(Path('/var/backups/ak-bots').glob('*/deployment.json'), reverse=True):
        try:
            launch = json.loads(record.read_text()).get('launch', {}).get(profile)
        except (OSError, ValueError):
            continue
        if launch:
            return launch
    raise RuntimeError('No recorded bot deployment; run deploy_activity.py first')


def start(profile):
    if sp.run(['systemctl', 'is-active', '--quiet', 'aurakingdom']).returncode != 0:
        raise RuntimeError('The game service is not active; start the realm first')
    world = Path('/etc/ak-bots/arden-world.json' if profile == 'arden' else '/etc/ak-bots/normal-world.json')
    try:
        enabled = json.loads(world.read_text()).get('enabled') is True
    except (OSError, ValueError):
        enabled = False
    if not enabled:
        raise RuntimeError(f'Normal-world bot access is not enabled for {profile}')
    launch = launch_record(profile)
    log = '/var/lib/ak-bots/' + PROFILES[profile] + '/session.log'
    sp.run(['systemd-run', '--collect', '--unit=' + unit(profile), '--uid=akbots',
            '--property=NoNewPrivileges=yes', '--property=WorkingDirectory=' + str(ROOT),
            '--property=StandardOutput=append:' + log,
            '--property=StandardError=append:' + log,
            '/usr/bin/python3', '-u', str(ROOT / 'probe_login.py'), '--normal-world',
            *launch['args'], *launch['flags'], '--chat', '--continuous', '--encounter-learning'],
           check=True, timeout=50)
    return {'message': f'Bot {profile} started with the flags of the last deployment.'}


def stop(profile):
    if not running(profile):
        return {'message': f'Bot {profile} was not running.'}
    sp.run(['systemctl', 'stop', unit(profile)], check=True, timeout=50)
    return {'message': f'Bot {profile} stopped. Quest progress is preserved on the server.'}


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ('start', 'stop') or sys.argv[2] not in PROFILES:
        raise SystemExit('usage: bot_control.py start|stop awan|arden')
    try:
        result = (start if sys.argv[1] == 'start' else stop)(sys.argv[2])
    except Exception as exc:
        print(json.dumps({'error': str(exc)[-500:]}))
        raise SystemExit(1)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
