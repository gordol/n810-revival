"""Optional native opaque text/RGB background path. Imported only by explicit Host.enable_native()."""
import themes
from paint import chrome_ink
from array import array
from math import ceil
from paint import FRAME_INK, FRAME_DEFERRED, frame_template, valid_ink, control_ink, foreground, background


def load(path):
    import importlib.util
    spec=importlib.util.spec_from_file_location('_cellengine',str(path))
    if spec is None or spec.loader is None:raise ImportError('invalid native library')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


class Surface:
    def __init__(self,lib,width,height):
        self.lib=lib;self.pointer=lib.surface(width,height);self.length=width*height
    @property
    def bytes(self):return self.lib.bytes(self.pointer)


class Front(Surface):
    """Sequence compatibility; Cell objects are made only when Python inspects it."""
    def __init__(self,lib,width,height,cell):super().__init__(lib,width,height);self.cell=cell
    def __len__(self):return self.length
    def __getitem__(self,index):
        if isinstance(index,slice):return [self[i] for i in range(*index.indices(self.length))]
        if index<0:index+=self.length
        if not 0<=index<self.length:raise IndexError(index)
        value=self.lib.get(self.pointer,index)
        return self.cell(chr(value[0]),value[1]) if value is not None else None
    def __setitem__(self,index,value):
        if index<0:index+=self.length
        if not 0<=index<self.length:raise IndexError(index)
        self.lib.set(self.pointer,index,ord(value.char),value.color)
    def __iter__(self):
        for i in range(self.length):yield self[i]
    def __eq__(self,other):return list(self)==list(other)


