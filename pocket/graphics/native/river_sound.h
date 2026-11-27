/* SDL calls the mixer independently of rendering and terrain preparation. */
static float animal_call(int voice,int sample,float noise){
 /* Repeated notes with rounded attacks. The crow has a noisy harmonic edge,
    the owl a low sustained vowel, the small mammals short rising chips. */
 const float spacing[]={0,.43f,.51f,.29f,.17f};
 const float duration[]={0,.26f,.35f,.17f,.075f};
 float t=fmodf(sample/22050.f,spacing[voice]),length=duration[voice];
 if(t>=length)return 0;
 float env=sinf(3.141593f*t/length);
 float base=voice==1?660.f:voice==2?340.f:voice==3?2200.f:3100.f;
 float glide=voice==1?-440.f:voice==2?-85.f:voice==3?1250.f:2100.f;
 float phase=6.2831853f*(base*t+.5f*glide*t*t);
 float note=sinf(phase);
 if(voice==1)note=.60f*note+.26f*sinf(phase*2)+.14f*noise;
 return env*env*note*fminf(1.f,(22050-sample)/882.f);
}

static void SDLCALL mix_walk_sound(void *ptr,Uint8 *stream,int bytes){
 struct gpu_scene *s=ptr;
 int16_t *samples=(int16_t *)stream;
 float river=s->river_level,gain=s->animal_gain,wind=s->wind_level,skis=s->ski_level;
 for(int i=0;i<bytes/(int)sizeof(*samples);i++){
  s->river_seed=s->river_seed*1664525u+1013904223u;
  float noise=((int)(s->river_seed>>16)-32768)/32768.f;
  s->river_low+=.065f*(noise-s->river_low);
  float signal=river*(s->river_low*.40f+noise*.0325f);
  if(wind>0.f){
   s->wind_low+=.024f*(noise-s->wind_low);
   s->wind_gust+=.00010f*(noise-s->wind_gust);
   float gust=.65f+fminf(.7f,55.f*fabsf(s->wind_gust));
   signal+=wind*gust*(.85f*s->wind_low+.19f*s->river_low);
   s->snow_gain+=.0025f*(skis-s->snow_gain);
   signal+=s->snow_gain*(.17f*(noise-s->river_low)+.38f*s->river_low);
   signal+=s->landing_env*(1.6f*s->river_low+.08f*noise);
   s->landing_env*=.9993f;
  }
  if(s->animal_voice){
   signal+=.24f*gain*animal_call(s->animal_voice,s->animal_sample,noise);
   if(++s->animal_sample>=22050)s->animal_voice=0;
  }
  if(s->river_cue){
   int part=s->river_note/3308;
   float t=(s->river_note%3308)/22050.f;
   const float notes[]={523.25f,659.25f,783.99f,1046.5f};
   float hz=notes[s->river_cue==4?part:(s->river_cue-1)];
   signal+=.13f*sinf(6.2831853f*hz*t)*expf(-22.f*t)*fminf(1.f,t*140.f);
   if(++s->river_note>=3308*(s->river_cue==4?4:1)){s->river_cue=0;s->river_note=0;}
  }
  samples[i]=(int16_t)(fmaxf(-1.f,fminf(1.f,signal))*32767.f);
 }
}

static int walk_sound(void *ptr,int enabled,int cue,float river,int voice,float gain,
                      float wind,float skis,int landed){
 struct gpu_scene *s=ptr;
 if(!s)return -1;
 if(!enabled){
  if(s->river_audio){SDL_CloseAudioDevice(s->river_audio);s->river_audio=0;}
  s->river_cue=s->river_note=s->animal_voice=0;
  s->wind_low=s->wind_gust=s->snow_gain=s->landing_env=0.f;return 0;
 }
 int opening=!s->river_audio;
 if(opening){
  if(s->river_audio_failed)return -1;
  SDL_AudioSpec want;SDL_zero(want);want.freq=22050;want.format=AUDIO_S16SYS;
  want.channels=1;want.samples=1024;want.callback=mix_walk_sound;want.userdata=s;
  if(SDL_WasInit(SDL_INIT_AUDIO)||SDL_InitSubSystem(SDL_INIT_AUDIO)==0)s->river_audio=SDL_OpenAudioDevice(NULL,0,&want,NULL,0);
  if(!s->river_audio){s->river_audio_failed=1;return -1;}
 }
 SDL_LockAudioDevice(s->river_audio);
 s->river_level=river;s->animal_gain=gain;s->wind_level=wind;s->ski_level=skis;
 if(voice>=1&&voice<=4){s->animal_voice=voice;s->animal_sample=0;}
 if(landed)s->landing_env=1.f;
 if(cue>=1&&cue<=4){s->river_cue=cue;s->river_note=0;}
 SDL_UnlockAudioDevice(s->river_audio);
 if(opening)SDL_PauseAudioDevice(s->river_audio,0);
 return 0;
}

int pocket_scene_river_sound(void *ptr,int enabled,int cue,float river,int voice,float gain){
 return walk_sound(ptr,enabled,cue,river,voice,gain,0.f,0.f,0);
}

int pocket_scene_summit_sound(void *ptr,int enabled,float wind,float skis,int landed){
 return walk_sound(ptr,enabled,0,0.f,0,0.f,wind,skis,landed);
}
