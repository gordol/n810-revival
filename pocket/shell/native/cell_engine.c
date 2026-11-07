/* Optional retained opaque-text compositor. No Python API, threads or device I/O. */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <limits.h>

typedef struct { uint32_t w,h; uint32_t *glyph; uint64_t *ink; unsigned char *valid; char *output; size_t capacity,used; } Surface;
typedef struct { Surface *plane; int32_t x,y; } Layer;
typedef struct { uint64_t ink; const char *escape; } Style;
static int dimensions(uint32_t w,uint32_t h) { return w && h && w<=65535 && h<=65535 && (uint64_t)w*h<=1000000; }
void *cw_surface(uint32_t w,uint32_t h) {
    if (!dimensions(w,h)) return NULL;
    Surface *s=calloc(1,sizeof(*s)); if (!s) return NULL;
    size_t n=(size_t)w*h; s->w=w;s->h=h;
    s->glyph=calloc(n,sizeof(uint32_t));s->ink=calloc(n,sizeof(uint64_t));s->valid=calloc(n,1);
    if (!s->glyph || !s->ink || !s->valid) { free(s->glyph);free(s->ink);free(s->valid);free(s);return NULL; }
    return s;
}
void cw_free(void *ptr) { Surface *s=ptr;if(!s)return;free(s->glyph);free(s->ink);free(s->valid);free(s->output);free(s); }
size_t cw_bytes(void *ptr) { Surface *s=ptr;return sizeof(*s)+(size_t)s->w*s->h*13+s->capacity; }
int cw_set(void *ptr,uint32_t i,uint32_t glyph,uint64_t ink,int valid) {
    Surface *s=ptr;if(i>=(size_t)s->w*s->h)return -1;
    s->glyph[i]=glyph;s->ink[i]=ink;s->valid[i]=(unsigned char)!!valid;return 0;
}
int cw_get(void *ptr,uint32_t i,uint32_t *glyph,uint64_t *ink) {
    Surface *s=ptr;if(i>=(size_t)s->w*s->h)return -1;
    *glyph=s->glyph[i];*ink=s->ink[i];return s->valid[i];
}
/* Input is trusted Python-encoded UTF-8; still reject malformed input/bounds. */
int cw_row(void *ptr,uint32_t row,const unsigned char *text,size_t bytes,uint64_t ink) {
    Surface *s=ptr;if(row>=s->h)return -1;
    size_t base=(size_t)row*s->w,pos=0;uint32_t x=0;
    while(pos<bytes && x<s->w) {
        uint32_t ch=text[pos++];unsigned tail=0;
        if(ch>=0xc2 && ch<=0xdf){ch&=31;tail=1;}
        else if(ch>=0xe0 && ch<=0xef){ch&=15;tail=2;}
        else if(ch>=0xf0 && ch<=0xf4){ch&=7;tail=3;}
        else if(ch>=128)return -1;
        if(pos+tail>bytes)return -1;
        for(unsigned j=0;j<tail;j++){if((text[pos]&0xc0)!=0x80)return -1;ch=(ch<<6)|(text[pos++]&63);}
        if(ch>0x10ffff || (ch>=0xd800 && ch<=0xdfff) || (tail==1 && ch<128) || (tail==2 && ch<2048) || (tail==3 && ch<65536))return -1;
        s->glyph[base+x]=ch;s->ink[base+x]=ink;s->valid[base+x]=1;x++;
    }
    for(;x<s->w;x++){s->glyph[base+x]=32;s->ink[base+x]=ink;s->valid[base+x]=1;}
    return 0;
}
int cw_style(void *ptr,uint32_t row,uint32_t start,uint32_t end,uint64_t ink) {
    Surface *s=ptr;if(row>=s->h || start>end || end>s->w)return -1;
    for(uint32_t x=start;x<end;x++){s->ink[(size_t)row*s->w+x]=ink;}
    return 0;
}
static int append(Surface *s,const char *text,size_t n) {
    if(n>SIZE_MAX-s->used-1)return -1;
    size_t need=s->used+n+1;
    if(need>s->capacity){size_t cap=s->capacity?s->capacity:256;while(cap<need){if(cap>SIZE_MAX/2)return -1;cap*=2;}char *p=realloc(s->output,cap);if(!p)return -1;s->output=p;s->capacity=cap;}
    memcpy(s->output+s->used,text,n);s->used+=n;s->output[s->used]=0;return 0;
}
static int emit_glyph(Surface *s,uint32_t ch){
    char b[4];size_t n;
    if(ch<128){b[0]=(char)ch;n=1;}else if(ch<2048){b[0]=(char)(0xc0|(ch>>6));b[1]=(char)(0x80|(ch&63));n=2;}
    else if(ch<65536){b[0]=(char)(0xe0|(ch>>12));b[1]=(char)(0x80|((ch>>6)&63));b[2]=(char)(0x80|(ch&63));n=3;}
    else {b[0]=(char)(0xf0|(ch>>18));b[1]=(char)(0x80|((ch>>12)&63));b[2]=(char)(0x80|((ch>>6)&63));b[3]=(char)(0x80|(ch&63));n=4;}
    return append(s,b,n);
}
#define CW_FRAME_INK (UINT64_C(1)<<49)
#define CW_FRAME_TINTED (UINT64_C(1)<<52)
#define CW_FRAME_DEFERRED (UINT64_C(1)<<55)
#define CW_FRAME_ROLE(c) (((c)>>50)&3)
static inline int cw_ink_valid(uint64_t color) {
    if(color<(UINT64_C(1)<<49))return 1;
    uint64_t allowed=((UINT64_C(1)<<48)-1)|(UINT64_C(1)<<48)|CW_FRAME_INK|(UINT64_C(3)<<50)|CW_FRAME_TINTED|CW_FRAME_DEFERRED;
    return (color&CW_FRAME_INK) && (color&(UINT64_C(1)<<48)) && (CW_FRAME_ROLE(color)==1 || CW_FRAME_ROLE(color)==2) && !(color&~allowed);
}
static unsigned cw_even(double value) {
    unsigned n=(unsigned)value;double tail=value-n;
    return n+(tail>.5 || (tail==.5 && (n&1)));
}
static unsigned cw_channel(double value,unsigned levels) {
    return cw_even(cw_even(value*levels/255.)*255./levels);
}
static uint64_t cw_frame_background(uint32_t glyph,uint64_t under,uint64_t frame) {
    double channels[3];
    if(under>=(UINT64_C(1)<<48)) {
        for(unsigned j=0;j<3;j++) {
            unsigned shift=16-j*8,a=(unsigned)((under>>(shift+24))&255),b=(unsigned)((under>>shift)&255);
            channels[j]=glyph==0x2584 || glyph==0x2580 ? (a+b)/2. : glyph==0x2588 ? a : b;
        }
    } else {
        double value=under==14 ? 8 : under>=4 && (frame&CW_FRAME_TINTED) ? 10 : 18;
        channels[0]=channels[1]=channels[2]=value;
    }
    return ((uint64_t)cw_channel(channels[0],31)<<16)|((uint64_t)cw_channel(channels[1],63)<<8)|cw_channel(channels[2],31);
}
static uint64_t cw_frame_resolve(uint64_t frame,uint32_t glyph,uint64_t under) {
    return (frame&~(CW_FRAME_DEFERRED|UINT64_C(0xffffff)))|cw_frame_background(glyph,under,frame);
}
/* Only deferred chrome consults lower layers. Ordinary opaque pixels retain
   the first-hit path; blank chrome exposes the complete underlying cell. */
