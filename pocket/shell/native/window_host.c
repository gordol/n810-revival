/* Retained native window host. App text, glyph policy and role colors keep their
   existing Python interfaces; row preparation and change admission live here. */
typedef struct {
    PyObject *plane,*context,*inks;
    PyObject **text,**spans;
    uint32_t width,height;
} WindowHost;
static const char *window_host_name="pocket.window-host.v1";
static void window_host_free(PyObject *capsule){
    WindowHost *p=PyCapsule_GetPointer(capsule,window_host_name);
    if(!p){PyErr_Clear();return;}
    for(uint32_t i=0;i<p->height;i++){if(p->text)Py_XDECREF(p->text[i]);if(p->spans)Py_XDECREF(p->spans[i]);}
    PyMem_Free(p->text);PyMem_Free(p->spans);
    Py_XDECREF(p->plane);Py_XDECREF(p->context);Py_XDECREF(p->inks);PyMem_Free(p);
}
static int host_row(Surface *s,uint32_t y,PyObject *text,uint64_t ink){
    Py_ssize_t bytes;const char *value=PyUnicode_AsUTF8AndSize(text,&bytes);
    if(!value)return -1;
    if(cw_row(s,y,(const unsigned char*)value,(size_t)bytes,ink)){PyErr_SetString(PyExc_ValueError,"invalid native window row");return -1;}
    return 0;
}
static PyObject *host_glyph(PyObject *glyphs,const char *method,PyObject *value,int ascii){
    /* The existing policy owns Unicode width, font support and replacement. */
    if(!PyUnicode_Check(value)){PyErr_SetString(PyExc_TypeError,"window text must be Unicode");return NULL;}
    return PyObject_CallMethod(glyphs,method,"Oi",value,ascii);
}
static int host_body(Surface *s,uint32_t y,PyObject *text,PyObject *vertical,uint64_t ink){
    Py_ssize_t nt,nv;const char *t=PyUnicode_AsUTF8AndSize(text,&nt),*v=PyUnicode_AsUTF8AndSize(vertical,&nv);
    Py_ssize_t count=PyUnicode_GetLength(text);if(!t||!v||count<0)return -1;
    if(count>(Py_ssize_t)s->w-2||nv>4){PyErr_SetString(PyExc_ValueError,"invalid glyph policy result");return -1;}
    size_t padding=s->w-2-(size_t)count;
    size_t size=(size_t)nt+2*(size_t)nv+padding;
    char *buffer=PyMem_Malloc(size+1);if(!buffer){PyErr_NoMemory();return -1;}
    memcpy(buffer,v,(size_t)nv);memcpy(buffer+nv,t,(size_t)nt);memset(buffer+nv+nt,' ',padding);memcpy(buffer+nv+nt+padding,v,(size_t)nv);
    int result=cw_row(s,y,(unsigned char*)buffer,size,0);PyMem_Free(buffer);
    if(result||cw_style(s,y,0,1,ink)||cw_style(s,y,s->w-1,s->w,ink)){PyErr_SetString(PyExc_ValueError,"invalid native window body");return -1;}
    return 0;
}
static PyObject *window_host(PyObject *self,PyObject *args){
    (void)self;PyObject *prior,*title,*lines,*style_rows,*borders,*glyphs,*inkfn,*palette,*context;
    unsigned width,height;unsigned long long frame;int ascii,focused;
    if(!PyArg_ParseTuple(args,"OIIOOOOKOpOOpO",&prior,&width,&height,&title,&lines,&style_rows,&borders,&frame,&glyphs,&ascii,&inkfn,&palette,&focused,&context))return NULL;
    if(width<2||!dimensions(width,height)||!cw_ink_valid(frame)||!PyTuple_Check(lines)||!PyTuple_Check(style_rows)||!PyTuple_Check(borders)||PyTuple_Size(borders)!=6){PyErr_SetString(PyExc_ValueError,"invalid native window plan");return NULL;}
    WindowHost *p=NULL;PyObject *capsule=NULL,*empty=NULL,*empty_spans=NULL,*styles=NULL,*vertical=NULL,*normalized=NULL,*result=NULL;
    Py_ssize_t builds=0;
    if(prior!=Py_None){p=PyCapsule_GetPointer(prior,window_host_name);if(!p)return NULL;}
    if(p&&(p->width!=width||p->height!=height))p=NULL;
    if(!p){
        p=PyMem_Calloc(1,sizeof(*p));if(!p)return PyErr_NoMemory();
        p->width=width;p->height=height;p->text=PyMem_Calloc(height,sizeof(PyObject*));p->spans=PyMem_Calloc(height,sizeof(PyObject*));
        capsule=PyCapsule_New(p,window_host_name,window_host_free);
        if(!capsule){PyMem_Free(p->text);PyMem_Free(p->spans);PyMem_Free(p);return NULL;}
        if(!p->text||!p->spans){PyErr_NoMemory();goto done;}
        Surface *s=cw_surface(width,height);if(!s){PyErr_NoMemory();goto done;}
        p->plane=PyCapsule_New(s,capsule_name,dispose);if(!p->plane){cw_free(s);goto done;}
    }else{capsule=prior;Py_INCREF(capsule);}
    int same=p->context?PyObject_RichCompareBool(p->context,context,Py_EQ):0;
    if(same<0)goto done;
    Surface *s=surface(p->plane);if(!s)goto done;
    empty=PyUnicode_FromString("");empty_spans=PyTuple_New(0);styles=PyDict_New();
    if(!empty||!empty_spans||!styles)goto done;
    for(Py_ssize_t i=0;i<PyTuple_Size(style_rows);i++){
        PyObject *entry=PyTuple_GetItem(style_rows,i);
        if(!PyTuple_Check(entry)||PyTuple_Size(entry)!=2){PyErr_SetString(PyExc_ValueError,"invalid window styles");goto done;}
        if(PyDict_SetItem(styles,PyTuple_GetItem(entry,0),PyTuple_GetItem(entry,1)))goto done;
    }
    if(!same){
        normalized=host_glyph(glyphs,"text",title,ascii);if(!normalized||host_row(s,0,normalized,frame))goto done;Py_CLEAR(normalized);builds++;
        if(height>1){
            PyObject *bl=host_glyph(glyphs,"cell",PyTuple_GetItem(borders,2),ascii),*br=host_glyph(glyphs,"cell",PyTuple_GetItem(borders,3),ascii),*h=host_glyph(glyphs,"cell",PyTuple_GetItem(borders,4),ascii);
            if(!bl||!br||!h){Py_XDECREF(bl);Py_XDECREF(br);Py_XDECREF(h);goto done;}
            Py_ssize_t nb,nr,nh;const char *b=PyUnicode_AsUTF8AndSize(bl,&nb),*r=PyUnicode_AsUTF8AndSize(br,&nr),*v=PyUnicode_AsUTF8AndSize(h,&nh);
            if(!b||!r||!v||nb>4||nr>4||nh>4){Py_DECREF(bl);Py_DECREF(br);Py_DECREF(h);if(!PyErr_Occurred())PyErr_SetString(PyExc_ValueError,"invalid border glyph");goto done;}
            size_t n=(size_t)nb+(width-2)*(size_t)nh+(size_t)nr;char *buffer=PyMem_Malloc(n+1);
            if(!buffer){Py_DECREF(bl);Py_DECREF(br);Py_DECREF(h);PyErr_NoMemory();goto done;}
            memcpy(buffer,b,(size_t)nb);for(unsigned x=0;x<width-2;x++)memcpy(buffer+nb+x*nh,v,(size_t)nh);memcpy(buffer+nb+(width-2)*nh,r,(size_t)nr);
            int bad=cw_row(s,height-1,(unsigned char*)buffer,n,frame);PyMem_Free(buffer);Py_DECREF(bl);Py_DECREF(br);Py_DECREF(h);
            if(bad){PyErr_SetString(PyExc_ValueError,"invalid border row");goto done;}builds++;
        }
    }
    for(uint32_t row=0;row+2<height;row++){
        PyObject *raw=row<(uint32_t)PyTuple_Size(lines)?PyTuple_GetItem(lines,row):empty;
        PyObject *key=PyLong_FromUnsignedLong(row);if(!key)goto done;
        PyObject *spans=PyDict_GetItemWithError(styles,key);Py_DECREF(key);if(!spans){if(PyErr_Occurred())goto done;spans=empty_spans;}
        if(!PyUnicode_Check(raw)||!PyTuple_Check(spans)){PyErr_SetString(PyExc_TypeError,"invalid window row");goto done;}
        int text_same=same&&p->text[row]?PyObject_RichCompareBool(p->text[row],raw,Py_EQ):0;
        int spans_same=same&&p->spans[row]?PyObject_RichCompareBool(p->spans[row],spans,Py_EQ):0;
        if(text_same<0||spans_same<0)goto done;
        if(text_same&&spans_same)continue;
        if(!vertical){vertical=host_glyph(glyphs,"cell",PyTuple_GetItem(borders,5),ascii);if(!vertical)goto done;}
        PyObject *clipped=PyUnicode_Substring(raw,0,width-2);if(!clipped)goto done;
        normalized=host_glyph(glyphs,"text",clipped,ascii);Py_DECREF(clipped);if(!normalized||host_body(s,row+1,normalized,vertical,frame))goto done;Py_CLEAR(normalized);
        for(Py_ssize_t i=0;i<PyTuple_Size(spans);i++){
            PyObject *span=PyTuple_GetItem(spans,i),*first,*last,*role;long start,end;int overflow;
            if(!PyArg_ParseTuple(span,"OOO",&first,&last,&role))goto done;
            start=PyLong_AsLongAndOverflow(first,&overflow);if(PyErr_Occurred())goto done;if(overflow)start=overflow<0?0:(long)width;
            end=PyLong_AsLongAndOverflow(last,&overflow);if(PyErr_Occurred())goto done;if(overflow)end=overflow<0?-1:(long)width;
            if(start<0)start=0;
            if(end>(long)width-2)end=width-2;
            if(start>=end)continue;
            PyObject *value=PyObject_CallFunction(inkfn,"OOi",role,palette,focused);if(!value)goto done;
            unsigned long long ink=PyLong_AsUnsignedLongLong(value);Py_DECREF(value);if(PyErr_Occurred())goto done;
            if(!cw_ink_valid(ink)||cw_style(s,row+1,(uint32_t)start+1,(uint32_t)end+1,ink)){PyErr_SetString(PyExc_ValueError,"invalid span ink");goto done;}
        }
        Py_INCREF(raw);Py_XDECREF(p->text[row]);p->text[row]=raw;Py_INCREF(spans);Py_XDECREF(p->spans[row]);p->spans[row]=spans;builds++;
    }
    /* Derive the palette from the retained surface, including unchanged rows. */
    PyObject *inks=PySet_New(NULL);if(!inks)goto done;
    for(size_t i=0;i<(size_t)width*height;i++){
        /* Runs usually contain hundreds of identical cells. */
        if(i&&s->ink[i]==s->ink[i-1])continue;
        PyObject *ink=PyLong_FromUnsignedLongLong(s->ink[i]);if(!ink||PySet_Add(inks,ink)){Py_XDECREF(ink);Py_DECREF(inks);goto done;}Py_DECREF(ink);
    }
    Py_XDECREF(p->inks);p->inks=inks;Py_INCREF(context);Py_XDECREF(p->context);p->context=context;
    result=Py_BuildValue("OOOn",capsule,p->plane,p->inks,builds);
done:
    Py_XDECREF(normalized);Py_XDECREF(vertical);Py_XDECREF(empty);Py_XDECREF(empty_spans);Py_XDECREF(styles);Py_XDECREF(capsule);return result;
}
