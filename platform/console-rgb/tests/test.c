#include <assert.h>
#include <stdio.h>
#include <linux/vt_rgb.h>

static bool rgb_console=true;
static unsigned redraws,legacy_scrolls;
static bool con_is_visible(struct vc_data *vc) { return true; }
static bool con_should_update(struct vc_data *vc) { return true; }
static void vc_uniscr_scroll(struct vc_data *vc,unsigned t,unsigned b,enum con_scroll d,unsigned n) {}
static void vc_uniscr_insert(struct vc_data *vc,unsigned nr) {}
static void vc_uniscr_delete(struct vc_data *vc,unsigned nr) {}
static void scr_memmovew(u16 *d,const u16 *s,size_t n) { memmove(d,s,n); }
static void scr_memsetw(u16 *d,u16 value,size_t n) { while(n) { *d++=value;n-=2; } }
static u16 scr_readw(const u16 *s) { return *s; }
static void do_update_region(struct vc_data *vc,unsigned long start,int count) { redraws++; }
static bool legacy_scroll(struct vc_data *vc,unsigned t,unsigned b,enum con_scroll d,unsigned n) { legacy_scrolls++;return false; }
#include "vt-functions.inc"

struct fb_bitfield { unsigned offset,length; };
struct fb_var_screeninfo { unsigned bits_per_pixel;struct fb_bitfield red,green,blue,transp; };
struct fb_fillrect { u32 color,dx,dy,width,height,rop; };
struct fb_info;
struct fbcon_ops {
 void (*putcs)(struct vc_data *,struct fb_info *,const u16 *,int,int,int,int,int);
 void (*cursor)(struct vc_data *,struct fb_info *,int,int,int);
};
struct fb_ops { void (*fb_fillrect)(struct fb_info *,const struct fb_fillrect *); };
struct fb_info { void *pseudo_palette,*fbcon_par;struct { int visual; } fix;struct fb_var_screeninfo var;const struct fb_ops *fbops; };
struct fbcon_display { int unused; };
static struct fbcon_display fb_display[1];
#define FB_VISUAL_TRUECOLOR 2
#define ROP_COPY 0
static int real_y(struct fbcon_display *display,int y) { return y; }
static int get_color(struct vc_data *vc,struct fb_info *info,u16 c,int fg) { return fg?((c>>8)&15):((c>>12)&15); }
#include "fb-functions.inc"
static u32 painted_fg[40],painted_bg[40];
static void putcs(struct vc_data *vc,struct fb_info *info,const u16 *s,int count,int y,int x,int fg,int bg) {
 u32 *palette=info->pseudo_palette;
 for(int i=0;i<count;i++) { painted_fg[y*vc->vc_cols+x+i]=palette[fg];painted_bg[y*vc->vc_cols+x+i]=palette[bg]; }
}
static void cursor(struct vc_data *vc,struct fb_info *info,int mode,int fg,int bg) {
 u32 *palette=info->pseudo_palette;painted_fg[39]=palette[fg];painted_bg[39]=palette[bg];
}
static void fillrect(struct fb_info *info,const struct fb_fillrect *rect) { painted_bg[38]=((u32 *)info->pseudo_palette)[rect->color]; }

