"""Message model acceptance independent of curses, files, sockets or radio."""
import importlib.util
from pathlib import Path
import unittest

p=Path(__file__).with_name('n810-messages-model.py')
spec=importlib.util.spec_from_file_location('messages_model_test',p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class ModelTests(unittest.TestCase):
    def state(self):
        return m.State('N0ANT',clock=lambda:'12:34:56',identifier_factory=lambda:'A12')

    def test_draft_is_validated_before_state_change_and_has_existing_shape(self):
        state=self.state()
        with self.assertRaises(ValueError):state.draft('W7DK','bad|text')
        self.assertEqual(state.outbox,[])
        self.assertEqual(state.draft('w7dk','hello'),dict(to='W7DK',text='hello',kind='MSG',id='A12',time='12:34:56',status='Draft'))

    def test_submission_is_not_peer_acknowledgement_and_retry_keeps_native_id(self):
        state=self.state();row=state.draft('W7DK','hello')
        first=state.begin_submission(row,['WIDE1-1'])
        self.assertEqual(row['status'],'Submitting');self.assertEqual(row['attempts'],1)
        self.assertEqual(row['wire_hex'],first.hex());self.assertEqual(row['source'],'N0ANT')
        state.submitted(row);self.assertEqual(row['status'],'Submitted')
        state.unconfirmed(row,'connection lost');self.assertEqual(row['status'],'Unconfirmed')
        self.assertEqual(state.begin_submission(row,['WIDE1-1']),first)
        self.assertEqual(row['id'],'A12');self.assertEqual(row['attempts'],2)

    def test_only_exact_peer_and_addressee_acknowledges_non_draft(self):
        state=self.state();row=state.draft('W7DK','hello')
        ack='12:00:00 W7DK>APRS ctl=03 pid=f0 :N0ANT    :ackA12'
        state.add(ack);self.assertEqual(row['status'],'Draft')
        state.begin_submission(row,[]);state.submitted(row)
        for line in ('12:00:01 OTHER>APRS ctl=03 pid=f0 :N0ANT    :ackA12',
                     '12:00:02 W7DK>APRS ctl=03 pid=f0 :N0ANT-1  :ackA12',
                     '12:00:03 W7DK>APRS ctl=03 pid=f0 :N0ANT    :ackB12'):
            state.add(line);self.assertEqual(row['status'],'Submitted')
        state.add(ack.replace('12:00:00','12:00:04'))
        self.assertEqual(row['status'],'Acknowledged')

    def test_rejection_and_reply_ack_preserve_original_rx(self):
        state=self.state();row=state.draft('W7DK','hello');state.begin_submission(row,[])
        raw='12:00:00 GATE>APRS ctl=03 pid=f0 }W7DK>APRS,TCPIP*::N0ANT    :reply{B2}A12\\x0d'
        state.add(raw);self.assertEqual(row['status'],'Acknowledged')
        received=state.received[0]
        self.assertEqual(received['raw'],raw);self.assertEqual(received['source'],'W7DK')
        self.assertEqual(received['reply_ack'],'A12');self.assertEqual(received['time'],'12:00:00')
        state.add('12:00:01 W7DK>APRS ctl=03 pid=f0 :N0ANT    :rejA12')
        self.assertEqual(row['status'],'Rejected')

    def test_thread_filters_exact_ssid_and_returns_detached_groups(self):
        state=self.state();draft=state.draft('W7DK','hello');state.begin_submission(draft,['WIDE1-1'])
        state.draft('W7DK-1','other')
        for line in ('12:00:00 W7DK>APRS ctl=03 pid=f0 :N0ANT    :hello{B2',
                     '12:00:01 W7DK>APRS ctl=03 pid=f0 :OTHER    :not ours{B3',
                     '12:00:02 W7DK-1>APRS ctl=03 pid=f0 :N0ANT    :different SSID{B4'):
            state.add(line)
        thread=state.thread('w7dk')
        self.assertEqual(thread['peer'],'W7DK')
        self.assertEqual(len(thread['received']),1);self.assertEqual(len(thread['outbox']),1)
        thread['outbox'][0]['path'].append('CHANGED')
        self.assertEqual(draft['path'],['WIDE1-1'])
        self.assertNotIn('capture_id',thread['received'][0])

    def test_persistence_shape_unknown_fields_and_restart_uncertainty(self):
        state=self.state();draft=state.draft('W7DK','hello');state.begin_submission(draft,[]);state.submitted(draft)
        draft['future_metadata']={'source':'preserved'}
        document=m.outbox_document(state.outbox)
        self.assertEqual(set(document),{'version','outbox'});self.assertEqual(document['version'],1)
        restored=m.restore_outbox(document)
        self.assertEqual(restored[0]['status'],'Unconfirmed')
        self.assertEqual(document['outbox'][0]['status'],'Submitted')
        self.assertEqual(restored[0]['future_metadata'],draft['future_metadata'])
        restored[0]['future_metadata']['source']='changed'
        self.assertEqual(draft['future_metadata']['source'],'preserved')
        for malformed in ([],None,dict(version=2,outbox=[]),dict(version=1,outbox=None)):
            self.assertEqual(m.restore_outbox(malformed),[])

    def test_history_and_outbox_stay_bounded_and_status_is_not_message(self):
        state=self.state()
        state.add('Feed disconnected');self.assertEqual(state.status,'Feed disconnected')
        self.assertEqual(len(state.received),0)
        for n in range(201):
            line=f'12:00:00 W7DK>APRS ctl=03 pid=f0 :N0ANT    :test {n}{{A12'
            state.add(line);state.add(line)
            state.draft('W7DK',str(n))
        self.assertEqual(len(state.received),200);self.assertEqual(len(state.outbox),100)
        self.assertEqual(state.received[0]['text'],'test 200')

    def test_ack_submission_has_honest_state(self):
        state=self.state();row=state.draft('W7DK','',kind='ACK',identifier='B2')
        state.begin_submission(row,[]);state.submitted(row)
        self.assertEqual(row['status'],'ACK submitted')
        self.assertIn('RF delivery unconfirmed',state.notice)

    def test_detail_projection_distinguishes_reconstructed_and_submitted_bytes(self):
        state=self.state();row=state.draft('W7DK','hello')
        before=m.detail_lines(row,outgoing=True,source=state.call,path=[])
        self.assertIn('KISS bytes reconstructed (older attempt):',before)
        wire=state.begin_submission(row,[])
        after=m.detail_lines(row,outgoing=True,source=state.call,path=[])
        self.assertIn('KISS bytes submitted',after)
        self.assertIn(' '.join(wire.hex()[i:i+2] for i in range(0,len(wire.hex()),2)),after)
        self.assertIn('These are local submission bytes, not a capture of the RF transmission.',after)
        raw='12:00:00 W7DK>APRS ctl=03 pid=f0 :N0ANT    :hello{B2'
        received=m.parse_message(raw)
        self.assertEqual(m.detail_lines(received),['RECEIVE DETAILS','',raw])

if __name__=='__main__':unittest.main()
