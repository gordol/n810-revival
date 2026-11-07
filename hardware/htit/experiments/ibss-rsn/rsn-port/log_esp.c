// Bounded protocol diagnostics. Never emit hexdumps, including decrypted KDEs.
#include "utils/includes.h"
#include "utils/common.h"
int wpa_debug_level=2,wpa_debug_show_keys=0,wpa_debug_timestamp=0;
static void log_message(int level,const char* format,va_list args){
 if(level<wpa_debug_level)return;
 char line[256];vsnprintf(line,sizeof(line),format,args);printf("RSN: %s\n",line);
}
void wpa_printf(int level,const char* fmt,...){va_list args;va_start(args,fmt);log_message(level,fmt,args);va_end(args);}
void wpa_msg(void* ctx,int level,const char* fmt,...){(void)ctx;va_list args;va_start(args,fmt);log_message(level,fmt,args);va_end(args);}
void wpa_msg_ctrl(void* ctx,int level,const char* fmt,...){(void)ctx;(void)level;(void)fmt;}
void wpa_hexdump(int level,const char* title,const void* buf,size_t n){(void)level;(void)title;(void)buf;(void)n;}
void wpa_hexdump_key(int level,const char* title,const void* buf,size_t n){(void)level;(void)title;(void)buf;(void)n;}
void wpa_hexdump_ascii(int level,const char* title,const void* buf,size_t n){(void)level;(void)title;(void)buf;(void)n;}
void wpa_hexdump_ascii_key(int level,const char* title,const void* buf,size_t n){(void)level;(void)title;(void)buf;(void)n;}
