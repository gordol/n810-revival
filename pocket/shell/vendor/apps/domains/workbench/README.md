# Local Workbench domain

The domain owns local-file IO, a single bounded worker, cancellation, replay
process lifecycle and retained reports. It has no UI imports. A presentation
renders `snapshot()` and dispatches explicit commands; rendering must not launch
jobs or read artifacts. No process exists until the user starts CW replay.

```python
from domains.workbench import Workbench

model = Workbench(app_state_directory)
model.select(user_selected_path)  # returns job UUID immediately
# Inspect cached snapshot until terminal status; redraw on revision change.
view = model.snapshot()
model.run_cw(tone=700, wpm=20, seconds=30, method="route")  # explicit user action
model.cancel()                   # safe while a worker is running
model.load_result(retained_job_id)
model.refresh_evidence()         # explicit read of fixed FIR/VFP report refs
model.close()                    # cancel and join on app/runtime shutdown
```

One domain instance belongs to the application lifecycle. Reuse it when panes
hide/reopen; hiding must not instantiate another worker. `close()` is terminal.
Every operation returns a job ID except `cancel`/`close`/`snapshot`.
`cancel()` returns whether an active worker was signalled. A concurrent command
raises RuntimeError; invalid settings/missing selection raise ValueError.
Filesystem/replay failures become terminal snapshot status `failed` with `error`.
The optional constructor `wall_timeout` is0.01–30 seconds (default30).

## Snapshot contract

All snapshots are detached plain JSON data. They do not perform filesystem IO
or DSP. Fields:

- `revision`: increments on relevant state/progress updates.
- `status`: idle, running, cancelling, complete, cancelled or failed.
- `progress`: null, or job_id/kind/fraction and optional audio_seconds/event_count.
  Fraction is indeterminate on cancellation/failure. Audio progress comes from
  processed candidate events, not a wall-time estimate.
- `selected`: inspected path/name/size/SHA/kind and WAV metadata when available;
  includes `cw_supported` and a truthful unsupported-format note.
- `result`: inspection metadata, CW settings/events/text, an evidence report list,
  or a retained history report. CW text always has `verified: false`.
- `history`: newest at end, maximum20 entries; each has UUID, kind, terminal
  status, error and a local JSON artifact_ref. `load_result(id)` reopens a retained
  result asynchronously without adding a duplicate history entry.
- `experiments`: available CW operation and fixed read-only FIR/VFP report refs.
  Evidence starts `not_loaded`; explicit refresh reports available/unavailable.
  It never runs accelerator binaries or interprets report text as commands.
- `error`, `persistence_error`: distinct visible failures.

Use job IDs as row identities. Render any file/report text as text, never markup
with commands. Missing files remain missing; they do not imply acquisition is
running. An empty CW result means the adapter emitted no text candidates, not
proof that a recording contains no Morse.

## Input, execution and persistence bounds

Only explicitly selected regular files32MiB or smaller are opened; there is no
directory scan, capture, hardware access or network. Inspection can describe an
unsupported file, but CW requires uncompressed8kHz mono S16 WAV. Supported WAV
payloads are checked for truncation during inspection. Resampling is not hidden
inside this model. The existing stream adapter is reused without duplicated DSP.

Explicit CW replay accepts300–3000Hz,5–30WPM,0.1–60 audio seconds and one of route,
probabilistic, matched or timing. It invokes fixed trusted Python files with an
argument list and no shell. Parent validates the selected SHA before and after
execution, passes the already opened regular file descriptor, and applies a
30-second wall limit,256KiB combined output limit and256-event limit. Child applies
15-second CPU and zero core-dump limits on POSIX. It inherits the existing bounded
adapter/DSP windows; this is not an OS hard address-space or N810 memory claim.
Cancel terminates/reaps the child; process termination escalates to kill after1s.

`state_dir` is chosen by the application. It stores atomic history state and
at most20 per-job JSON reports, mode0600. Audio is referenced, never copied.
Older owned report UUIDs are pruned as history rolls over. Reopening restores
history only: selection permission and running work are not restored, and no job
starts automatically. Result loading validates retained UUID identity and rejects
symlinks. State/report content is bounded. The known example is
`packet-console/experiments/cw-reference/known-cq.wav` and can be offered as an
explicit example action; it is never automatically run.

## Verification and integration status

```sh
python3 -m unittest -v domains.workbench.test_workbench
```

Seven tests cover a real selected-WAV→CW candidate→persisted/reopened history flow;
unsupported/missing/changed/truncated/oversize inputs; detached snapshots;
single-worker cancellation and timeout; evidence reading and bad parameter/result
IDs, bounded retained history and private report modes. Known example returns `CQ N0CALL SOS 73`. All work is local receive-only file
replay. The native Workbench presenter/launcher is owned by the framework chat;
this domain alone is not a shipped GUI, live HF connection or N810 deployment.
