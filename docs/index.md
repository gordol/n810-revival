---
title: N810 revival
template: home.html
hide:
  - navigation
  - toc
---

## On the N810

Pocket runs as a native GPU desktop or a terminal interface. See [hardware and application support](status.md) for physical test results and known failures, the [roadmap](roadmap.md) for planned work, and the [SD A/B installation guide](how-to/install-n810-ab.md) for the tested install route.

## Get started

Start with [Set up an N810](start.md) for the tablet installation routes and their requirements. To explore Pocket on a laptop, follow [Your first Pocket session](tutorials/first-session.md). The tutorial includes downloads, launch commands, and the controls for opening applications and quitting.

With Python 3.11 or newer, Make, and Git installed, the laptop launch commands are:

```sh
git clone https://github.com/gordol/n810-revival.git
cd n810-revival/pocket
make
```

Watch the [window-controls tour](tutorials/laptop-tour.md), explore the [documentation](guides.md), or follow the [journal from the beginning](journal.md).

For the native Mac/Linux window, use the [graphical frontend guide](pocket/graphics.md). Its source build shares the desktop and applications with the terminal version.