static void cw_source(const Layer *layers,size_t nl,uint32_t x,uint32_t y,uint32_t *glyph,uint64_t *ink) {
    *glyph=32;*ink=13;
    for(size_t j=0;j<nl;j++) {
        Surface *p=layers[j].plane;int64_t xx=(int64_t)x-layers[j].x,yy=(int64_t)y-layers[j].y;
        if(xx<0 || yy<0 || xx>=p->w || yy>=p->h)continue;
        size_t at=(size_t)yy*p->w+(size_t)xx;
        if(!p->valid[at])continue;
        if(!(p->ink[at]&CW_FRAME_DEFERRED)){*glyph=p->glyph[at];*ink=p->ink[at];return;}
        /* Bottom-to-top only for this frame pixel, avoiding recursive scans. */
        for(size_t k=nl;k-->j;) {
            p=layers[k].plane;xx=(int64_t)x-layers[k].x;yy=(int64_t)y-layers[k].y;
            if(xx<0 || yy<0 || xx>=p->w || yy>=p->h)continue;
            at=(size_t)yy*p->w+(size_t)xx;if(!p->valid[at])continue;uint32_t g=p->glyph[at];uint64_t c=p->ink[at];
            if(c&CW_FRAME_DEFERRED) {
                if(g==32)continue;
                c=cw_frame_resolve(c,*glyph,*ink);
            }
            *glyph=g;*ink=c;
        }
        return;
    }
}
static uint32_t cw_mapped_glyph(uint32_t glyph,const uint32_t *map,size_t count) {
    size_t low=0,high=count;
    while(low<high){size_t middle=(low+high)/2;if(map[middle*2]<glyph)low=middle+1;else high=middle;}
    return low<count && map[low*2]==glyph ? map[low*2+1] : glyph;
}
/* RGB channels are bounded bytes; avoid printf's general format parser for
   every colored cell. */