class Compositor:
    def __init__(self,path,cell):
        self.lib=load(path)
        if getattr(self.lib,'frame_ink',0)<2:raise ImportError('native library lacks frame material support')
        if hasattr(self.lib,'flux_surface'):
            import paint
            paint.NATIVE_SCENES=self.lib
        self.cell=cell;self.front=None;self.planes={};self.style_cache=None
        self.outline_plane=None;self.outline_layer=None;self.blank_plane=None;self.blend_plane=None;self.mixed_plane=None;self.mixed_python_cells=0;self.mixed_cache_key=None;self.mixed_background=None;self.mixed_epoch=0
        self.row_builds=0;self.overlays={};self.background_plane=None;self.cell_planes={};self.layer_cells_set=0;self.layer_cells_sampled=0
        self.setup_calls=0;self.flush_calls=0;self.menu_calls=0
        self.mixed_content_plan=None;self.mixed_content_tokens=None
    def text_overlay(self,key,width,height,rows):
        """Cache an opaque text plane using the existing compositor row API."""
        prior=self.overlays.get(key)
        if prior is None or prior[:2]!=(width,height):
            plane=Surface(self.lib,width,height);old_rows=()
        else:plane,old_rows=prior[2:]
        for row,(text,color) in enumerate(rows):
            if row<len(old_rows) and old_rows[row]==(text,color):continue
            self.lib.row(plane.pointer,row,text,color);self.row_builds+=1
        self.overlays[key]=(width,height,plane,rows)
        return plane

    @staticmethod
    def supports_layer(host,w):
        if not w.layer:return True
        if w.name in host.terminal_layers and host.terminal_opacity<1:return False
        try:
            x,y,width,height,cells=w.layer
            return (all(isinstance(v,int) and not isinstance(v,bool) for v in (x,y,width,height))
                    and width>0 and height>0 and len(cells)==width*height
                    and hasattr(cells,'__getitem__'))
        except (TypeError,ValueError,OverflowError):return False

    def cell_plane(self,host,w,bounds,indices,inks,glyph_map=None):
        """Sample only this dirty batch; retain clipped RGB planes across revisions.

        Producer identity/revision controls Host damage, not a full-plane repack.
        Mutable producers must use layer_patch; each requested cell is read again.
        """
        if not w.layer:return None
        x,y,width,height=bounds;lx,ly,lw,lh,cells=w.layer
        left,top=max(0,lx),max(0,ly)
        right,bottom=min(width-2,lx+lw),min(height-2,ly+lh)
        cw,ch=right-left,bottom-top
        if cw<=0 or ch<=0:return None
        key=(cw,ch)
        prior=self.cell_planes.get(w.name)
        if prior is None or prior[0]!=key:
            plane=Surface(self.lib,cw,ch);seen=[None]*(cw*ch)
        else:plane,seen=prior[1:3]
        self.cell_planes[w.name]=(key,plane,seen,cells)
        ox,oy=x+1+left,y+1+top
        for i in indices:
            xx,yy=i%host.width-ox,i//host.width-oy
            if not (0<=xx<cw and 0<=yy<ch):continue
            char,color=cells[(yy+top-ly)*lw+xx+left-lx]
            self.layer_cells_sampled+=1
            if not isinstance(color,int) or not (0<=color<1<<49 or valid_ink(color)):raise ValueError('unsupported cell layer color')
            # Portable layer ASCII policy is ':' for non-ASCII layer scalars.
            if host.ascii and ord(char)>127:char=':'
            if glyph_map is None:char=host.glyphs.cell(char,host.ascii)
            else:
                glyph_map[ord(char)]=ord(host.glyphs.cell(char,host.ascii))
            value=(char,color);at=yy*cw+xx
            if seen[at]!=value:
                self.lib.set(plane.pointer,at,ord(char),color)
                seen[at]=value;self.layer_cells_set+=1
            inks.add(color)
        return plane.pointer,ox,oy

    def mixed_regions(self,host,windows):
        """Only these intervals need portable alpha/shadow semantics."""
        rects=[host.bounds(w) for w in windows]
        if host.shadow_enabled:
            dx,dy={'SE':(1,1),'S':(0,1),'SW':(-1,1),'W':(-1,0),'NW':(-1,-1),'N':(0,-1),'NE':(1,-1),'E':(1,0)}[host.shadow_direction]
            rects += [(x+dx*host.shadow_size,y+dy*host.shadow_size,w,h) for x,y,w,h in rects[:]]
        if host.pager:rects += [r[:4] for r in host.pager.rects]
        if host.launcher_lines:rects.append(host.launcher_bounds())
        if host.drag:rects.append((0,0,host.width,1))
        if host.drag and (host.resize_mode if host.drag[3] else host.move_mode)=='outline':
            x,y,w,h=host.drag[2]
            rects.extend(((x,y,w,1),(x,y+h-1,w,1),(x,y+1,1,h-2),(x+w-1,y+1,1,h-2)))
        for lines in (host.help_lines,host.settings_lines):
            if lines:rects.append((max(0,(host.width-58)//2),1,58,len(lines)))
        rows=[[] for _ in range(host.height)]
        for x,y,w,h in rects:
            for yy in range(ceil(max(0,y)),ceil(min(host.height,y+h))):rows[yy].append((max(0,x),min(host.width,x+w)))
        # Cache the underlying scene, independently of temporary UI overlays.
        # Live drag bounds remain in each window entry; outline bounds do not.
        key=(host.focus,host.style,host.ascii,host.glyphs.key,host.palette,host.tinted,host.control_side(),host.window_fill,host.window_opacity,host.terminal_opacity,host.show_underlying_text,host.shadow_enabled,host.shadow_size,host.shadow_opacity,host.shadow_direction,host.pager.signature if host.pager else None,tuple((w.name,host.bounds(w),w.rolled,w.pinned,w.name in host.maximized,w.layer[:4] if w.layer else None) for w in windows))
        if key!=self.mixed_cache_key:self.mixed_epoch+=1;self.mixed_cache_key=key
        # Text/style changes affect the intersected body rows, not every cached
        # pixel under every window. Keep overlapping windows in painter order.
        content_rows=[[] for _ in range(host.height)]
        for w in windows:
            x,y,width,height=host.bounds(w)
            if w.rolled:continue
            for yy in range(max(0,y+1),min(host.height,y+height-1)):
                row=yy-y-1
                token=(w.lines[row] if row<len(w.lines) else '',tuple(w.styles.get(row,())))
                content_rows[yy].append((x+1,x+width-1,token))
        if self.mixed_content_plan is None or len(self.mixed_content_plan)!=host.height or len(self.mixed_content_tokens[0])!=host.width:
            self.mixed_content_plan=[None]*host.height
            self.mixed_content_tokens=[[()]*host.width for _ in range(host.height)]
        for yy,entries in enumerate(content_rows):
            signature=tuple(entries)
            if self.mixed_content_plan[yy]==signature:continue
            tokens=[()]*host.width
            edges=sorted({0,host.width}|{max(0,min(host.width,x)) for left,right,_ in entries for x in (left,right)})
            for left,right in zip(edges,edges[1:]):
                token=tuple(value for start,end,value in entries if start<=left<end)
                tokens[left:right]=[token]*(right-left)
            self.mixed_content_tokens[yy]=tokens;self.mixed_content_plan[yy]=signature
        self.mixed_dynamic=[host.bounds(w) for w in windows if w.layer]
        return rows

    def supports_outline(self,host):
        return (hasattr(self.lib,'outline') and host.drag is not None and host.pointer_origin is not None
                and (host.resize_mode if host.drag[3] else host.move_mode)=='outline')

    def prepare_outline(self,host):
        self.outline_layer=None
        if not self.supports_outline(host):return
        x,y,width,height=host.drag[2]
        glyphs=tuple(ord(host.glyphs.cell(c,host.ascii)) for c in ('++++-|' if host.ascii else '┌┐└┘─│'))
        key=(width,height,glyphs)
        if self.outline_plane is None or self.outline_plane[0]!=key:
            plane=Surface.__new__(Surface);plane.lib=self.lib;plane.pointer=self.lib.outline(width,height,glyphs);plane.length=width*height
            self.outline_plane=(key,plane)
        self.outline_layer=(self.outline_plane[1].pointer,x,y)

    def supports_blend(self,host,windows):
        scene=getattr(host.backdrop,'native_surface',None) is not None and (host.backdrop.width,host.backdrop.height)==(host.width,host.height)
        return (hasattr(self.lib,'blend_scene') and (scene or not host.backdrop)
                and all(not w.layer or (getattr(self.lib,'blend_cell_layers',False) and host.window_fill and not host.ascii and self.supports_layer(host,w)) for w in windows)
                and not (host.pager or host.launcher_lines or host.help_lines or host.settings_lines or host.drag and not self.supports_outline(host) or host.terrain_loading))

    def blend_flush(self,host,indices,prepared,serialize=True):
        self.flush_calls+=1
        plans,inks,menu,backdrop=prepared
        if self.blend_plane is None or self.blend_plane[:2]!=(host.width,host.height):
            self.blend_plane=(host.width,host.height,Surface(self.lib,host.width,host.height))
        plane=self.blend_plane[2]
        if backdrop is None:
            if self.blank_plane is None or self.blank_plane[:2]!=(host.width,host.height):
                blank=Surface(self.lib,host.width,host.height)
                for row in range(host.height):self.lib.row(blank.pointer,row,'',13)
                self.blank_plane=(host.width,host.height,blank)
            backdrop=self.blank_plane[2]
        dirty=indices if isinstance(indices,memoryview) else array('I',indices)
        dx,dy={'SE':(1,1),'S':(0,1),'SW':(-1,1),'W':(-1,0),'NW':(-1,-1),'N':(0,-1),'NE':(1,-1),'E':(1,0)}[host.shadow_direction]
        phase=host._phase_start()
        args=(plane.pointer,backdrop.pointer,tuple((p,b[0],b[1]) for w,b,p in plans),dirty,
            int(host.window_fill),host.window_opacity,int(host.show_underlying_text),dx,dy,host.shadow_size,host.shadow_opacity if host.shadow_enabled else 0.)
        if any(w.layer for w,b,p in plans):
            layer_inks=set(inks)
            layers=tuple(self.cell_plane(host,w,b,indices,layer_inks) for w,b,p in plans)
            self.lib.blend_scene(*args,layers)
        else:self.lib.blend_scene(*args)
        host._phase_end('native_blend',phase)
        key=('blend',host.palette,host.tinted)
        if self.style_cache is None or self.style_cache[0]!=key:
            colors=host._ansi_colors()
            entries=tuple((color,f'\x1b[0;{foreground(color,colors)};48;{background(color,"5;232" if color==14 else "2;10;10;10" if color>=4 and host.tinted else "5;233")}m') for color in (0,1,2,3,13,14))
            self.style_cache=(key,entries)
        glyphs=array('I',(v for c in sorted(getattr(host.backdrop,'native_glyphs','')) for v in (ord(c),ord(host.glyphs.cell(c,host.ascii)))))
        ordered=memoryview(self.lib.sorted_indices(dirty)).cast('I')
        layers=((self.outline_layer,) if self.outline_layer is not None else ())+((plane.pointer,0,0),)
        output,changed=(self.lib.flush if serialize else getattr(self.lib,'compose',self.lib.flush))(self.front.pointer,layers,ordered,self.style_cache[1],*host.origin,glyphs)
        return output if serialize else '',changed,len(indices)

    def mixed_flush(self,host,indices,regions,serialize=True):
        """Portable blending on occupied cells; C owns retained output/ANSI.

        This is explicitly reported as native_mixed, not C alpha composition.
        Ordinary landscape cells bypass the Python window/decorations walker.
        """
        if host.front is not self.front:
            prior=host.front;self.front=Front(self.lib,host.width,host.height,self.cell)
            for i,value in enumerate(prior):
                if value is not None:self.lib.set(self.front.pointer,i,ord(value.char),value.color)
            host.front=self.front
        if self.mixed_plane is None or self.mixed_plane[:2]!=(host.width,host.height):
            self.mixed_plane=(host.width,host.height,Surface(self.lib,host.width,host.height),[None]*(host.width*host.height))
            self.mixed_values=[None]*(host.width*host.height);self.mixed_background=[None]*(host.width*host.height);self.mixed_stamps=[-1]*(host.width*host.height);self.mixed_content=[None]*(host.width*host.height)
        # 'seen' is the final uploaded plane. mixed_values retains pixels beneath
        # outlines/help/menu so restoring an old edge does not reblend windows.
        plane,seen=self.mixed_plane[2:];inks=set();blank=self.cell(' ',13);updates=[]
        resolved=retained=overlays=0
        misses=dict(cold=0,dynamic_layer=0,geometry=0,content_row=0,background=0)
        loader=host._loader_cell if host.terrain_loading else None
        phase=host._phase_start()
        geometry=tuple((w,*host.bounds(w)) for w in (host.windows if host._frame_windows is None else host._frame_windows) if host.shown(w))
        for i in indices:
            x,y=i%host.width,i//host.width
            value=host.overlay_cell(x,y)
            if value is None:value=host.outline_cell(x,y)
            if value is None:
                source=loader(x,y) if loader else host.backdrop.get((x,y),blank)
                occupied=any(left<=x<right for left,right in regions[y])
                dynamic=occupied and any(xx<=x<xx+w and yy<=y<yy+h for xx,yy,w,h in self.mixed_dynamic)
                content=self.mixed_content_tokens[y][x] if occupied else ()
                geometry_changed=self.mixed_stamps[i]!=self.mixed_epoch
                content_changed=self.mixed_content[i]!=content
                source_changed=self.mixed_background[i]!=source
                if occupied and (dynamic or geometry_changed or content_changed or source_changed):
                    reason='cold' if self.mixed_stamps[i]<0 else 'dynamic_layer' if dynamic else 'geometry' if geometry_changed else 'content_row' if content_changed else 'background'
                    misses[reason]+=1
                    value=host.scene_cell(x,y,include_outline=False,geometry=geometry);self.mixed_python_cells+=1
                    resolved+=1
                    self.mixed_values[i]=value
                elif occupied:value=self.mixed_values[i];retained+=1
                else:value=source;self.mixed_values[i]=source
                self.mixed_background[i]=source;self.mixed_stamps[i]=self.mixed_epoch;self.mixed_content[i]=content
            else:overlays+=1
            char,color=value
            char=host.glyphs.cell(char,host.ascii)
            if not isinstance(color,int) or not (0<=color<1<<49 or valid_ink(color)):raise ValueError('unsupported mixed cell color')
            value=(char,color)
            if seen[i]!=value:updates.append((i,char,color));seen[i]=value
            inks.add(color)
        host._phase_end('mixed_resolve',phase)
        if phase is not None:
            row=host.compose_phases['mixed_resolve']
            for name,count in (('selected_cells',len(indices)),('blended_cells',resolved),('retained_cells',retained),('overlay_cells',overlays)):
                row[name]=row.get(name,0)+count
            for reason,count in misses.items():
                name='miss_'+reason;row[name]=row.get(name,0)+count
        phase=host._phase_start()
        for i,char,color in updates:self.lib.set(plane.pointer,i,ord(char),color)
        host._phase_end('mixed_upload',phase)
        phase=host._phase_start()
        colors=host._ansi_colors();entries=[]
        shade=round((10 if host.tinted else 18)*(1-host.overview_opacity)+24*host.overview_opacity)
        pane=f'2;{shade};{shade};{shade}'
        for color in sorted(inks):
            if color>=1<<48 and not color&FRAME_INK and getattr(self.lib,"rgb_inline",False):continue
            bg=background(color,pane if color in (15,16) else '5;232' if color==14 else '2;10;10;10' if color>=4 and host.tinted else '5;233')
            entries.append((color,f'\x1b[0;{foreground(color,colors)};48;{bg}m'))
        host._phase_end('mixed_palette',phase)
        phase=host._phase_start()
        output,changed=(self.lib.flush if serialize else getattr(self.lib,'compose',self.lib.flush))(self.front.pointer,((plane.pointer,0,0),),array('I',sorted(indices)),tuple(entries),*host.origin)
        host._phase_end('mixed_native_flush',phase)
        return output if serialize else '',changed,len(indices)

    def menu_flush(self,host,indices,serialize=True):
        """Present opaque menu damage over the retained front, without scenery."""
        self.menu_calls+=1
        if host.front is not self.front:
            prior=host.front;self.front=Front(self.lib,host.width,host.height,self.cell)
            for i,value in enumerate(prior):
                if value is not None:self.lib.set(self.front.pointer,i,ord(value.char),value.color)
            host.front=self.front
        x,y,width,height=host.launcher_bounds()
        rows=tuple((host.glyphs.text(line[:width].ljust(width),host.ascii),
                    1 if row==0 or line.startswith('>') else 0)
                   for row,line in enumerate(host.launcher_lines[:height]))
        plane=self.text_overlay('launcher',width,height,rows)
        colors=host._ansi_colors()
        entries=tuple((color,f'\x1b[0;{foreground(color,colors)};48;5;233m') for color in (0,1))
        output,changed=(self.lib.flush if serialize else getattr(self.lib,'compose',self.lib.flush))(self.front.pointer,((plane.pointer,x,y),),
                                      array('I',indices),entries,*host.origin)
        return output if serialize else '',changed,len(indices)

    def prepare(self,host,windows,styles):
        """Prepare one coherent window plan before bounded damage batches."""
        self.setup_calls+=1
        self.prepare_outline(host)
        if host.front is not self.front:
            prior=host.front;self.front=Front(self.lib,host.width,host.height,self.cell)
            # Typical first/reset paint is all invalid. Conversion only when switching
            # from an already-rendered portable mode; never rebuild a whole frame per flush.
            for i,value in enumerate(prior):
                if value is not None:self.lib.set(self.front.pointer,i,ord(value.char),value.color)
            host.front=self.front
        active=set();plans=[];inks={1,2,3,13}
        for w in reversed(windows):
            w._opaque_cache=None;w._opaque_plane_cache=None
            x,y,width,height=host.bounds(w);active.add(w.name)
            window_styles=themes.window_styles(host.palette,w.styles,width,height)
            signature=(width,height,host.focus==w.name,host.style,host.ascii,host.glyphs.key,host.palette,host.tinted,w.name,w.rolled,w.pinned,w.name in host.maximized,host.control_side(),tuple(w.lines),tuple((row,tuple(spans)) for row,spans in sorted(window_styles.items())))
            prior=self.planes.get(w.name)
            if hasattr(self.lib,'window_host'):
                if prior is None or prior[0]!=signature:
                    focused=w.name==host.focus
                    color=chrome_ink(1 if focused else 2,host._ansi_colors(),host.tinted)
                    borders=('+','+','+','+','-','|') if host.ascii else styles[host.style]
                    retained,pointer,colors,built=self.lib.window_host(prior[2] if prior else None,
                        width,height,host.titlebar(w,width)[0],signature[13],signature[14],borders,
                        color,host.glyphs,host.ascii,control_ink,host.palette,focused,signature[:13])
                    plane=Surface.__new__(Surface);plane.lib=self.lib;plane.pointer=pointer;plane.length=width*height
                    self.row_builds+=built
                    prior=(signature,plane,retained,colors);self.planes[w.name]=prior
                inks.update(prior[3])
            else:
                if prior is None or prior[0][:2]!=(width,height):
                    plane=Surface(self.lib,width,height);prior=None
                else:plane=prior[1]
                if prior is None or prior[0]!=signature:
                    focus=w.name==host.focus;color=chrome_ink(1 if focus else 2,host._ansi_colors(),host.tinted)
                    tl,tr,bl,br,horizontal,vertical=('+','+','+','+','-','|') if host.ascii else styles[host.style]
                    title=host.titlebar(w,width)[0]
                    rows=[(host.glyphs.text(title,host.ascii),color,())]
                    vertical=host.glyphs.cell(vertical,host.ascii)
                    bl,br,horizontal=(host.glyphs.cell(c,host.ascii) for c in (bl,br,horizontal))
                    for row in range(max(0,height-2)):
                        text=w.lines[row] if row<len(w.lines) else ''
                        text=host.glyphs.text(text[:width-2],host.ascii)
                        spans=tuple((max(0,start)+1,min(width-2,end)+1,control_ink(role,host.palette,focus)) for start,end,role in window_styles.get(row,()) if max(0,start)<min(width-2,end))
                        rows.append((vertical+text.ljust(width-2)+vertical,0,((0,1,color),(width-1,width,color))+spans))
                    if height>1:rows.append((bl+horizontal*(width-2)+br,color,()))
                    prior_rows=prior[2] if prior is not None else ()
                    for row,entry in enumerate(rows):
                        if row<len(prior_rows) and prior_rows[row]==entry:continue
                        text,color,spans=entry
                        self.lib.row(plane.pointer,row,text,color)
                        for start,end,ink in spans:
                            self.lib.style(plane.pointer,row,start,end,ink)
                        self.row_builds+=1
                    prior=(signature,plane,tuple(rows));self.planes[w.name]=prior
                for _,color,spans in prior[2]:
                    inks.add(color);inks.update(ink for _,_,ink in spans)
            plans.append((w,(x,y,width,height),prior[1].pointer))
        self.planes={name:value for name,value in self.planes.items() if name in active}
        self.cell_planes={name:value for name,value in self.cell_planes.items() if name in active and host.window(name).layer}
        menu=None
        if host.launcher_lines:
            x,y,width,height=host.launcher_bounds()
            rows=tuple((host.glyphs.text(line[:width].ljust(width),host.ascii),
                        1 if row==0 or line.startswith('>') else 0)
                       for row,line in enumerate(host.launcher_lines[:height]))
            plane=self.text_overlay('launcher',width,height,rows)
            menu=(plane.pointer,x,y);inks.update(color for _,color in rows)
        else:self.overlays.clear()
        backdrop=None
        if getattr(host.backdrop,'native_surface',None) is not None:
            backdrop=Surface.__new__(Surface);backdrop.lib=self.lib;backdrop.pointer=host.backdrop.native_surface;backdrop.length=host.backdrop.width*host.backdrop.height
        elif host.backdrop:
            if self.background_plane is None or self.background_plane[:2]!=(host.width,host.height):
                self.background_plane=(host.width,host.height,Surface(self.lib,host.width,host.height))
            backdrop=self.background_plane[2]
        return tuple(plans),frozenset(inks),menu,backdrop

    def scene_snapshot(self,host,windows,styles):
        """Render a fresh opaque scene into private storage without presenting it."""
        if (host.shadow_enabled or host.pager or host.terrain_loading or
            not host.window_fill or host.window_opacity<1 or
            any(w.layer is not None for w in windows) or
            host.backdrop and getattr(host.backdrop,'native_surface',None) is None):
            return None
        plans,inks,menu,backdrop=self.prepare(host,windows,styles)
        original=self.front
        snapshot=Front(self.lib,host.width,host.height,self.cell)
        try:
            self.front=snapshot
            self.flush(host,windows,range(host.width*host.height),styles,
                       prepared=(plans,inks,None,backdrop))
        finally:
            self.front=original
        return snapshot

    def flush(self,host,windows,indices,styles,prepared=None,max_seconds=None,serialize=True):
        self.flush_calls+=1
        plans,inks,menu,backdrop=self.prepare(host,windows,styles) if prepared is None else prepared
        layers=[];glyph_map={}
        batch_inks=set(inks)
        for w,bounds,plane in plans:
            cell_layer=self.cell_plane(host,w,bounds,indices,batch_inks,glyph_map)
            if cell_layer is not None:layers.append(cell_layer)
            layers.append((plane,bounds[0],bounds[1]))
        if menu is not None:layers.insert(0,menu)
        if self.outline_layer is not None:layers.insert(0,self.outline_layer)
        if backdrop is not None:layers.append((backdrop.pointer,0,0))
        colors=host._ansi_colors();layers=tuple(layers)
        if backdrop is not None and getattr(host.backdrop,'native_surface',None) is not None:
            glyph_map.update((ord(c),ord(host.glyphs.cell(c,host.ascii))) for c in host.backdrop.native_glyphs)
        elif backdrop is not None:
            for index in indices:
                value=host.backdrop.get((index%host.width,index//host.width))
                char,color=(' ',13) if value is None else value
                raw=ord(char);glyph_map[raw]=ord(host.glyphs.cell(char,host.ascii))
                self.lib.set(backdrop.pointer,index,raw,color);batch_inks.add(color)
        style_key=(tuple(sorted(batch_inks)),host.palette,host.tinted,host.overview_opacity)
        if self.style_cache is None or self.style_cache[0]!=style_key:
            shade=round((10 if host.tinted else 18)*(1-host.overview_opacity)+24*host.overview_opacity)
            pane=f'2;{shade};{shade};{shade}'
            entries=[]
            for ink in sorted(batch_inks):
                if ink>=1<<48 and getattr(self.lib,"rgb_inline",False):continue
                bg=background(ink,pane if ink in (15,16) else '5;232' if ink==14 else '2;10;10;10' if ink>=4 and host.tinted else '5;233')
                entries.append((ink,f'\x1b[0;{foreground(ink,colors)};48;{bg}m'))
            self.style_cache=(style_key,tuple(entries))
        dirty=memoryview((self.lib.sorted_batches if max_seconds is not None else self.lib.sorted_indices)(indices)).cast('I') if isinstance(indices,memoryview) else array('I',sorted(indices))
        if dirty.itemsize!=4:raise ValueError('native requires 32-bit damage indices')
        glyphs=array('I',(value for pair in sorted(glyph_map.items()) for value in pair))
        if max_seconds is not None:
            output,changed,computed=(self.lib.flush_budget if serialize else getattr(self.lib,'compose_budget',self.lib.flush_budget))(self.front.pointer,layers,dirty,self.style_cache[1],*host.origin,glyphs,max_seconds)
            return output if serialize else '',changed,computed
        output,changed=(self.lib.flush if serialize else getattr(self.lib,'compose',self.lib.flush))(self.front.pointer,layers,dirty,self.style_cache[1],*host.origin,glyphs)
        return output if serialize else '',changed,len(indices)
    @property
    def bytes(self):return (self.front.bytes if self.front else 0)+sum(value[1].bytes for value in self.planes.values())+sum(value[2].bytes for value in self.overlays.values())+(self.background_plane[2].bytes if self.background_plane else 0)+sum(value[1].bytes for value in self.cell_planes.values())+(self.mixed_plane[2].bytes if self.mixed_plane else 0)+(self.blend_plane[2].bytes if self.blend_plane else 0)+(self.blank_plane[2].bytes if self.blank_plane else 0)+(self.outline_plane[1].bytes if self.outline_plane else 0)
