/* SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
 * SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef POCKET_NATIVE_TEXT_H
#define POCKET_NATIVE_TEXT_H
#include <SDL.h>
#include <stdint.h>
#include <stddef.h>
int pocket_native_text_stage(const uint32_t *,size_t);
int pocket_native_text_clear(uint32_t *,size_t,unsigned,unsigned,int,int,unsigned,unsigned);
int pocket_native_text_marks(uint32_t *,size_t,unsigned,unsigned,const void *,unsigned,int,int,unsigned,unsigned);
unsigned pocket_native_text_density(unsigned,unsigned,unsigned,unsigned,unsigned,unsigned);
int pocket_native_text_draw(SDL_Renderer *,unsigned,unsigned);
void pocket_native_text_close(void);
#endif
