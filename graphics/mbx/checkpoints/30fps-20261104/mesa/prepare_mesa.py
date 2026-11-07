"""Apply the owned MBX integration to the pinned, unmodified Mesa source.

Edits are idempotent and require exact anchors. Upstream files stay in the
existing private Mesa build tree; owned additions are kept alongside this file.
"""
from pathlib import Path
import hashlib, json, sys

def prepare(source):
    own = Path(__file__).resolve().parent
    target = source / 'src/gallium/drivers/softpipe'
    def edit(name, before, after):
        path = target / name
        data = path.read_text()
        if after in data:
            return
        if data.count(before) != 1:
            raise RuntimeError(f'Mesa integration anchor changed: {name}')
        path.write_text(data.replace(before, after))
    for name in ('sp_mbx_vgp.h','sp_mbx_vgp_impl.h','mbx_trace.h','sp_mbx.c', 'sp_mbx.h','sp_mbx_backend.h','mbx_startup_gate.h','mbx_cpu_profile.h','mbx_color_cache.h'):
        (target / name).write_bytes((own / name).read_bytes())
    edit('meson.build', "  'sp_buffer.c',", "  'sp_mbx.c',\n  'sp_mbx.h',\n  'sp_buffer.c',")
    # pipe_context must remain at offset zero: Gallium casts its base pointer.
    # Repair the initial bring-up layout as well as handling pristine sources.
    context = target / 'sp_context.h'
    text = context.read_text()
    bad = 'struct sp_mbx_capture;\nstruct softpipe_context {\n   struct sp_mbx_capture *mbx_capture;\n   bool mbx_capture_checked;'
    if bad in text:
        context.write_text(text.replace(bad, 'struct softpipe_context {'))
    edit('sp_context.h', '   struct pipe_context pipe;  /**< base class */',
         '   struct pipe_context pipe;  /**< base class */\n   struct sp_mbx_capture *mbx_capture;\n   bool mbx_capture_checked;')
    for name in ('sp_clear.c', 'sp_setup.c', 'sp_context.c','sp_flush.c'):
        edit(name, '#include "sp_context.h"', '#include "sp_context.h"\n#include "sp_mbx.h"')
    setup=target/'sp_setup.c'
    text=setup.read_text().replace('   sp_mbx_triangle(setup->softpipe, v0, v1, v2, setup->vprovoke);\n','')
    setup.write_text(text)
    edit('sp_setup.c', '   if (!setup_sort_vertices( setup, det, v0, v1, v2 ))',
         '   /* GPU path needs the same winding, but no setup for culled faces. */\n'
         '   if (sp_mbx_early_cull(setup->softpipe)) {\n'
         '      unsigned face=((det < 0.0) ^ setup->softpipe->rasterizer->front_ccw) ? PIPE_FACE_BACK : PIPE_FACE_FRONT;\n'
         '      if (face & setup->cull_face) return;\n'
         '   }\n'
         '   if (!setup_sort_vertices( setup, det, v0, v1, v2 ))')
    edit('sp_setup.c', '   setup_tri_coefficients( setup );',
         '   if (sp_mbx_triangle(setup->softpipe, v0, v1, v2, setup->vprovoke)) return;\n   setup_tri_coefficients( setup );')
    setup.write_text(setup.read_text().replace('   sp_mbx_prepare(sp);\n',''))
    edit('sp_setup.c', '   /* Note: nr_attrs is only used for debugging (vertex printing) */',
         '   sp_mbx_invalidate(sp);\n   /* Note: nr_attrs is only used for debugging (vertex printing) */')
    edit('sp_flush.c', '   /* Enable to dump BMPs of the color/depth buffers each frame */',
         '   sp_mbx_present(softpipe);\n\n   /* Enable to dump BMPs of the color/depth buffers each frame */')
    edit('sp_screen.c','#include "sp_screen.h"','#include "sp_screen.h"\n#include "sp_mbx.h"')
    edit('sp_screen.c','   return "softpipe";','   return sp_mbx_renderer_name();')
    clear=target/'sp_clear.c'
    if 'sp_mbx_clear(softpipe,' not in clear.read_text():
        edit('sp_clear.c', '   if (buffers & PIPE_CLEAR_COLOR) {',
             '   sp_mbx_clear(softpipe, buffers, scissor_state, color, depth);\n\n   if (buffers & PIPE_CLEAR_COLOR) {')
    edit('sp_clear.c', '   sp_mbx_clear(softpipe, buffers, scissor_state, color, depth);',
         '   if (sp_mbx_clear(softpipe, buffers, scissor_state, color, depth)) return;')
    edit('sp_context.c', '   if (softpipe->blitter) {',
         '   sp_mbx_destroy(softpipe);\n\n   if (softpipe->blitter) {')
    draw=source/'src/gallium/auxiliary/draw'
    (draw/'mbx_trace.h').write_bytes((own/'mbx_trace.h').read_bytes())
    (draw/'draw_mbx_fast_vs.h').write_bytes((own/'draw_mbx_fast_vs.h').read_bytes())
    (draw/'draw_mbx_arm_jit.h').write_bytes((own/'draw_mbx_arm_jit.h').read_bytes())
    vp=draw/'draw_vs_exec.c';v=vp.read_text()
    if '#include "draw_mbx_fast_vs.h"' not in v:
        v=v.replace('struct exec_vertex_shader {','#include "draw_mbx_fast_vs.h"\n\nstruct exec_vertex_shader {')
        v=v.replace('   struct tgsi_exec_machine *machine;','   struct tgsi_exec_machine *machine;\n   struct mf_program *fast;')
        v=v.replace('   unsigned slot;','   unsigned slot;\n   float (*verify_output)[4]=NULL;\n   float (*original_output)[4]=output;\n   if(evs->fast){\n      if(!evs->fast->verify){\n         if(mf_run(evs->fast,shader,input,output,constants,const_size,count,input_stride,output_stride))return;\n      }else{\n         verify_output=calloc(count,output_stride);\n         if(!verify_output||!mf_run(evs->fast,shader,input,verify_output,constants,const_size,count,input_stride,output_stride)){free(verify_output);verify_output=NULL;}\n      }\n   }')
        anchor='\n}\n\n\nstatic void\nvs_exec_delete'
        verify='\n   if(verify_output){\n      for(unsigned v=0;v<count;++v){\n         float (*a)[4]=(float (*)[4])((char *)original_output+v*output_stride);\n         float (*b)[4]=(float (*)[4])((char *)verify_output+v*output_stride);\n         for(unsigned s=0;s<shader->info.num_outputs;++s)for(unsigned c=0;c<4;++c)\n            if(memcmp(&a[s][c],&b[s][c],4)){\n               fprintf(stderr,"N810_MBX_VERTEX_MISMATCH vertex=%u slot=%u channel=%u reference=%a fast=%a\\n",v,s,c,a[s][c],b[s][c]);abort();\n            }\n      }\n      evs->fast->verified+=count;\n      if(evs->fast->verified<2048)fprintf(stderr,"N810_MBX_VERTEX_VERIFIED vertices=%u bit_exact=1\\n",evs->fast->verified);\n      free(verify_output);\n   }\n'
        assert anchor in v;v=v.replace(anchor,verify+anchor)
        v=v.replace('   FREE((void*) dvs->state.tokens);','   free(exec_vertex_shader(dvs)->fast);\n   FREE((void*) dvs->state.tokens);')
        v=v.replace('   vs->machine = draw->vs.tgsi.machine;','   vs->machine = draw->vs.tgsi.machine;\n   vs->fast=mf_create(&vs->base);')
        vp.write_text(v)
    v=vp.read_text()
    v=v.replace('free(exec_vertex_shader(dvs)->fast);','mf_destroy(exec_vertex_shader(dvs)->fast);')
    vp.write_text(v)
    marker='      evs->fast->verified+=count;'
    if 'N810_MBX_VERTEX_CHECK_COMPLETE' not in v:
        v=v.replace(marker,marker+'\n      if(evs->fast->verify_limit&&evs->fast->verified>=evs->fast->verify_limit){\n         evs->fast->verify=false;\n         fprintf(stderr,"N810_MBX_VERTEX_CHECK_COMPLETE vertices=%u bit_exact=1 mode=fast\\n",evs->fast->verified);\n      }')
        vp.write_text(v)
    (draw/'draw_mbx_clip.h').write_bytes((own/'draw_mbx_clip.h').read_bytes())
    cp=draw/'draw_cliptest_tmp.h';cv=cp.read_text()
    if 'mbx_clip_cube_inside' not in cv:
        cv=cv.replace('#include "util/u_bitcast.h"','#include "util/u_bitcast.h"\n#include "draw_mbx_clip.h"')
        begin='         if (flags & DO_CLIP_XY_GUARD_BAND) {'
        end='         if (flags & DO_CLIP_USER) {\n            unsigned ucp_mask'
        assert cv.count(begin)==1 and cv.count(end)==1
        cv=cv.replace(begin,'         if (!((flags & DO_CLIP_XY) && (flags & DO_CLIP_FULL_Z) &&\n               !(flags & DO_CLIP_XY_GUARD_BAND) && mbx_clip_cube_inside(position))) {\n'+begin)
        cv=cv.replace(end,'         } /* exact interior fast path */\n\n'+end)
        cp.write_text(cv)
    pp=draw/'draw_pt_fetch_shade_pipeline.c'
    pv=pp.read_text()
    if 'N810_MBX_PIPELINE_PROFILE' not in pv:
        helper = r"""
#include <time.h>
static uint64_t mbx_pipeline_clock(void)
{ struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t); return (uint64_t)t.tv_sec*1000000000+t.tv_nsec; }
static uint64_t mbx_pipeline_ns[4],mbx_pipeline_calls;
static void mbx_pipeline_profile(const uint64_t t[5])
{
   for(unsigned i=0;i<4;++i)mbx_pipeline_ns[i]+=t[i+1]-t[i];
   if((++mbx_pipeline_calls&2047)==0)
      fprintf(stderr,"N810_MBX_PIPELINE_PROFILE calls=%llu fetch_us=%llu shade_us=%llu post_us=%llu emit_us=%llu\n",
         (unsigned long long)mbx_pipeline_calls,
         (unsigned long long)(mbx_pipeline_ns[0]/1000),(unsigned long long)(mbx_pipeline_ns[1]/1000),
         (unsigned long long)(mbx_pipeline_ns[2]/1000),(unsigned long long)(mbx_pipeline_ns[3]/1000));
}
"""
        marker='static void\nfetch_pipeline_generic('
        assert pv.count(marker)==1
        pv=pv.replace(marker,helper+'\n'+marker)
        before,body=pv.split(marker,1)
        body,after=body.split('\nstatic inline unsigned\nprim_type',1)
        edits=[
          ('   int num_vertex_streams = 1;', '   int num_vertex_streams = 1;\n   uint64_t mbx_t[5];mbx_t[0]=mbx_pipeline_clock();'),
          ('   vert_info = &fetched_vert_info;', '   mbx_t[1]=mbx_pipeline_clock();\n   vert_info = &fetched_vert_info;'),
          ('   /* Finished with fetch:', '   mbx_t[2]=mbx_pipeline_clock();\n   /* Finished with fetch:'),
          ('      /* Do we need to run the pipeline?', '      mbx_t[3]=mbx_pipeline_clock();\n      /* Do we need to run the pipeline?'),
          ('   FREE(vert_info->verts);\n   if (free_prim_info)', '   mbx_t[4]=mbx_pipeline_clock();\n   if(draw_current_shader_position_output(draw)!=-1)mbx_pipeline_profile(mbx_t);\n   FREE(vert_info->verts);\n   if (free_prim_info)')]
        for old,new in edits:
            assert body.count(old)==1,old
            body=body.replace(old,new)
        pp.write_text(before+marker+body+'\nstatic inline unsigned\nprim_type'+after)
    pv=pp.read_text()
    if 'mbx_pipeline_enabled' not in pv:
        pv=pv.replace('static uint64_t mbx_pipeline_clock(void)\n{ struct timespec t;',
          'static int mbx_pipeline_enabled=-1;\nstatic uint64_t mbx_pipeline_clock(void)\n{ if(mbx_pipeline_enabled<0)mbx_pipeline_enabled=getenv("N810_MBX_DETAILED_PROFILE")!=NULL; if(!mbx_pipeline_enabled)return 0; struct timespec t;')
        pv=pv.replace('static void mbx_pipeline_profile(const uint64_t t[5])\n{',
          'static void mbx_pipeline_profile(const uint64_t t[5])\n{ if(!mbx_pipeline_enabled)return;')
        pp.write_text(pv)
    pv=pp.read_text()
    if 'mbx_stage_trace' not in pv:
        pv=pv.replace('#include <time.h>', '#include <time.h>\n#include "mbx_trace.h"')
        pv=pv.replace('uint64_t mbx_t[5];mbx_t[0]=mbx_pipeline_clock();', 'uint64_t mbx_t[5];mbx_t[0]=mbx_pipeline_clock();\n   struct mbx_trace_stamp mbx_stage_trace=mbx_trace_begin();')
        for index,label in ((1,'vertex_fetch'),(2,'pipeline_shade'),(3,'post_vertex')):
            anchor=f'mbx_t[{index}]=mbx_pipeline_clock();'
            assert pv.count(anchor)==1
            pv=pv.replace(anchor,anchor+f'\n   mbx_trace_end_n("{label}",mbx_stage_trace,0,4096);mbx_stage_trace=mbx_trace_begin();')
        anchor='if(draw_current_shader_position_output(draw)!=-1)mbx_pipeline_profile(mbx_t);'
        assert pv.count(anchor)==1
        pv=pv.replace(anchor,'if(draw_current_shader_position_output(draw)!=-1){mbx_trace_end_n("primitive_emit",mbx_stage_trace,0,4096);mbx_pipeline_profile(mbx_t);}')
        pp.write_text(pv)
    for name in ('mbx_vgp_capture.h','mbx_vgp_shader.h','mbx_vgp_isa.h','mbx_vgp_isa.c'):
        (draw/name).write_bytes((own/name).read_bytes())
    aux=draw.parent/'meson.build'
    av=aux.read_text()
    if "'draw/mbx_vgp_isa.c'" not in av:
        anchor="  'draw/draw_pt_fetch_shade_pipeline.c',"
        assert av.count(anchor)==1
        aux.write_text(av.replace(anchor,anchor+"\n  'draw/mbx_vgp_isa.c',"))
    pv=pp.read_text()
    if 'mbx_vgp_capture_begin(draw,' not in pv:
        pv=pv.replace('static void\nfetch_pipeline_generic(', '#include "mbx_vgp_capture.h"\n\nstatic void\nfetch_pipeline_generic(')
        pv=pv.replace('   vert_info = &fetched_vert_info;', '   vert_info = &fetched_vert_info;\n   bool mbx_raw_capture=mbx_vgp_capture_begin(draw,vert_info,prim_info);')
        pv=pv.replace('   mbx_t[2]=mbx_pipeline_clock();', '   if(mbx_raw_capture)mbx_vgp_capture_end(vert_info);\n   mbx_t[2]=mbx_pipeline_clock();')
        pp.write_text(pv)
    for name in ('mbx_vgp_topology.h','mbx_vgp_topology.c','mbx_vgp_wire.h','mbx_vgp_draw.h','mbx_packets.h'):
        (draw/name).write_bytes((own/name).read_bytes())
    av=aux.read_text()
    if "'draw/mbx_vgp_topology.c'" not in av:
        aux.write_text(av.replace("  'draw/mbx_vgp_isa.c',","  'draw/mbx_vgp_isa.c',\n  'draw/mbx_vgp_topology.c',"))
    private=draw/'draw_private.h';v=private.read_text()
    if 'mbx_vgp_submit' not in v:
        v=v.replace('struct draw_context\n{','struct draw_vertex_info;\nstruct draw_prim_info;\nstruct draw_context\n{\n   bool (*mbx_vgp_submit)(struct draw_context *,const struct draw_vertex_info *,const struct draw_prim_info *);')
        private.write_text(v)
    pv=pp.read_text()
    if 'draw->mbx_vgp_submit(draw,' not in pv:
        anchor='   bool mbx_raw_capture=mbx_vgp_capture_begin(draw,vert_info,prim_info);'
        assert pv.count(anchor)==1
        pv=pv.replace(anchor,anchor+'\n   if(draw->mbx_vgp_submit && !mbx_raw_capture && (fpme->opt & PT_SHADE) &&\n      draw->mbx_vgp_submit(draw,vert_info,prim_info)){\n      mbx_vertex_release(&fpme->mbx_buffers,vert_info->verts);return;\n   }')
        pp.write_text(pv)
    xlib=source/'src/gallium/winsys/sw/xlib/xlib_sw_winsys.c'
    xv=xlib.read_text()
    stride_anchor='   xlib_dt->stride = align(util_format_get_stride(format, width), alignment);'
    if 'GPU vertex service owns packed RGB565 rows' not in xv:
        assert xv.count(stride_anchor)==1
        xv=xv.replace(stride_anchor,stride_anchor+'\n   /* GPU vertex service owns packed RGB565 rows; allocation base stays aligned. */\n   if(getenv("N810_MBX_GPU_VERTEX") && !strcmp(getenv("N810_MBX_GPU_VERTEX"),"1") &&\n      format==PIPE_FORMAT_B5G6R5_UNORM && width==400 && height==400)xlib_dt->stride=800;')
        xlib.write_text(xv)
    pv=pp.read_text()
    if 'GPU backend owns all post-fetch vertex work' not in pv:
        anchor='   draw_pt_post_vs_prepare(fpme->post_vs,'
        assert pv.count(anchor)==1
        pv=pv.replace(anchor,'   /* GPU backend owns all post-fetch vertex work and rejects unsupported state. */\n   if(draw->mbx_vgp_submit && (opt & PT_SHADE) && !getenv("N810_MBX_VGP_CAPTURE")){\n      *max_vertices=4096;return;\n   }\n'+anchor)
        pp.write_text(pv)
    # Optional direct GPU-image presentation. The existing X image path remains
    # the default and the only path used during software reference captures.
    xp=source/'src/gallium/winsys/sw/xlib/xlib_sw_winsys.c'
    (xp.parent/'mbx_trace.h').write_bytes((own/'mbx_trace.h').read_bytes())
    (xp.parent/'mbx_shared_image.h').write_bytes((own/'mbx_shared_image.h').read_bytes())
    xv=xp.read_text()
    if '#include "mbx_shared_image.h"' not in xv:
        xv=xv.replace('struct xlib_displaytarget\n{','#include "mbx_shared_image.h"\n\nstruct xlib_displaytarget\n{\n   struct mbx_shared_image *mbx_shared;')
        anchor='static volatile int XErrorFlag = 0;'
        bridge='int n810_mbx_shared_bind(struct sw_displaytarget *dt,int fd,size_t bytes)\n{ struct xlib_displaytarget *d=xlib_displaytarget(dt); if(mbx_shared_prepare(&d->mbx_shared,d->display,fd,bytes))return -1; mbx_shared_wait(d->mbx_shared); return 0; }\n\n'
        assert anchor in xv;xv=xv.replace(anchor,bridge+anchor)
        old='   xlib_dt->mapped = xlib_dt->data;'
        xv=xv.replace(old,'   if(xlib_dt->mbx_shared&&(flags&PIPE_MAP_READ))return xlib_dt->mbx_shared->map;\n'+old)
        anchor='   if (xlib_dt->data) {'
        destroy=xv.index('xlib_displaytarget_destroy(')
        at=xv.index(anchor,destroy)
        xv=xv[:at]+'   mbx_shared_destroy(xlib_dt->mbx_shared);\n'+xv[at:]
        anchor='   if (xlib_dt->drawable != xlib_drawable->drawable) {'
        replacement='   if(xlib_dt->mbx_shared){\n      if(mbx_shared_display(xlib_dt->mbx_shared,xlib_drawable->visual,xlib_drawable->depth,xlib_drawable->drawable,xlib_dt->width,xlib_dt->height,xlib_dt->stride,box->x,box->y,box->width,box->height)){fprintf(stderr,"N810_MBX_GPU_FAILED: shared X image presentation failed\\n");exit(1);}\n      return;\n   }\n\n'+anchor
        assert anchor in xv;xv=xv.replace(anchor,replacement)
        xp.write_text(xv)
    from prepare_async import prepare_async
    (xp.parent/'mbx_async_image.h').write_bytes((own/'mbx_async_image.h').read_bytes())
    prepare_async(xp)
    flush=target/'sp_flush.c'
    text=flush.read_text().replace('   if (fence) sp_mbx_finish();\n','')
    text=text.replace('*fence = (void*)(intptr_t)1;', '*fence = n810_mbx_fence_create();')
    flush.write_text(text)
    fence=target/'sp_fence.c';text=fence.read_text()
    if '#include "sp_mbx.h"' not in text:text=text.replace('#include "sp_fence.h"','#include "sp_fence.h"\n#include "sp_mbx.h"')
    text=text.replace('   *ptr = fence;', '   *ptr = n810_mbx_fence_reference(*ptr, fence);')
    text=text.replace('   return TRUE;', '   return n810_mbx_fence_finish(fence, timeout);')
    fence.write_text(text)
    from prepare_vertex_buffers import prepare_vertex_buffers
    (draw/'draw_mbx_buffers.h').write_bytes((own/'draw_mbx_buffers.h').read_bytes())
    prepare_vertex_buffers(pp)
    from prepare_sampler_scan import prepare_sampler_scan
    prepare_sampler_scan(source/'src/gallium/drivers/softpipe/sp_state_derived.c')
    from prepare_float_fetch import prepare_float_fetch
    translate=source/'src/gallium/auxiliary/translate'
    (translate/'mbx_float_fetch.h').write_bytes((own/'mbx_float_fetch.h').read_bytes())
    prepare_float_fetch(translate/'translate_generic.c')
    from prepare_tile_cache import prepare_tile_cache
    prepare_tile_cache(target)
    from prepare_texture_storage import prepare_texture_storage
    prepare_texture_storage(target)
    names = ['sp_mbx.c', 'sp_mbx.h', 'sp_mbx_backend.h', 'mbx_startup_gate.h','mbx_cpu_profile.h','mbx_color_cache.h', 'meson.build', 'sp_context.h', 'sp_setup.c', 'sp_clear.c', 'sp_context.c','sp_flush.c','sp_fence.c','sp_screen.c','sp_tile_cache.c','sp_tile_cache.h','sp_tex_tile_cache.c','sp_tex_tile_cache.h']
    result={name: hashlib.sha256((target/name).read_bytes()).hexdigest() for name in names}
    result['draw_pt_fetch_shade_pipeline.c']=hashlib.sha256(pp.read_bytes()).hexdigest()
    result['draw_vs_exec.c']=hashlib.sha256(vp.read_bytes()).hexdigest()
    result['xlib_sw_winsys.c']=hashlib.sha256(xp.read_bytes()).hexdigest()
    result['mbx_async_image.h']=hashlib.sha256((xp.parent/'mbx_async_image.h').read_bytes()).hexdigest()
    result['mbx_shared_image.h']=hashlib.sha256((xp.parent/'mbx_shared_image.h').read_bytes()).hexdigest()
    result['draw_mbx_buffers.h']=hashlib.sha256((draw/'draw_mbx_buffers.h').read_bytes()).hexdigest()
    result['draw_mbx_clip.h']=hashlib.sha256((draw/'draw_mbx_clip.h').read_bytes()).hexdigest()
    result['draw_mbx_arm_jit.h']=hashlib.sha256((draw/'draw_mbx_arm_jit.h').read_bytes()).hexdigest()
    result['draw_mbx_fast_vs.h']=hashlib.sha256((draw/'draw_mbx_fast_vs.h').read_bytes()).hexdigest()
    result['translate_generic.c']=hashlib.sha256((translate/'translate_generic.c').read_bytes()).hexdigest()
    result['mbx_float_fetch.h']=hashlib.sha256((translate/'mbx_float_fetch.h').read_bytes()).hexdigest()
    return result

if __name__ == '__main__':
    print(json.dumps(prepare(Path(sys.argv[1])), indent=2))
