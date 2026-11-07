#define PY_SSIZE_T_CLEAN
#define Py_LIMITED_API 0x030b0000
#include <Python.h>
#include <time.h>
#include <math.h>
#include "cell_engine.c"
static const char *capsule_name="current_world.cells.v1";
static Surface *surface(PyObject *o){return PyCapsule_GetPointer(o,capsule_name);}
static void dispose(PyObject *o){Surface *s=surface(o);if(s)cw_free(s);else PyErr_Clear();}
static PyObject *create(PyObject *self,PyObject *args){(void)self;unsigned w,h;if(!PyArg_ParseTuple(args,"II",&w,&h))return NULL;Surface *s=cw_surface(w,h);if(!s)return PyErr_NoMemory();PyObject *p=PyCapsule_New(s,capsule_name,dispose);if(!p)cw_free(s);return p;}
static PyObject *getcell(PyObject *self,PyObject *args){(void)self;PyObject *o;unsigned i;uint32_t glyph;uint64_t ink;if(!PyArg_ParseTuple(args,"OI",&o,&i))return NULL;Surface *s=surface(o);if(!s)return NULL;int valid=cw_get(s,i,&glyph,&ink);if(valid<0){PyErr_SetString(PyExc_IndexError,"cell index");return NULL;}if(!valid)Py_RETURN_NONE;return Py_BuildValue("IK",glyph,(unsigned long long)ink);}
/* Packed native export for pixel presenters. No per-cell Python objects. */
static PyObject *export_cells(PyObject *self,PyObject *args){
 (void)self;PyObject *o,*indices;Py_buffer view;
 if(!PyArg_ParseTuple(args,"OO",&o,&indices))return NULL;
 Surface *s=surface(o);if(!s)return NULL;
 if(PyObject_GetBuffer(indices,&view,PyBUF_FORMAT|PyBUF_C_CONTIGUOUS))return NULL;
 if(view.itemsize!=4||view.ndim!=1||!view.format||strcmp(view.format,"I")||view.len%4||view.len/4>65536||(view.len&&(uintptr_t)view.buf%4)){
  PyBuffer_Release(&view);PyErr_SetString(PyExc_ValueError,"invalid packed cell indices");return NULL;
 }
 Py_ssize_t count=view.len/4;const uint32_t *ids=view.buf;PyObject *result=PyBytes_FromStringAndSize(NULL,count*16);
 if(!result){PyBuffer_Release(&view);return NULL;}
 char *out=PyBytes_AsString(result);
 for(Py_ssize_t i=0;i<count;++i){uint32_t n=ids[i];if(n>=(size_t)s->w*s->h||!s->valid[n]){Py_DECREF(result);PyBuffer_Release(&view);PyErr_SetString(PyExc_ValueError,"invalid native front cell");return NULL;}
  memcpy(out+i*16,&n,4);memcpy(out+i*16+4,s->glyph+n,4);memcpy(out+i*16+8,s->ink+n,8);
 }
 PyBuffer_Release(&view);return result;
}
static PyObject *setcell(PyObject *self,PyObject *args){(void)self;PyObject *o;unsigned i,glyph;unsigned long long ink;if(!PyArg_ParseTuple(args,"OIIK",&o,&i,&glyph,&ink))return NULL;Surface *s=surface(o);if(!s)return NULL;if(!cw_ink_valid(ink) || glyph>0x10ffff || (glyph>=0xd800 && glyph<=0xdfff) || cw_set(s,i,glyph,ink,1)){PyErr_SetString(PyExc_ValueError,"invalid cell");return NULL;}Py_RETURN_NONE;}
static PyObject *row(PyObject *self,PyObject *args){(void)self;PyObject *o,*text;unsigned y;unsigned long long ink;if(!PyArg_ParseTuple(args,"OIOK",&o,&y,&text,&ink))return NULL;Surface *s=surface(o);if(!s)return NULL;Py_ssize_t size;const char *utf8=PyUnicode_AsUTF8AndSize(text,&size);if(!utf8)return NULL;if(!cw_ink_valid(ink) || cw_row(s,y,(const unsigned char*)utf8,(size_t)size,ink)){PyErr_SetString(PyExc_ValueError,"invalid row");return NULL;}Py_RETURN_NONE;}
static PyObject *style(PyObject *self,PyObject *args){(void)self;PyObject *o;unsigned row,start,end;unsigned long long ink;if(!PyArg_ParseTuple(args,"OIIIK",&o,&row,&start,&end,&ink))return NULL;Surface *s=surface(o);if(!s)return NULL;if(!cw_ink_valid(ink) || cw_style(s,row,start,end,ink)){PyErr_SetString(PyExc_ValueError,"invalid style span");return NULL;}Py_RETURN_NONE;}
static PyObject *bytes_used(PyObject *self,PyObject *o){(void)self;Surface *s=surface(o);if(!s)return NULL;return PyLong_FromSize_t(cw_bytes(s));}
static PyObject *flush_engine(PyObject *self,PyObject *args,int budgeted,int encode){
    (void)self;PyObject *o,*layer_seq,*dirty_obj,*style_seq,*map_obj=Py_None;int ox,oy;
    double seconds=0;
    if(budgeted){if(!PyArg_ParseTuple(args,"OOOOiiOd",&o,&layer_seq,&dirty_obj,&style_seq,&ox,&oy,&map_obj,&seconds))return NULL;if(!isfinite(seconds)||seconds<0||seconds>1){PyErr_SetString(PyExc_ValueError,"invalid rendering budget");return NULL;}}
    else if(!PyArg_ParseTuple(args,"OOOOii|O",&o,&layer_seq,&dirty_obj,&style_seq,&ox,&oy,&map_obj))return NULL;
    Surface *s=surface(o);if(!s)return NULL;
    Py_ssize_t nl=PyTuple_Size(layer_seq),ns=PyTuple_Size(style_seq);
    if(nl<0 || ns<0)return NULL;
    if(!encode)ns=0;
    if(nl>1024 || ns>65536){PyErr_SetString(PyExc_ValueError,"native batch too large");return NULL;}
    Py_buffer dirty;if(PyObject_GetBuffer(dirty_obj,&dirty,PyBUF_FORMAT|PyBUF_C_CONTIGUOUS))return NULL;
    if(dirty.itemsize!=4 || dirty.ndim!=1 || !dirty.format || strcmp(dirty.format,"I") || (uintptr_t)dirty.buf%4 || dirty.len%4){PyBuffer_Release(&dirty);PyErr_SetString(PyExc_ValueError,"invalid damage bytes");return NULL;}
    /* Temporary descriptors scale with windows/colors, never with screen cells. */
    Layer *layers=PyMem_Calloc((size_t)nl+1,sizeof(Layer));Style *styles=PyMem_Calloc((size_t)ns+1,sizeof(Style));
    PyObject *result=NULL;
    if(!layers || !styles){PyErr_NoMemory();goto done;}
    for(Py_ssize_t i=0;i<nl;i++){
        PyObject *entry=PyTuple_GetItem(layer_seq,i),*p;int x,y;
        if(!entry || !PyArg_ParseTuple(entry,"Oii",&p,&x,&y))goto done;
        layers[i].plane=surface(p);if(!layers[i].plane)goto done;layers[i].x=x;layers[i].y=y;
    }
    for(Py_ssize_t i=0;i<ns;i++){
        PyObject *entry=PyTuple_GetItem(style_seq,i),*text;unsigned long long ink;
        if(!entry || !PyArg_ParseTuple(entry,"KO",&ink,&text))goto done;
        styles[i].ink=ink;styles[i].escape=PyUnicode_AsUTF8AndSize(text,NULL);if(!styles[i].escape)goto done;
        if(strlen(styles[i].escape)>192){PyErr_SetString(PyExc_ValueError,"style escape too long");goto done;}
    }
    Py_buffer map={0};
    if(map_obj!=Py_None) {
        if(PyObject_GetBuffer(map_obj,&map,PyBUF_FORMAT|PyBUF_C_CONTIGUOUS))goto done;
        if(map.itemsize!=4 || map.ndim!=1 || !map.format || strcmp(map.format,"I") || map.len%8 || map.len/8>65536 || (map.len && (uintptr_t)map.buf%4)) {
            PyBuffer_Release(&map);PyErr_SetString(PyExc_ValueError,"invalid glyph map bytes");goto done;
        }
        const uint32_t *m=map.buf;
        for(size_t j=0;j<(size_t)map.len/8;j++)if(m[j*2]>0x10ffff || m[j*2+1]>0x10ffff || (m[j*2]>=0xd800 && m[j*2]<=0xdfff) || (m[j*2+1]>=0xd800 && m[j*2+1]<=0xdfff) || (j && m[(j-1)*2]>=m[j*2])) {
            PyBuffer_Release(&map);PyErr_SetString(PyExc_ValueError,"invalid glyph map");goto done;
        }
    }
    size_t changed=0,computed=0,total=(size_t)dirty.len/4;int code=0;Surface collected={0};
    struct timespec start={0},now={0};if(budgeted)clock_gettime(CLOCK_MONOTONIC,&start);
    /* No GIL release while mutable producer planes/buffers are read. Check the
       same time budget at native 64-cell boundaries; metadata is admitted once. */
    do {
        size_t count=budgeted&&total-computed>64?64:total-computed,part=0;
        code=encode?cw_flush_mapped(s,layers,(size_t)nl,(uint32_t*)dirty.buf+computed,count,styles,(size_t)ns,ox,oy,&part,map.buf,(size_t)map.len/8):cw_compose_mapped(s,layers,(size_t)nl,(uint32_t*)dirty.buf+computed,count,&part,map.buf,(size_t)map.len/8);
        if(code)break;
        changed+=part;computed+=count;
        if(encode&&budgeted&&append(&collected,cw_output(s),cw_output_size(s))){PyErr_NoMemory();code=-1;break;}
        if(!budgeted||computed==total)break;
        clock_gettime(CLOCK_MONOTONIC,&now);
        if((double)(now.tv_sec-start.tv_sec)+(now.tv_nsec-start.tv_nsec)*1e-9>=seconds)break;
    }while(computed<total);
    if(map.obj)PyBuffer_Release(&map);
    if(code){free(collected.output);if(!PyErr_Occurred())PyErr_SetString(PyExc_ValueError,"native composition rejected batch");goto done;}
    PyObject *text=PyUnicode_DecodeUTF8(!encode?"":budgeted?(collected.output?collected.output:""):cw_output(s),!encode?0:budgeted?(Py_ssize_t)collected.used:(Py_ssize_t)cw_output_size(s),"strict");
    free(collected.output);
    if(text){result=budgeted?Py_BuildValue("Onn",text,(Py_ssize_t)changed,(Py_ssize_t)computed):Py_BuildValue("On",text,(Py_ssize_t)changed);Py_DECREF(text);}
done:
    PyMem_Free(layers);PyMem_Free(styles);PyBuffer_Release(&dirty);return result;
}
static PyObject *flush(PyObject *self,PyObject *args){return flush_engine(self,args,0,1);}
static PyObject *flush_budget(PyObject *self,PyObject *args){return flush_engine(self,args,1,1);}
static PyObject *compose(PyObject *self,PyObject *args){return flush_engine(self,args,0,0);}
static PyObject *compose_budget(PyObject *self,PyObject *args){return flush_engine(self,args,1,0);}
#include "window_host.c"
#include "scene_host.c"
#include "blend_host.c"
#include "input_pump.c"
static PyObject *outline(PyObject *self,PyObject *args){
    (void)self;unsigned w,h;PyObject *chars;
    if(!PyArg_ParseTuple(args,"IIO",&w,&h,&chars))return NULL;
    if(w<2||!dimensions(w,h)||!PyTuple_Check(chars)||PyTuple_Size(chars)!=6){PyErr_SetString(PyExc_ValueError,"invalid outline geometry/glyphs");return NULL;}
    uint32_t g[6];
    for(unsigned i=0;i<6;i++){
        unsigned long value=PyLong_AsUnsignedLong(PyTuple_GetItem(chars,i));
        if(PyErr_Occurred())return NULL;
        if(value>0x10ffff||(value>=0xd800&&value<=0xdfff)){PyErr_SetString(PyExc_ValueError,"invalid outline glyph");return NULL;}
        g[i]=(uint32_t)value;
    }
    Surface *s=cw_surface(w,h);if(!s)return PyErr_NoMemory();
    for(unsigned x=0;x<w;x++){
        cw_set(s,x,x==0?g[0]:x==w-1?g[1]:g[4],3,1);
        if(h>1)cw_set(s,(h-1)*w+x,x==0?g[2]:x==w-1?g[3]:g[4],3,1);
    }
    for(unsigned y=1;y+1<h;y++){cw_set(s,y*w,g[5],3,1);cw_set(s,y*w+w-1,g[5],3,1);}
    PyObject *result=PyCapsule_New(s,capsule_name,dispose);if(!result)cw_free(s);return result;
}
static PyMethodDef methods[]={
 {"compose",compose,METH_VARARGS,"Compose retained cells without terminal serialization."},
 {"compose_budget",compose_budget,METH_VARARGS,"Compose bounded cells without terminal serialization."},
 {"input_start",input_start,METH_VARARGS,"Start bounded native input acquisition."},
 {"input_fileno",input_fileno,METH_O,"Input readiness descriptor."},
 {"input_read",input_read,METH_O,"Read ordered raw input and explicit loss count."},
 {"input_discard",input_discard,METH_O,"Discard pre-resync buffered input."},
 {"input_close",input_close,METH_O,"Stop and join input acquisition."},
 {"outline",outline,METH_VARARGS,"Build a hollow retained move/resize boundary."},
 {"blend_scene",blend_scene,METH_VARARGS,"Compose text-window alpha and shadows over a retained scene in bounded batches."},
 {"flush_budget",flush_budget,METH_VARARGS,"Compose bounded 64-cell batches within an explicit time budget."},
 {"sorted_batches",sorted_batches,METH_O,"Order within priority-preserving 64-cell batches."},
 {"sorted_indices",sorted_indices,METH_O,"Order a bounded native index batch."},
 {"damage_new",dirty_new,METH_VARARGS,"Allocate a bounded dirty map."},
 {"damage_count",dirty_count,METH_O,"Count dirty cells."},
 {"damage_has",dirty_has,METH_VARARGS,"Test a dirty index."},
 {"damage_rect",dirty_rect,METH_VARARGS,"Mark a clipped rectangle."},
 {"damage_update",dirty_update,METH_VARARGS,"Add/remove bounded indices."},
 {"damage_merge",dirty_merge,METH_VARARGS,"Union/intersect/subtract dirty maps."},
 {"damage_take",dirty_take,METH_VARARGS,"Select a bounded priority batch."},
 {"damage_intersects",dirty_intersects,METH_VARARGS,"Test a packed index batch."},
 {"damage_diff",dirty_diff,METH_VARARGS,"Compare native scene planes."},
 {"scene_has",scene_has,METH_VARARGS,"Test a native overlay cell."},
 {"scene_indices",scene_indices,METH_O,"Export retained overlay order."},
 {"nebula",nebula,METH_VARARGS,"Build the shared Flux backdrop."},
 {"flux_surface",flux_surface,METH_VARARGS,"Build a bounded native Flux plane."},
 {"window_host",window_host,METH_VARARGS,"Prepare retained window rows with the existing app glyph and role policies."},
 {"surface",create,METH_VARARGS,"Allocate retained packed surface."},
 {"export_cells",export_cells,METH_VARARGS,"Export a bounded packed native cell batch."},
 {"get",getcell,METH_VARARGS,"Read a cell for portable fallback/inspection."},
 {"set",setcell,METH_VARARGS,"Seed a cell on backend switch."},
 {"row",row,METH_VARARGS,"Replace a retained UTF-8 row."},
 {"style",style,METH_VARARGS,"Apply a retained ink span."},
 {"bytes",bytes_used,METH_O,"Owned native allocation size."},
 {"flush",flush,METH_VARARGS,"Compose dirty cells and encode ANSI in one batch."},
 {NULL,NULL,0,NULL}};
static struct PyModuleDef definition={PyModuleDef_HEAD_INIT,"_cellengine","Optional opaque text compositor.",-1,methods,NULL,NULL,NULL,NULL};
PyMODINIT_FUNC PyInit__cellengine(void){PyObject *m=PyModule_Create(&definition);if(m && PyModule_AddIntConstant(m,"rgb_inline",1)<0){Py_DECREF(m);return NULL;}if(m && PyModule_AddIntConstant(m,"frame_ink",2)<0){Py_DECREF(m);return NULL;}if(m && PyModule_AddIntConstant(m,"blend_cell_layers",1)<0){Py_DECREF(m);return NULL;}return m;}
