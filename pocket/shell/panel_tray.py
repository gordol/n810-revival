"""Compact panel menus over existing owner snapshots and explicit intents."""
BATTERY_ACTIONS = [
    ('Top off battery (85–95%)', 'charge:topoff'),
    ('Battery longevity (55–80%)', 'charge:longevity'),
    ('CPU performance', 'cpu:performance'), ('CPU balanced', 'cpu:balanced'),
    ('CPU power save', 'cpu:save'),
]
AIRPLANE_MENU = ('Airplane mode…', 'submenu:Airplane')
# Each command is fixed. Volume uses the desktop user's audio group.
CONTROL_ACTIONS = {
    'charge:topoff': (['sudo','-n','/usr/local/bin/n810-power','topoff'], 'Top-off charging enabled (85–95%)'),
    'charge:longevity': (['sudo','-n','/usr/local/bin/n810-power','longevity'], 'Battery longevity enabled (55–80%)'),
    'display:brighter': (['sudo','-n','/usr/local/sbin/n810-screen','brighter'], 'Brightness increased'),
    'display:dimmer': (['sudo','-n','/usr/local/sbin/n810-screen','dimmer'], 'Brightness decreased'),
    'display:auto': (['sudo','-n','/usr/local/sbin/n810-screen','auto'], 'Automatic brightness enabled'),
    'volume:up': (['/usr/bin/amixer','-q','-c','N810','sset','PCM','5%+'], 'Playback volume increased'),
    'volume:down': (['/usr/bin/amixer','-q','-c','N810','sset','PCM','5%-'], 'Playback volume decreased'),
    'airplane:on': (['sudo','-n','/usr/local/sbin/n810-radio','airplane-on'], 'Airplane mode on'),
    'airplane:off': (['sudo','-n','/usr/local/sbin/n810-radio','airplane-off'], 'Airplane mode off'),
    'power:shutdown': (['sudo','-n','/sbin/shutdown','-h','now'], 'Shutdown requested'),
}
for mode in ('performance','balanced','save'):
    CONTROL_ACTIONS['cpu:'+mode] = (['sudo','-n','/usr/local/sbin/n810-cpu-policy',mode], 'CPU mode: '+mode)


def display_levels():
    from pathlib import Path
    import re
    import subprocess
    brightness = volume = "—"
    for light in sorted(Path("/sys/class/backlight").glob("*")):
        try:
            current = int((light / "brightness").read_text())
            maximum = int((light / "max_brightness").read_text())
            if 0 <= current <= maximum and maximum > 0:
                brightness = f"{round(100 * current / maximum)}%"
                break
        except (OSError, ValueError):
            continue
    try:
        mixer = subprocess.run(["/usr/bin/amixer", "-c", "N810", "get", "PCM"],
                               capture_output=True, text=True, timeout=2, check=True)
        levels = re.findall(r"Playback\s+\d+\s+\[(\d+)%\]", mixer.stdout)
        if levels:
            volume = "/".join(dict.fromkeys(levels)) + "%"
    except (OSError, subprocess.SubprocessError):
        pass
    return f"Brightness {brightness} · Volume {volume}"


def handles(action):
    return bool(action and action.startswith(('system:', 'bluetooth:', 'radio:')))


def menu(action, system=None, bluetooth=None, radio=None):
    """Return title and semantic actions. Never collect or change hardware here."""
    if not handles(action):return None
    if action.startswith('bluetooth:'):
        state=bluetooth.read() if bluetooth else {}
        powered=state.get('powered')
        title='Bluetooth · '+('on' if powered is True else 'off' if powered is False else 'unavailable')
        if state.get('devices'):title+=' · '+', '.join(state['devices'])
        labels=(('controller_on','Turn Bluetooth on'),('controller_off','Turn Bluetooth off'),
                ('receive_start','Start radio reception'),('receive_stop','Stop radio reception'),
                ('radio_disconnect','Disconnect radio'))
        entries=[(label,'bt:'+key) for key,label in labels if bluetooth and bluetooth.available(key)
                 and not (key=='controller_on' and powered is True or key=='controller_off' and powered is False)]
        feedback=(bluetooth.message or bluetooth.feedback()) if bluetooth else ''
        if feedback:title+=' · '+feedback
        return title,entries+[AIRPLANE_MENU, ('Open Bluetooth…','window:Bluetooth')]
    if action=='system:Power':
        return 'N810 power', BATTERY_ACTIONS + [
            ('Brightness and volume…','submenu:Display'), ('Power and battery details','window:System'),
            ('Shut down…','power:confirm-shutdown')]
    if action=='system:Display':
        return 'Brightness and volume', [('Brighter','display:brighter'), ('Dimmer','display:dimmer'),
            ('Automatic brightness','display:auto'), ('Volume up','volume:up'), ('Volume down','volume:down')]
    if action=='system:Airplane':
        return 'Airplane mode · Wi-Fi and Bluetooth', [
            ('Turn airplane mode on (disconnect both)','airplane:on'),
            ('Turn airplane mode off','airplane:off')]
    if action.startswith('system:'):
        if system:system.update()
        result=system.result if system else {}
        current=system.current if system else {}
        if action in ('system:Battery','system:open'):
            batteries=result.get('batteries') or []
            battery=batteries[0] if batteries else {}
            percent=battery.get('capacity_percent')
            title='Battery · '+('unknown' if percent is None else str(percent)+'%')
            if battery.get('status'):title+=' · '+str(battery['status'])
            entries=BATTERY_ACTIONS+[('Brightness and volume…','submenu:Display'),('Open power / system details…','window:System'),('Open settings…','window:Settings')]
        else:
            wifi=(current.get('wifi') or {}).get('wlan0') or {}
            title=('Wi-Fi' if action=='system:WiFi' else 'USB networking')+' · '+str((wifi.get('state') if action=='system:WiFi' else (current.get('network') or {}).get('usb0')) or 'unknown')
            if action=='system:WiFi' and wifi.get('ssid'):title+=' · '+str(wifi['ssid'])
            entries=[('Manage connections…','window:Connections'),('Open system details…','window:System')]
            if action=='system:WiFi':entries.insert(0,AIRPLANE_MENU)
        if result.get('freshness')!='fresh':title+=' · stale / unavailable'
        return title, [('Refresh status','system:refresh')]+entries
    status=(radio.result.get('statusbar',{}).get('radio',{})) if radio else {}
    title='Radio · '+str(status.get('state','unavailable'))
    if radio and radio.read_message:title+=' · '+radio.read_message
    entries=[('Check read progress','radio:check'),('Refresh radio snapshot','radio:read') ] if radio else []
    return title,entries+[AIRPLANE_MENU, ('Open Radio…','window:Radio'),('Open Radio Manager…','window:Radio Manager')]
