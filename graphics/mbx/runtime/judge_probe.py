"""Offline probe receipt checking and next-command preparation. Executes nothing."""
import argparse,json,shlex
from pathlib import Path
RELEASE='5.15.224-n810-mbx-clock-wip1'
CLEAN={'resident_fault':0,'cleanup_error':0,'restoration_error':0,'final_state_error':0,
       'clock_operation_error':0,'divider_operation_error':0,'divider_restoration_error':0,
       'reset_asserted_verified':1,'lifetime_pinned':0,'enabled_references':0,
       'held_clock_handles':0,'shared_handle_held':0,'rate_claimed':0,'sibling_rate_claimed':0,'active_divider':1,
       'divider_change_attempted':1,'divider_restore_attempts':1,'cleanup_phase':11,
       'restoration_attempts':1,'gpu_mask_changed':0}
READY={'handshake_error':0,'handshake_complete':1,'readiness_attempted':1,
       'readiness_error':0,'ready':1,'gpu_attempted':1,'gpu_error':0}
INPUTS={'permit_gpu_probe':1,'target_divider':2,'handshake_samples':1000,'readiness_limit':1000,
        'pause_min_us':100,'pause_max_us':200,'operation_samples':1000,
        'operation_pause_min_us':100,'operation_pause_max_us':200,'fill_pixel':0xffffffff}

def judge(receipt,pin,inputs=None):
    inputs=INPUTS if inputs is None else inputs
    if receipt.get('kernel_release')!=RELEASE or receipt.get('module_sha256')!=pin:
        raise ValueError('kernel/module identity mismatch')
    for field in ('log_complete','initial_final_gates_match','initial_final_selector_match'):
        if receipt.get(field) is not True:raise ValueError(field+' is not confirmed')
    p=receipt.get('parameters',{})
    initial=receipt.get('initial_divider',1)  # legacy receipts entered at divider1
    if type(initial) is not int or initial not in (1,2):raise ValueError('invalid initial divider')
    if inputs.get('target_divider')!=2 or (p.get('observed_select',0)&7)!=initial:
        raise ValueError('initial selector was not restored')
    transition=int(initial!=inputs['target_divider'])
    expected=CLEAN|READY|inputs|{'active_divider':initial,
        'divider_change_attempted':transition,'divider_restore_attempts':transition}
    for name,want in expected.items():
        if type(p.get(name)) is not int or p[name]!=want:raise ValueError(name+' missing or unexpected')
    if not 2<=p.get('readiness_samples',0)<=inputs['readiness_limit']:raise ValueError('readiness sample count invalid')
    if p.get('gpu_dma_stage')!=0:raise ValueError('DMA ownership not released')
    mode=p.get('probe_mode')
    if type(mode) is not int or mode not in (0,1):raise ValueError('unknown probe mode')
    if mode==0:
        for k in ('gpu_submitted','gpu_words_written','gpu_completion_status','gpu_capture_valid','gpu_quiesced'):
            if p.get(k)!=0:raise ValueError('identity-only mode unexpectedly mutated DMA/commands')
    else:
        for k,v in {'gpu_pipeline_cycles':16,'gpu_pipeline_initialized':1,'gpu_submitted':1,'gpu_words_written':163,'gpu_ta_completed':1,'gpu_capture_valid':1,'gpu_quiesced':1}.items():
            if p.get(k)!=v:raise ValueError(k+' incomplete')
        events=p.get('gpu_completion_status',0)
        if not events&0x100 or events&0x2a0 or events==0xffffffff:raise ValueError('completion missing or error')
    identities={}
    for observed,expected in [('observed_core_id','expected_core_id'),('observed_revision','expected_revision'),
                              ('observed_product_id','expected_product_id'),('observed_part_number','expected_part_number')]:
        value=p.get(observed)
        if type(value) is not int or not 0<=value<0xffffffff:raise ValueError(observed+' invalid')
        identities[expected]=value
        if mode and p.get(expected)!=value:raise ValueError('executed identity differs from requested identity')
    product=identities['expected_product_id'];part=identities['expected_part_number'];core=identities['expected_core_id']
    if product==0xb105f00d:
        if part not in (0x910,0x930):raise ValueError('unsupported part')
    elif core&0xffff0000 not in (0x01010000,0x01020000):raise ValueError('unsupported legacy core')
    result=dict(status='CLEAN_IDENTITY_RECEIPT' if mode==0 else 'CLEAN_ALLOCATOR_RECEIPT_REQUIRES_CAPTURE_CHECK',normal_removal_supported=True,hardware_execution_verified=False)
    if mode==0:
        argv=['sudo','/sbin/insmod','./n810_mbx_gpu_probe.ko']+[f'{k}={v}' for k,v in (inputs|{'probe_mode':1}|identities).items()]
        result['next_fill_runner_after_normal_removal']='python3 run_probe.py --mode fill --identity-receipt IDENTITY_RESULT/receipt.json --output NEW_RENDER_RESULT --permit-global-clock-commit --run'
    return result

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('receipt',type=Path);ap.add_argument('--module-sha256',required=True);ap.add_argument('--settings',type=Path,default=Path(__file__).with_name('PROBE-SETTINGS.json'));a=ap.parse_args()
    if len(a.module_sha256)!=64 or any(c not in '0123456789abcdef' for c in a.module_sha256):ap.error('invalid SHA-256')
    with a.receipt.open() as f:raw=f.read(32769)
    if len(raw)>32768:raise ValueError('receipt too large')
    print(json.dumps(judge(json.loads(raw),a.module_sha256,json.loads(a.settings.read_text())['effective']),indent=2))
