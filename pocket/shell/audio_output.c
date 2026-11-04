/* Optional Mac S16LE PCM sink. No files, network, codecs, or capture. */
#include <AudioToolbox/AudioToolbox.h>
#include <stdatomic.h>
#include <errno.h>
#include <stdlib.h>
#include <unistd.h>

typedef struct { AudioQueueBufferRef buffers[3]; atomic_int free[3]; } State;
static void completed(void *opaque, AudioQueueRef queue, AudioQueueBufferRef buffer) {
    (void)queue;State *state=opaque;
    for(int i=0;i<3;i++) if(state->buffers[i]==buffer) atomic_store(&state->free[i],1);
}
int main(int argc,char **argv) {
    if(argc!=3)return 2;
    int rate=atoi(argv[1]),channels=atoi(argv[2]);
    if((rate!=8000 && rate!=16000 && rate!=32000 && rate!=44100 && rate!=48000)||(channels!=1 && channels!=2))return 2;
    AudioStreamBasicDescription format={0};format.mSampleRate=rate;format.mFormatID=kAudioFormatLinearPCM;
    format.mFormatFlags=kLinearPCMFormatFlagIsSignedInteger|kAudioFormatFlagIsPacked;
    format.mBytesPerPacket=format.mBytesPerFrame=channels*2;format.mFramesPerPacket=1;format.mChannelsPerFrame=channels;format.mBitsPerChannel=16;
    State state={0};AudioQueueRef queue;
    if(AudioQueueNewOutput(&format,completed,&state,NULL,NULL,0,&queue)!=noErr)return 3;
    int size=(rate/50)*channels*2,started=0,result=0;
    for(int i=0;i<3;i++) {
        if(AudioQueueAllocateBuffer(queue,size,&state.buffers[i])!=noErr){result=4;goto done;}
        atomic_store(&state.free[i],1);
    }
    for(int index=0;;index=(index+1)%3) {
        while(!atomic_load(&state.free[index]))usleep(2000);
        AudioQueueBufferRef buffer=state.buffers[index];int count=0;
        while(count<size) {
            ssize_t n=read(STDIN_FILENO,(char *)buffer->mAudioData+count,size-count);
            if(n<0 && errno==EINTR)continue;
            if(n<=0)goto done;
            count+=(int)n;
        }
        buffer->mAudioDataByteSize=count;atomic_store(&state.free[index],0);
        if(AudioQueueEnqueueBuffer(queue,buffer,0,NULL)!=noErr){result=5;goto done;}
        if(!started){if(AudioQueueStart(queue,NULL)!=noErr){result=6;goto done;}started=1;}
    }
done:
    AudioQueueStop(queue,true);AudioQueueDispose(queue,true);return result;
}
