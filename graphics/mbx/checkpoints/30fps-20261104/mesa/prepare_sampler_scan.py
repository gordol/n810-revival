"""Avoid touching unused texture-cache objects during derived-state updates."""
def prepare_sampler_scan(path):
    text = path.read_text()
    marker = '/* MBX: unbound sampler caches have no texture to validate. */'
    if marker in text:
        return
    before = '''   for (sh = 0; sh < ARRAY_SIZE(softpipe->tex_cache); sh++) {
      for (i = 0; i < PIPE_MAX_SAMPLERS; i++) {'''
    after = '''   for (sh = 0; sh < ARRAY_SIZE(softpipe->tex_cache); sh++) {
      /* MBX: unbound sampler caches have no texture to validate. */
      const unsigned bound = MIN2(PIPE_MAX_SAMPLERS,
                                  softpipe->num_sampler_views[sh]);
      for (i = 0; i < bound; i++) {'''
    assert text.count(before) == 1
    path.write_text(text.replace(before, after))
