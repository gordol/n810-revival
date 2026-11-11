/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef POCKET_ROOM_DRAW_H
#define POCKET_ROOM_DRAW_H
/* GL owner thread only. The backend binds a dedicated tile target with depth
 * storage before calling. Drawing uses the complete view projection, clipped
 * by the target; target_height describes its backing viewport height.
 * Does not bind/allocate targets, finish, read pixels, or upload an image.
 * This is a command producer, not a claim of backend resource residency. */
int pocket_room_draw_tile(float age,float x,float z,float yaw,float pitch,
 unsigned width,unsigned height,unsigned tile_x,unsigned tile_y,
 unsigned tile_width,unsigned tile_height,unsigned target_height,int with_game);
int pocket_room_draw_region(float,float,float,float,float,unsigned,unsigned,int,int,unsigned,unsigned,unsigned,int);
#endif
