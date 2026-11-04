"""Parity and framework contracts; never start the desktop, services or devices."""
import contextlib
import io
import math
import os
from pathlib import Path
import pickle
import selectors
import socket
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

SHELL=Path(__file__).resolve().parents[1]/'shell'
sys.path.insert(0,str(SHELL))
import desktop


def outcome(argv,full):
    output,error=io.StringIO(),io.StringIO()
    with contextlib.redirect_stdout(output),contextlib.redirect_stderr(error):
        try:
            _,args=desktop.arguments(argv,full=full)
            return ('ok',vars(args),output.getvalue(),error.getvalue())
        except SystemExit as exited:return ('exit',exited.code,output.getvalue(),error.getvalue())


class ArgumentContracts(unittest.TestCase):
    def parity(self,argv):
        fast,full=outcome(argv,False),outcome(argv,True)
        self.assertEqual(fast,full,repr(argv));return full

    def test_defaults_and_independent_append_defaults(self):
        self.assertEqual(self.parity([])[0],'ok')
        _,first=desktop.arguments([]);first.library_root.append('caller mutation')
        _,second=desktop.arguments([]);self.assertEqual(second.library_root,[])
        self.assertEqual(self.parity(['--library-root','a','--library-root=b'])[1]['library_root'],['a','b'])

    def test_every_declaration_split_and_equals_forms(self):
        declarations,_=desktop.arguments([])
        self.assertGreater(len(declarations.options),70)
        for name,options,_ in declarations.options:
            with self.subTest(option=name):
                if options.get('action')=='store_true':
                    self.assertEqual(self.parity([name])[0],'ok')
                    self.assertEqual(self.parity([name+'=true'])[0],'exit');continue
                if options.get('choices') is not None:value=str(next(iter(options['choices'])))
                elif options.get('type') is int:value='7'
                elif options.get('type') is float:value='0.75'
                else:value='relative path/with space'
                self.assertEqual(self.parity([name,value])[0],'ok')
                self.assertEqual(self.parity([name+'='+value])[0],'ok')

    def test_combinations_repetition_negative_and_switchlike_values(self):
        for case in (
            ['--minimal','--no-save','--profile=wide','--scene-seed=42','--terminal-opacity=.5','--library-root=a','--library-root','b'],
            ['--scene-seed','-12','--mirror-delay','-0.5'],
            ['--scene-seed=1','--scene-seed=2','--no-save','--no-save'],
            ['--connection-address=--minimal'],['--connection-address',''],
            ['--library-root=a','--library-root=a'],['--radio-state','-'],
            ['--'],['--','--minimal'],['unexpected-positional'],
        ):
            with self.subTest(argv=case):self.parity(case)

    def test_mutually_exclusive_selections(self):
        for case in (
            ['--reticulum-local','state'],['--reticulum-socket=sock'],
            ['--reticulum-local=state','--reticulum-socket=sock'],
            ['--keyboard-fd=9'],['--keyboard-device','/not/opened'],
            ['--keyboard-fd=9','--keyboard-device=/not/opened'],
        ):
            with self.subTest(argv=case):self.parity(case)

    def test_all_missing_values_numeric_types_and_choices(self):
        declarations,_=desktop.arguments([])
        for name,options,_ in declarations.options:
            if options.get('action')=='store_true':continue
            cases=[[name],[name,'--minimal']]
            if options.get('type') in (int,float):cases.append([name,'not-a-number'])
            if options.get('choices') is not None:cases.append([name,'not-a-declared-choice'])
            for case in cases:
                with self.subTest(argv=case):
                    result=self.parity(case);self.assertEqual(result[:2],('exit',2))
                    self.assertIn('--scene-preset',result[3])

    def test_help_unknown_abbreviations_and_argv_none(self):
        for case in (['--help'],['-h'],['--definitely-unknown'],['--scene-ba=cpu'],['--ter'],['--touch-rot=90'],['--profile','w']):
            with self.subTest(argv=case):self.parity(case)
        with patch.object(sys,'argv',['pocket-contract-test','--minimal','--scene-seed=3']):
            self.assertEqual(outcome(None,False),outcome(None,True))
        self.assertEqual(self.parity(['--help'])[:2],('exit',0))

    def test_environment_and_platform_defaults(self):
        for radio in ('','relative-radio.json','/tmp/not-opened-radio.json'):
            with self.subTest(radio=radio),patch.dict(os.environ,{'N810_RADIO_STATE':radio,'XDG_STATE_HOME':'/tmp/contract-state','HOME':'/tmp/contract-home'}):
                args=self.parity([])[1]
                self.assertEqual(args['radio_state'],Path(radio))
                self.assertEqual(args['session'],Path('/tmp/contract-state/current-world/session.msgpack'))
                self.parity(['--radio-state=override'])
        with patch.dict(os.environ,{},clear=True):self.assertIsNone(self.parity([])[1]['radio_state'])
        for platform in ('n810','mac'):
            with patch.object(desktop.build_identity,'IDENTITY',{**desktop.build_identity.IDENTITY,'platform':platform,'touch_acquisition_default':'process'}):
                args=self.parity([])[1];self.assertEqual(args['shell'],platform=='n810')
                self.assertEqual(args['touch_acquisition'],'process')


