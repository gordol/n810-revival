#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
if test -x "$script_dir/n810-bluetooth"; then
	helper_dir=$script_dir
else
	helper_dir=$(CDPATH= cd -- "$script_dir/../scripts" && pwd)
fi
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT INT TERM

sh -n "$helper_dir/n810-bluetooth"
sh -n "$helper_dir/n810-audio"
sh -n "$helper_dir/n810-media"

# Production rejects every path/tool override. Exercise those branches only in
# an ephemeral validator copy whose compile-time switch is changed exactly once.
test "$(grep -c '^test_overrides_allowed=0$' "$helper_dir/n810-audio")" -eq 1
sed 's/^test_overrides_allowed=0$/test_overrides_allowed=1/' \
	"$helper_dir/n810-audio" > "$tmp/n810-audio-test"
chmod 755 "$tmp/n810-audio-test"
audio_helper=$tmp/n810-audio-test
export N810_AUDIO_TEST_MODE=1

if N810_AUDIO_TEST_MODE=0 N810_AUDIO_PCM_GATE="$tmp/fake-gate" \
	"$helper_dir/n810-audio" status >"$tmp/prod-override.out" 2>"$tmp/prod-override.err"; then
	echo 'production audio helper accepted a gate override' >&2
	exit 1
fi
grep -Fqx 'N810_AUDIO_PCM_GATE is available only in an instrumented test build' \
	"$tmp/prod-override.err"
if N810_AUDIO_TEST_MODE=0 N810_ASOUND_CARDS="$tmp/cards" \
	"$helper_dir/n810-audio" status >"$tmp/prod-cards.out" 2>"$tmp/prod-cards.err"; then
	echo 'production audio helper accepted an ALSA-card path override' >&2
	exit 1
fi
grep -Fqx 'N810_ASOUND_CARDS is available only in an instrumented test build' \
	"$tmp/prod-cards.err"
if N810_AUDIO_TEST_MODE=0 N810_STAT="$tmp/stat" \
	"$helper_dir/n810-audio" status >"$tmp/prod-stat.out" 2>"$tmp/prod-stat.err"; then
	echo 'production audio helper accepted a stat-tool override' >&2
	exit 1
fi
grep -Fqx 'N810_STAT is available only in an instrumented test build' \
	"$tmp/prod-stat.err"
if N810_AUDIO_TEST_MODE=0 N810_UNAME="$tmp/uname" \
	"$helper_dir/n810-audio" status >"$tmp/prod-uname.out" 2>"$tmp/prod-uname.err"; then
	echo 'production audio helper accepted a uname-tool override' >&2
	exit 1
fi
grep -Fqx 'N810_UNAME is available only in an instrumented test build' \
	"$tmp/prod-uname.err"
for override in N810_CAT N810_WC N810_TR; do
	if env N810_AUDIO_TEST_MODE=0 "$override=/tmp/fake" \
		"$helper_dir/n810-audio" status >"$tmp/prod-tool.out" 2>"$tmp/prod-tool.err"; then
		echo "production audio helper accepted $override" >&2
		exit 1
	fi
	grep -Fqx "$override is available only in an instrumented test build" \
		"$tmp/prod-tool.err"
done
if N810_AUDIO_TEST_MODE=1 "$helper_dir/n810-audio" status \
	>"$tmp/prod-test.out" 2>"$tmp/prod-test.err"; then
	echo 'production audio helper enabled test mode' >&2
	exit 1
fi
grep -Fqx 'n810-audio test overrides are disabled in this build' \
	"$tmp/prod-test.err"

cat > "$tmp/bluetoothctl" <<'FAKE'
#!/bin/sh
set -eu
printf '%s\n' "$*" >> "$N810_TEST_LOG"
case ${1:-} in
list)
	case ${N810_TEST_BT_MODE:-controller} in
	controller) echo 'Controller 00:11:22:33:44:55 N810 [default]' ;;
	none) : ;;
	daemon-down) exit 1 ;;
	esac
	;;
