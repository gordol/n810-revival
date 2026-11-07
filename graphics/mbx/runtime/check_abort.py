"""Recognize a fully released pre-GPU failure; never treat it as GPU success."""
import hashlib,re
from judge_probe import RELEASE
FIELDS=('error refs handles shared claim pin resident reset_attempted gpu_attempted gpu_submitted gates_match selector_match').split()
def judge_abort(receipt,log,pin):
    if receipt.get('kernel_release')!=RELEASE or receipt.get('module_sha256')!=pin:
        raise ValueError('abort kernel/module identity mismatch')
    if receipt.get('kernel_log_complete') is not True or receipt.get('module_present_after_load') is not False:
        raise ValueError('abort log incomplete or module still resident')
    if type(receipt.get('loader_exit_code')) is not int or receipt['loader_exit_code']==0:
        raise ValueError('failed insertion required')
    if receipt.get('parameters') or receipt.get('mode')!='identity':
        raise ValueError('only an absent identity-mode module can be classified')
    if hashlib.sha256(log).hexdigest()!=receipt.get('log_sha256'):raise ValueError('log hash mismatch')
    pattern=r'n810_mbx_gpu_probe: released-before-gpu '+r' '.join(k+r'=(-?\d+)' for k in FIELDS)
    rows=re.findall(pattern,log.decode('utf-8',errors='strict'))
    if len(rows)!=1:raise ValueError('unique completed teardown record required')
    result=dict(zip(FIELDS,map(int,rows[0])))
    if result['error']>=0 or any(result[k] for k in FIELDS[1:-2]) or result['gates_match']!=1 or result['selector_match']!=1:
        raise ValueError('release record does not prove pre-GPU cleanup')
    return dict(status='CLEAN_PRE_GPU_ABORT',operation_succeeded=False,hardware_execution_verified=False,
                module_loaded=False,normal_removal_required=False,automatic_retry=False,error=result['error'])