int main(void) {
 u16 chars[40];memset(chars,0,sizeof(chars));
 struct consw sw={legacy_scroll};
 struct vc_data vc={.vc_rows=4,.vc_cols=10,.vc_size_row=20,.vc_screenbuf_size=80,.vc_origin=(unsigned long)chars,.vc_scr_end=(unsigned long)(chars+40),.vc_sw=&sw,.vc_font={6,12},.vc_video_erase_char=' '};
 vc.state.rgb_fg=vc.state.rgb_bg=VC_RGB_DEFAULT;
 assert(vc_rgb_alloc(&vc));
 for(int i=0;i<40;i++)assert(vc.vc_rgb[i].fg==VC_RGB_DEFAULT);
 vc.state.rgb_fg=0x193f59;vc.state.rgb_bg=0x142f27;
 vc_rgb_store(&vc,chars,40,false);
 vc.state.reverse=true;vc_rgb_store(&vc,chars+2,1,false);
 assert(vc.vc_rgb[2].fg==0x142f27 && vc.vc_rgb[2].bg==0x193f59);
 vc_rgb_invert(&vc,chars+2,1);assert(vc.vc_rgb[2].fg==0x193f59);vc.state.reverse=false;
 for(int i=0;i<40;i++) { chars[i]=i;vc.vc_rgb[i].fg=i;vc.vc_rgb[i].bg=40+i; }
 con_scroll(&vc,1,4,SM_UP,1);
 assert(chars[10]==20 && vc.vc_rgb[10].fg==20 && vc.vc_rgb[29].fg==39);
 assert(chars[30]==' ' && vc.vc_rgb[30].bg==0x142f27);
 assert(redraws==1 && legacy_scrolls==0);
 con_scroll(&vc,1,4,SM_DOWN,1);
 assert(chars[20]==20 && vc.vc_rgb[20].fg==20 && vc.vc_rgb[10].bg==0x142f27);
 vc.state.x=3;vc.vc_pos=(unsigned long)(chars+3);
 for(int i=0;i<10;i++) { chars[i]=i;vc.vc_rgb[i].fg=i; }
 insert_char(&vc,2);assert(chars[5]==3 && vc.vc_rgb[5].fg==3);
 delete_char(&vc,2);assert(chars[3]==3 && vc.vc_rgb[3].fg==3);
 struct rgb rgb;rgb_from_256(16,&rgb);assert(rgb.r==0 && rgb.g==0 && rgb.b==0);
 rgb_from_256(17,&rgb);assert(rgb.b==95);
 rgb_from_256(231,&rgb);assert(rgb.r==255 && rgb.g==255 && rgb.b==255);
 vc.vc_npar=4;vc.vc_par[1]=2;vc.vc_par[2]=25;vc.vc_par[3]=63;vc.vc_par[4]=89;
 assert(vc_t416_color(&vc,0,rgb_foreground)==4 && vc.state.rgb_fg==0x193f59);
 vc.vc_npar=2;vc.vc_par[1]=5;vc.vc_par[2]=231;
 assert(vc_t416_color(&vc,0,rgb_background)==2 && vc.state.rgb_bg==0xffffff);
 u32 palette[16],saved[16];for(int i=0;i<16;i++)palette[i]=1000+i;memcpy(saved,palette,sizeof(palette));
 struct fbcon_ops ops={putcs,cursor};struct fb_ops fbops={fillrect};
 struct fb_info info={palette,&ops,{FB_VISUAL_TRUECOLOR},{16,{11,5},{5,6},{0,5},{0,0}},&fbops};
 assert(fbcon_rgb_pixel(&info,0xff0000)==0xf800);
 assert(fbcon_rgb_pixel(&info,0x00ff00)==0x07e0);
 assert(fbcon_rgb_pixel(&info,0x0000ff)==0x001f);
 assert(fbcon_rgb_pixel(&info,0xffffff)==0xffff);
 for(unsigned c=0;c<65536;c++) {
  u32 rgb=(((c>>11)&31)<<19)|(((c>>5)&63)<<10)|((c&31)<<3);
  assert(fbcon_rgb_pixel(&info,rgb)==c);
 }
 chars[0]=(15<<8)|(14<<12);chars[1]=chars[0];chars[2]=chars[0];
 vc.vc_rgb[0]=(struct vc_rgb){0x193f59,VC_RGB_DEFAULT};
 vc.vc_rgb[1]=(struct vc_rgb){VC_RGB_DEFAULT,0x142f27};
 vc.vc_rgb[2]=(struct vc_rgb){VC_RGB_DEFAULT,VC_RGB_DEFAULT};
 assert(fbcon_rgb_putcs(&vc,&info,chars,3,0,0));
 assert(painted_fg[0]==fbcon_rgb_pixel(&info,0x193f59) && painted_bg[0]==saved[14]);
 assert(painted_fg[1]==saved[15] && painted_bg[1]==fbcon_rgb_pixel(&info,0x142f27));
 assert(painted_fg[2]==saved[15] && painted_bg[2]==saved[14]);
 assert(!memcmp(palette,saved,sizeof(palette)));
 vc.state.x=0;vc.state.y=0;fbcon_do_cursor(&vc,&info,0,chars[0]);
 assert(painted_fg[39]==fbcon_rgb_pixel(&info,0x193f59));
 assert(!memcmp(palette,saved,sizeof(palette)));
 vc.state.rgb_bg=0x142f27;assert(fbcon_rgb_clear(&vc,&info,0,0,1,10));
 assert(painted_bg[38]==fbcon_rgb_pixel(&info,0x142f27));
 assert(!memcmp(palette,saved,sizeof(palette)));
 vc_rgb_store(&vc,chars+39,100,true);
 vc_rgb_move(&vc,39,0,100);
 vc_rgb_move(&vc,40,0,100);
 vc_rgb_store(&vc,(u16 *)1,100,true);
 free(vc.vc_rgb);vc.vc_rgb=NULL;
 con_scroll(&vc,0,4,SM_UP,1);assert(legacy_scrolls==1);
 puts("PASS: RGB parsing, standard 256-color cube, all 65536 RGB565 values, scrolling, insert/delete, inversion, clipping, cursor and palette isolation");
}