show) echo 'Controller 00:11:22:33:44:55 (public)' ;;
devices) echo 'Device 01:23:45:67:89:AB Test keyboard' ;;
*) : ;;
esac
FAKE
cat > "$tmp/n810-ledctl" <<'FAKE'
#!/bin/sh
printf 'led %s\n' "$*" >> "$N810_TEST_LOG"
FAKE
cat > "$tmp/tmux" <<'FAKE'
#!/bin/sh
printf 'tmux %s\n' "$*" >> "$N810_TEST_LOG"
FAKE
cat > "$tmp/amixer" <<'FAKE'
#!/bin/sh
printf 'amixer %s\n' "$*" >> "$N810_TEST_LOG"
FAKE
cat > "$tmp/id" <<'FAKE'
#!/bin/sh
test "${1:-}" = -u && echo 0
FAKE
cat > "$tmp/modprobe" <<'FAKE'
#!/bin/sh
printf 'modprobe %s\n' "$*" >> "$N810_TEST_LOG"
FAKE
cat > "$tmp/sleep" <<'FAKE'
#!/bin/sh
:
FAKE
cat > "$tmp/uname" <<'FAKE'
#!/bin/sh
test "${1:-}" = -r && echo 5.15.86-n810-audio-safe-test+
FAKE
cat > "$tmp/stat" <<'FAKE'
#!/bin/sh
case ${N810_TEST_GATE_OWNER:-root} in
root) echo '0 644' ;;
user) echo '1001 644' ;;
writable) echo '0 666' ;;
esac
FAKE
cat > "$tmp/speaker-test" <<'FAKE'
#!/bin/sh
printf 'speaker-test %s\n' "$*" >> "$N810_TEST_LOG"
FAKE
cat > "$tmp/arecord" <<'FAKE'
#!/bin/sh
printf 'arecord %s\n' "$*" >> "$N810_TEST_LOG"
FAKE
for tool in cmus mpg123 ncmpc w3m; do
	cat > "$tmp/$tool" <<'FAKE'
#!/bin/sh
printf '%s %s\n' "${0##*/}" "$*" >> "$N810_TEST_LOG"
FAKE
done
printf ' 0 [Other          ]: USB - Other card\n' > "$tmp/other-cards"
printf ' 1 [N810           ]: N810 - N810\n' > "$tmp/cards"
chmod +x "$tmp/bluetoothctl" "$tmp/n810-ledctl" "$tmp/tmux" "$tmp/amixer" \
	"$tmp/id" "$tmp/modprobe" "$tmp/sleep" "$tmp/uname" \
	"$tmp/stat" "$tmp/speaker-test" "$tmp/arecord"
chmod +x "$tmp/cmus" "$tmp/mpg123" "$tmp/ncmpc" "$tmp/w3m"
export N810_UNAME=$tmp/uname
export N810_CAT=/bin/cat N810_WC=/usr/bin/wc N810_TR=/usr/bin/tr

export N810_TEST_LOG=$tmp/log
N810_BLUETOOTHCTL=$tmp/bluetoothctl N810_LEDCTL=$tmp/n810-ledctl \
	"$helper_dir/n810-bluetooth" status >/dev/null
TMUX=/tmp/fake N810_BLUETOOTHCTL=$tmp/bluetoothctl \
	N810_LEDCTL=$tmp/n810-ledctl N810_TMUX_BIN=$tmp/tmux \
	"$helper_dir/n810-bluetooth" pair 01:23:45:67:89:AB
TMUX=/tmp/fake N810_BLUETOOTHCTL=$tmp/bluetoothctl \
	N810_LEDCTL=$tmp/n810-ledctl N810_TMUX_BIN=$tmp/tmux \
	"$helper_dir/n810-bluetooth" connect 01:23:45:67:89:AB
PATH="$tmp:$PATH" N810_BLUETOOTHCTL=$tmp/bluetoothctl \
	"$helper_dir/n810-bluetooth" discover 1 >/dev/null
N810_BLUETOOTHCTL=$tmp/bluetoothctl \
	"$helper_dir/n810-bluetooth" info 01:23:45:67:89:AB >/dev/null

# Distinguish an absent controller from an unavailable bluetoothd, and never
# continue into an operation in either state.
if N810_TEST_BT_MODE=none N810_BLUETOOTHCTL=$tmp/bluetoothctl \
	"$helper_dir/n810-bluetooth" status >"$tmp/bt-none.out" 2>"$tmp/bt-none.err"; then
	echo 'Bluetooth status accepted an absent controller' >&2
	exit 1
