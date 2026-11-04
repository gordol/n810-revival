# Start the N810 console workspace only for a normal interactive tty1 login.
# Create ~/.config/n810/no-auto to suppress this hook until that file is removed.
if [ -z "${TMUX:-}" ] &&
   [ "$(id -u)" -ne 0 ] && [ -t 0 ] && [ "$(tty 2>/dev/null)" = /dev/tty1 ]; then
	config=${XDG_CONFIG_HOME:-$HOME/.config}/n810/pocket.conf
	complete=${XDG_CONFIG_HOME:-$HOME/.config}/n810/setup-complete
	skip=${XDG_CONFIG_HOME:-$HOME/.config}/n810/no-auto
	if [ -e "$skip" ]; then
		:
	elif [ -r "$config" ] && [ -r "$complete" ]; then
		n810-session launch
	else
		n810-setup
		if [ -r "$complete" ]; then n810-session launch; fi
	fi
fi
