"""Patch private Mesa scratch-buffer ownership with exact upstream anchors."""
def prepare_vertex_buffers(path):
 s=path.read_text()
 if 'struct mbx_vertex_buffers mbx_buffers;' in s:
  s=s.replace('   struct mbx_vertex_buffers mbx_buffers;\n   struct draw_pt_middle_end base;', '   struct draw_pt_middle_end base;\n   struct mbx_vertex_buffers mbx_buffers;')
  path.write_text(s);return
 s=s.replace('struct fetch_pipeline_middle_end {','#include "draw_mbx_buffers.h"\n\nstruct fetch_pipeline_middle_end {')
 s=s.replace('   struct draw_pt_middle_end base;', '   struct draw_pt_middle_end base;\n   struct mbx_vertex_buffers mbx_buffers;')
 s=s.replace('draw_vertex_shader_run(struct draw_vertex_shader *vshader,','draw_vertex_shader_run(struct fetch_pipeline_middle_end *fpme,\n                       struct draw_vertex_shader *vshader,')
 s=s.replace('      draw_vertex_shader_run(vshader,','      draw_vertex_shader_run(fpme, vshader,')
 a='(struct vertex_header *)MALLOC(output_verts->vertex_size *'
 b='(struct vertex_header *)MALLOC(fpme->vertex_size *'
 assert s.count(a)==1 and s.count(b)==1
 s=s.replace(a,'(struct vertex_header *)mbx_vertex_alloc(&fpme->mbx_buffers,1,output_verts->vertex_size *')
 s=s.replace(b,'(struct vertex_header *)mbx_vertex_alloc(&fpme->mbx_buffers,0,fpme->vertex_size *')
 # All GS/assembler outputs remain normally allocated and are freed; only
 # pointers actually owned by this middle-end survive the draw boundary.
 start=s.index('fetch_pipeline_generic(');end=s.index('\nstatic inline unsigned\nprim_type',start)
 body=s[start:end];assert body.count('FREE(vert_info->verts);')==5
 body=body.replace('FREE(vert_info->verts);','mbx_vertex_release(&fpme->mbx_buffers,vert_info->verts);')
 s=s[:start]+body+s[end:]
 a='   FREE(middle);';assert s.count(a)==1
 s=s.replace(a,'   mbx_vertex_buffers_destroy(&fpme->mbx_buffers);\n'+a)
 path.write_text(s)
