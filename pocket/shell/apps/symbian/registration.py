"""Symbian launcher metadata; discovery does not start the runtime."""
class Launcher:
    def __init__(self,host):self.notice='Enter: ChessGenius   S: Snakes';self.width=52;self.height=8
    def lines(self):return ('Symbian applications',self.notice,'The managed graphics session returns to Pocket on exit.')
    def key(self,key):
        if key not in ('enter','\n','\r','s','S'):return False
        from symbian_launch import launch
        try:launch('snakes' if key.lower()=='s' else 'chess');self.notice='Launching…'
        except (OSError,RuntimeError,ValueError) as error:self.notice=str(error)
        return True
    def close(self):pass

def descriptor():
    return dict(id='symbian',title='Symbian',factory=Launcher,preferred_size=(60,10),minimum_size=(30,6),category='Applications',description='Launch installed Symbian applications',help=(('Launch',('Enter: ChessGenius','S: Snakes','Exit the application to return to Pocket.')),))
