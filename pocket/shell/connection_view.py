"""Read-only link capability and profile presentation; no network collection."""
LINKS=(('wifi-sta','Wi-Fi STA'),('usb-ip','USB networking'),('wifi-ibss','Wi-Fi IBSS'),
       ('bt-rfcomm','Bluetooth RFCOMM'),('bt-pan','Bluetooth PAN'))


def truth(value):return 'yes' if value is True else 'no' if value is False else '?'


def project(value):
    value=value if isinstance(value,dict) and value.get('version')==1 else {}
    supplied={row['id']:row for row in (value.get('links') or []) if isinstance(row,dict) and isinstance(row.get('id'),str)}
    links=[]
    identities=LINKS+tuple((identity,str(row.get('label') or identity)) for identity,row in supplied.items() if identity not in dict(LINKS))
    for identity,label in identities:
        row=supplied.get(identity,{})
        links.append(dict(id=identity,label=str(row.get('label') or label),
                          **{field:row.get(field) if type(row.get(field)) is bool else None for field in ('advertised','configured','connected','tested')},
                          observed_at=row.get('observed_at'),peer=row.get('peer'),detail=row.get('detail'),
                          owner_station_id=row.get('owner_station_id'),radio_id=row.get('radio_id')))
    profiles=[]
    for row in value.get('profiles') or []:
        if not isinstance(row,dict) or not isinstance(row.get('id'),str):continue
        profiles.append(dict(id=row['id'],label=str(row.get('label') or row['id']),
                             steps=tuple(s for s in (row.get('steps') or []) if isinstance(s,str)),
                             disruptions=tuple(s for s in (row.get('disruptions') or []) if isinstance(s,str)),
                             rescue_required=row.get('rescue_required') is True,
                             rescue_ready=row.get('rescue_ready') if type(row.get('rescue_ready')) is bool else None))
    station=value.get('station') if isinstance(value.get('station'),dict) else {}
    return dict(station=dict(id=station.get('id'),label=station.get('label')),links=tuple(links),profiles=tuple(profiles),
                peer_connected=value.get('peer_connected'),internet_available=value.get('internet_available'))


class Links:
    def __init__(self):self.index=0;self.choosing=False;self.review=None;self.current=project({});self.hits=[]

    def update(self,value):
        self.current=project(value);self.index=min(self.index,max(0,len(self.current['profiles'])-1))
        if self.review and not any(p['id']==self.review for p in self.current['profiles']):self.review=None

    def key(self,key):
        profiles=self.current['profiles']
        if key=='\x1b' and (self.choosing or self.review):self.choosing=False;self.review=None;return True
        if key=='p' and profiles:self.choosing=True;self.review=None;return True
        if self.choosing and not self.review and key in ('up','down'):
            self.index=(self.index+(-1 if key=='up' else 1))%len(profiles);return True
        if self.choosing and not self.review and key in ('\r','\n'):
            self.review=profiles[self.index]['id'];return True
        return False

    def rows(self):
        self.hits=[];profiles=self.current['profiles']
        if self.review:
            profile=next(p for p in profiles if p['id']==self.review)
            rows=['PROFILE REVIEW: '+profile['label'],'']
            rows+=list(profile['steps']) or ['No plan supplied']
            if profile['disruptions']:rows+=['','Link changes:']+list(profile['disruptions'])
            if profile['rescue_required']:rows+=['','Rescue connection ready: '+truth(profile['rescue_ready'])]
            return rows+['','Review only · no network changes','Esc: back']
        rows=['Local peer reachable: '+truth(self.current['peer_connected']),
              'Internet available: '+truth(self.current['internet_available']),'',
              'Link                  Advert Config Connect Tested']
        station=self.current['station']
        if station['id'] or station['label']:rows.insert(0,'Station: '+str(station['label'] or station['id']))
        for link in self.current['links']:
            rows.append(f"{link['label'][:21]:21} {truth(link['advertised']):6} {truth(link['configured']):6} {truth(link['connected']):7} {truth(link['tested'])}")
            if link.get('peer'):rows.append('  '+str(link['peer'])+' · '+str(link.get('detail') or ''))
        rows+=['? = unknown · connected does not imply Internet','']
        if profiles:
            rows+=['Connection profiles · review']
            for index,profile in enumerate(profiles):
                self.hits.append((len(rows),index))
                rows.append(('> ' if self.choosing and index==self.index else '  ')+profile['label'])
            rows+=['p: choose profile · Enter: review · Esc: back','']
        return rows

    def pointer(self,row):
        for hit,index in self.hits:
            if row==hit:
                self.index=index;self.choosing=True;self.review=self.current['profiles'][index]['id'];return True
        return False
