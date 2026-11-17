"""Unit cleanup: release temporary game bridge before restoring production."""
import subprocess
subprocess.run(['systemctl', 'stop', 'ak-bot-observer'], check=False)
subprocess.run(['systemctl', 'start', 'aurakingdom'], check=True)
