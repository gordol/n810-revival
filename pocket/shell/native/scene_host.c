/* Bounded native dirty maps and immutable scene planes. No device I/O. */
#include <math.h>
typedef struct {uint32_t n,count;unsigned char *marked;} DirtyMap;
static const char *dirty_name="pocket.damage.v1";
static DirtyMap *dirty_map(PyObject *o){return PyCapsule_GetPointer(o,dirty_name);}
static void dirty_free(PyObject *o){DirtyMap *d=dirty_map(o);if(d){PyMem_Free(d->marked);PyMem_Free(d);}else PyErr_Clear();}
static void dirty_mark(DirtyMap *d,uint32_t i,int on){if(d->marked[i]!=on){d->marked[i]=(unsigned char)on;if(on)d->count++;else d->count--;}}
static PyObject *dirty_new(PyObject *self,PyObject *args){
    (void)self;unsigned n;if(!PyArg_ParseTuple(args,"I",&n))return NULL;
    if(!n||n>1000000){PyErr_SetString(PyExc_ValueError,"invalid damage capacity");return NULL;}
    DirtyMap *d=PyMem_Calloc(1,sizeof(*d));if(!d)return PyErr_NoMemory();d->n=n;d->marked=PyMem_Calloc(n,1);
    if(!d->marked){PyMem_Free(d);return PyErr_NoMemory();}
    PyObject *o=PyCapsule_New(d,dirty_name,dirty_free);if(!o){PyMem_Free(d->marked);PyMem_Free(d);}return o;
}
static PyObject *dirty_count(PyObject *self,PyObject *o){(void)self;DirtyMap *d=dirty_map(o);return d?PyLong_FromUnsignedLong(d->count):NULL;}
/* Pixel presentation needs one rectangle, not an allocated index stream.
 * Read the canonical map directly; this operation never consumes damage. */
static PyObject *dirty_bounds(PyObject *self,PyObject *args){
    (void)self;PyObject *o;unsigned stride;
    if(!PyArg_ParseTuple(args,"OI",&o,&stride))return NULL;
    DirtyMap *d=dirty_map(o);if(!d)return NULL;
    if(!stride||d->n%stride){PyErr_SetString(PyExc_ValueError,"invalid damage stride");return NULL;}
    if(!d->count)return Py_BuildValue("(IIII)",0u,0u,0u,0u);
    unsigned left=stride,top=d->n/stride,right=0,bottom=0;
    for(unsigned y=0;y<d->n/stride;y++){
        const unsigned char *row=d->marked+y*stride;
        unsigned first=0,last=stride;
        while(first<stride&&!row[first])++first;
        if(first==stride)continue;
        while(last>first+1&&!row[last-1])--last;
        /* Interior membership cannot affect this row's extrema. In the
         * common rectangular-damage case, skip the whole marked run. */
        if(first<left)left=first;
        if(last>right)right=last;
        if(y<top)top=y;
        bottom=y+1;
    }
    return Py_BuildValue("(IIII)",left,top,right-left,bottom-top);
}
static PyObject *dirty_has(PyObject *self,PyObject *args){(void)self;PyObject *o;long i;if(!PyArg_ParseTuple(args,"Ol",&o,&i))return NULL;
    DirtyMap *d=dirty_map(o);if(!d)return NULL;return PyBool_FromLong(i>=0&&(uint32_t)i<d->n&&d->marked[i]);}
