/* SPDX-License-Identifier: MIT */
#include <CoreText/CoreText.h>
#include <CoreGraphics/CoreGraphics.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
int main(void){
 CTFontRef font=CTFontCreateWithName(CFSTR("Menlo"),14,NULL);
 CGColorSpaceRef gray=CGColorSpaceCreateDeviceGray();unsigned code;
 while(scanf("%x",&code)==1){
  if(code<32||code>0x10ffff||(code>=0xd800&&code<=0xdfff))continue;
  uint32_t utf=code;CFStringRef text=CFStringCreateWithBytes(NULL,(const UInt8*)&utf,4,kCFStringEncodingUTF32LE,false);
  const void *keys[]={kCTFontAttributeName,kCTForegroundColorFromContextAttributeName};
  const void *values[]={font,kCFBooleanTrue};
  CFDictionaryRef attrs=CFDictionaryCreate(NULL,keys,values,2,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
  CFAttributedStringRef attributed=CFAttributedStringCreate(NULL,text,attrs);CTLineRef line=CTLineCreateWithAttributedString(attributed);
  unsigned char pixels[128]={0},bits[16]={0};CGContextRef ctx=CGBitmapContextCreate(pixels,8,16,8,8,gray,kCGImageAlphaNone);
  double width=CTLineGetTypographicBounds(line,NULL,NULL,NULL);CGContextSetGrayFillColor(ctx,1,1);
  CGContextTranslateCTM(ctx,0,2);if(width>8)CGContextScaleCTM(ctx,8/width,1);
  CGContextSetTextPosition(ctx,0,0);CTLineDraw(line,ctx);
  for(unsigned y=0;y<16;y++)for(unsigned x=0;x<8;x++)if(pixels[(15-y)*8+x]>=64)bits[y]|=128>>x;
  fwrite(&utf,4,1,stdout);fwrite(bits,16,1,stdout);
  CGContextRelease(ctx);CFRelease(line);CFRelease(attributed);CFRelease(attrs);CFRelease(text);
 }
 CGColorSpaceRelease(gray);CFRelease(font);return ferror(stdout)?1:0;
}
