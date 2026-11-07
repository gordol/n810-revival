#!/usr/bin/env python3
"""Generate private LAN trial credentials and a seven-day self-signed certificate."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import secrets
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--bind', required=True)
p.add_argument('--port', type=int, default=8443)
p.add_argument('--target', required=True)
p.add_argument('--control-path', required=True)
a = p.parse_args()
if not ipaddress.ip_address(a.bind).is_private:
    p.error('Use a local private LAN address')
run = Path(__file__).resolve().parent / '.private'
run.mkdir(mode=0o700, exist_ok=True)
if (run / 'config.json').exists():
    p.error('Private configuration already exists; preserve it or move it aside explicitly')
config = dict(bind=a.bind, port=a.port, target=a.target,
              controlPath=a.control_path, password=secrets.token_urlsafe(18))
(run / 'config.json').write_text(json.dumps(config))
os.chmod(run / 'config.json', 0o600)
(run / 'openssl.cnf').write_text('[req]\ndistinguished_name=dn\nx509_extensions=ext\nprompt=no\n[dn]\nCN=N810 phone trial\n[ext]\nsubjectAltName=IP:' + a.bind + '\n')
subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '7',
                '-keyout', str(run/'key.pem'), '-out', str(run/'cert.pem'),
                '-config', str(run/'openssl.cnf')], check=True, stdout=subprocess.DEVNULL,
               stderr=subprocess.DEVNULL)
os.chmod(run/'key.pem', 0o600)
fingerprint = subprocess.check_output(['openssl', 'x509', '-in', str(run/'cert.pem'),
                                       '-noout', '-fingerprint', '-sha256'], text=True)
(run/'ACCESS.txt').write_text('URL: https://' + a.bind + ':' + str(a.port) +
    '\nTrial password: ' + config['password'] + '\n\nLocal self-signed certificate:\n' + fingerprint)
os.chmod(run/'ACCESS.txt', 0o600)
print('Private access details saved in .private/ACCESS.txt')
