"""Phone observations for the existing local System and Bluetooth views."""
import json
import math
import subprocess
import time


def output(command):
    try:
        return subprocess.check_output(command, stderr=subprocess.DEVNULL,
                                       timeout=3, text=True).strip()
    except (OSError, UnicodeError, subprocess.SubprocessError):
        return ''


class PhoneStatus:
    def __init__(self, system_snapshot):
        self.system_snapshot = system_snapshot
        self.power = []
        self.next_battery = 0

    def __call__(self):
        try:
            status = self.system_snapshot()
        except OSError:
            status = {'system': {'source': 'Phone', 'observed_at': time.time()}}
        status['system']['platform'] = 'Android (Termux)'
        now = time.monotonic()
        if now >= self.next_battery:
            self.next_battery = now + 30
            self.power = []
            try:
                battery = json.loads(output(['termux-battery-status']))
            except ValueError:
                battery = None
            if isinstance(battery, dict):
                percent = battery.get('percentage')
                if type(percent) is int and 0 <= percent <= 100:
                    row = dict(POWER_SUPPLY_TYPE='Battery', POWER_SUPPLY_NAME='Phone',
                               POWER_SUPPLY_CAPACITY=percent)
                    state = battery.get('status')
                    if isinstance(state, str):
                        row['POWER_SUPPLY_STATUS'] = state.replace('_', ' ').title()
                    temp = battery.get('temperature')
                    if type(temp) in (int, float) and math.isfinite(temp) and -100 <= temp <= 200:
                        row['POWER_SUPPLY_TEMP'] = round(temp * 10)
                    self.power = [row]
        status['power'] = self.power
        setting = output(['settings', 'get', 'global', 'bluetooth_on'])
        if setting in ('0', '1'):
            status['bluetooth_controller'] = dict(available=True, powered=setting == '1',
                                                  observed_at=time.time())
        return status


def bluetooth_settings():
    subprocess.Popen(['am', 'start', '-a', 'android.settings.BLUETOOTH_SETTINGS'],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
