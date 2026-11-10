#include <cubeb/cubeb.h>
#include <atomic>
#include <cstdio>
#include <cstring>
#include <cstdarg>
#include <thread>
#include <chrono>
static std::atomic<unsigned> calls{0},errors{0};
static long fill(cubeb_stream*,void*,const void*,void* out,long frames){if(frames<0)return -1;std::memset(out,0,size_t(frames)*2*sizeof(short));++calls;return frames;}
static void state(cubeb_stream*,void*,cubeb_state value){if(value==CUBEB_STATE_ERROR)++errors;}
static void debug(const char* fmt,...){va_list a;va_start(a,fmt);vfprintf(stderr,fmt,a);va_end(a);}
int main(){std::setvbuf(stdout,nullptr,_IONBF,0);cubeb_set_log_callback(CUBEB_LOG_NORMAL,debug);puts("phase=context");cubeb* c=nullptr;if(cubeb_init(&c,"N810 native PCM validation","alsa")!=CUBEB_OK)return 1;
 puts("phase=context_ready");cubeb_stream_params p{};p.format=CUBEB_SAMPLE_S16LE;p.rate=44100;p.channels=2;p.layout=CUBEB_LAYOUT_STEREO;p.prefs=CUBEB_STREAM_PREF_NONE;
 cubeb_stream* s=nullptr;unsigned latency=4410;cubeb_get_min_latency(c,&p,&latency);
 puts("phase=stream_init");int r=cubeb_stream_init(c,&s,"bounded silence",nullptr,nullptr,nullptr,&p,latency,fill,state,nullptr);
 if(r){std::printf("stream_init=%d\n",r);cubeb_destroy(c);return 2;}
 puts("phase=stream_ready");if(cubeb_stream_start(s)){cubeb_stream_destroy(s);cubeb_destroy(c);return 3;}
 puts("phase=stream_started");std::this_thread::sleep_for(std::chrono::milliseconds(1200));unsigned long long position=0;uint64_t pos=0;cubeb_stream_get_position(s,&pos);position=pos;
 puts("phase=stop");int stopped=cubeb_stream_stop(s);std::printf("backend=%s callbacks=%u frames_played=%llu errors=%u stop=%d silence_only=1\n",cubeb_get_backend_id(c),calls.load(),position,errors.load(),stopped);
 cubeb_stream_destroy(s);cubeb_destroy(c);return calls.load()>0&&position>0&&!errors.load()&&!stopped?0:4;}