static PyObject *dirty_rect(PyObject *self,PyObject *args){
    (void)self;PyObject *o;unsigned stride,x,y,w,h;int on=1;
    if(!PyArg_ParseTuple(args,"OIIIII|p",&o,&stride,&x,&y,&w,&h,&on))return NULL;
    DirtyMap *d=dirty_map(o);if(!d)return NULL;
    if(!stride||d->n%stride||x>stride||w>stride-x||y>d->n/stride||h>d->n/stride-y){PyErr_SetString(PyExc_ValueError,"damage rectangle outside viewport");return NULL;}
    for(unsigned row=y;row<y+h;row++)for(unsigned col=x;col<x+w;col++)dirty_mark(d,row*stride+col,on);
    Py_RETURN_NONE;
}
static int dirty_buffer(DirtyMap *d,PyObject *values,int on,int *intersects){
    Py_buffer view;
    if(PyObject_GetBuffer(values,&view,PyBUF_FORMAT|PyBUF_C_CONTIGUOUS))return -1;
    if(view.itemsize!=4||view.ndim!=1||!view.format||strcmp(view.format,"I")||view.len%4||(uintptr_t)view.buf%4){PyBuffer_Release(&view);PyErr_SetString(PyExc_ValueError,"damage requires native uint32 indices");return -1;}
    const uint32_t *indices=view.buf;size_t n=(size_t)view.len/4;
    for(size_t i=0;i<n;i++)if(indices[i]>=d->n){PyBuffer_Release(&view);PyErr_SetString(PyExc_IndexError,"damage outside viewport");return -1;}
    for(size_t i=0;i<n;i++){if(intersects){if(d->marked[indices[i]]){*intersects=1;break;}}else dirty_mark(d,indices[i],on);}
    PyBuffer_Release(&view);return 0;
}
static PyObject *dirty_update(PyObject *self,PyObject *args){
    (void)self;PyObject *o,*values;int on;
    if(!PyArg_ParseTuple(args,"OOp",&o,&values,&on))return NULL;
    DirtyMap *d=dirty_map(o);if(!d)return NULL;
    if(PyObject_CheckBuffer(values)){if(dirty_buffer(d,values,on,NULL))return NULL;Py_RETURN_NONE;}
    PyObject *iterator=PyObject_GetIter(values);if(!iterator)return NULL;PyObject *value;
    while((value=PyIter_Next(iterator))){unsigned long i=PyLong_AsUnsignedLong(value);Py_DECREF(value);if(PyErr_Occurred()){Py_DECREF(iterator);return NULL;}if(i>=d->n){Py_DECREF(iterator);PyErr_SetString(PyExc_IndexError,"damage outside viewport");return NULL;}dirty_mark(d,(uint32_t)i,on);}
    Py_DECREF(iterator);if(PyErr_Occurred())return NULL;Py_RETURN_NONE;
}
static PyObject *dirty_merge(PyObject *self,PyObject *args){
    (void)self;PyObject *a,*b;int mode;if(!PyArg_ParseTuple(args,"OOi",&a,&b,&mode))return NULL;
    DirtyMap *d=dirty_map(a),*other=dirty_map(b);if(!d||!other)return NULL;
    if(mode<0||mode>2||d->n!=other->n){PyErr_SetString(PyExc_ValueError,"incompatible damage maps");return NULL;}
    for(uint32_t i=0;i<d->n;i++)dirty_mark(d,i,mode==0?(d->marked[i]||other->marked[i]):mode==1?(d->marked[i]&&other->marked[i]):(d->marked[i]&&!other->marked[i]));
    Py_RETURN_NONE;
}
static PyObject *dirty_take(PyObject *self,PyObject *args){
    (void)self;PyObject *o,*priority=Py_None;unsigned budget;
    if(!PyArg_ParseTuple(args,"OI|O",&o,&budget,&priority))return NULL;
    DirtyMap *d=dirty_map(o),*p=priority==Py_None?NULL:dirty_map(priority);if(!d||(priority!=Py_None&&!p))return NULL;
    if(p&&p->n!=d->n){PyErr_SetString(PyExc_ValueError,"incompatible priority map");return NULL;}
    if(budget>d->count)budget=d->count;
    uint32_t *result=PyMem_Malloc(((size_t)budget+1)*4);if(!result)return PyErr_NoMemory();uint32_t used=0,u=0,b=0;
    if(!p||!p->count){for(uint32_t i=0;i<d->n&&used<budget;i++)if(d->marked[i])result[used++]=i;}
    else while(used<budget){
        unsigned take=b<d->n?48:64;
        while(take&&u<d->n&&used<budget){if(d->marked[u]&&p->marked[u]){result[used++]=u;take--;}u++;}
        take=u>=d->n?64:16;
        while(take&&b<d->n&&used<budget){if(d->marked[b]&&!p->marked[b]){result[used++]=b;take--;}b++;}
        if(u>=d->n&&b>=d->n)break;
    }
    PyObject *raw=PyBytes_FromStringAndSize((char*)result,(Py_ssize_t)used*4);PyMem_Free(result);return raw;
}
static PyObject *dirty_intersects(PyObject *self,PyObject *args){(void)self;PyObject *o,*values;if(!PyArg_ParseTuple(args,"OO",&o,&values))return NULL;
    DirtyMap *d=dirty_map(o);if(!d)return NULL;int result=0;if(dirty_buffer(d,values,0,&result))return NULL;return PyBool_FromLong(result);}
