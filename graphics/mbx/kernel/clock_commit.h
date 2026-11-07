/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef CLOCK_COMMIT_H
#define CLOCK_COMMIT_H
#define COMMIT_GUARDS 8
struct commit_io {
 void *cookie;
 unsigned int (*read)(void *,unsigned int);
 void (*write)(void *,unsigned int,unsigned int);
 void (*pause)(void *,unsigned int);
 void (*lock)(void *);
 void (*unlock)(void *);
};
struct commit_result {
 unsigned int attempted,commits,target,restored,target_samples,restore_samples;
 unsigned int guards_before[COMMIT_GUARDS],guards_after[COMMIT_GUARDS];
 unsigned int initial_config,final_config,initial_status,final_status;
 int error,restoration_error;
};
struct commit_result clock_commit_apply(const struct commit_io *,unsigned int,unsigned int,unsigned int,unsigned int);
#endif