class RecordContracts(unittest.TestCase):
    def test_entity_identity_excludes_live_payload(self):
        from entity_actions import EntityRef
        left=EntityRef('station','test',{'value':1})
        right=EntityRef('station','test',{'value':2})
        self.assertEqual(left,right)
        self.assertEqual(hash(left),hash(right))
        self.assertNotEqual(left,tuple(left))
        self.assertNotIn('payload',repr(left))

    def test_defaults_immutability_keyword_construction_and_pickle(self):
        from app_registry import Setting,ServiceUse,AppContext,Registration
        from app_command import Argument,Command
        from app_readiness import AppReady
        from app_widgets import PanelSpec,Column
        from app_docks import Pane
        from native_feed import FeedAction
        from last_heard_model import Peer,Position,Observation,Snapshot
        from pointer_events import SourceStamp
        from entity_actions import EntityRef
        cases=[
            (EntityRef('station','test'),{'payload':None}),
            (Setting('enabled','Enabled','bool',False),{'choices':(),'minimum':None,'maximum':None,'step':None}),
            (ServiceUse('fixture'),{'required':True}),(AppContext(None,'fixture',None),{}),
            (Registration('fixture','Fixture',(40,20),(20,10),'','Local',(),None,Path('.')),{'resources':(),'resource_option':'resource_root','settings':(),'uses':(),'commands':()}),
            (Argument('limit','int','Limit'),{'required':False,'default':None,'minimum':None,'maximum':None}),
            (Command('list','List',None),{'arguments':(),'capability':'','effect':'read','manual_topic':None}),
            (AppReady(None),{'error_reference':None,'listeners':()}),
            (PanelSpec('left','Left',10,20),{}),(Column('Name',12),{'role':'body'}),
            (Pane('Inspector','Feed','Inspector'),{}),
            (FeedAction('inspect','Inspect',('i',)),{'contexts':('browse','inspect')}),
            (Peer('aprs','rf','W1TEST'),{}),(Position(47,-122),{'recorded_at':None}),
            (Observation('1',Peer('aprs','rf','W1TEST'),'Test',None),{'position':None,'roles':(),'path':(),'path_kind':'unavailable','summary':''}),
            (Snapshot(),{'observations':(),'selected':None,'reference':None,'source':'Source unavailable','status':'Unavailable','scope':'Retained receptions; not proof of live RF arrival'}),
            (SourceStamp(0,'touch'),{'kind':'source','batch':None}),
        ]
        for record,defaults in cases:
            with self.subTest(record=type(record).__name__):
                for field,value in defaults.items():self.assertEqual(getattr(record,field),value)
                field=next(iter(type(record).__annotations__))
                with self.assertRaises(AttributeError):setattr(record,field,'mutated')
                with self.assertRaises(AttributeError):delattr(record,field)
                self.assertEqual(type(record)(**{name:getattr(record,name) for name in type(record).__annotations__}),record)
                self.assertEqual(pickle.loads(pickle.dumps(record)),record)

    def test_scenery_defers_dataclasses_but_camera_adjustment_still_works(self):
        script="""import sys,math
sys.path.insert(0,sys.argv[1])
import scenery
assert 'dataclasses' not in sys.modules
from geometry import Camera,Vec
base=Camera(origin=Vec(1,2,3),span_y=4)
config=scenery.Config(east=5,north=7,height=11,yaw=90,zoom=2)
result=scenery.camera(base,config,1.5)
assert result.origin==Vec(6,13,10)
assert result.span_y==2 and result.span_x==3
assert abs(result.yaw-math.pi/2)<1e-9
assert base.origin==Vec(1,2,3) and base.span_y==4
"""
        child=subprocess.run([sys.executable,'-B','-c',script,str(SHELL)],capture_output=True,text=True,timeout=15)
        self.assertEqual(child.returncode,0,child.stdout+child.stderr)

    def test_source_stamp_and_position_validation(self):
        from pointer_events import SourceStamp,evdev_stamp
        from last_heard_model import Position
        for args in ((-1,'touch'),(True,'touch'),(1.0,'touch'),(0,''),(0,'touch','unknown'),(0,'touch','ingress'),(0,'touch','ingress',-1),(0,'touch','ingress',True)):
            with self.subTest(stamp=args),self.assertRaises(ValueError):SourceStamp(*args)
        self.assertEqual(SourceStamp(0,'touch','ingress',0).batch,0)
        self.assertEqual(evdev_stamp(1,234,'touch').ns,1000234000)
        self.assertIsNone(evdev_stamp(1,1000000,'touch'))
        for lat,lon in ((91,0),(-91,0),(0,181),(0,-181),(True,0),('47',0),(math.nan,0),(0,math.inf)):
            with self.subTest(position=(lat,lon)),self.assertRaises(ValueError):Position(lat,lon)
        for lat,lon in ((-90,-180),(90,180),(0,0)):self.assertEqual(Position(lat,lon).lat,lat)

    def test_command_registry_settings_and_context_consumers(self):
        from app_command import normalize_commands,dispatch
        from app_registry import Registry,AppContext
        calls=[]
        def handler(context,values):calls.append(values);return values['limit']
        command=normalize_commands([dict(name='list',help='Read fixture',handler=handler,capability='read_fixture',arguments=[dict(name='limit',kind='int',help='Limit',default=3,minimum=1,maximum=8)])])[0]
        context=SimpleNamespace(capabilities={'read_fixture'},services={})
        self.assertEqual(dispatch(command,{},context),3);self.assertEqual(calls,[{'limit':3}])
        for value in (True,0,9,'3'):
            with self.subTest(value=value),self.assertRaises(ValueError):dispatch(command,{'limit':value},context)
        registry=Registry(root=SHELL)
        registry.register(dict(id='fixture',title='Fixture',factory=lambda host:None,settings=[dict(id='enabled',label='Enabled',kind='bool',default=False)]))
        self.assertFalse(registry.preferences('fixture')['enabled'])
        registry.host=SimpleNamespace(app_preferences={})
        registry.host.set_preference=lambda key,value:setattr(registry.host,key,value)
        registry.set_setting('fixture','enabled',True)
        app=AppContext(registry,'fixture',{})
        self.assertTrue(app.preferences['enabled'])
        with self.assertRaises(TypeError):app.preferences['enabled']=False
        with self.assertRaises(ValueError):registry.set_setting('fixture','enabled',1)

    def test_readiness_selector_and_pointer_consumers(self):
        from app_readiness import AppReadiness
        from app_registry import LazyApplication
        from pointer_events import SourceStamp,PointerEvent,coalesce_motion,deliver_pointer
        calls=[]
        class Form:
            def __init__(self,label):self.label=label
            def readiness_sources(self):return ((reader,self.ready),)
            def ready(self):calls.append((self.label,reader.recv(1)))
        reader,writer=socket.socketpair()
        try:
            with selectors.DefaultSelector() as selector:
                first,second=Form('first'),Form('second');readiness=AppReadiness(selector)
                readiness.sync((first,second));writer.send(b'xy')
                for key,_ in selector.select(.5):key.data.callback()
                self.assertEqual(calls,[('first',b'x'),('second',b'y')]);readiness.close()
        finally:reader.close();writer.close()
        a=PointerEvent(('mouse',32,2,4,False),stamp=SourceStamp(1,'touch'))
        b=PointerEvent(('mouse',32,5,1,False),stamp=SourceStamp(2,'touch'))
        event=coalesce_motion(a,b);received=[]
        form=LazyApplication.__new__(LazyApplication)
        form.owner=SimpleNamespace(pointer_event=lambda event,width:received.append((event,width)) or True)
        self.assertTrue(deliver_pointer(form,event,10,6,40))
        self.assertEqual(received[0][0].bounds,(7,6,10,9));self.assertEqual(received[0][0].stamp,b.stamp)

    def test_last_heard_layout_feed_and_dock_consumers(self):
        from last_heard_model import Peer,Position,Observation,Snapshot,direction
        from last_heard_view import LastHeard
        from app_widgets import ViewOptions,status_text,Column,PanelSpec,AdaptivePanels
        from native_feed import FEED_ACTIONS,binding_label,KEY_ACTIONS
        from app_docks import Docks,PANES
        item=Observation('1',Peer('aprs','rf','W1TEST'),'Test station','2026-10-25T00:00:00Z',Position(0,1),roles=('station',))
        view=LastHeard(lambda:Snapshot((item,),item,Position(0,0),'Fixture','Retained'))
        text='\n'.join(view.lines());self.assertIn('W1TEST',text);self.assertIn('111.2 km',text);self.assertIn('090° E',text)
        self.assertEqual(direction(Position(0,0),Position(0,0)),(0.0,None))
        self.assertEqual(status_text('short','details',20,ViewOptions(status='detailed')),'details')
        self.assertEqual(Column('Call',12).role,'body')
        self.assertIsNotNone(AdaptivePanels((PanelSpec('list','List',10,20),PanelSpec('details','Details',10,20))))
        self.assertTrue(all(binding_label(action) for action in FEED_ACTIONS))
        self.assertEqual(KEY_ACTIONS[('browse','e')],'feed.evidence.toggle')
        changed=[];aprs=SimpleNamespace(inspector=False,changed=lambda:changed.append(True),inspector_lines=lambda:('packet',))
        chat=SimpleNamespace(messages=lambda:(('Peer','hello'),),changed=lambda:changed.append(True))
        docks=Docks(None,{'APRS':aprs,'Conversations':chat})
        self.assertEqual(docks.rows(PANES[0]),('packet',));self.assertEqual(docks.rows(PANES[1]),('Peer: hello',))
        docks.place(PANES[0],'Floating');self.assertEqual(docks.locations[PANES[0].window],'Floating')

if __name__=='__main__':unittest.main()
