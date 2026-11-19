#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Run the reconstructed LED registration with an immediate trigger callback."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, required=True)
args = parser.parse_args()
source = args.source.read_text()
start = source.index('int lp55xx_register_leds(')
end = source.index('\nEXPORT_SYMBOL_GPL(lp55xx_register_leds);', start)
harness = r'''
#include <assert.h>
#include <errno.h>
#include <stdio.h>
typedef unsigned char u8;
struct lp55xx_chip;
struct lp55xx_led { struct lp55xx_chip *chip; };
struct led_config { u8 led_current; };
struct lp55xx_platform_data { int num_channels; struct led_config led_config[3]; };
struct lp55xx_device_config { int brightness_fn; void (*set_led_current)(struct lp55xx_led *, u8); };
struct client { int dev; };
struct lp55xx_chip { struct lp55xx_platform_data *pdata; struct lp55xx_device_config *cfg; struct client *cl; int num_leds; };
static unsigned callbacks;
static int fail_at = -1;
#define dev_err(...) ((void)0)
static int lp55xx_init_led(struct lp55xx_led *led, struct lp55xx_chip *chip, int channel) {
 /* LED class registration can activate a default trigger synchronously. */
 assert(led->chip == chip);
 assert(led->chip->cfg->brightness_fn);
 ++callbacks;
 return channel == fail_at ? -EIO : 0;
}
''' + source[start:end] + r'''
int main(void) {
 struct lp55xx_led leds[3] = {0};
 struct lp55xx_platform_data pdata = {3, {{1}, {0}, {1}}};
 struct lp55xx_device_config cfg = {1, NULL};
 struct lp55xx_chip chip = {&pdata, &cfg, NULL, 0};
 assert(lp55xx_register_leds(leds, &chip) == 0);
 assert(callbacks == 2 && chip.num_leds == 2 && !leds[1].chip);
 callbacks = 0; chip.num_leds = 0; fail_at = 0;
 assert(lp55xx_register_leds(leds, &chip) == -EIO);
 assert(callbacks == 1 && !chip.num_leds);
 cfg.brightness_fn = 0; callbacks = 0;
 assert(lp55xx_register_leds(leds, &chip) == -EINVAL && !callbacks);
 puts("LP55xx: callback context initialized before registration; skipped channels and failures preserved");
}
'''
with tempfile.TemporaryDirectory(prefix='n810-led-registration-') as folder:
    root = Path(folder)
    test = root / 'registration.c'
    test.write_text(harness)
    binary = root / 'registration'
    subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-Wall', '-Wextra', '-Werror',
                    str(test), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
