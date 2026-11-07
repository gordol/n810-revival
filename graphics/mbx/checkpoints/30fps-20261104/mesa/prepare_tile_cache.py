"""Skip flushing a software tile cache that has never been used.
Once accessed or cleared, the original Mesa behavior is retained permanently.
"""
def prepare_tile_cache(directory):
 h=directory/'sp_tile_cache.h';s=h.read_text()
 if 'boolean ever_used;' not in s:
  anchor='   struct pipe_context *pipe;';assert s.count(anchor)==1
  s=s.replace(anchor,anchor+'\n   boolean ever_used; /* Conservative: never reset after first CPU access. */')
  anchor='   union tile_address addr = tile_address( x, y, layer );';assert s.count(anchor)==1
  s=s.replace(anchor,anchor+'\n   tc->ever_used = TRUE;')
  h.write_text(s)
 p=directory/'sp_tile_cache.c';s=p.read_text()
 if 'if (!tc->ever_used) return;' in s:return
 for name in ('sp_find_cached_tile','sp_tile_cache_clear'):
  start=s.index('\n'+name+'(');brace=s.index('{',start)
  s=s[:brace+1]+'\n   tc->ever_used = TRUE;'+s[brace+1:]
 start=s.index('\nsp_flush_tile_cache(');brace=s.index('{',start)
 s=s[:brace+1]+'\n   if (!tc->ever_used) return;'+s[brace+1:]
 assert 'CALLOC_STRUCT( softpipe_tile_cache )' in s or 'CALLOC_STRUCT(softpipe_tile_cache)' in s
 p.write_text(s)
