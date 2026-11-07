"""Clock-only verdict; never enables reset, identity reads or GPU execution."""
from judge_probe import RELEASE
ZERO='resident_fault cleanup_error restoration_error final_state_error clock_operation_error divider_operation_error divider_restoration_error lifetime_pinned enabled_references held_clock_handles shared_handle_held rate_claimed handshake_error handshake_complete readiness_attempted readiness_error ready readiness_samples restoration_attempts gpu_attempted gpu_error gpu_submitted gpu_words_written gpu_dma_stage gpu_capture_valid gpu_mask_changed'.split()
def judge(r,pin,settings):
 if r.get('kernel_release')!=RELEASE or r.get('module_sha256')!=pin or r.get('loader_exit_code')!=0:raise ValueError('clock probe identity/load failed')
 for k in ('log_complete','initial_final_gates_match','initial_final_selector_match'):
  if r.get(k) is not True:raise ValueError(k)
 p=r.get('parameters',{})
 for k in ZERO:
  if p.get(k)!=0:raise ValueError(k)
 for k,v in (settings|dict(probe_mode=0,active_divider=1,cleanup_phase=11,divider_change_attempted=1,divider_restore_attempts=1)).items():
  if p.get(k)!=v:raise ValueError(k)
 return dict(status='CLEAN_CLOCK_DIVIDER_ROUND_TRIP',operation_succeeded=True,hardware_execution_verified=False,gpu_access=False,normal_removal_supported=True,automatic_retry=False)
