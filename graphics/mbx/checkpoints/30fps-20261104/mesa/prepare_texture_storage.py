"""Avoid faulting unused software texture payloads during context construction.

Keep every cache slot and preserve zero-initialized data on its first access.
The all-one address sentinel cannot name a valid tile (invalid bit is set), and
survives the original invalidation operations until the slot is first filled.
"""
def prepare_payload(directory):
 p=directory/'sp_tex_tile_cache.c';s=p.read_text()
 if 'MBX_LAZY_TEXTURE_PAYLOAD' in s:return
 old='   tc = CALLOC_STRUCT( softpipe_tex_tile_cache );\n   if (tc) {\n      tc->pipe = pipe;'
 new='''   /* MBX_LAZY_TEXTURE_PAYLOAD: metadata now, zero payload on first use.
    * malloc avoids eagerly clearing all software-only texture storage. */
   tc = MALLOC_STRUCT(softpipe_tex_tile_cache);
   if (tc) {
      memset(tc, 0, offsetof(struct softpipe_tex_tile_cache, entries));
      memset((char *)tc + offsetof(struct softpipe_tex_tile_cache, tex_trans),
             0, sizeof(*tc) - offsetof(struct softpipe_tex_tile_cache, tex_trans));
      tc->pipe = pipe;'''
 assert s.count(old)==1;s=s.replace(old,new)
 old='         tc->entries[pos].addr.bits.invalid = 1;'
 assert s.count(old)==2
 # Only construction uses the sentinel; subsequent invalidation retains it.
 at=s.index(old,s.index('sp_create_tex_tile_cache'))
 s=s[:at]+s[at:].replace(old,'         tc->entries[pos].addr.value = UINT64_MAX;',1)
 old='   if (addr.value != tile->addr.value) {'
 new=old+'''
      if (tile->addr.value == UINT64_MAX)
         memset(&tile->data, 0, sizeof(tile->data));
'''
 assert s.count(old)==1;s=s.replace(old,new)
 p.write_text(s)

def prepare_metadata(directory):
 prepare_payload(directory)
 h=directory/'sp_tex_tile_cache.h';s=h.read_text()
 if 'unsigned last_tile_index;' not in s:
  anchor='   struct softpipe_tex_cached_tile entries[NUM_TEX_TILE_ENTRIES];'
  assert s.count(anchor)==1
  s=s.replace(anchor,'   /* Keep address writes off unused 16 KiB payload pages. */\n   union tex_tile_address tile_addrs[NUM_TEX_TILE_ENTRIES];\n   unsigned last_tile_index;\n'+anchor)
  anchor='tc->last_tile->addr.value == addr.value';assert s.count(anchor)==1
  s=s.replace(anchor,'tc->tile_addrs[tc->last_tile_index].value == addr.value')
  h.write_text(s)
 p=directory/'sp_tex_tile_cache.c';s=p.read_text()
 if 'tc->last_tile_index = pos;' in s:return
 s=s.replace('tc->entries[pos].addr','tc->tile_addrs[pos]').replace('tc->entries[i].addr','tc->tile_addrs[i]')
 anchor='   tile = tc->entries + tex_cache_pos( addr );';assert s.count(anchor)==1
 s=s.replace(anchor,'   unsigned pos = tex_cache_pos(addr);\n   tile = tc->entries + pos;')
 s=s.replace('addr.value != tile->addr.value','addr.value != tc->tile_addrs[pos].value')
 s=s.replace('tile->addr.value == UINT64_MAX','tc->tile_addrs[pos].value == UINT64_MAX')
 anchor='      tile->addr = addr;';assert s.count(anchor)==1
 s=s.replace(anchor,anchor+'\n      tc->tile_addrs[pos] = addr;')
 anchor='   tc->last_tile = tile;';assert s.count(anchor)==1
 s=s.replace(anchor,'   tc->last_tile_index = pos;\n'+anchor)
 p.write_text(s)

def prepare_texture_storage(directory):
 prepare_metadata(directory)
 h=directory/'sp_tex_tile_cache.h';s=h.read_text()
 if 'MBX_COMPACT_TEXTURE_METADATA' in s:return
 entry='   struct softpipe_tex_cached_tile entries[NUM_TEX_TILE_ENTRIES];'
 assert s.count(entry)==1;s=s.replace(entry+'\n','')
 anchor='   struct softpipe_tex_cached_tile *last_tile;  /**< most recently retrieved tile */'
 assert s.count(anchor)==1
 s=s.replace(anchor,anchor+'\n\n   /* MBX_COMPACT_TEXTURE_METADATA: all writable metadata precedes payloads. */\n'+entry)
 h.write_text(s)
 p=directory/'sp_tex_tile_cache.c';s=p.read_text()
 suffix='      memset((char *)tc + offsetof(struct softpipe_tex_tile_cache, tex_trans),\n             0, sizeof(*tc) - offsetof(struct softpipe_tex_tile_cache, tex_trans));\n'
 assert s.count(suffix)==1;s=s.replace(suffix,'')
 p.write_text(s)
