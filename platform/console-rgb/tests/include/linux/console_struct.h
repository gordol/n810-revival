#ifndef TEST_CONSOLE_STRUCT_H
#define TEST_CONSOLE_STRUCT_H
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
typedef uint32_t u32;
typedef uint16_t u16;
typedef uint8_t u8;
#define U32_MAX UINT32_MAX
#define min(a,b) ((a)<(b)?(a):(b))
#define max3(a,b,c) ((a)>(b)?((a)>(c)?(a):(c)):((b)>(c)?(b):(c)))
#define swap(a,b) do { __typeof__(a) tmp=(a);(a)=(b);(b)=tmp; } while(0)
enum vc_intensity { VCI_HALF_BRIGHT, VCI_NORMAL, VCI_BOLD };
enum con_scroll { SM_UP, SM_DOWN };
struct vc_rgb { u32 fg,bg; };
struct vc_state { unsigned x,y;u8 color;u32 rgb_fg,rgb_bg;bool reverse;enum vc_intensity intensity; };
struct consw;
struct vc_data {
 struct vc_state state;
 struct vc_rgb *vc_rgb;
 size_t vc_screenbuf_size;
 unsigned long vc_origin,vc_scr_end,vc_pos;
 unsigned vc_rows,vc_cols,vc_size_row,vc_num,vc_npar,vc_par[16];
 u16 vc_video_erase_char;
 bool vc_decscnm,vc_need_wrap;
 struct { unsigned width,height; } vc_font;
 const struct consw *vc_sw;
};
struct consw { bool (*con_scroll)(struct vc_data *,unsigned,unsigned,enum con_scroll,unsigned); };
#endif
