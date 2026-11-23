'use strict';
const el = id => document.getElementById(id);
const map = el('map'), ctx = map.getContext('2d');
const clamp = (v, low, high) => Math.max(low, Math.min(high, v));
let land, cities = [], box, anchor, draw = false, saved = false;
let lon = 0, lat = 0, zoom = 0, width, height, scale;
const fingers = new Map();
function coordinates(x,y) {
    return [clamp(lon+(x-width/2)/scale,-180,180),clamp(lat-(y-height/2)/scale,-89.999999,89.999999)];
}
function paint() {
    width = map.clientWidth;
    height = map.clientHeight;
    if (!width || !height) return;
    const ratio = window.devicePixelRatio || 1;
    const w = Math.round(width*ratio), h = Math.round(height*ratio);
    if (map.width !== w || map.height !== h) { map.width=w; map.height=h; }
    scale = Math.min(width/360,height/180)*2**zoom;
    ctx.setTransform(ratio,0,0,ratio,0,0);
    ctx.clearRect(0,0,width,height);
    if (!land) return;
    const x = a => width/2+(a-lon)*scale, y = b => height/2-(b-lat)*scale;
    ctx.save();
    ctx.translate(x(0),y(0)); ctx.scale(scale,scale);
    ctx.fillStyle='#e6e4c9'; ctx.fill(land,'evenodd');
    ctx.restore();
    ctx.font='13px system-ui'; ctx.fillStyle='#244044';
    const occupied=[];
    for (const [name,,a,b] of cities) {
        const px=x(a), py=y(b);
        if (px<4 || px>width-12 || py<13 || py>height-15) continue;
        const end=px+ctx.measureText(name).width+8;
        if (end>width || occupied.some(([l,r,t])=>px<r && end>l && Math.abs(t-py)<23)) continue;
        ctx.fillRect(px,py,3,3); ctx.fillText(name,px+5,py+3);
        occupied.push([px,end,py]);
        if (occupied.length>=24) break;
    }
    if (box) {
        const [west,south,east,north]=box;
        ctx.fillStyle='rgba(15,105,104,.25)'; ctx.strokeStyle='#085d60'; ctx.lineWidth=2;
        const rect=[x(west),y(north),(east-west)*scale,(north-south)*scale];
        ctx.fillRect(...rect); ctx.strokeRect(...rect);
    }
    if (anchor) {
        ctx.fillStyle='#804118'; ctx.beginPath(); ctx.arc(x(anchor[0]),y(anchor[1]),5,0,2*Math.PI); ctx.fill();
    }
}
function status() {
    el('draw').setAttribute('aria-pressed',String(draw));
    el('use').disabled=!box || draw || saved;
    if (saved) return;
    if (draw) el('info').textContent=anchor?'Tap the opposite corner.':'Drag a rectangle or tap two opposite corners.';
    else if (box) el('info').textContent='W, S, E, N · '+box.map(v=>v.toFixed(5)).join('   ')+
        ((box[2]-box[0])*(box[3]-box[1])>.25?' · Matching OSM extract URL required.':'');
    else el('info').textContent='Find a city or zoom and pan, then draw your area.';
}
function changeZoom(delta) { zoom=clamp(zoom+delta,0,16); paint(); }
el('plus').onclick=()=>changeZoom(1);
el('minus').onclick=()=>changeZoom(-1);
el('world').onclick=()=>{zoom=lon=lat=0; paint();};
el('draw').onclick=()=>{draw=!draw; anchor=null; status(); paint();};
map.onwheel=e=>{e.preventDefault();changeZoom(-Math.sign(e.deltaY));};
const point=e=>{const r=map.getBoundingClientRect();return [e.clientX-r.left,e.clientY-r.top];};
const distance=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
function rectangle(a,b) {
    const bounds=[Math.min(a[0],b[0]),Math.min(a[1],b[1]),Math.max(a[0],b[0]),Math.max(a[1],b[1])].map(v=>Number(v.toFixed(6)));
    return bounds[0]<bounds[2] && bounds[1]<bounds[3] ? bounds : null;
}
let start,second;
map.onpointerdown=e=>{
    if (saved || !land) return;
    const p=point(e); fingers.set(e.pointerId,p); map.setPointerCapture(e.pointerId);
    if (draw && fingers.size===1) {
        start=p; second=!!anchor; anchor=anchor || coordinates(...p); status(); paint();
    }
};
map.onpointermove=e=>{
    const previous=fingers.get(e.pointerId);
    if (!previous) return;
    const p=point(e); fingers.set(e.pointerId,p);
    if (draw) {
        if (anchor && fingers.size===1 && distance(start,p)>4) box=rectangle(anchor,coordinates(...p));
    } else if (fingers.size===2) {
        const other=[...fingers].find(([id])=>id!==e.pointerId)[1];
        const before=distance(previous,other), after=distance(p,other);
        if (before>1 && after>1) changeZoom(Math.log2(after/before));
    } else {
        lon=clamp(lon-(p[0]-previous[0])/scale,-180,180);
        lat=clamp(lat+(p[1]-previous[1])/scale,-90,90);
    }
    paint();
};
map.onpointerup=e=>{
    if (!fingers.delete(e.pointerId)) return;
    const p=point(e);
    if (draw && anchor && (second || distance(start,p)>4)) {
        box=rectangle(anchor,coordinates(...p));
        if (box) { anchor=null; draw=false; }
    }
    status(); paint();
};
map.onpointercancel=e=>{fingers.delete(e.pointerId);};
el('search').oninput=()=>{
    const q=el('search').value.toLocaleLowerCase().trim(), select=el('places');
    select.replaceChildren(new Option('Choose a matching city',''));
    if (q) cities.forEach(([name,country],i)=>{
        if (select.length<=30 && name.toLocaleLowerCase().includes(q)) select.add(new Option(name+', '+country,i));
    });
    select.hidden=select.length===1;
};
el('places').onchange=e=>{
    if (e.target.value==='') return;
    const [name,,x,y]=cities[Number(e.target.value)];
    lon=x; lat=y; zoom=9; el('search').value=name; e.target.hidden=true; paint();
};
async function load(url,options) {
    const r=await fetch(url,options);
    if (!r.ok) throw Error('Pocket returned '+r.status);
    return r.json();
}
el('use').onclick=async()=>{
    el('use').disabled=true;
    try {
        await load('selection',{method:'POST',body:JSON.stringify(box)});
        saved=true; el('draw').disabled=true;
        el('info').textContent='Area saved. Return to Pocket and choose Plan or Download and build.';
    } catch (e) {el('info').textContent='Could not save. Reopen the picker from Pocket.'; el('use').disabled=false;}
};
new ResizeObserver(paint).observe(map);
Promise.all([load('world.json'),load('selection')]).then(([data,selection])=>{
    land=new Path2D(data.land); cities=data.places; box=selection; paint();
    if (box) {
        lon=(box[0]+box[2])/2; lat=(box[1]+box[3])/2;
        zoom=clamp(Math.log2(.75*Math.min(width/(box[2]-box[0]),height/(box[3]-box[1]))/scale),0,16);
    }
    el('draw').disabled=false; status(); paint();
}).catch(()=>{el('info').textContent='Overview unavailable. Reopen the picker from Pocket.';});
