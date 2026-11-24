/* Short queued blocks keep the river quiet when the walk is hidden. */
int pocket_scene_river_sound(void *ptr,int enabled,int cue,float river){
 struct gpu_scene *s=ptr;
 if(!s)return -1;
 if(!enabled){
  if(s->river_audio){SDL_CloseAudioDevice(s->river_audio);s->river_audio=0;}
  s->river_cue=s->river_note=0;return 0;
 }
 if(!s->river_audio){
  if(s->river_audio_failed)return -1;
  SDL_AudioSpec want;SDL_zero(want);want.freq=22050;want.format=AUDIO_S16SYS;
  want.channels=1;want.samples=1024;
  if(SDL_WasInit(SDL_INIT_AUDIO)||SDL_InitSubSystem(SDL_INIT_AUDIO)==0)s->river_audio=SDL_OpenAudioDevice(NULL,0,&want,NULL,0);
  if(!s->river_audio){s->river_audio_failed=1;return -1;}
  SDL_PauseAudioDevice(s->river_audio,0);
 }
 if(cue){s->river_cue=cue;s->river_note=0;}
 while(SDL_GetQueuedAudioSize(s->river_audio)<6144){
  int16_t samples[1024];
  for(unsigned i=0;i<1024;i++){
   s->river_seed=s->river_seed*1664525u+1013904223u;
   float noise=((int)(s->river_seed>>16)-32768)/32768.f;
   s->river_low+=.065f*(noise-s->river_low);
   float signal=river*(s->river_low*.16f+noise*.013f);
   if(s->river_cue){
    int part=s->river_note/3308;
    float t=(s->river_note%3308)/22050.f;
    const float notes[]={523.25f,659.25f,783.99f,1046.5f};
    float hz=notes[s->river_cue==4?part:(s->river_cue-1)];
    signal+=.13f*sinf(6.2831853f*hz*t)*expf(-22.f*t)*fminf(1.f,t*140.f);
    if(++s->river_note>=3308*(s->river_cue==4?4:1)){s->river_cue=0;s->river_note=0;}
   }
   samples[i]=(int16_t)(signal*32767.f);
  }
  if(SDL_QueueAudio(s->river_audio,samples,sizeof(samples))<0)return -1;
 }
 return 0;
}
