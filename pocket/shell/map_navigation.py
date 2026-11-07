"""Map-local navigation adapted from the accepted preview; no host import hooks."""
import math
import os
from dataclasses import dataclass
from map_target import Target
from map_overview import Overview,LocalOverview,contains,corners

@dataclass
class Drag:
    x:float
    y:float
    center:tuple
    span:float
    width:int
    height:int
    image_width:int
    image_height:int
    projection:object
    view_center:tuple
    view_span:float
    dragged:bool=False
    moving_box:bool=False

    def position(self,column,row):
        x=(column+.5)*self.image_width/self.width-.5
        y=(row-2+.5)*self.image_height/self.height-.5
        if callable(getattr(self.projection,'unproject',None)):return self.projection.unproject(x,y)
        view=self.projection
        center=getattr(view,'center',self.view_center)
        span=getattr(view,'span',self.view_span)
        width=getattr(view,'width',self.image_width);height=getattr(view,'height',self.image_height)
        degrees=span/max(1,width-1)/111.32
        return (center[0]-(y-(height-1)/2)*degrees*getattr(view,'cell_aspect',2),
                center[1]+(x-(width-1)/2)*degrees/max(.000001,math.cos(math.radians(center[0]))))

    def destination(self,column,row):
        column=max(self.x-self.width*2,min(self.x+self.width*2,column))
        row=max(self.y-self.height*2,min(self.y+self.height*2,row))
        start=self.position(self.x,self.y);end=self.position(column,row)
        if self.moving_box:start,end=end,start
        return (max(-85,min(85,self.center[0]+start[0]-end[0])),
                (self.center[1]+start[1]-end[1]+180)%360-180)


