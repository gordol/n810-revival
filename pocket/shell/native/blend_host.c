/* Text-window material composition over retained scene planes. No app callbacks. */
typedef struct {uint32_t glyph;uint64_t ink;} BlendCell;
static uint64_t blend_rgb(double r,double g,double b){
    double v[3]={r,g,b};uint64_t result=0;
    for(unsigned j=0;j<3;j++){double value=v[j]<0?0:v[j]>255?255:v[j];result=(result<<8)|cw_channel(value,j==1?63:31);}
    return result;
}
static uint64_t blend_pack(const double *fg,const double *bg){return (UINT64_C(1)<<48)|(blend_rgb(fg[0],fg[1],fg[2])<<24)|blend_rgb(bg[0],bg[1],bg[2]);}
static void blend_channels(uint64_t value,double *out){for(unsigned j=0;j<3;j++)out[j]=(value>>(16-j*8))&255;}
static int blend_role(uint64_t color,double *out){
    static const unsigned char roles[9][3]={{0,70,25},{65,68,65},{0,125,50},{145,78,110},{160,130,55},{35,85,100},{145,165,168},{95,105,108},{35,110,70}};
    if(color<4||color>12)return 0;
    for(unsigned j=0;j<3;j++)out[j]=roles[color-4][j];
    return 1;
}
static uint64_t blend_shade(uint64_t color,double strength){
    if(strength<=0)return color;
    double fg[3],bg[3],scale=1-strength;
    if(color<(UINT64_C(1)<<48)){
        if(!blend_role(color,fg))return 14;
        for(unsigned j=0;j<3;j++){fg[j]*=scale;bg[j]=10*scale;}
    }else{blend_channels(color>>24,fg);blend_channels(color,bg);for(unsigned j=0;j<3;j++){fg[j]*=scale;bg[j]*=scale;}}
    return blend_pack(fg,bg);
}
static uint64_t blend_pane(uint64_t color,double opacity){
    double fg[3],bg[3];
    if(color<(UINT64_C(1)<<48)){
        if(!blend_role(color,fg))for(unsigned j=0;j<3;j++)fg[j]=10;
        for(unsigned j=0;j<3;j++)bg[j]=fg[j];
        color=blend_pack(fg,bg);
    }
    blend_channels(color>>24,fg);blend_channels(color,bg);
    for(unsigned j=0;j<3;j++){fg[j]=fg[j]*(1-opacity)+24*opacity;bg[j]=bg[j]*(1-opacity)+24*opacity;}
    return blend_pack(fg,bg);
}
static uint64_t blend_text(uint64_t color){
    double fg[3]={195,199,195},bg[3];
    for(unsigned j=0;j<3;j++)bg[j]=(((color>>(40-j*8))&255)+((color>>(16-j*8))&255))/2.;
    return blend_pack(fg,bg);
}
static BlendCell blend_terminal(uint32_t glyph,uint64_t color,BlendCell under,double opacity){
    if(opacity>=1)return (BlendCell){glyph,color};
    double fg[3],bg[3],tint[3];
    if(under.ink<(UINT64_C(1)<<48)){
        if(!blend_role(under.ink,fg))for(unsigned j=0;j<3;j++)fg[j]=18;
        for(unsigned j=0;j<3;j++)bg[j]=18;
        under.ink=blend_pack(fg,bg);
    }
    blend_channels(color,tint);blend_channels(under.ink>>24,fg);blend_channels(under.ink,bg);
    int half=under.glyph==0x2584||under.glyph==0x2580;
    if(glyph==32){
        for(unsigned j=0;j<3;j++){fg[j]=cw_even(tint[j]*opacity+fg[j]*(1-opacity));bg[j]=cw_even(tint[j]*opacity+bg[j]*(1-opacity));}
        uint64_t result=blend_pack(fg,bg);
        return (BlendCell){half&&((result>>24)&0xffffff)==(result&0xffffff)?32:under.glyph,result};
    }
    for(unsigned j=0;j<3;j++){double base=half?cw_even((fg[j]+bg[j])/2):bg[j];bg[j]=cw_even(tint[j]*opacity+base*(1-opacity));}
    return (BlendCell){glyph,(color&~UINT64_C(0xffffff))|blend_rgb(bg[0],bg[1],bg[2])};
}
static uint64_t blend_inherit(uint64_t color,uint64_t under){
    if(color==14||color>=(UINT64_C(1)<<48))return color;
    double fg[3],bg[3];
    if(color>=(UINT64_C(1)<<24))blend_channels(color,fg);
    else if(!blend_role(color,fg)){fg[0]=150;fg[1]=155;fg[2]=150;}
    if(under>=(UINT64_C(1)<<48))blend_channels(under,bg);else for(unsigned j=0;j<3;j++)bg[j]=10;
    return blend_pack(fg,bg);
}
static PyObject *blend_scene(PyObject *self,PyObject *args){
    (void)self;PyObject *target_obj,*base_obj,*plans,*dirty_obj,*apps=Py_None;int fill,show,dx,dy;double opacity,size,shadow;
    if(!PyArg_ParseTuple(args,"OOOOidiiidd|O",&target_obj,&base_obj,&plans,&dirty_obj,&fill,&opacity,&show,&dx,&dy,&size,&shadow,&apps))return NULL;
    if((fill!=0&&fill!=1)||(show!=0&&show!=1)||!isfinite(opacity)||opacity<0||opacity>1||!isfinite(shadow)||shadow<0||shadow>1||dx < -1||dx>1||dy < -1||dy>1||!isfinite(size)||size<0||size>65535){PyErr_SetString(PyExc_ValueError,"invalid blend material");return NULL;}
    Surface *target=surface(target_obj),*base=surface(base_obj);if(!target||!base)return NULL;
    if(target==base||target->w!=base->w||target->h!=base->h){PyErr_SetString(PyExc_ValueError,"blend plane dimensions/alias mismatch");return NULL;}
    Py_ssize_t count=PyTuple_Size(plans);if(count<0)return NULL;
    if(count>4096){PyErr_SetString(PyExc_ValueError,"too many blend windows");return NULL;}
    Layer *layers=PyMem_Calloc(count?count:1,sizeof(*layers));if(!layers)return PyErr_NoMemory();
    Layer *app_layers=PyMem_Calloc(count?count:1,sizeof(*app_layers));
    if(!app_layers){PyMem_Free(layers);return PyErr_NoMemory();}
    Py_buffer dirty={0};PyObject *result=NULL;
    if(PyObject_GetBuffer(dirty_obj,&dirty,PyBUF_FORMAT|PyBUF_C_CONTIGUOUS))goto done;
    if(dirty.itemsize!=4||dirty.ndim!=1||!dirty.format||strcmp(dirty.format,"I")||dirty.len%4||(uintptr_t)dirty.buf%4){PyErr_SetString(PyExc_ValueError,"invalid blend indices");goto done;}
    size_t n=(size_t)target->w*target->h,nd=(size_t)dirty.len/4;const uint32_t *indices=dirty.buf;
    if(nd>n){PyErr_SetString(PyExc_ValueError,"blend batch exceeds viewport");goto done;}
    for(size_t i=0;i<nd;i++)if(indices[i]>=n){PyErr_SetString(PyExc_IndexError,"blend cell index");goto done;}
    for(Py_ssize_t i=0;i<count;i++){
        PyObject *entry=PyTuple_GetItem(plans,i),*plane;int x,y;
        if(!entry||!PyArg_ParseTuple(entry,"Oii",&plane,&x,&y))goto done;
        Surface *p=surface(plane);if(!p)goto done;
        if(p==target){PyErr_SetString(PyExc_ValueError,"blend target aliases a window");goto done;}
        layers[i]=(Layer){p,x,y};
    }
    if(apps!=Py_None){
        if(!fill||!PyTuple_Check(apps)||PyTuple_Size(apps)!=count){PyErr_SetString(PyExc_ValueError,"invalid app blend layers");goto done;}
        for(Py_ssize_t i=0;i<count;i++){
            PyObject *entry=PyTuple_GetItem(apps,i),*obj;int x,y;
            if(entry==Py_None)continue;
            if(!PyArg_ParseTuple(entry,"Oii",&obj,&x,&y))goto done;
            Surface *p=surface(obj);if(!p)goto done;
            if(p==target){PyErr_SetString(PyExc_ValueError,"app layer aliases target");goto done;}
            app_layers[i]=(Layer){p,x,y};
        }
    }
    /* Inputs stay under the GIL; callers submit the existing bounded batches. */
    for(size_t i=0;i<nd;i++){
        size_t at=indices[i];int64_t x=at%target->w,y=at/target->w;
        BlendCell value={base->valid[at]?base->glyph[at]:32,base->valid[at]?base->ink[at]:13},under=value;
        for(Py_ssize_t j=count;j-->0;){
            Layer layer=layers[j];Surface *plane=layer.plane;int64_t xx=x-layer.x,yy=y-layer.y;
            int inside=xx>=0&&yy>=0&&xx<plane->w&&yy<plane->h;
            if(shadow>0&&!inside&&xx>=(int64_t)dx*size&&yy>=(int64_t)dy*size&&xx<(int64_t)dx*size+plane->w&&yy<(int64_t)dy*size+plane->h){value.ink=blend_shade(value.ink,shadow);under.ink=blend_shade(under.ink,shadow);}
            if(!inside)continue;
            size_t p=(size_t)yy*plane->w+(size_t)xx;BlendCell behind=value,prior=under;
            uint32_t glyph=plane->glyph[p];uint64_t color=plane->ink[p];
            if(color&CW_FRAME_DEFERRED){
                if(glyph!=32)value=(BlendCell){glyph,cw_frame_resolve(color,behind.glyph,behind.ink)};
                under=fill?(opacity<1?(BlendCell){prior.glyph,blend_pane(prior.ink,opacity)}:(BlendCell){32,0}):prior;
            }else if(color&CW_FRAME_INK){
                /* Opaque chrome includes spaces and does not inherit pane opacity. */
                value=(BlendCell){glyph,color};
                under=fill?(opacity<1?(BlendCell){prior.glyph,blend_pane(prior.ink,opacity)}:(BlendCell){32,0}):prior;
            }else{
                if(color){
                    if(fill&&opacity<1){
                        under=blend_terminal(32,color,prior,opacity);
                        BlendCell base_cell=show&&glyph==32?behind:prior;
                        value=glyph==32&&!(show&&glyph==32)?under:blend_terminal(glyph,color,base_cell,opacity);
                    }else{value=(BlendCell){glyph,color};under=fill?(BlendCell){32,color}:prior;}
                }else if(!fill||opacity>=1){value=(BlendCell){glyph,0};under=fill?(BlendCell){32,0}:prior;}
                else{
                    uint64_t pane=blend_pane(prior.ink,opacity);under=(BlendCell){prior.glyph,pane};
                    value=glyph==32?(show?(BlendCell){behind.glyph,blend_pane(behind.ink,opacity)}:under):(BlendCell){glyph,blend_text(pane)};
                }
                Layer app=app_layers[j];
                int64_t ax=x-app.x,ay=y-app.y;
                if(app.plane&&xx>0&&yy>0&&xx<plane->w-1&&yy<plane->h-1&&ax>=0&&ay>=0&&ax<app.plane->w&&ay<app.plane->h){
                    size_t ai=(size_t)ay*app.plane->w+(size_t)ax;
                    if(app.plane->valid[ai]){
                        value=(BlendCell){app.plane->glyph[ai],app.plane->ink[ai]};
                        under=(BlendCell){value.glyph==0x2584||value.glyph==0x2580||value.glyph==0x2588?value.glyph:32,value.ink};
                    }
                }
                if(!fill){
                    if(value.glyph==32||value.glyph==0x2584||value.glyph==0x2580)value=behind;
                    else if(value.ink>=(UINT64_C(1)<<48)){
                        double fg[3],bg[3];blend_channels(value.ink>>24,fg);
                        if(behind.ink>=(UINT64_C(1)<<48))blend_channels(behind.ink,bg);else for(unsigned k=0;k<3;k++)bg[k]=12;
                        value.ink=blend_pack(fg,bg);
                    }else value.ink=blend_inherit(value.ink,behind.ink);
                }
            }
        }
        cw_set(target,(uint32_t)at,value.glyph,value.ink,1);
    }
    result=PyLong_FromSize_t(nd);
done:
    if(dirty.obj)PyBuffer_Release(&dirty);
    PyMem_Free(app_layers);PyMem_Free(layers);return result;
}
