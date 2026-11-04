"""Small normal-user client for typed local desktop app actions."""
import argparse,os,socket,math
from runtime_codec import frame,read_frame

def exchange(path,request,timeout=10):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        connection.settimeout(timeout);connection.connect(str(path));connection.sendall(frame(request,256))
        with connection.makefile("rb") as stream:return read_frame(stream)



def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--socket',default=os.environ.get('N810_DESKTOP_SOCKET'),help='private socket reported by desktop metrics')
    parser.add_argument('command',choices=('system-status','status','open-map','pan','zoom','set-view','pointer-trace','radio-status','radio-read','radio-check','radio-cancel'))
    parser.add_argument('values',nargs='*')
    args=parser.parse_args()
    if not args.socket:parser.error('Specify --socket or N810_DESKTOP_SOCKET')
    request={'command':args.command}
    if args.command in ('pan','zoom'):
        choices=('left','right','up','down') if args.command=='pan' else ('in','out')
        if len(args.values)!=1 or args.values[0] not in choices:parser.error('Expected direction: '+', '.join(choices))
        request['direction']=args.values[0]
    elif args.command=='set-view':
        if len(args.values)!=3:parser.error('Expected latitude longitude span-km')
        try:request.update(zip(('latitude','longitude','span'),map(float,args.values)))
        except ValueError:parser.error('View values must be numbers')
        if any(not math.isfinite(request[key]) for key in ('latitude','longitude','span')):parser.error('View values must be finite')
    elif args.command=='pointer-trace':
        if args.values not in (['on'],['off']):parser.error('Expected on or off')
        request['enabled']=args.values==['on']
    elif args.values:parser.error('This command takes no values')
    try:result=exchange(args.socket,request)
    except (OSError,ValueError) as error:
        raise SystemExit(str(error)+'. Command outcome may be unknown; query status before retrying.')
    from app_command_cli import text_lines
    print('\n'.join(text_lines(result)))
    if not result.get('ok'):raise SystemExit(1)


if __name__=='__main__':main()
