"""Request an application from the managed N810 graphics owner."""
import argparse
import array,os
import socket
from pathlib import Path
import re

SOCKET='/run/n810-pocket-native/symbian.sock'
UI_SOCKET='/run/n810-pocket-native/ui/desktop.sock'
APPS={'chess':'ChessGenius','snakes':'Snakes'}

def launch(application):
    if application not in APPS and not re.fullmatch(r'(?:[0-9a-f]{8}|install:[A-Za-z0-9 _().-]{1,160}\.sisx?)',application,re.I):raise ValueError('Choose an installed app UID or a private inbox installer')
    if not application.startswith('install:') and Path(UI_SOCKET).exists():
        from desktop_command import exchange
        result=exchange(UI_SOCKET,dict(command='symbian-open',application=application))
        if not result.get('ok'):raise RuntimeError(result.get('error','Symbian window launch failed'))
        return
    with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as connection:
        connection.settimeout(5)
        try:connection.connect(SOCKET)
        except OSError as error:raise RuntimeError('Start the managed N810 GPU desktop first') from error
        connection.sendall(application.encode('ascii'))
        response=connection.recv(256).decode('utf-8')
        if response!='accepted':raise RuntimeError(response or 'The graphics owner closed the request')

def request_window(application):
    if not re.fullmatch(r'[0-9a-f]{8}',application,re.I):raise ValueError('Choose an installed Symbian app UID')
    descriptors=array.array('i')
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as connection:
            connection.settimeout(5);connection.connect(SOCKET)
            connection.sendall(('window:'+application).encode('ascii'))
            data,ancillary,flags,_=connection.recvmsg(256,socket.CMSG_SPACE(3*descriptors.itemsize),socket.MSG_CMSG_CLOEXEC)
            for level,kind,payload in ancillary:
                if level==socket.SOL_SOCKET and kind==socket.SCM_RIGHTS:descriptors.frombytes(payload[:len(payload)//descriptors.itemsize*descriptors.itemsize])
            if flags&(socket.MSG_TRUNC|socket.MSG_CTRUNC) or data!=b'window' or len(descriptors)!=3:
                raise RuntimeError(data.decode('utf-8',errors='replace') or 'GPU window launch failed')
        frames=socket.socket(fileno=descriptors[0]);control=socket.socket(fileno=descriptors[2])
        return frames,descriptors[1],control
    except BaseException:
        for descriptor in descriptors:
            try:os.close(descriptor)
            except OSError:pass
        raise

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('application',help='installed app UID, chess or snakes')
    args=parser.parse_args()
    try:launch(args.application)
    except (OSError,RuntimeError,ValueError) as error:parser.exit(1,str(error)+'\n')
if __name__=='__main__':main()
