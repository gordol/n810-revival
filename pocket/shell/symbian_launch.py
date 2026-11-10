"""Request an application from the managed N810 graphics owner."""
import argparse
import socket
from pathlib import Path

SOCKET='/run/n810-pocket-native/symbian.sock'
APPS={'chess':'ChessGenius','snakes':'Snakes'}

def launch(application):
    if application not in APPS:raise ValueError('Choose chess or snakes')
    with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as connection:
        connection.settimeout(5)
        try:connection.connect(SOCKET)
        except OSError as error:raise RuntimeError('Start the managed N810 GPU desktop first') from error
        connection.sendall(application.encode('ascii'))
        response=connection.recv(256).decode('utf-8')
        if response!='accepted':raise RuntimeError(response or 'The graphics owner closed the request')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('application',choices=APPS)
    args=parser.parse_args()
    try:launch(args.application)
    except (OSError,RuntimeError,ValueError) as error:parser.exit(1,str(error)+'\n')
if __name__=='__main__':main()
