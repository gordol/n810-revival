"""Small ordinary windows to exercise desktop behavior; observations are synthetic."""
from core import Window

NAMES=('Kitchen Sink','Pane Lab')


def windows(width,height):
    result=[]
    for name,wanted in (('Kitchen Sink',58),('Pane Lab',64)):
        w,h=min(width,wanted),min(height,18)
        result.append(Window(name,max(0,(width-w)//2),min(2,max(0,height-h)),w,h,visible=False,opened=False))
    return result


def open_workspace(host):
    import app_gallery
    app_gallery.open_workspace(host)


def update(host,now):
    for name,form in getattr(host,'app_forms',{}).items():
        window=host.window(name)
        if window.opened and (host.overview or host.shown(window)):
            if hasattr(form,'width'):form.width=max(8,window.w-2)
            if hasattr(form,'height'):form.height=max(3,window.h-2)
            lines=form.lines();host.content(name,lines,lines,form.spans() if hasattr(form,'spans') else (),form.layer() if hasattr(form,'layer') else None)
            if host.overview:
                host.invalidate(host.mini_window(window,window.desktop))
                host.invalidate(host.expose_window(window))


def forms(host,scene):
    from controls import Choice,Slider,TextPanel,Toggle,Button,Progress,RadioList,SplitPane
    from settings import SettingsWindow
    local={'enabled':True,'choice':'one','amount':.5,'presses':0}
    def bind(name):return lambda:local[name],lambda value:local.update({name:value})
    def press():local['presses']+=1
    kitchen=[Toggle('Checkbox',*bind('enabled')),Choice('Choice',*bind('choice'),('one','two','three')),Slider('Slider',*bind('amount'),0,1,.1),Button('Push button',press),Progress('Progress',lambda:local['amount'])]
    radio=RadioList(*bind('choice'),('one','two','three'))
    def reset_camera():
        host.parallax=.005;host.overview_zoom=1.65;host.background_step=-1
    scene['view'].append(Button('Reset camera',reset_camera))
    return {'Pane Lab':SplitPane(TextPanel(('Sources','Stations','Messages','Services','Telemetry')),SettingsWindow([('Details',[c.row() for c in kitchen[:3]]),('Actions',[kitchen[3].row()])],width=34)),
            'Kitchen Sink':SettingsWindow([('Controls',[c.row() for c in kitchen]+[('Button count',lambda:str(local['presses']),lambda d:None)]),('List',radio.rows()),('Camera',[c.row() for c in scene['view']]),('Shadows',[c.row() for c in scene['shadows']])]),
            }