static PyObject *dirty_diff(PyObject *self,PyObject *args){
    (void)self;PyObject *o,*before,*after;if(!PyArg_ParseTuple(args,"OOO",&o,&before,&after))return NULL;
    DirtyMap *d=dirty_map(o);Surface *b=before==Py_None?NULL:surface(before),*a=surface(after);if(!d||!a||(before!=Py_None&&!b))return NULL;
    if((size_t)a->w*a->h!=d->n){PyErr_SetString(PyExc_ValueError,"scene viewport differs");return NULL;}
    int same=b&&b->w==a->w&&b->h==a->h;
    for(uint32_t i=0;i<d->n;i++)if(!same||a->glyph[i]!=b->glyph[i]||a->ink[i]!=b->ink[i]||a->valid[i]!=b->valid[i])dirty_mark(d,i,1);
    Py_RETURN_NONE;
}
/* Effect planes retain overlay insertion order for the existing Scene mapping. */
typedef struct {uint32_t *order;size_t count;unsigned char *mask;} SceneInfo;
static void scene_free(PyObject *o){Surface *s=surface(o);if(!s){PyErr_Clear();return;}SceneInfo *info=PyCapsule_GetContext(o);if(info){PyMem_Free(info->order);PyMem_Free(info->mask);PyMem_Free(info);}cw_free(s);}
static PyObject *scene_indices(PyObject *self,PyObject *o){(void)self;SceneInfo *info=PyCapsule_GetContext(o);if(!info){if(!PyErr_Occurred())PyErr_SetString(PyExc_ValueError,"scene metadata missing");return NULL;}return PyBytes_FromStringAndSize((char*)info->order,(Py_ssize_t)info->count*4);}
static PyObject *scene_has(PyObject *self,PyObject *args){
    (void)self;PyObject *o;unsigned index;if(!PyArg_ParseTuple(args,"OI",&o,&index))return NULL;
    Surface *s=surface(o);if(!s)return NULL;SceneInfo *info=PyCapsule_GetContext(o);
    if(!info||index>=(size_t)s->w*s->h){if(!PyErr_Occurred())PyErr_SetString(PyExc_IndexError,"scene index");return NULL;}
    return PyBool_FromLong(info->mask[index]);
}
static double fx_clamp(double v){return v<0?0:v>255?255:v;}
static uint64_t fx_rgb(double r,double g,double b){return ((uint64_t)cw_channel(fx_clamp(r),31)<<16)|((uint64_t)cw_channel(fx_clamp(g),63)<<8)|cw_channel(fx_clamp(b),31);}
static uint64_t fx_ink(double *fore,double *back){return (UINT64_C(1)<<48)|(fx_rgb(fore[0],fore[1],fore[2])<<24)|fx_rgb(back[0],back[1],back[2]);}
static int fx_check(PyObject *callback){PyObject *value=PyObject_CallNoArgs(callback);if(!value)return -1;Py_DECREF(value);return 0;}
static PyObject *nebula(PyObject *self,PyObject *args){
    (void)self;unsigned w,h;int ascii;PyObject *callback;
    if(!PyArg_ParseTuple(args,"IIpO",&w,&h,&ascii,&callback))return NULL;
    if(!dimensions(w,h)){PyErr_SetString(PyExc_ValueError,"invalid nebula viewport");return NULL;}
    Surface *s=cw_surface(w,h);if(!s)return PyErr_NoMemory();unsigned sw=w<96?w:96,sh=h<48?h:48;
    for(unsigned y=0;y<h;y++){
        if(!(y%8)&&fx_check(callback)){cw_free(s);return NULL;}
        Py_BEGIN_ALLOW_THREADS
        for(unsigned x=0;x<w;x++){
            unsigned xx=x*sw/w,yy=y*sh/h;double u=(double)xx/(sw>1?sw-1:1),v=(double)yy/(sh>1?sh-1:1);
            double aa=.5+.5*sin(u*6+v*3),bb=.5+.5*cos(u*4-v*7),glow=exp(-((u-.52)*(u-.52)+(v-.5)*(v-.5))*5);aa=aa*aa;bb=bb*bb;
            double upper[3]={7+17*bb*glow,8+24*aa*glow,15+25*bb*glow},lower[3];for(int c=0;c<3;c++)lower[c]=upper[c]+1.5*glow;
            uint64_t color=fx_ink(lower,upper);
            cw_set(s,y*w+x,ascii?' ':0x2584,color,1);
        }
        Py_END_ALLOW_THREADS
    }
    PyObject *result=PyCapsule_New(s,capsule_name,dispose);if(!result)cw_free(s);return result;
}
static int fx_round(double x){double n=floor(x),tail=x-n;return (int)(n+(tail>.5||(tail==.5&&fmod(n,2)!=0)));}
static int fx_color_edge(const double *v){
    for(unsigned j=0;j<3;j++){
        double q=fx_clamp(v[j])*(j==1?63:31)/255.;
        if(fabs(q-(unsigned)q-.5)<1e-7)return 1;
    }
    return 0;
}
static PyObject *flux_surface(PyObject *self,PyObject *args){
    (void)self;PyObject *base_obj,*callback;double step,scale,glow_strength;unsigned w,h;int ascii,arms;
    if(!PyArg_ParseTuple(args,"IIdpddiOO",&w,&h,&step,&ascii,&scale,&glow_strength,&arms,&base_obj,&callback))return NULL;
    Surface *base=surface(base_obj);if(!base)return NULL;
    if(!dimensions(w,h)||w!=base->w||h!=base->h||!isfinite(step)||!isfinite(scale)||!isfinite(glow_strength)||arms<0||arms>4||glow_strength<0||glow_strength>1){PyErr_SetString(PyExc_ValueError,"invalid Flux parameters");return NULL;}
    size_t n=(size_t)w*h;Surface *s=cw_surface(w,h);if(!s)return PyErr_NoMemory();
    double *density=PyMem_Calloc(n,sizeof(double)),*glow=PyMem_Calloc(n,sizeof(double));uint32_t *heads=PyMem_Calloc(n,4),*order=PyMem_Malloc(n*4),*gorder=PyMem_Malloc(n*4);char *trails=PyMem_Calloc(n,1);unsigned char *seen=PyMem_Calloc(n,1),*mask=PyMem_Calloc(n,1);
    PyObject *result=NULL;size_t count=0,gcount=0;double *phases=NULL;
    if(!density||!glow||!heads||!order||!gorder||!trails||!seen||!mask){PyErr_NoMemory();goto done;}
    memcpy(s->glyph,base->glyph,n*4);memcpy(s->ink,base->ink,n*8);memcpy(s->valid,base->valid,n);
    double t=step/90,a=-1.4+.12*sin(t),b=1.6,c=1+.15*cos(t*.7),d=.7,x=.1,y=.1;
    unsigned budget=(unsigned)(w*h/8);if(budget<64)budget=64;if(budget>768)budget=768;budget=cw_even(budget*(scale<.5?.5:scale>4?4:scale));
    for(unsigned start=0;start<budget+32;start+=256){
        if(fx_check(callback))goto done;
        unsigned end=start+256;if(end>budget+32)end=budget+32;
        Py_BEGIN_ALLOW_THREADS
        for(unsigned i=start;i<end;i++){
            double nx=sin(a*y)+c*cos(a*x),ny=sin(b*x)+d*cos(b*y);x=nx;y=ny;if(i<32)continue;
            int xx=(int)((x+2.2)/4.4*w),yy=(int)((y+2)/4*h);if(xx<0)xx=0;if(xx>=(int)w)xx=w-1;if(yy<0)yy=0;if(yy>=(int)h)yy=h-1;
            uint32_t index=(uint32_t)yy*w+(uint32_t)xx;if(!density[index])order[count++]=index;density[index]+=1;
        }
        Py_END_ALLOW_THREADS
    }
    size_t primary=count;for(size_t i=0;i<primary;i++)heads[order[i]]=(uint32_t)density[order[i]];
    for(size_t k=0;k<primary;k++){
        if(!(k%128)&&fx_check(callback))goto done;
        uint32_t index=order[k];unsigned xx=index%w,yy=index/w;
        double angle=sin((double)xx/w*5+t*.3)+(double)yy/h*3,dx=cos(angle),dy=sin(angle)*.5;char glyph=fabs(dy)<.25?'-':dx*dy<0?'/':'\\';
        for(int distance=1;distance<=arms;distance++){
            int tx=fx_round(xx-dx*distance),ty=fx_round(yy-dy*distance);if(tx<0||ty<0||tx>=(int)w||ty>=(int)h)continue;
            uint32_t at=(uint32_t)ty*w+(uint32_t)tx;if(heads[at])continue;double weight=(1-(double)distance/(arms+1))*.65;
            if(!density[at])order[count++]=at;
            if(density[at]<weight)density[at]=weight;
            trails[at]=glyph;
        }
    }
    for(size_t k=0;k<count;k++){
        if(!(k%128)&&fx_check(callback))goto done;
        uint32_t index=order[k];int xx=index%w,yy=index/w;
        double strength=.45+log1p(density[index])*.35;if(strength>1.7)strength=1.7;
        const int dx[5]={0,-1,1,0,0},dy[5]={0,0,0,-1,1};const double weight[5]={1,.18,.18,.12,.12};
        for(int j=0;j<5;j++){
            int tx=xx+dx[j],ty=yy+dy[j];if(tx<0||ty<0||tx>=(int)w||ty>=(int)h)continue;uint32_t at=(uint32_t)ty*w+(uint32_t)tx;
            if(!seen[at]){seen[at]=1;gorder[gcount++]=at;}double value=glow[at]+strength*weight[j]*(j?glow_strength:1);glow[at]=value>2.2?2.2:value;
        }
    }
    /* Separate row/column phases instead of three transcendental calls per
       colored cell. Near quantization edges use the original expression. */
    int fast=fabs(t)<=1e6&&(size_t)2*w+(size_t)6*h<3*gcount;
    const double shifts[3]={0,2.1,4.2};
    if(fast){
        phases=PyMem_Malloc(((size_t)2*w+(size_t)6*h)*sizeof(double));
        if(!phases){PyErr_NoMemory();goto done;}
        for(unsigned xx=0;xx<w;xx++){
            if(!(xx%128)&&fx_check(callback))goto done;
            double angle=(double)xx/w*2.4;
            phases[xx]=sin(angle);phases[w+xx]=cos(angle);
        }
        for(unsigned yy=0;yy<h;yy++){
            if(!(yy%128)&&fx_check(callback))goto done;
            for(unsigned j=0;j<3;j++){
                double angle=(double)yy/h*1.7+t*.12+shifts[j];
                phases[2*w+(size_t)yy*6+j*2]=sin(angle);
                phases[2*w+(size_t)yy*6+j*2+1]=cos(angle);
            }
        }
    }
    for(size_t k=0;k<gcount;k++){
        if(!(k%128)&&fx_check(callback))goto done;
        uint32_t index=gorder[k];double phase=(double)(index%w)/w*2.4+(double)(index/w)/h*1.7+t*.12;
        double rgb[3],bg[3]={(double)((base->ink[index]>>16)&255),(double)((base->ink[index]>>8)&255),(double)(base->ink[index]&255)},fore[3],back[3];
        for(int j=0;j<3;j++){
            double wave=fast?phases[index%w]*phases[2*w+(size_t)(index/w)*6+j*2+1]+phases[w+index%w]*phases[2*w+(size_t)(index/w)*6+j*2]:sin(phase+shifts[j]);
            rgb[j]=65+85*(.5+.5*wave);double bottom=bg[j]+rgb[j]*glow[index]*(heads[index]?1.15:.65);fore[j]=bottom>240?240:bottom;back[j]=bg[j]+rgb[j]*glow[index]*.08*glow_strength;
        }
        if(fast){
            double actual_fore[3],actual_back[3];
            for(unsigned j=0;j<3;j++){actual_fore[j]=density[index]?fore[j]:bg[j];actual_back[j]=density[index]?back[j]:bg[j]+rgb[j]*glow[index]*.20;}
            if(fx_color_edge(actual_fore)||fx_color_edge(actual_back)){
                for(unsigned j=0;j<3;j++){
                    rgb[j]=65+85*(.5+.5*sin(phase+shifts[j]));double bottom=bg[j]+rgb[j]*glow[index]*(heads[index]?1.15:.65);fore[j]=bottom>240?240:bottom;back[j]=bg[j]+rgb[j]*glow[index]*.08*glow_strength;
                }
            }
        }
        if(density[index]){s->glyph[index]=trails[index]?(uint32_t)trails[index]:heads[index]>=3?'+':ascii?'.':0xb7;s->ink[index]=fx_ink(fore,back);mask[index]=1;}
        else if(glow_strength>0){for(int j=0;j<3;j++){fore[j]=bg[j];back[j]=bg[j]+rgb[j]*glow[index]*.20;}s->glyph[index]=' ';s->ink[index]=fx_ink(fore,back);mask[index]=1;}
    }
    /* Filter overlay keys without changing insertion order. */
    size_t used=0;for(size_t i=0;i<gcount;i++)if(mask[gorder[i]])gorder[used++]=gorder[i];
    SceneInfo *info=PyMem_Calloc(1,sizeof(*info));if(!info){PyErr_NoMemory();goto done;}info->order=gorder;info->count=used;info->mask=mask;gorder=NULL;mask=NULL;
    result=PyCapsule_New(s,capsule_name,scene_free);if(!result){PyMem_Free(info->order);PyMem_Free(info->mask);PyMem_Free(info);goto done;}PyCapsule_SetContext(result,info);s=NULL;
done:
    cw_free(s);PyMem_Free(phases);PyMem_Free(density);PyMem_Free(glow);PyMem_Free(heads);PyMem_Free(order);PyMem_Free(gorder);PyMem_Free(trails);PyMem_Free(seen);PyMem_Free(mask);return result;
}

