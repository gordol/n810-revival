/* Read input without the Python GIL. No mapping, gesture policy or device writes. */
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <pthread.h>
#include <unistd.h>
#define INPUT_RECORDS 4096u
#define INPUT_BATCH 256u
typedef struct {
    int fd, wake[2], stop[2], error, closed;
    size_t unit, capacity, head, used;
    unsigned long losses, reads;
    unsigned char *data;
    pthread_t thread;
    pthread_mutex_t lock;
} InputPump;
static const char *input_capsule="pocket.input.pump.v1";
static void input_notify(InputPump *p){unsigned char b=1;ssize_t n=write(p->wake[1],&b,1);(void)n;}
static void *input_run(void *arg){
    InputPump *p=arg;unsigned char block[24*INPUT_BATCH];
    struct pollfd fds[2]={{p->fd,POLLIN,0},{p->stop[0],POLLIN,0}};
    for(;;){
        int rc=poll(fds,2,-1);
        if(rc<0&&errno==EINTR)continue;
        if(rc>=0&&fds[1].revents)break;
        int error=rc<0?errno:0;
        pthread_mutex_lock(&p->lock);
        ssize_t n=error?-1:read(p->fd,block,p->unit*INPUT_BATCH);
        if(n<0&&!error&&(errno==EINTR||errno==EAGAIN)){pthread_mutex_unlock(&p->lock);continue;}
        if(n<=0&&!error)error=n==0?ENODEV:errno;
        if(n>0&&(size_t)n%p->unit)error=EPROTO;
        if(error){p->error=error;input_notify(p);pthread_mutex_unlock(&p->lock);break;}
        p->reads++;
        if(p->used+(size_t)n>p->capacity){p->head=0;p->used=0;p->losses++;}
        int notify=p->used==0;
        size_t tail=(p->head+p->used)%p->capacity;
        size_t first=p->capacity-tail;if(first>(size_t)n)first=(size_t)n;
        memcpy(p->data+tail,block,first);memcpy(p->data,block+first,(size_t)n-first);
        p->used+=(size_t)n;
        if(notify)input_notify(p);
        pthread_mutex_unlock(&p->lock);
    }
    return NULL;
}
static void input_close_internal(InputPump *p){
    if(p->closed)return;
    p->closed=1;
    unsigned char b=1;ssize_t n=write(p->stop[1],&b,1);(void)n;
    Py_BEGIN_ALLOW_THREADS
    pthread_join(p->thread,NULL);
    Py_END_ALLOW_THREADS
    close(p->fd);close(p->wake[0]);close(p->wake[1]);close(p->stop[0]);close(p->stop[1]);
}
static void input_dispose(PyObject *o){
    InputPump *p=PyCapsule_GetPointer(o,input_capsule);
    if(!p){PyErr_Clear();return;}
    input_close_internal(p);pthread_mutex_destroy(&p->lock);free(p->data);free(p);
}
static int input_pipe(int fds[2]){
    if(pipe(fds))return -1;
    for(int i=0;i<2;i++){
        if(fcntl(fds[i],F_SETFD,FD_CLOEXEC)<0||fcntl(fds[i],F_SETFL,O_NONBLOCK)<0){
            int error=errno;close(fds[0]);close(fds[1]);fds[0]=fds[1]=-1;errno=error;return -1;
        }
    }
    return 0;
}
static PyObject *input_start(PyObject *self,PyObject *args){
    (void)self;int fd,unit;
    if(!PyArg_ParseTuple(args,"ii",&fd,&unit))return NULL;
    if(unit!=16&&unit!=24){PyErr_SetString(PyExc_ValueError,"input record size");return NULL;}
    int flags=fcntl(fd,F_GETFL);
    if(flags<0)return PyErr_SetFromErrno(PyExc_OSError);
    if(!(flags&O_NONBLOCK)){PyErr_SetString(PyExc_ValueError,"input fd must be nonblocking");return NULL;}
    InputPump *p=calloc(1,sizeof(*p));if(!p)return PyErr_NoMemory();
    p->fd=-1;p->wake[0]=p->wake[1]=p->stop[0]=p->stop[1]=-1;
    p->unit=(size_t)unit;p->capacity=INPUT_RECORDS*p->unit;p->data=calloc(1,p->capacity);
    if(!p->data){free(p);return PyErr_NoMemory();}
    p->fd=fcntl(fd,F_DUPFD_CLOEXEC,0);
    int error=0,mutex_ready=0;
    if(p->fd<0||input_pipe(p->wake)||input_pipe(p->stop)){error=errno;goto fail;}
    error=pthread_mutex_init(&p->lock,NULL);if(error)goto fail;mutex_ready=1;
    error=pthread_create(&p->thread,NULL,input_run,p);if(error)goto fail;
    PyObject *result=PyCapsule_New(p,input_capsule,input_dispose);
    if(!result){input_close_internal(p);pthread_mutex_destroy(&p->lock);free(p->data);free(p);}
    return result;
fail:
    if(mutex_ready)pthread_mutex_destroy(&p->lock);
    if(p->fd>=0)close(p->fd);
    for(int i=0;i<2;i++){if(p->wake[i]>=0)close(p->wake[i]);if(p->stop[i]>=0)close(p->stop[i]);}
    free(p->data);free(p);errno=error;return PyErr_SetFromErrno(PyExc_OSError);
}
static InputPump *input_get(PyObject *o){
    InputPump *p=PyCapsule_GetPointer(o,input_capsule);
    if(p&&p->closed){PyErr_SetString(PyExc_ValueError,"input pump closed");return NULL;}return p;
}
static PyObject *input_fileno(PyObject *self,PyObject *o){(void)self;InputPump *p=input_get(o);return p?PyLong_FromLong(p->wake[0]):NULL;}
static PyObject *input_read(PyObject *self,PyObject *o){
    (void)self;InputPump *p=input_get(o);if(!p)return NULL;
    unsigned char block[24*INPUT_BATCH],signals[64];size_t n;int error;unsigned long losses,reads;
    pthread_mutex_lock(&p->lock);
    while(read(p->wake[0],signals,sizeof(signals))>0){}
    n=p->used;if(n>p->unit*INPUT_BATCH)n=p->unit*INPUT_BATCH;
    size_t first=p->capacity-p->head;if(first>n)first=n;
    memcpy(block,p->data+p->head,first);memcpy(block+first,p->data,n-first);
    p->head=(p->head+n)%p->capacity;p->used-=n;
    losses=p->losses;p->losses=0;reads=p->reads;error=p->error;
    if(p->used||error)input_notify(p);
    pthread_mutex_unlock(&p->lock);
    if(!n&&error){errno=error;return PyErr_SetFromErrno(PyExc_OSError);}
    return Py_BuildValue("y#kk",block,(Py_ssize_t)n,losses,reads);
}
static PyObject *input_close(PyObject *self,PyObject *o){
    (void)self;InputPump *p=PyCapsule_GetPointer(o,input_capsule);if(!p)return NULL;
    input_close_internal(p);Py_RETURN_NONE;
}

static PyObject *input_discard(PyObject *self,PyObject *o){
    (void)self;InputPump *p=input_get(o);if(!p)return NULL;
    unsigned char block[24*INPUT_BATCH],signals[64];
    pthread_mutex_lock(&p->lock);
    p->head=0;p->used=0;
    /* Clear the pre-resync backlog, bounded even for a continuously busy fd. */
    for(unsigned i=0;i<16;i++){
        ssize_t n=read(p->fd,block,p->unit*INPUT_BATCH);
        if(n<0&&(errno==EAGAIN||errno==EINTR))break;
        if(n<=0){p->error=n==0?ENODEV:errno;break;}
    }
    while(read(p->wake[0],signals,sizeof(signals))>0){}
    if(p->error)input_notify(p);
    pthread_mutex_unlock(&p->lock);
    Py_RETURN_NONE;
}
