#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise the reconstructed LM8323 reset wait with transient and permanent NACKs."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, required=True, help='Reconstructed drivers/input/keyboard/lm8323.c')
args = parser.parse_args()
source = args.source.read_text()
start = source.index('\ttmo = jiffies + msecs_to_jiffies(100);', source.index('lm8323_reset(lm);'))
end = source.index('\n\tlm8323_configure(lm);', start)
loop = source[start:end]
harness = r'''
#include <assert.h>
#include <errno.h>
#include <stdio.h>
static unsigned long jiffies;
static unsigned reads, errors, nack_reads, ready_at;
#define LM8323_CMD_READ_INT 0x82
#define INT_NOINIT 0x10
#define msecs_to_jiffies(n) (n)
#define time_after(a,b) ((long)((b)-(a)) < 0)
#define dev_err(...) (++errors)
static void msleep(unsigned n) { jiffies += n; }
static int lm8323_read(void *lm, unsigned cmd, unsigned char *data, unsigned len) {
 (void)lm; assert(cmd == 0x82 && len == 1); ++reads;
 if (reads <= nack_reads) return -EREMOTEIO;
 data[0] = reads >= ready_at ? INT_NOINIT : 0;
 return 1;
}
static int wait_reset(void) {
 void *lm = NULL; unsigned long tmo; unsigned char data[2];
''' + loop + r'''
 return 0;
}
static int run(unsigned nacks, unsigned ready) {
 jiffies=reads=errors=0; nack_reads=nacks; ready_at=ready;
 return wait_reset();
}
int main(void) {
 assert(!run(0,1) && reads==1 && !errors);
 assert(!run(3,4) && reads==4 && !errors);
 assert(!run(0,8) && reads==8 && !errors);
 assert(run(1000,1001)==-ETIMEDOUT && errors==1 && jiffies<=102);
 assert(run(0,1000)==-ETIMEDOUT && errors==1 && jiffies<=102);
 puts("LM8323 reset: transient NACKs and delayed ready retried; permanent faults bounded and rejected");
}
'''
with tempfile.TemporaryDirectory(prefix='n810-keyboard-reset-') as folder:
    root = Path(folder)
    test = root / 'reset.c'
    test.write_text(harness)
    binary = root / 'reset'
    subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-Wall', '-Wextra', '-Werror',
                    str(test), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
