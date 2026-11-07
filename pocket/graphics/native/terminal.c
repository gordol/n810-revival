/* SPDX-License-Identifier: MIT */
#include <stdio.h>
struct terminal {void *renderer;const uint32_t *codes;const unsigned char *font;unsigned fonts;
 unsigned x,y,sx,sy,fg,bg,bold,inverse,mode,n,utf,need,top,bottom,missing,sync;char seq[256],reply[512];uint32_t chars[3000];};
static unsigned term_palette(unsigned n){
 static const unsigned base[]={0x000000,0xcd0000,0x00cd00,0xcdcd00,0x0000ee,0xcd00cd,0x00cdcd,0xe5e5e5,0x7f7f7f,0xff0000,0x00ff00,0xffff00,0x5c5cff,0xff00ff,0x00ffff,0xffffff};
 if(n<16)return base[n];
 if(n<232){n-=16;unsigned a[]={0,95,135,175,215,255};return (a[n/36]<<16)|(a[(n/6)%6]<<8)|a[n%6];}return (8+10*(n-232))*0x010101;
}
static unsigned term_pack(unsigned rgb){return ((rgb>>8)&0xf800)|((rgb>>5)&0x7e0)|((rgb>>3)&31);}
static void term_cell(struct terminal *t,unsigned x,unsigned y,unsigned ch){
 if(x>=100||y>=30)return;
 int g=find_glyph(t->codes,t->fonts,ch);
 if(g<0){g=find_glyph(t->codes,t->fonts,'?');t->missing++;}if(g<0)return;
 unsigned fg=term_pack(t->fg),bg=term_pack(t->bg);if(t->inverse){unsigned a=fg;fg=bg;bg=a;}
 unsigned char bits[16];memcpy(bits,t->font+g*16,16);
 if(t->bold)for(unsigned i=0;i<16;i++)bits[i]|=bits[i]>>1;
 pocket_mbx_stage(t->renderer,y*100+x,bits,fg,bg);t->chars[y*100+x]=ch;
}
static void term_clear(struct terminal *t,unsigned first,unsigned end){for(unsigned i=first;i<end&&i<3000;i++)term_cell(t,i%100,i/100,' ');}
static void term_scroll(struct terminal *t){
 struct renderer *r=t->renderer;
 for(unsigned y=t->top;y<t->bottom;y++)for(unsigned x=0;x<100;x++){
  r->cells[y*100+x]=r->cells[(y+1)*100+x];r->cells[y*100+x].dirty=1;t->chars[y*100+x]=t->chars[(y+1)*100+x];
 }
 term_clear(t,t->bottom*100,(t->bottom+1)*100);
}
static void term_put(struct terminal *t,unsigned ch){
 if(ch=='\r'){t->x=0;return;}if(ch=='\n'){if(t->y==t->bottom)term_scroll(t);else if(t->y<29)t->y++;return;}
 if(ch=='\b'){if(t->x)t->x--;return;}if(ch=='\t'){t->x=(t->x+8)&~7u;if(t->x>99)t->x=99;return;}
 if(ch<32||ch==127)return;
 if(t->x>=100){t->x=0;if(t->y==t->bottom)term_scroll(t);else if(t->y<29)t->y++;}
 term_cell(t,t->x++,t->y,ch);
}
static void term_reply(struct terminal *t,const char *s){size_t used=strlen(t->reply),n=strlen(s);if(used+n<sizeof(t->reply))memcpy(t->reply+used,s,n+1);}
static void term_csi(struct terminal *t,unsigned final){
 if(final=='u'&&t->n&&t->seq[0]=='?'){term_reply(t,"\033[?27u");return;}
 if(final=='u'&&t->n&&(t->seq[0]=='>'||t->seq[0]=='<'||t->seq[0]=='='))return;
 if(final=='c'){term_reply(t,"\033[?1;2c");return;}
 unsigned a[64]={0},count=1;int private=t->seq[0]=='?';
 for(unsigned i=private?1:0;i<t->n;i++){
  unsigned c=(unsigned char)t->seq[i];if(c>='0'&&c<='9'){if(a[count-1]<100000)a[count-1]=a[count-1]*10+c-'0';}
  else if(c==';'||c==':'){if(count<64)count++;}
 }
 if(private&&a[0]==2026&&(final=='h'||final=='l')){t->sync=final=='h';return;}
 unsigned n=a[0]?a[0]:1;
 if(final=='H'||final=='f'){t->y=(a[0]?a[0]-1:0);t->x=(count>1&&a[1]?a[1]-1:0);}
 else if(final=='A')t->y=t->y>n?t->y-n:0;
 else if(final=='B')t->y+=n;
 else if(final=='C')t->x+=n;
 else if(final=='D')t->x=t->x>n?t->x-n:0;
 else if(final=='G')t->x=n-1;
 else if(final=='d')t->y=n-1;
 else if(final=='s'){t->sx=t->x;t->sy=t->y;}
 else if(final=='u'){t->x=t->sx;t->y=t->sy;}
 else if(final=='r'){t->top=a[0]?a[0]-1:0;t->bottom=count>1&&a[1]?a[1]-1:29;if(t->top>=t->bottom||t->bottom>29){t->top=0;t->bottom=29;}t->x=t->y=0;}
 else if(final=='J'){unsigned p=t->y*100+(t->x<100?t->x:99);if(a[0]==2||a[0]==3)term_clear(t,0,3000);else if(a[0]==1)term_clear(t,0,p+1);else term_clear(t,p,3000);}
 else if(final=='K'){unsigned p=t->y*100+(t->x<100?t->x:99);if(a[0]==2)term_clear(t,t->y*100,(t->y+1)*100);else if(a[0]==1)term_clear(t,t->y*100,p+1);else term_clear(t,p,(t->y+1)*100);}
 else if(final=='m'&&!private)for(unsigned i=0;i<count;i++){
  unsigned c=a[i];if(!c){t->fg=0xe5e5e5;t->bg=0;t->bold=t->inverse=0;}
  else if(c==1)t->bold=1;else if(c==22)t->bold=0;else if(c==7)t->inverse=1;else if(c==27)t->inverse=0;
  else if(c==39)t->fg=0xe5e5e5;else if(c==49)t->bg=0;
  else if((c>=30&&c<=37)||(c>=90&&c<=97))t->fg=term_palette(c>=90?c-90+8:c-30);
  else if((c>=40&&c<=47)||(c>=100&&c<=107))t->bg=term_palette(c>=100?c-100+8:c-40);
  else if((c==38||c==48)&&i+2<count){unsigned rgb=0;
   if(a[i+1]==5){rgb=term_palette(a[i+2]&255);i+=2;}
   else if(a[i+1]==2&&i+4<count){rgb=((a[i+2]&255)<<16)|((a[i+3]&255)<<8)|(a[i+4]&255);i+=4;}
   else continue;
   if(c==38)t->fg=rgb;else t->bg=rgb;
  }
 }
 if(t->x>100)t->x=100;
 if(t->y>29)t->y=29;
}
void *pocket_term_open(void *renderer,const uint32_t *codes,const unsigned char *font,unsigned count){
 if(!renderer||!codes||!font||!count)return NULL;
 struct terminal *t=calloc(1,sizeof(*t));if(!t)return NULL;
 t->renderer=renderer;t->codes=codes;t->font=font;t->fonts=count;t->fg=0xe5e5e5;t->bottom=29;term_clear(t,0,3000);return t;
}
const char *pocket_term_reply(void *p){return ((struct terminal*)p)->reply;}
void pocket_term_reply_clear(void *p){((struct terminal*)p)->reply[0]=0;}
void pocket_term_close(void *p){free(p);}
unsigned pocket_term_sync(void *p){return ((struct terminal*)p)->sync;}
unsigned pocket_term_missing(void *p){return ((struct terminal*)p)->missing;}
unsigned pocket_term_char(void *p,unsigned index){return index<3000?((struct terminal*)p)->chars[index]:0;}
int pocket_term_feed(void *ptr,const unsigned char *data,size_t size){
 struct terminal *t=ptr;if(!t||(!data&&size)||size>1048576)return -1;
 for(size_t i=0;i<size;i++){unsigned c=data[i];
  if(t->mode==3){if(c==7)t->mode=0;else if(c==27)t->mode=4;continue;}
  if(t->mode==4){t->mode=c=='\\'?0:3;continue;}
  if(t->mode==1){t->mode=0;if(c=='['){t->mode=2;t->n=0;}else if(c==']'||c=='P'||c=='_'||c=='^')t->mode=3;else if(c=='7'){t->sx=t->x;t->sy=t->y;}else if(c=='8'){t->x=t->sx;t->y=t->sy;}else if(c=='('||c==')')t->mode=5;continue;}
  if(t->mode==5){t->mode=0;continue;}
  if(t->mode==2){if(c>=0x40&&c<=0x7e){term_csi(t,c);t->mode=0;}else if(t->n<sizeof(t->seq))t->seq[t->n++]=(char)c;else t->mode=0;continue;}
  if(c==27){t->mode=1;t->need=0;continue;}
  if(t->need){if((c&0xc0)==0x80){t->utf=(t->utf<<6)|(c&63);if(!--t->need)term_put(t,t->utf);continue;}t->need=0;}
  if(c<128)term_put(t,c);else if(c>=0xc2&&c<0xe0){t->utf=c&31;t->need=1;}else if(c<0xf0){t->utf=c&15;t->need=2;}else if(c<0xf5){t->utf=c&7;t->need=3;}
 }
 return 0;
}