static char *cw_decimal_byte(char *out,unsigned value) {
    if(value>=100){*out++=(char)('0'+value/100);value%=100;*out++=(char)('0'+value/10);}
    else if(value>=10)*out++=(char)('0'+value/10);
    *out++=(char)('0'+value%10);return out;
}
static char *cw_rgb_triplet(char *out,uint64_t ink,unsigned shift) {
    out=cw_decimal_byte(out,(unsigned)((ink>>(shift+16))&255));*out++=';';
    out=cw_decimal_byte(out,(unsigned)((ink>>(shift+8))&255));*out++=';';
    return cw_decimal_byte(out,(unsigned)((ink>>shift)&255));
}
/* Layers topmost first. Dirty indices strictly increasing. One bounded batch.
   Reserve/validate before mutating front, so errors leave the prior frame intact. */
int cw_flush_mapped(void *ptr,const Layer *layers,size_t nl,const uint32_t *dirty,size_t nd,
             const Style *styles,size_t ns,int32_t ox,int32_t oy,size_t *changed,const uint32_t *map,size_t nm) {
    Surface *s=ptr;size_t n=(size_t)s->w*s->h;
    for(size_t k=0;k<nd;k++)if(dirty[k]>=n || (k && dirty[k]<=dirty[k-1]))return -1;
    for(size_t k=0;k<nl;k++)if(!layers[k].plane)return -1;
    /* Every source color must have an escape; validated at the Python boundary. */
    s->used=0;*changed=0;
    if(append(s,"",0))return -1;
    size_t cursor=SIZE_MAX;uint64_t last=0;int has_last=0,last_rgb=0;
    for(size_t k=0;k<nd;k++){
        uint32_t i=dirty[k],x=i%s->w,y=i/s->w,glyph=32;uint64_t ink=13;
        cw_source(layers,nl,x,y,&glyph,&ink);
        glyph=cw_mapped_glyph(glyph,map,nm);
        if(s->valid[i] && s->glyph[i]==glyph && s->ink[i]==ink)continue;
        if(i!=cursor || !x){
            char b[64];int len=snprintf(b,sizeof(b),"\033[%lld;%lldH",(long long)y+oy+1,(long long)x+ox+1);
            if(len<0 || (size_t)len>=sizeof(b))return -1;
            /* A same-row gap cannot cross the terminal's pending wrap state.
               Batch starts and row changes still establish an absolute cursor. */
            if(cursor!=SIZE_MAX && cursor%s->w && cursor/s->w==y && x && i>cursor){
                char relative[32];size_t gap=i-cursor;
                int r=gap==1 ? snprintf(relative,sizeof(relative),"\033[C") : snprintf(relative,sizeof(relative),"\033[%zuC",gap);
                if(r>0 && r<len && (size_t)r<sizeof(relative)){memcpy(b,relative,(size_t)r);len=r;}
            }
            if(append(s,b,(size_t)len))return -1;
        }
        if(!has_last || ink!=last){
            const char *escape=NULL;char rgb[128];int current_rgb=0;
            for(size_t j=0;j<ns;j++)if(styles[j].ink==ink){escape=styles[j].escape;break;}
            if(!escape && (ink&CW_FRAME_INK)) {
                const char *palette=NULL;
                for(size_t j=0;j<ns;j++)if(styles[j].ink==CW_FRAME_ROLE(ink)){palette=styles[j].escape;break;}
                const char *bg_start=palette ? strstr(palette,";48;") : NULL;
                if(!bg_start || append(s,palette,(size_t)(bg_start-palette)))return -1;
                char *p=rgb;memcpy(p,";48;2;",6);p+=6;
                p=cw_rgb_triplet(p,ink,0);*p++='m';*p=0;
                escape=rgb;
            }
            if(!escape && ink>=UINT64_C(0x1000000000000) && ink<UINT64_C(0x2000000000000)){
                /* State is local to this batch: arbitrary panel writes and
                   styled UI text require a fresh reset and both components.
                   Consecutive plain RGB cells only change differing colours. */
                char *p=rgb;*p++='\033';*p++='[';
                if(!last_rgb){*p++='0';*p++=';';}
                int fg=!last_rgb || ((ink^last)&UINT64_C(0xffffff000000));
                int bg=!last_rgb || ((ink^last)&UINT64_C(0xffffff));
                if(fg){memcpy(p,"38;2;",5);p+=5;p=cw_rgb_triplet(p,ink,24);}
                if(bg){if(fg)*p++=';';memcpy(p,"48;2;",5);p+=5;p=cw_rgb_triplet(p,ink,0);}
                *p++='m';*p=0;current_rgb=1;
                escape=rgb;
            }
            if(!escape || append(s,escape,strlen(escape)))return -1;
            last=ink;has_last=1;last_rgb=current_rgb;
        }
        if(emit_glyph(s,glyph))return -1;
        cursor=(size_t)i+1;(*changed)++;
    }
    /* Commit only after serialization succeeded, without a second full plane. */
    for(size_t k=0;k<nd;k++){
        uint32_t i=dirty[k],x=i%s->w,y=i/s->w,glyph=32;uint64_t ink=13;
        cw_source(layers,nl,x,y,&glyph,&ink);
        glyph=cw_mapped_glyph(glyph,map,nm);
        s->glyph[i]=glyph;s->ink[i]=ink;s->valid[i]=1;
    }
    return 0;
}
/* Compose retained cells without allocating or encoding terminal output.
 * All fallible batch validation precedes the single update pass. */
