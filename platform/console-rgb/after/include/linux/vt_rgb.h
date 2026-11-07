/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _LINUX_VT_RGB_H
#define _LINUX_VT_RGB_H

#include <linux/console_struct.h>
#include <linux/slab.h>
#include <linux/string.h>

#define VC_RGB_DEFAULT U32_MAX

static inline struct vc_rgb vc_rgb_current(const struct vc_data *vc, bool erase)
{
	struct vc_rgb color = { vc->state.rgb_fg, vc->state.rgb_bg };

	if (vc->vc_decscnm ^ (!erase && vc->state.reverse))
		swap(color.fg, color.bg);
	return color;
}

static inline size_t vc_rgb_count(const struct vc_data *vc)
{
	return vc->vc_screenbuf_size / sizeof(u16);
}

static inline bool vc_rgb_alloc(struct vc_data *vc)
{
	size_t count = vc_rgb_count(vc);

	if (vc->vc_rgb)
		return true;
	vc->vc_rgb = kmalloc_array(count, sizeof(*vc->vc_rgb), GFP_KERNEL);
	if (!vc->vc_rgb)
		return false;
	memset(vc->vc_rgb, 0xff, count * sizeof(*vc->vc_rgb));
	return true;
}

static inline void vc_rgb_fill(struct vc_data *vc, size_t first, size_t count,
			      struct vc_rgb color)
{
	if (!vc->vc_rgb || first >= vc_rgb_count(vc))
		return;
	count = min(count, vc_rgb_count(vc) - first);
	while (count--)
		vc->vc_rgb[first++] = color;
}

static inline void vc_rgb_store(struct vc_data *vc, const u16 *pos,
			       size_t count, bool erase)
{
	unsigned long address = (unsigned long)pos;

	if (address < vc->vc_origin || address >= vc->vc_scr_end)
		return;
	vc_rgb_fill(vc, (address - vc->vc_origin) / sizeof(u16), count,
		    vc_rgb_current(vc, erase));
}

static inline void vc_rgb_move(struct vc_data *vc, size_t dest,
			      size_t source, size_t count)
{
	size_t cells = vc_rgb_count(vc);

	if (!vc->vc_rgb || source >= cells || dest >= cells)
		return;
	count = min(count, min(cells - source, cells - dest));
	memmove(vc->vc_rgb + dest, vc->vc_rgb + source,
		count * sizeof(*vc->vc_rgb));
}

static inline void vc_rgb_invert(struct vc_data *vc, const u16 *pos,
				size_t count)
{
	size_t first;
	unsigned long address = (unsigned long)pos;

	if (!vc->vc_rgb || address < vc->vc_origin || address >= vc->vc_scr_end)
		return;
	first = (address - vc->vc_origin) / sizeof(u16);
	count = min(count, vc_rgb_count(vc) - first);
	while (count--) {
		swap(vc->vc_rgb[first].fg, vc->vc_rgb[first].bg);
		first++;
	}
}

static inline struct vc_rgb vc_rgb_cell(const struct vc_data *vc,
				       unsigned int y, unsigned int x)
{
	struct vc_rgb color = { VC_RGB_DEFAULT, VC_RGB_DEFAULT };

	if (vc->vc_rgb && y < vc->vc_rows && x < vc->vc_cols)
		color = vc->vc_rgb[(size_t)y * vc->vc_cols + x];
	return color;
}

#endif