fi
grep -Fqx 'No Bluetooth controller is registered (expected hci0)' "$tmp/bt-none.err"
if N810_TEST_BT_MODE=daemon-down N810_BLUETOOTHCTL=$tmp/bluetoothctl \
	"$helper_dir/n810-bluetooth" status >"$tmp/bt-down.out" 2>"$tmp/bt-down.err"; then
	echo 'Bluetooth status accepted an unavailable bluetoothd' >&2
	exit 1
fi
grep -Fqx 'BlueZ is unavailable; bluetoothctl could not contact bluetoothd' "$tmp/bt-down.err"
PATH="$tmp:$PATH" N810_ASOUND_CARDS="$tmp/cards" \
	"$audio_helper" speaker >/dev/null
PATH="$tmp:$PATH" N810_ASOUND_CARDS="$tmp/cards" \
	"$audio_helper" probe >/dev/null
if PATH="$tmp:$PATH" N810_ASOUND_CARDS="$tmp/other-cards" \
	"$audio_helper" probe >/dev/null 2>&1; then
	echo 'audio probe accepted a non-N810 ALSA card' >&2
	exit 1
fi

# Card registration is not PCM safety. The known-hard-lock path must stay
# blocked until a root-owned, per-boot gate names the exact running kernel.
if PATH="$tmp:$PATH" N810_ASOUND_CARDS="$tmp/cards" \
	N810_AUDIO_PCM_GATE="$tmp/pcm-gate" \
	"$audio_helper" play-test >/dev/null 2>&1; then
	echo 'audio playback ran without the per-kernel PCM safety gate' >&2
	exit 1
fi
if grep -q '^speaker-test ' "$tmp/log" 2>/dev/null; then
	echo 'blocked audio playback reached speaker-test' >&2
	exit 1
fi
printf '%s\n' 5.15.86-n810-wrong+ > "$tmp/pcm-gate"
if PATH="$tmp:$PATH" N810_ASOUND_CARDS="$tmp/cards" \
	N810_AUDIO_PCM_GATE="$tmp/pcm-gate" \
	"$audio_helper" record-test "$tmp/capture.wav" >/dev/null 2>&1; then
	echo 'audio capture accepted a gate for another kernel' >&2
	exit 1
fi
# A second unterminated line used to evade the newline-count check. Keep all
# trailing bytes fail-closed before allowing either playback or capture.
printf '%s\n%s' 5.15.86-n810-audio-safe-test+ unexpected > "$tmp/pcm-gate"
if PATH="$tmp:$PATH" N810_ASOUND_CARDS="$tmp/cards" \
	N810_AUDIO_PCM_GATE="$tmp/pcm-gate" \
	"$audio_helper" play-test >/dev/null 2>&1; then
	echo 'audio playback accepted trailing approval-file data' >&2
	exit 1
fi
printf '%s\n' 5.15.86-n810-audio-safe-test+ > "$tmp/pcm-gate"
for unsafe_owner in user writable; do
	if PATH="$tmp:$PATH" N810_ASOUND_CARDS="$tmp/cards" \
		N810_STAT="$tmp/stat" N810_TEST_GATE_OWNER=$unsafe_owner \
		N810_AUDIO_PCM_GATE="$tmp/pcm-gate" \
		"$audio_helper" play-test >/dev/null 2>&1; then
		echo "audio playback accepted unsafe gate metadata: $unsafe_owner" >&2
		exit 1
	fi
done
PATH="$tmp:$PATH" N810_ASOUND_CARDS="$tmp/cards" \
	N810_STAT="$tmp/stat" N810_AUDIO_PCM_GATE="$tmp/pcm-gate" \
	"$audio_helper" pcm-status | grep -Fq 'pcm_streaming=approved'
PATH="$tmp:$PATH" N810_ASOUND_CARDS="$tmp/cards" \
	N810_STAT="$tmp/stat" N810_AUDIO_PCM_GATE="$tmp/pcm-gate" \
	"$audio_helper" play-test >/dev/null
