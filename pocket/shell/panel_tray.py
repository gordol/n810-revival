"""Compact panel menus over existing owner snapshots and explicit intents."""
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
        return title,entries+[('Open Bluetooth…','window:Bluetooth')]
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
            entries=[('Open power / system details…','window:System'),('Open settings…','window:Settings')]
        else:
            wifi=(current.get('wifi') or {}).get('wlan0') or {}
            title=('Wi-Fi' if action=='system:WiFi' else 'USB networking')+' · '+str((wifi.get('state') if action=='system:WiFi' else (current.get('network') or {}).get('usb0')) or 'unknown')
            if action=='system:WiFi' and wifi.get('ssid'):title+=' · '+str(wifi['ssid'])
            entries=[('Manage connections…','window:Connections'),('Open system details…','window:System')]
        if result.get('freshness')!='fresh':title+=' · stale / unavailable'
        return title, [('Refresh status','system:refresh')]+entries
    status=(radio.result.get('statusbar',{}).get('radio',{})) if radio else {}
    title='Radio · '+str(status.get('state','unavailable'))
    if radio and radio.read_message:title+=' · '+radio.read_message
    entries=[('Check read progress','radio:check'),('Refresh radio snapshot','radio:read') ] if radio else []
    return title,entries+[('Open Radio…','window:Radio'),('Open Radio Manager…','window:Radio Manager')]
