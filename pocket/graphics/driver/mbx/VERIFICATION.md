# Selectable render verification

`gpu_verification_mode` is fixed at module insertion; 0 is the existing full diagnostic default, 1 is normal checkpoint verification. Values above 1 reject render writes. This setting never changes rendering commands or pixel quality.

Both modes retain command/resource admission, bounds and ownership checks, generation tokens, FIFO flow control, GPU completion/error/timeouts, DMA synchronization, startup render proof and fault retention.

Full mode scans guard memory and compares submitted texture bytes after every job. Normal mode scans guards on the first job of each session, after texture replacements and every 32 completed jobs. It compares uploaded textures when replaced. Session close scans all guards and the current verified texture arena before freeing command storage. A failed checkpoint latches the fault and retains storage for attended diagnosis. Normal mode can detect corruption later than full mode; it does not provide per-job corruption detection.

Read-only counters `gpu_verification_checks` and `gpu_verification_skipped` expose the selected coverage. `gpu_last_guard_checked` reports whether the most recent job/checkpoint actually scanned guards. The internal `gpu_bounds_verified` handoff accepts completion under the selected verification policy, including scheduled skips; it remains false on failed checks. Detailed existing timing counters remain available for the matched comparison.

Local service tests exercise a failing normal close checkpoint, retained storage, and successful cleanup after the injected fault is removed. Physical CPU/FPS and final-pixel comparisons remain pending device ownership. No persistent device default has been changed.