PATH="$tmp:$PATH" N810_ASOUND_CARDS="$tmp/cards" \
	N810_AUDIO_PCM_GATE="$tmp/pcm-gate" \
	"$audio_helper" record-test "$tmp/capture.wav" >/dev/null

# Every audio frontend crosses the same exact-kernel gate. Browsing does not.
rm -f "$tmp/pcm-gate"
if PATH="$tmp:$PATH" N810_ASOUND_CARDS="$tmp/cards" \
	N810_AUDIO_BIN="$audio_helper" N810_AUDIO_PCM_GATE="$tmp/pcm-gate" \
	"$helper_dir/n810-media" music >/dev/null 2>&1; then
	echo 'cmus launcher bypassed the PCM safety gate' >&2
	exit 1
fi
if grep -q '^cmus ' "$tmp/log" 2>/dev/null; then
	echo 'blocked cmus launcher reached the player' >&2
	exit 1
fi
printf '%s\n' 5.15.86-n810-audio-safe-test+ > "$tmp/pcm-gate"
for invocation in music 'radio https://radio.example/stream' mpd; do
	# Intentional word splitting supplies each fixed test argument.
	set -- $invocation
	PATH="$tmp:$PATH" N810_ASOUND_CARDS="$tmp/cards" \
		N810_AUDIO_BIN="$audio_helper" N810_AUDIO_PCM_GATE="$tmp/pcm-gate" \
		N810_STAT="$tmp/stat" \
		"$helper_dir/n810-media" "$@" >/dev/null
done
PATH="$tmp:$PATH" N810_AUDIO_BIN="$audio_helper" \
	"$helper_dir/n810-media" web https://example.test/ >/dev/null
if PATH="$tmp:$PATH" N810_AUDIO_BIN="$audio_helper" \
	"$helper_dir/n810-media" web file:///etc/passwd >/dev/null 2>&1; then
	echo 'web launcher accepted a non-HTTP URL' >&2
	exit 1
fi

for expected in \
	'--agent=KeyboardDisplay pair 01:23:45:67:89:AB' \
	'trust 01:23:45:67:89:AB' \
	'connect 01:23:45:67:89:AB' \
	'scan on' \
	'scan off' \
	'info 01:23:45:67:89:AB' \
	'led notify bluetooth 4' \
	'tmux display-message -- Bluetooth paired and trusted' \
	'tmux display-message -- Bluetooth connected' \
	"amixer -c N810 sset Jack Function Off" \
	"amixer -c N810 sset Speaker Function On" \
	"modprobe snd-soc-tlv320aic3x-i2c" \
	"modprobe snd-soc-omap-mcbsp" \
	"modprobe snd-soc-n810" \
	"speaker-test -D hw:N810,0 -c 2 -r 48000 -F S16_LE -t sine -l 1" \
	"arecord -D hw:N810,0 -c 2 -r 48000 -f S16_LE -d 5 -- $tmp/capture.wav"
do
	grep -Fqx -- "$expected" "$tmp/log"
done
for expected in \
	'cmus ' \
	'mpg123 -b 1024 -- https://radio.example/stream' \
	'ncmpc ' \
	'w3m -- https://example.test/'
do
	grep -Fqx -- "$expected" "$tmp/log"
done

if N810_BLUETOOTHCTL=$tmp/bluetoothctl "$helper_dir/n810-bluetooth" pair invalid >/dev/null 2>&1; then
	echo 'invalid address was accepted' >&2
	exit 1
fi
if N810_BLUETOOTHCTL=$tmp/bluetoothctl "$helper_dir/n810-bluetooth" status extra >/dev/null 2>&1; then
	echo 'Bluetooth status accepted trailing arguments' >&2
	exit 1
fi
if PATH="$tmp:$PATH" N810_AUDIO_BIN="$audio_helper" \
	"$helper_dir/n810-media" music extra >/dev/null 2>&1; then
	echo 'media music launcher accepted trailing arguments' >&2
	exit 1
fi
if PATH="$tmp:$PATH" N810_ASOUND_CARDS="$tmp/cards" \
	"$audio_helper" status extra >/dev/null 2>&1; then
	echo 'audio status accepted trailing arguments' >&2
	exit 1
fi

echo 'media userland helper validation passed'