def map_class(Base):
    from offline_map import Plane,ScaledPlane,ContextPlane,raster_size
    from paint import ink
    class StationMap(Base):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs)
            self.target_box=Target()
            self.preview=os.environ.get('CW_MAP_MODE','preview')=='preview'
            self._target_drag=None;self._target_layer=None;self._target_layer_key=None
            self._overview_patch=None;self._overview_published_layer=None;self._detail_request=None;self._loading_overview=None
            self._zoom_context_image=None
            self._zoom_context_view=None
            self._zoom_applied=None
            self._pan_display_source=None
            self.maidenhead_grid='auto'
            self._overview=Overview();self._shown_image=None;self._detail_lines=None
            self._local_overview=LocalOverview(self.renderer);self._overview_camera=None
            self.full_overview=False;self.side_overview=os.environ.get('CW_MAP_OVERVIEW','manual')=='side'
            self._locator_overview=Overview();self._locator_rect=None;self._locator_drag=None;self._locator_center=None
            self._locator_layer=None;self._locator_layer_key=None;self._header_hits=()
        def interaction_deactivated(self):
            self.cancel_pointer()
        def poll(self):
            return super().poll()
        def poll_interval(self):return None
        def close(self):
            self.cancel_pointer();super().close()
        def apply_target(self,force=True):
            if not force or self.target_box.held:return True
            view=self.target_box.view or (tuple(self.center),self.span)
            self.target_box.choose(*view)
            self.tracks.pause()
            shown=self._shown_image
            self._loading_overview=shown if self.full_overview else None
            self._detail_request=(view,self.target_box.revision)
            self._zoom_applied=None
            return True
        def zoom_feedback(self):
            if self._detail_request is not None:
                span=self._detail_request[0][1]
                if self.renderer.error:return f'Zoom unavailable · {self.distance_label(span)} · Esc cancel'
                return f'Zoom accepted · Loading {self.distance_label(span)} · Esc cancel'
            return self._zoom_applied or ''
        def preview_zoom(self):
            if self.target_box.view is not None and self.renderer.module is not None:
                from map_overview import zoom_context
                center,span=self.target_box.view
                retained=self._zoom_context_image
                if retained is not None and span>=retained.projection.span*.2 and contains(retained,center,span,self.width,max(1,self.height-3)):
                    self._detail_request=None;self._loading_overview=None
                    return True
                if retained is not None and retained.projection.span*.2<=span<=retained.projection.span*.6:
                    from offline_map import Image,ReprojectedPlane
                    view=self.renderer.module.Viewport(tuple(center),retained.projection.span,retained.width,retained.height)
                    self._zoom_context_image=Image(retained.width,retained.height,ReprojectedPlane(retained,view),
                        retained.legend,(),0.,view,'pan-preview')
                    self._zoom_context_view=(tuple(center),view.span)
                    self._detail_request=None;self._loading_overview=None
                    return True
                self._zoom_context_image=zoom_context(self._shown_image or self._image,self._overview,self.renderer.module,center,span,self.width,max(1,self.height-3))
                image=self._zoom_context_image;projection=getattr(image,'projection',None)
                self._zoom_context_view=(tuple(center),span*2.5) if projection is None or span<projection.span*.2 else (tuple(projection.center),projection.span)
            self._detail_request=None;self._loading_overview=None
            return True
        def _resolve_detail(self):
            request=self._detail_request
            if request is None:return
            view,revision=request
            if self.target_box.revision!=revision or self.target_box.view!=view:
                self._detail_request=None;self._loading_overview=None;self._zoom_context_image=None;return
            width,height=raster_size(self.width,self.height-3)
            image=self.renderer.frame(*view,width,height)
            projection=getattr(image,'projection',None)
            if image is None or projection is None or self.target_box.held or self._target_drag is not None:return
            if (image.width,image.height)!=(width,height) or tuple(projection.center)!=tuple(view[0]) or projection.span!=view[1]:return
            self.center,self.span=view;self._image=image;self._image_view=view
            self.target_box.cancel();self._detail_request=None;self._loading_overview=None;self.full_overview=False
            self._zoom_context_image=None
            self._zoom_applied='Zoom applied · '+self.distance_label(self.span)
        def discard_target(self):
            self._zoom_applied=None
            self._detail_request=None;self._loading_overview=None;self._zoom_context_image=None;self.target_box.cancel();self.full_overview=False
            return True
        def open_overview(self):
            center,span=self.target_box.view or (self.center,self.span)
            self._overview_camera=(tuple(center),min(2000.,span*4))
            self._zoom_context_image=None;self._zoom_context_view=None
            self._detail_request=None;self._loading_overview=None
            self.full_overview=True
        def accept_overview(self):
            return self.apply_target()
        def key(self,key):
            self._zoom_applied=None
            if key=='u':self.maidenhead_grid={'auto':'on','on':'off','off':'auto'}[self.maidenhead_grid];return True
            if key=='z':
                self.renderer.forest_roads=not getattr(self.renderer,'forest_roads',False)
                self.renderer.ready.clear();self.renderer.regions.ready.clear()
                self._image=None;self._image_view=None;self._shown_image=None;self._display_image=None
                self._zoom_context_image=None;self._local_overview=LocalOverview(self.renderer)
                return True
            self.double_tap.reset()
            had_locator=self._locator_drag is not None
            self._locator_drag=None;self._locator_center=None
            self.end_target_drag()
            if self.filter_open:return super().key(key)
            if key in ('o','s'):
                self.double_tap.reset();self._locator_drag=None;self._locator_center=None
                if key=='o':
                    if self.full_overview:return self.discard_target()
                    self.open_overview()
                else:
                    self._detail_request=None;self._loading_overview=None
                    self.side_overview=not self.side_overview
                    if self.side_overview and self.full_overview:
                        self.full_overview=False
                        if self.target_box.view is not None:self.target_box.choose(*self.target_box.view)
                return True
            if key in ('\x1b','escape','back') and had_locator:
                self._locator_drag=None;self._locator_center=None;return True
            if key in ('\r','\n') and self.full_overview:return self.accept_overview()
            if key in ('\x1b','escape','back') and self.full_overview:
                return self.discard_target()
            if key=='v':
                self._zoom_context_image=None;self._detail_request=None
                super().cancel_pointer()
                self.target_box.cancel();self._target_drag=None;self.preview=not self.preview;return True
            if self.full_overview and key in ('+','=','-','left','right','up','down'):
                self.tracks.pause()
                if key in ('+','=','-'):
                    self.target_box.zoom(self.center,self.span,key!='-')
                else:self.target_box.pan(self.center,self.span,key)
                return True
            if key in ('\r','\n') and self.target_box.view is not None:return self.apply_target()
            if self.preview:
                if key in ('\x1b','escape','back') and self.target_box.view is not None:
                    self._target_drag=None;return self.discard_target()
                if key in ('\r','\n') and self.target_box.view is not None:return self.apply_target()
                if key in ('+','=','-','left','right','up','down'):
                    self.tracks.pause()
                    if key in ('+','=','-'):
                        changed=self.target_box.zoom(self.center,self.span,key!='-')
                    else:self.target_box.pan(self.center,self.span,key)
                    self.preview_zoom()
                    return True
            self.target_box.cancel();result=super().key(key)
            return result
        def zoom_target_at_pointer(self,column,row,width,out=False):
            center,old_span=self.target_box.view or (tuple(self.center),self.span)
            span=max(getattr(self,'minimum_span',.25),min(2000.,old_span*(1.25 if out else .8)))
            if span==old_span:return False
            height=max(1,self.height-3);width=max(1,width)
            column=max(0,min(width-1,column));row=max(2,min(height+1,row))
            image=self._shown_image or self._image
            view_center,view_span=self._image_view or (self.center,self.span)
            camera=Drag(column,row,tuple(center),old_span,width,height,
                        getattr(image,'width',width),getattr(image,'height',height),
                        getattr(image,'projection',None),tuple(view_center),view_span)
            lat,lon=camera.position(column,row)
            rw,rh=raster_size(width,height)
            x=(column+.5)*rw/width-.5;y=(row-2+.5)*rh/height-.5
            degrees=span/max(1,rw-1)/111.32
            lat=max(-85,min(85,lat+(y-(rh-1)/2)*degrees*2))
            lon-=(x-(rw-1)/2)*degrees/max(.000001,math.cos(math.radians(lat)))
            return self.target_box.choose((lat,(lon+180)%360-180),span)
        def zoom_at_pointer(self,column,row,width,out=False):
            if self.full_overview:
                self.end_target_drag();self.double_tap.reset()
                self.zoom_target_at_pointer(column,row,width,out)
                return True
            if not self.preview:
                self.end_target_drag()
                original=self._image,self._image_view
                shown=self._shown_image
                if shown is not None and shown.source=='cached-overview':
                    self._image=shown;self._image_view=(shown.projection.center,shown.projection.span)
                elif self._image_view!=(self.center,self.span):
                    # Accumulate wheel input against the requested camera while
                    # the retained image waits for worker completion.
                    self._image=None;self._image_view=(self.center,self.span)
                try:
                    result=super().zoom_at_pointer(column,row,width,out)
                    return result
                finally:self._image,self._image_view=original
            self.end_target_drag();self.double_tap.reset()
            self.tracks.pause();changed=self.zoom_target_at_pointer(column,row,width,out)
            if changed:self.preview_zoom()
            return True
        def end_target_drag(self):
            self._pan_drag=None;self._target_drag=None
            self.target_box.held=False
        @property
        def pointer_captured(self):return self._locator_drag is not None or self._target_drag is not None or super().pointer_captured
        def cancel_pointer(self):
            self._pan_display_source=None
            self._detail_request=None;self._loading_overview=None
            self._zoom_context_image=None
            self.double_tap.reset()
            self.target_box.cancel();self._target_drag=None;self._locator_drag=None;self._locator_center=None;super().cancel_pointer()
        def pointer_event(self,event,width):
            _,button,x,y,released=event
            if self._locator_drag is not None or (self._target_drag is None and self._pan_drag is None and self.locator_hit(x,y)):return self.locator_pointer(x,y,button,released)
            if y==0 and button==0 and not released:return self.pointer(x,y,width,button,released)
            if self.filter_open or (not self.preview and self._target_drag is None and not self.showing_overview()):return super().pointer_event(event,width)
            if self.full_overview:return self.pointer(x,y,width,button,released)
            context=(self._image_view or (self.center,self.span),width,self.height,id(self._image),self.filter_open)
            empty=0<=x<width and 2<=y<self.height-1 and not self.entities_at(x,y)
            zoom=self.double_tap.feed(event,empty=empty,context=context)
            if self._target_drag is not None:
                drag=self._target_drag;px,py=drag.x,drag.y
                left,top,right,bottom=getattr(event,'bounds',(x,y,x,y))
                if max(abs(left-px),abs(right-px),abs(top-py),abs(bottom-py))>1:drag.dragged=True
            handled=self.pointer(x,y,width,button,released)
            return self.zoom_at_pointer(x,y,width) if zoom else handled
        def pointer(self,column,row,width,button=0,released=False):
            if self.filter_open:return super().pointer(column,row,width,button,released)
            if self._locator_drag is not None or (self._target_drag is None and self._pan_drag is None and self.locator_hit(column,row)):return self.locator_pointer(column,row,button,released)
            if button==0 and not released and row==0:
                for start,length,key in self._header_hits:
                    if start<=column<start+length:return self.key(key)
                if column<20:return self.key('v')
            if self.full_overview:return self.overview_pointer(column,row,width,button,released)
            if not self.preview and self._target_drag is None and not self.showing_overview():return super().pointer(column,row,width,button,released)
            if button&64:return self.zoom_at_pointer(column,row,width,bool(button&1))
            if self._target_drag is not None:
                drag=self._target_drag
                if (width,max(1,self.height-3))!=(drag.width,drag.height):
                    self.cancel_pointer();return True
                if abs(column-drag.x)>1 or abs(row-drag.y)>1:drag.dragged=True
                if drag.dragged:
                    self.center,self.span=drag.destination(column,row),drag.span
                    self.target_box.cancel();self._detail_request=None
                    self._zoom_context_image=None;self._zoom_context_view=None
                if released:
                    self._target_drag=None;self.target_box.held=False
                    if not drag.dragged:self._pan_display_source=None
                    if not drag.dragged and self.target_box.view is None and self._detail_request is None:
                        # A stationary click retains the normal station selection path.
                        super().pointer(drag.x,drag.y,width,0,False);super().pointer(column,row,width,0,True)
                return True
            if button==0 and not released and 0<=column<width and 2<=row<self.height-1:
                center,span=self.target_box.view or (self.center,self.span)
                image=self._shown_image or self._image;view_center,view_span=self._image_view or (self.center,self.span)
                self._pan_display_source=self._pan_display_source or image
                self._target_drag=Drag(column,row,tuple(center),span,max(1,width),max(1,self.height-3),
                    getattr(image,'width',max(1,width)),getattr(image,'height',max(1,self.height-3)),
                    getattr(image,'projection',None),tuple(view_center),view_span)
                self.tracks.pause();self.target_box.held=self.preview;return True
            return super().pointer(column,row,width,button,released)
        def overview_pointer(self,column,row,width,button,released):
            if button&64:return self.zoom_at_pointer(column,row,width,bool(button&1))
            drag=self._target_drag
            if drag is not None:
                if (width,max(1,self.height-3))!=(drag.width,drag.height):
                    self.cancel_pointer();return True
                if abs(column-drag.x)>1 or abs(row-drag.y)>1:drag.dragged=True
                if drag.dragged:self.target_box.choose(drag.destination(column,row),drag.span)
                if released:
                    self.end_target_drag();return True
                return True
            if released or button&32:return True
            if button!=0 or not (0<=column<width and 2<=row<self.height-1):return False
            image=self._shown_image
            if image is None:return False
            center,span=self.target_box.view or (self.center,self.span)
            drag=Drag(column,row,tuple(center),span,width,max(1,self.height-3),image.width,image.height,
                      image.projection,tuple(center),span,moving_box=True)
            lat,lon=drag.position(column,row)
            (west,north),(east,south)=corners(center,span,width,max(1,self.height-3))
            # Pick up the box without snapping its center to the grab point.
            # An outside click places the same-sized box at that location.
            if not (west<=lon<=east and south<=lat<=north):
                drag.center=(max(-85,min(85,lat)),(lon+180)%360-180)
                self.target_box.choose(drag.center,span)
            self._target_drag=drag;self.target_box.held=True;self.tracks.pause()
            return True
        def showing_overview(self):
            return self._shown_image is not None and self._shown_image.source=='cached-overview'
        def entities_at(self,column,row):
            return () if self.showing_overview() else super().entities_at(column,row)
        def quality_label(self,image):
            state=getattr(image,'pack_status',None)
            if not state:return ''
            def meters(value):return f'{value:.0f} m' if value<1000 else f'{value/1000:.2g} km'
            grid=state.get('native_spacing_m');cells=state.get('requested_spacing_m')
            label='Map '+state.get('pack','regional')
            if grid is not None:label+=' · '+meters(grid)+' grid'
            if cells is not None:label+=' / '+meters(cells)+' display'
            if state.get('resolution_limited'):label+=' · best available at this extent'
            return label+' · '+state.get('dem_resolution','')
        def locator_hit(self,x,y):
            rect=self._locator_rect
            return bool(self.side_overview and not self.full_overview and rect and rect[0]<=x<rect[0]+rect[2] and rect[1]<=y<rect[1]+rect[3])
        def locator_pointer(self,x,y,button,released):
            if self._locator_rect is None:return False
            if button&64:return True
            if self._locator_drag is None:
                if released or button&32:return True
                if button!=0:return False
                left,top,width,height,image=self._locator_rect
                if not (left<=x<left+width and top<=y<top+height):return True
                self.end_target_drag();self.double_tap.reset();self._locator_drag=self._locator_rect
            left,top,width,height,image=self._locator_drag
            # Clamp to the fixed locator image, never to a newly arriving detail view.
            px=max(0,min(width-1,x-left));py=max(0,min(height-1,y-top))
            self._locator_center=image.projection.unproject((px+.5)*image.width/width-.5,(py+.5)*image.height/height-.5)
            if released:
                self.tracks.pause();self.center=tuple(self._locator_center)
                self._locator_drag=None;self._locator_center=None
            return True
        def locator_image(self,width,height):
            image=self._locator_overview.image(self.renderer.module,width,height)
            if image is not None:return image
            # Source-only installs do not ship the historical Puget preview.
            # Reuse current terrain immediately and refine through the same
            # bounded map worker, using the installed area instead of a fixed QTH.
            source=self._shown_image or self._image
            if source is None or self.renderer.module is None:return None
            from map_overview import LocalOverview,CropProjection,contains
            from offline_map import Image,ReprojectedPlane
            camera=getattr(self,'_locator_camera',None)
            previous=getattr(self,'_live_locator_image',None)
            if camera is None or previous is not None and not contains(previous,self.center,self.span,self.width,max(1,self.height-3)):
                camera=(tuple(self.center),min(2000.,max(160.,self.span*4)))
                self._locator_camera=camera
            if not hasattr(self,'_live_locator'):self._live_locator=LocalOverview(self.renderer)
            image=self._live_locator.image(self.renderer.module,width,height,*camera)
            key=(id(image or source),camera,width,height)
            if key!=getattr(self,'_live_locator_key',None):
                view=self.renderer.module.Viewport(*camera,width,height)
                cells=ReprojectedPlane(image or source,view)
                self._live_locator_image=Image(width,height,cells,'Installed-area locator',(),0.,CropProjection(view,0,0,width,height),'locator')
                self._live_locator_key=key
            return self._live_locator_image
        def locator(self,lines):
            self._locator_layer=None;self._locator_rect=None
            if not self.side_overview or self.full_overview or self.filter_open:return tuple(lines)
            width,height=self.width,max(1,self.height-3)
            if width<72 or height<10:
                lines[1]=('Locator needs a wider map · S hide')[:width].ljust(width);return tuple(lines)
            pane=min(32,width//3);left=width-pane;inner=pane-2
            image=self.locator_image(192,96)
            if image is None:return tuple(lines)
            iw=inner;ih=max(1,round(iw*image.height/image.width))
            # Use the sidebar's full width. Very short windows crop the
            # overview with its matching projection instead of squeezing it.
            limit=max(4,self.height-12)
            if ih>limit:
                image=self.locator_image(inner,limit)
                ih=max(1,round(iw*image.height/image.width))
            top=3;ix=left+1+(inner-iw)//2;iy=top+1
            self._locator_rect=(ix,iy,iw,ih,image)
            if self._locator_drag is not None and self._locator_drag[:4]!=self._locator_rect[:4]:
                self._locator_drag=None;self._locator_center=None
            base_layer=self._target_layer or super().layer()
            if base_layer is None:return tuple(lines)
            x0,y0,bw,bh,base=base_layer
            # The pane overlays the existing main map; enabling it never changes
            # the main camera, viewport dimensions or terrain request.
            center=self._locator_center or (self.target_box.view or (self.center,self.span))[0]
            span=(self.target_box.view or (self.center,self.span))[1]
            points=[image.projection.project(*point) for point in corners(center,span,width,height)]
            box=tuple((round((x+.5)*iw/image.width-.5)+ix,round((y+.5)*ih/image.height-.5)+iy) for x,y in points)
            key=(id(base),left,top,iw,ih,box,bw,bh)
            if key!=self._locator_layer_key:
                style=ink(185,195,200,background=(14,23,28));edge=ink(105,150,155,background=(14,23,28));gold=ink(255,210,65,background=(45,30,12))
                overlay={}
                def put(x,y,char,color=style):
                    if x0<=x<x0+bw and y0<=y<y0+bh:overlay[(y-y0)*bw+x-x0]=(char,color)
                for y in range(2,self.height-1):
                    for x in range(left,width):put(x,y,' ',style)
                    put(left,y,'│',edge)
                for dx,ch in enumerate(' Map sidebar · S hide '[:pane-1]):put(left+1+dx,2,ch,edge)
                for dy in range(ih):
                    for dx in range(iw):
                        char,color=image.cells[min(image.height-1,dy*image.height//ih)*image.width+min(image.width-1,dx*image.width//iw)]
                        put(ix+dx,iy+dy,char,color)
                (ax,ay),(bx,by)=box
                for x in range(max(ix,ax),min(ix+iw,bx+1)):
                    for y in (ay,by):
                        if iy<=y<iy+ih:put(x,y,'─',gold)
                for y in range(max(iy,ay),min(iy+ih,by+1)):
                    for x in (ax,bx):
                        if ix<=x<ix+iw:put(x,y,'│',gold)
                for dy,label in enumerate(('Drag locator','Release to pan','o full overview')):
                    for dx,ch in enumerate(label[:pane-2]):put(left+1+dx,iy+ih+1+dy,ch)
                self._locator_layer=(x0,y0,bw,bh,Plane(base,overlay));self._locator_layer_cache=self._locator_layer;self._locator_layer_key=key
            else:self._locator_layer=self._locator_layer_cache
            return tuple(lines)
        def lines(self):
            self._resolve_detail()
            if self._pan_drag is not None and self._pan_drag[4:]!=(self.width,max(1,self.height-3)):
                self._pan_drag=None;self.double_tap.reset()
            self._locator_layer=None
            # Direct retains detail while loading. Preview zoom-out may explicitly
            # select full overview context; ordinary dragging does not switch it.
            if self.full_overview or self._detail_request is not None or self.preview and self.target_box.view is not None:
                lines=list(self._detail_lines) if not self.full_overview and self._detail_lines is not None and len(self._detail_lines)==self.height and all(len(row)==self.width for row in self._detail_lines) else [' '*self.width for _ in range(self.height)]
            else:
                lines=list(super().lines());self._detail_lines=tuple(row[:self.width].ljust(self.width) for row in lines)
            previous_shown=self._shown_image
            self._target_layer=None;self._shown_image=getattr(self,'_display_image',None) or self._image
            if self.filter_open:return tuple(lines)
            pending=self.target_box.view;label='Preview' if self.preview else 'Direct'
            left=f'[ {label} v ]'
            if self.zoom_feedback():left='[ '+self.zoom_feedback()+' ]'
            from map_geography import maidenhead
            shown=self._shown_image or self._image
            grid_center=shown.projection.center if shown is not None else self.center
            controls=[('[ Back o ]' if self.full_overview else '[ Overview o ]','o'),('[ Sidebar S ]','s'),('[ Grid '+self.maidenhead_grid+' u ]','u'),('[ Forest '+('on' if getattr(self.renderer,'forest_roads',False) else 'off')+' z ]','z')]
            right=''
            self._header_hits=[];header=left
            for text,key in controls:
                self._header_hits.append((len(header)+1,len(text),key));header+=' '+text
            right=maidenhead(*grid_center)
            lines[0]=header[:max(0,self.width-len(right)-1)].ljust(max(0,self.width-len(right)))+right
            wanted=pending or (self.center,self.span)
            w,h=max(1,self.width),max(1,self.height-3)
            loading=self._image_view!=(tuple(self.center),self.span) or self._image is None or (self._image.width,self._image.height)!=raster_size(w,h)
            image=self._image;base_layer=self._display_layer
            if self._pan_display_source is not None and not self.full_overview and pending is None:
                if not loading:self._pan_display_source=None
                elif self._pan_display_source.projection is not None:
                    from offline_map import Image,ReprojectedPlane
                    key=(id(self._pan_display_source),tuple(self.center),self.span,w,h)
                    if getattr(self,'_pan_image_key',None)!=key:
                        view=self.renderer.module.Viewport(tuple(self.center),self.span,w,h)
                        plane=ReprojectedPlane(self._pan_display_source,view)
                        self._pan_image=Image(w,h,plane,'Moving retained map',(),0.,view,'pan-preview');self._pan_image_key=key
                    self._shown_image=self._pan_image
                    self._target_layer=self.station_layer(self._pan_image)
                    return self.locator(lines)
            if pending is not None and self._detail_request is None and self._zoom_context_view is not None:
                refined=self._local_overview.image(self.renderer.module,w,h,*self._zoom_context_view)
                if refined is not None:self._zoom_context_image=refined
            if pending is not None and self._zoom_context_image is not None and not self.full_overview:
                image=self._zoom_context_image
                cache=(id(image),w,h)
                if getattr(self,'_zoom_base_key',None)!=cache:
                    self._zoom_base=(0,2,w,h,ContextPlane(image.cells,image.width,image.height,w,h));self._zoom_base_key=cache
                base_layer=self._zoom_base;self._target_layer=base_layer;self._shown_image=image
            if self.full_overview:
                image=self._zoom_context_image if pending is not None and self._detail_request is None else self._loading_overview if self._detail_request is not None else previous_shown if self._target_drag is not None and previous_shown is not None and previous_shown.source=='cached-overview' else None
                if image is None and self._detail_request is None and self._overview_camera is not None:
                    engine=self.renderer.engine
                    vectors=engine if engine is not None and getattr(engine,'_atlas',None) is not None else None
                    image=self._local_overview.image(self.renderer.module,w,h,*self._overview_camera,engine=vectors)
                    if image is None and previous_shown is not None and previous_shown.source=='cached-overview':image=previous_shown
                if image is None and self._detail_request is None:image=self._overview.image(self.renderer.module,w,h)
                if image is not None:
                    cache=(id(image),w,h)
                    if getattr(self,'_overview_base_key',None)!=cache:
                        self._overview_base=(0,2,w,h,ContextPlane(image.cells,image.width,image.height,w,h));self._overview_base_key=cache
                    base_layer=self._overview_base;self._target_layer=base_layer;self._shown_image=image
            if pending is None and not loading and not self.full_overview:
                quality=self.quality_label(image)
                catalog=self.context.map_catalog
                if catalog is not None:
                    rows=self.filtered_stations();known=sum(row['position'] is not None for row in rows)
                    summary=f'{self.visible_count} shown · {known} located · {len(rows)-known} unknown'+(' · more not loaded' if catalog['has_more'] else '')
                    if self.map_notice:summary=self.map_notice+' · '+summary
                    if not self.selection_visible():summary='Selection hidden · '+summary
                    lines[1]=(self.scale_label()+' · '+summary+(' · '+quality if quality else ''))[:self.width].ljust(self.width)
                elif quality:lines[1]=(self.scale_label()+' · '+quality)[:self.width].ljust(self.width)
                return self.locator(lines)
            extent=''
            if image is not None and image.projection is not None and base_layer is not None and (pending is not None or self.full_overview):
                # Reproject the same station catalogue onto the displayed context;
                # never scale station glyphs with the terrain backdrop.
                from offline_map import Image
                context_key=(id(image),w,h)
                if getattr(self,'_station_context_key',None)!=context_key:
                    view=self.renderer.module.Viewport(image.projection.center,image.projection.span,w,h)
                    self._station_context_image=Image(w,h,base_layer[4],image.legend,image.places,0.,view,'station-context')
                    self._station_context_key=context_key
                base_layer=self.station_layer(self._station_context_image)
                self._target_layer=base_layer
                points=[image.projection.project(*point) for point in corners(*wanted,w,h)]
                _,_,w,h,base=base_layer
                def screen(point):return (round((point[0]+.5)*w/image.width-.5),round((point[1]+.5)*h/image.height-.5))
                (x0,y0),(x1,y1)=map(screen,points)
                if not contains(image,*wanted,w,h):extent=' · target extends beyond shown coverage'
                # In Direct mode leave the displayed detail untouched while pending.
                # A box belongs to explicit Overview or optional Preview only.
                if pending is not None or self.full_overview:
                    key=(id(base),x0,y0,x1,y1,w,h)
                    if key!=self._target_layer_key:
                        overlay={};style=ink(255,210,65,background=(45,30,12))
                        for x in range(max(0,x0),min(w,x1+1)):
                            for y in (y0,y1):
                                if 0<=y<h:overlay[y*w+x]=('─',style)
                        for y in range(max(0,y0),min(h,y1+1)):
                            for x in (x0,x1):
                                if 0<=x<w:overlay[y*w+x]=('│',style)
                        for x,y,char in ((x0,y0,'┌'),(x1,y0,'┐'),(x0,y1,'└'),(x1,y1,'┘')):
                            if 0<=x<w and 0<=y<h:overlay[y*w+x]=(char,style)
                        prior=getattr(self,'_target_layer_cache',None)
                        if self.full_overview and prior is not None and self._overview_published_layer is prior and prior[:4]==(0,2,w,h) and prior[4].base is base:
                            cells=prior[4];changed={i for i in cells.overlay.keys()|overlay.keys() if cells.overlay.get(i)!=overlay.get(i)}
                            cells.overlay.clear();cells.overlay.update(overlay)
                            if changed:
                                queued=self._overview_patch
                                if queued is not None and queued[0] is prior:changed.update(queued[1])
                                self._overview_patch=(prior,tuple(sorted(changed)))
                        else:
                            self._target_layer_cache=(0,2,w,h,Plane(base,overlay));self._overview_patch=None
                        self._target_layer_key=key
                    self._target_layer=self._target_layer_cache
            if pending is not None:
                wait=('detail unavailable · Esc back' if self.renderer.error else 'loading chosen detail · Esc stop') if self._detail_request is not None else 'preview · Enter confirm · Esc cancel'
                status=(('Local overview' if image and image.legend=='Local overview' else 'Regional overview')+' · ' if self.full_overview else '')+f'Target {wanted[1]:g} km · {wait}{extent}'
            elif self.full_overview and image is None:status='Overview unavailable · Esc back to map'
            elif self.full_overview:status=('Local overview' if image and image.legend=='Local overview' else 'Regional overview')+' · Enter confirm · Esc cancel · +/- zoom box'+extent
            else:
                error=getattr(self.renderer,'error',None)
                status=f'{self.distance_label(self.span)} requested · '+(str(error) if error else 'loading requested detail')
            lines[1]=status[:self.width].ljust(self.width)
            return self.locator(lines)
        def take_layer_patch(self):
            patch=self._overview_patch;self._overview_patch=None
            layer=self.layer();self._overview_published_layer=layer
            return patch if patch is not None and patch[0] is layer else None
        def layer(self):
            layer=self._locator_layer or self._target_layer or super().layer()
            if self.maidenhead_grid=='off' or layer is None or self._shown_image is None:return layer
            if self.maidenhead_grid=='auto' and self._shown_image.projection.span<30:return layer
            from map_geography import grid
            from offline_map import Plane
            x,y,w,h,plane=layer
            key=(id(plane),id(self._shown_image),w,h,self.side_overview,self.full_overview)
            if getattr(self,'_grid_key',None)!=key:
                view=self.renderer.module.Viewport(self._shown_image.projection.center,self._shown_image.projection.span,w,h)
                marks=grid(view)
                if self.side_overview and not self.full_overview:
                    sidebar_left=w-min(32,self.width//3)
                    marks={i:value for i,value in marks.items() if i%w<sidebar_left}
                # Keep station labels, roads, zoom box and path ahead of the grid.
                from paint import ink
                marks={i:(char,ink(*tuple((style>>s)&255 for s in (40,32,24)),background=tuple((plane[i][1]>>s)&255 for s in (16,8,0)))) for i,(char,style) in marks.items() if plane[i][0] in (' ','▀','▄')}
                self._grid_layer=(x,y,w,h,Plane(plane,marks));self._grid_key=key
            return self._grid_layer
    return StationMap
