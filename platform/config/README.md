# Platform configuration

These are templates and package lists, not the tablet's live settings.

- `n810-*` and `90-n810-network.conf`: login, radio, storage, and session defaults.
- `tmux-*` and `n810-programmer.map`: keyboard and terminal layout.
- `pocket-*.packages` and `media-bookworm-armel.packages`: package selections
  from the OS development tree. They are not a lockfile for Pocket 0.1.0.
- `comms/*.example`: mail and chat examples. Supply your own accounts and
  credentials outside the repository.

The source includes no actual Wi-Fi profile, mailbox account, or device secret.