int cw_compose_mapped(void *ptr,const Layer *layers,size_t nl,const uint32_t *dirty,size_t nd,
                     size_t *changed,const uint32_t *map,size_t nm) {
    Surface *s=ptr;size_t n=(size_t)s->w*s->h;
    for(size_t k=0;k<nd;k++)if(dirty[k]>=n || (k && dirty[k]<=dirty[k-1]))return -1;
    for(size_t k=0;k<nl;k++)if(!layers[k].plane)return -1;
    s->used=0;*changed=0;
    for(size_t k=0;k<nd;k++){
        uint32_t i=dirty[k],glyph=32;uint64_t ink=13;
        cw_source(layers,nl,i%s->w,i/s->w,&glyph,&ink);
        glyph=cw_mapped_glyph(glyph,map,nm);
        if(!s->valid[i] || s->glyph[i]!=glyph || s->ink[i]!=ink)(*changed)++;
        s->glyph[i]=glyph;s->ink[i]=ink;s->valid[i]=1;
    }
    return 0;
}
int cw_flush(void *ptr,const Layer *layers,size_t nl,const uint32_t *dirty,size_t nd,
             const Style *styles,size_t ns,int32_t ox,int32_t oy,size_t *changed) {
    return cw_flush_mapped(ptr,layers,nl,dirty,nd,styles,ns,ox,oy,changed,NULL,0);
}
const char *cw_output(void *ptr){return ((Surface*)ptr)->output;}
size_t cw_output_size(void *ptr){return ((Surface*)ptr)->used;}
uint32_t cw_abi(void){return 1;}