static int index_compare(const void *a,const void *b){uint32_t x=*(const uint32_t*)a,y=*(const uint32_t*)b;return (x>y)-(x<y);}
static PyObject *order_indices(PyObject *self,PyObject *o,int batches){
    (void)self;Py_buffer v;if(PyObject_GetBuffer(o,&v,PyBUF_FORMAT|PyBUF_C_CONTIGUOUS))return NULL;
    if(v.itemsize!=4||v.ndim!=1||!v.format||strcmp(v.format,"I")||v.len%4||(uintptr_t)v.buf%4){PyBuffer_Release(&v);PyErr_SetString(PyExc_ValueError,"invalid indices");return NULL;}
    PyObject *out=PyBytes_FromStringAndSize(v.buf,v.len);PyBuffer_Release(&v);if(!out)return NULL;
    uint32_t *values=(uint32_t*)PyBytes_AsString(out);size_t n=(size_t)PyBytes_Size(out)/4;
    size_t stride=batches?64:n;
    for(size_t start=0;start<n;start+=stride){
        size_t count=n-start<stride?n-start:stride;
        for(size_t i=1;i<count;i++)if(values[start+i-1]>values[start+i]){qsort(values+start,count,4,index_compare);break;}
    }
    return out;
}

static PyObject *sorted_indices(PyObject *self,PyObject *o){return order_indices(self,o,0);}
static PyObject *sorted_batches(PyObject *self,PyObject *o){return order_indices(self,o,1);}
