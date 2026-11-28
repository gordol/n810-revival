/* Static world-space terrain and vegetation. Use the SDL OpenGL canvas
 * directly, preserving the renderer state used by subsequent UI drawing. */
static GLuint rainier_program(void){
 const char *vs="#version 120\n"
  "varying vec3 pos,relativePos;varying vec4 tint;varying float distanceToEye;"
  "uniform vec3 waterEye;uniform float poseBlend;uniform int skyPass;"
  "void main(){if(skyPass!=0){pos=gl_Vertex.xyz;relativePos=pos;distanceToEye=0.;tint=vec4(1.);gl_Position=gl_Vertex;return;}pos=mix(gl_Vertex.xyz,gl_MultiTexCoord0.xyz,poseBlend);relativePos=pos-waterEye;tint=gl_Color;"
  "vec4 eye=gl_ModelViewMatrix*vec4(pos,1.);"
  "distanceToEye=length(eye.xyz);gl_Position=gl_ProjectionMatrix*eye;}";
 const char *fs="#version 120\n"
  "varying vec3 pos,relativePos;varying vec4 tint;varying float distanceToEye;"
  "uniform vec4 supplies;uniform int camp;uniform int season;uniform float originY;uniform float hazeDensity;uniform float waterTime;uniform vec3 picked;uniform int highDetail;uniform int animal;uniform sampler2D forestShade;uniform sampler2D flightPhoto;uniform vec3 photoArea;uniform vec3 flightAreas[111];uniform int photoSlot;uniform float hiddenPlane;uniform int underwater;"
  "float hash(vec2 p){vec3 q=fract(vec3(p.xyx)*.1031);q+=dot(q,q.yzx+33.33);return fract((q.x+q.y)*q.z);}"
  "float noise(vec2 p){vec2 i=floor(p),u=fract(p);u=u*u*(3.-2.*u);"
  "return mix(mix(hash(i),hash(i+vec2(1,0)),u.x),mix(hash(i+vec2(0,1)),hash(i+1.),u.x),u.y);}"
  "uniform vec3 waterEye;uniform vec2 shadeCenter;uniform vec2 shadowStep;uniform int regional;uniform int skyPass;uniform vec4 skyCamera;uniform vec2 bankCS;uniform float daylight;uniform float overcast;"
  "vec3 horizon(){return mix(vec3(.095,.13,.20),mix(vec3(.87,.58,.43),vec3(.68,.80,.86),smoothstep(.35,.9,daylight)),daylight);}"
  "vec3 skyDirection(){vec2 uv=vec2(pos.x*skyCamera.z,-pos.y)*skyCamera.w;"
  "uv=vec2(dot(uv,bankCS),dot(uv,vec2(-bankCS.y,bankCS.x)));"
  "float cp=cos(skyCamera.y),sp=sin(skyCamera.y);float f=cp+uv.y*sp;"
  "return normalize(vec3(uv.x*cos(skyCamera.x)+f*sin(skyCamera.x),uv.y*cp-sp,f*cos(skyCamera.x)-uv.x*sin(skyCamera.x)));}"
  "vec3 skyColor(vec3 dir){"
  "float alt=max(0.,dir.y);vec3 col=mix(horizon(),mix(vec3(.012,.023,.064),vec3(.24,.48,.73),daylight),smoothstep(0.,.65,alt));"
  "vec2 dome=dir.xz/(1.+dir.y+.001);vec2 star=dome*300.;float seed=hash(floor(star));"
  "float light=1.-smoothstep(.04,.33,length(fract(star)-.5));"
  "col+=vec3(.79,.86,1.)*light*step(.975,seed)*(1.-smoothstep(.08,.38,daylight))*smoothstep(.01,.18,alt);"
  "vec2 p=dir.xz/max(.075,alt)*2.1+vec2(waterTime*.013,waterTime*.002);"
  "float n=.57*noise(p)+.30*noise(2.1*p)+.13*noise(4.4*p);"
  "float cloud=smoothstep(.52-.15*overcast,.78-.12*overcast,n)*smoothstep(.015,.14,alt);"
  "return mix(col,mix(vec3(.13,.16,.22),vec3(.87,.88,.86),daylight),cloud);}"
  "uniform sampler2D marketMaterials;uniform vec3 marketLamps[4];uniform int marketNear;"
  "vec3 lampGlow(vec3 ray,float depth){vec3 glow=vec3(0.);"
  "for(int i=0;i<4;i++){vec3 d=marketLamps[i]-waterEye;float t=dot(d,ray);"
  "if(t>.2 && t<min(depth+.32,45.)){vec3 miss=d-ray*t;float r=length(miss);"
  "float halo=exp(-r*6.)*.33+exp(-abs(miss.y)*65.-r*3.)*.16;"
  "glow+=halo*(1.-smoothstep(18.,45.,t))*(i==0?vec3(1.,.12,.04):vec3(1.,.70,.33));}}return glow;}"
  "vec3 reflectedBank(vec3 ray){vec3 sky=skyColor(ray);"
  // The valley canopy texture stores crown heights at the actual tree sites.
  // Trace a short ray above the water plane; the far field uses the sky.
  "for(int i=1;i<=16;i++){float d=float(i)*(.8+.21*float(i));vec3 p=pos+d*ray;"
  "vec2 uv=p.xz/2048.+.5;if(max(abs(uv.x-.5),abs(uv.y-.5))>=.5)break;"
  "float crown=texture2D(forestShade,uv).r*85.;float hit=smoothstep(.0,1.4,crown-(p.y-pos.y));"
  "if(hit>.05){vec3 needles=vec3(.12,.24,.18)*(.74+.35*noise(p.xz*.35))*(.24+.76*daylight);"
  "return mix(sky,needles,hit);}}return sky;}"
  "void main(){if(underwater!=0){vec3 fog=vec3(.035,.20,.21);"
  "if(skyPass!=0){vec3 ray=skyDirection();float glow=smoothstep(.25,1.,ray.y);"
  "gl_FragColor=vec4(mix(fog,vec3(.23,.56,.49),glow),1.);return;}"
  "float beam=smoothstep(.68,.82,noise(pos.xz*.55+waterTime*.17));"
  "gl_FragColor=vec4(mix(tint.rgb*(.85+.28*beam),fog,1.-exp(-.068*distanceToEye)),1.);return;}"
  "if(skyPass!=0){gl_FragColor=vec4(skyColor(skyDirection())+(marketNear!=0?lampGlow(skyDirection(),1000.):vec3(0.)),1.);return;}if(hiddenPlane>0. && abs(tint.a-hiddenPlane)<.0002)discard;if(tint.a>.85 && tint.a<.89 && (season==1 || season==2 || (season==3 && tint.a<.87)))discard;if((abs(tint.a-.60)<.004 && supplies.x>.5)||(abs(tint.a-.61)<.004 && supplies.y>.5)||(abs(tint.a-.62)<.004 && supplies.z>.5)||(abs(tint.a-.63)<.004 && supplies.w<.5))discard;if((abs(tint.a-.57)<.005 && camp<1)||(abs(tint.a-.59)<.005 && camp<2))discard;if((abs(tint.a-.08)<.01 && picked.x>.5)||(abs(tint.a-.13)<.01 && picked.y>.5)||(abs(tint.a-.18)<.01 && picked.z>.5))discard;float alpha=1.;float reflection=0.;vec3 reflected=vec3(0.);float castShade=0.;vec3 marketSpec=vec3(0.);vec3 col=tint.rgb;if(tint.a>.9){vec2 p=pos.xz;"
  "float broad=noise(p*.015);float detail=(noise(p*.64)-.5)*(1.-smoothstep(80.,600.,distanceToEye));"
  "col*=.80+.40*broad+.30*detail;col+=vec3(.032,.024,-.013)*broad;"
  "if(highDetail!=0){float grit=noise(p*11.)-.5;float moss=noise(p*.18);"
  "col+=vec3(.075,.055,.026)*moss;col+=grit*vec3(.041,.037,.024)*(1.-smoothstep(6.,38.,distanceToEye));"
  "}"
  "if(regional!=0){float elev=pos.y+originY;float line=1920.+100.*sin(p.x*.0017)+55.*cos(p.y*.0021);"
  "float meadow=smoothstep(1480.,1650.,elev)*(1.-smoothstep(2100.,2380.,elev));"
  "float drift=.65*noise(p*.115)+.35*noise(p*.38);float blades=noise(vec2(p.x*2.7,p.y*7.1));"
  "vec3 turf=mix(vec3(.18,.25,.12),vec3(.42,.45,.25),drift);"
  "if(season==1)turf=mix(vec3(.31,.19,.16),vec3(.55,.43,.23),drift);"
  "col=mix(col,turf*(.79+.41*blades),.72*meadow*(1.-smoothstep(90.,380.,distanceToEye)));"
  "float stand=(1.-smoothstep(line-230.,line,elev))*smoothstep(.26,.69,noise(p*.018));"
  // Seen from flight, resolve patches of crowns, then merge them into
  // larger stands as the screen footprint outgrows an individual tree.
  "float footprintM=length(fwidth(p));"
  "float crowns=(noise(p*.16)-.5)*(1.-smoothstep(2.,9.,footprintM));"
  "float standLight=.85+.24*noise(p*.0035)+.32*crowns;"
  "vec3 canopy=col*vec3(.48,.71,.54)*standLight;"
  "col=mix(col,canopy,stand*smoothstep(65.,170.,distanceToEye));}"
  "float footprint=regional!=0?512.:2048.;vec2 uv=(p-shadeCenter)/footprint+.5;"
  "if(daylight>.12 && distanceToEye<340. && max(abs(uv.x-.5),abs(uv.y-.5))<.46){"
  "vec3 n=cross(dFdx(relativePos),dFdy(relativePos));float slope=abs(n.y)>.001?dot(n.xz/n.y,shadowStep):0.;"
  "float shade=0.;for(int i=0;i<8;i++){float level=.75+float(i)*(1.5+.95*float(i));"
  "float canopy=texture2D(forestShade,uv-shadowStep*level/footprint).r*85.;"
  "shade=max(shade,smoothstep(-.6,.6,canopy-level*(1.-clamp(slope,-1.,.85)))*step(.1,canopy));}"
  "float fade=(1.-smoothstep(175.,340.,distanceToEye))*smoothstep(.12,.62,daylight)*(1.-.68*overcast);"
  "castShade=shade*fade;}}"
  "if(tint.a>.935 && tint.a<.97){float grains=noise(pos.xz*24.);float stone=noise(pos.xz*6.);"
  "float lensing=sin(7.*pos.z+3.*sin(5.*pos.x+waterTime*.9)+waterTime)*sin(5.*pos.x+1.7*pos.z-waterTime*.8);"
  "col*=.84+.20*stone+.15*grains;col+=vec3(.10,.12,.095)*smoothstep(.60,.95,lensing)*daylight;}"
  "if(highDetail!=0 && tint.a>.46 && tint.a<.50){float bark=noise(vec2((pos.x+pos.z)*21.,pos.y*2.6));col*=.68+.6*bark;}"
  "if(highDetail!=0 && tint.a>.06 && tint.a<.20){vec3 n=normalize(cross(dFdx(relativePos),dFdy(relativePos)));"
  "float wax=pow(abs(dot(n,normalize(vec3(-.42,.79,-.44)))),14.);col+=vec3(.28,.34,.43)*wax;}"
  "if(animal==0 && tint.a>.020 && tint.a<.040){"
  "vec2 wood=vec2(pos.x+.61*pos.z,2.7*pos.y-.18*pos.z);"
  "float patch=.66*noise(wood*2.4)+.34*noise(wood*7.);"
  "float grain=noise(vec2(wood.x*2.7,wood.y*16.)+patch);"
  "float moss=smoothstep(.16,.46,(tint.a-.030)/.009+.96*(patch-.52));"
  "vec3 cushion=mix(vec3(.15,.23,.075),vec3(.44,.52,.19),patch+ .28*(grain-.5));"
  "col=mix(col*(.6+.62*grain),cushion,moss);}"
  // Cascade tiers repeat at two scales: a sweeping bough, then its sprays.
  // Interpolated local coordinates keep the pattern fixed to each tree.
  "if(animal==0 && tint.a>=.639 && tint.a<=.650){"
  "float h=clamp((tint.a-.640)/.009,0.,1.);float side=2.*tint.r-1.;"
  "float span=.055+.945*pow(1.-h,.73);float outboard=abs(side)/span;"
  "float bend=noise(pos.xz*.36+pos.y*.11);"
  "float phase=h*10.+outboard*.62+.48*bend+.16*side;"
  "float tiers=.5+.5*cos(6.283*phase);"
  "float sprays=noise(vec2(side*16.,h*39.)+bend);"
  "float edge=.41+.49*tiers+.25*(sprays-.40);"
  "if(outboard>edge)discard;"
  "float sun=.71+.21*tiers+.28*sprays+.13*side;"
  "col=vec3(.53*tint.g,tint.g,tint.b)*sun;}"
  // Distant crown vertices encode lateral position in red and height in alpha.
  "if(regional!=0 && tint.a>.539 && tint.a<.561){float h=(tint.a-.54)*50.;"
  "float whorl=fract(h*7.+.18*sin(pos.x+pos.z));float side=abs(2.*tint.r-1.);"
  "if(side>(1.-h)*(.68+.75*whorl)+.08)discard;"
  "float light=.78+.27*whorl+.16*noise(pos.xz*1.4);col=vec3(.55*tint.g,tint.g,tint.b)*light;}"
  "if(regional==2 && abs(tint.a-.252)<.0001){"
  "float grain=noise(pos.xz*vec2(3.,54.))*.13+noise(pos.xz*vec2(.8,9.))*.16;"
  "float tile=mod(floor(pos.z*2.),2.);vec2 seam=abs(fract(pos.xz*vec2(.51,2.)+vec2(tile*.5,0.))-.5);"
  "float joint=smoothstep(.465,.495,max(seam.x,seam.y))*(1.-smoothstep(.08,.4,length(fwidth(pos.xz))));"
  "vec2 lamp=vec2(pos.x,mod(pos.z+12.,4.)-2.);float pool=exp(-.16*dot(lamp,lamp));"
  "col*=vec3(.68,.64,.59)+grain+.52*pool*vec3(1.,.88,.68)-.22*joint;}"
  "if(regional==2 && abs(tint.a-.253)<.0001){vec2 q=vec2(pos.x+pos.z,pos.y);"
  "float warm=exp(-.20*pow(mod(pos.z+12.,4.)-2.,2.));"
  "col*=vec3(.77,.73,.70)+.20*warm*vec3(1.,.87,.69)+.11*noise(q*10.);}"
  "if(regional==2 && abs(tint.a-.241)<.0001){vec2 uv=vec2(pos.x+.65*pos.z,pos.y);"
  "float patina=noise(uv*vec2(.45,.18));float grain=(noise(uv*19.)-.5)*(1.-smoothstep(.02,.10,length(fwidth(uv))));"
  "col*=.86+.24*patina+.14*grain;}"
  "if(regional==2 && abs(tint.a-.244)<.0001){vec3 ray=normalize(pos-waterEye);"
  "vec3 n=normalize(cross(dFdx(relativePos),dFdy(relativePos)));vec3 mirror=reflect(ray,n);"
  "float skyline=noise(mirror.xz*17.)*.21-.03;"
  "vec3 reflection=mix(vec3(.21,.23,.22),skyColor(vec3(mirror.x,max(.01,mirror.y),mirror.z)),smoothstep(skyline-.015,skyline+.025,mirror.y));"
  "col=mix(col,reflection,.28+.55*pow(1.-abs(dot(ray,n)),3.));}"
  "if(regional==2 && abs(tint.a-.251)<.0001){vec3 n=normalize(cross(dFdx(relativePos),dFdy(relativePos)));vec2 uv=vec2((abs(n.x)>abs(n.z)?pos.z:pos.x)*3.2,pos.y*8.);uv.x+=.5*mod(floor(uv.y),2.);"
  "vec2 edge=abs(fract(uv)-.5);float joint=smoothstep(.43,.49,max(edge.x,edge.y));"
  "col=mix(col*(.80+.32*hash(floor(uv))),vec3(.32,.29,.26),joint*.65);}"
  // Repeat photo detail in metres. The GPU mipmaps each surface independently.
  "if(regional==2 && ((tint.a>=.256-.0001 && tint.a<=.258+.0001)||abs(tint.a-.237)<.0001)){"
  "vec2 axis=vec2(-.5299,.8480),along=vec2(-.8480,-.5299);vec2 floorUV=vec2(dot(pos.xz,axis),dot(pos.xz,along));"
  "vec3 normal=normalize(cross(dFdx(relativePos),dFdy(relativePos)));vec2 uv=abs(normal.y)>.65?floorUV:vec2(abs(dot(normal.xz,axis))>.7?floorUV.y:floorUV.x,pos.y);"
  "vec4 scan=texture2D(marketMaterials,uv*(abs(tint.a-.237)<.0001?.42:.65));"
  "float detail=abs(tint.a-.237)<.0001?scan.b:(tint.a<.2565?scan.g:(tint.a<.2575?scan.r:scan.a));"
  "col*=.47+1.02*detail;}"
  "if(regional==2 && abs(tint.a-.259)<.0001){vec2 p=relativePos.xz+vec2(waterEye.x,waterEye.z);"
  "float blush=noise(p*23.);float skin=noise(p*370.)*(1.-smoothstep(.15,1.,length(fwidth(relativePos.xz*370.))));"
  "col*=vec3(.83+.25*blush,.71+.43*blush,.76+.31*blush)*(.94+.10*skin);}"
  // Dense layers on the lower Post Alley bricks. Filter sub-pixel pieces at distance.
  "if(regional==2 && abs(tint.a-.255)<.0001){vec2 uv=pos.zy*vec2(32.,38.);"
  "vec2 cell=floor(uv);float seed=hash(cell);vec2 q=fract(uv)-.5+.24*(vec2(seed,hash(cell+7.))-.5);"
  "float r=length(q*vec2(.84+.45*seed,.95));float aa=max(.035,min(.34,length(fwidth(uv))));"
  "vec3 gum=.49+.33*cos(6.283*(seed+vec3(.06,.39,.72)));"
  "col=mix(col,gum*(.82-.32*q.y)+.16*exp(-32.*dot(q+.17,q+.17)),1.-smoothstep(.35-aa,.50+aa,r));}"
  "if(regional==2 && (abs(tint.a-.237)<.0001||abs(tint.a-.254)<.0001)){"
  "vec2 paving=vec2(dot(pos.xz,vec2(-.5299,.8480)),dot(pos.xz,vec2(-.8480,-.5299)));"
  "vec2 brick=paving*(tint.a<.25?vec2(4.6,9.2):vec2(4.));brick.x+=.5*mod(floor(brick.y),2.);"
  "float joint=smoothstep(.41,.49,max(abs(fract(brick.x)-.5),abs(fract(brick.y)-.5)));"
  "float filtered=1.-smoothstep(.08,.45,length(fwidth(brick)));joint*=filtered;"
  "if(tint.a<.25){float kiln=hash(floor(brick));col*=mix(vec3(.97,.80,.72),vec3(.68,.63,.59),kiln*filtered);"
  "col=mix(col,vec3(.19,.17,.15),joint*.55);}"
  "float pool=(.22+.78*smoothstep(.21,.78,noise(pos.xz*.71)+.19*overcast))*(1.-.80*joint);vec3 incident=normalize(pos-waterEye);"
  "vec3 n=normalize(vec3(.024*(noise(pos.xz*7.)-.5),1.,.024*(noise(pos.zx*7.)-.5)));"
  "vec3 ray=reflect(incident,n);float fresnel=.10+.74*pow(1.-abs(dot(incident,n)),3.);"
  "vec3 sheen=skyColor(vec3(ray.x,max(.01,ray.y),ray.z));"
  "if(abs(tint.a-.254)<.0001){float opening=clamp(ray.y*1.4-abs(ray.x),0.,1.);sheen=mix(vec3(.20,.13,.11),sheen,opening);}"
  "col=mix(col*(1.-.24*pool),sheen,pool*fresnel*(.32+.64*overcast));"
  "if(marketNear!=0){for(int i=0;i<4;i++){vec3 d=marketLamps[i]-pos;float t=dot(d,ray);if(t>0.){"
  "vec3 missVec=d-ray*t;if(i==0){vec3 axis=vec3(-.5299,0.,.8480);"
  "vec3 lateral=axis-ray*dot(axis,ray);missVec-=lateral*clamp(dot(lateral,missVec)/max(.001,dot(lateral,lateral)),-6.6,6.6);}"
  "float miss=length(missVec);float streak=exp(-miss/(.21+.055*t))/(1.+.0018*t*t);"
  "marketSpec+=pool*streak*(.35+.65*overcast)*(i==0?vec3(.99,.13,.06):vec3(.98,.66,.30));}}}}"
  // Worn concrete slabs: joints disappear smoothly below a pixel.
  "if(regional==2 && abs(tint.a-.260)<.0001){vec2 uv=pos.xz*.65;"
  "vec2 edge=.5-abs(fract(uv)-.5);float seam=min(edge.x,edge.y);float aa=max(.001,length(fwidth(uv)));"
  "float joint=(1.-smoothstep(.002,.006+aa,seam))*(1.-smoothstep(.01,.1,aa));"
  "float grit=texture2D(marketMaterials,pos.xz*.75).a;"
  "col*=.76+.29*grit+.10*hash(floor(uv))-.30*joint;}"
  "if(regional==2 && abs(tint.a-.249)<.0001){vec2 p=pos.xz;"
  "float grit=(noise(p*15.)-.5)*(1.-smoothstep(.025,.11,length(fwidth(p))));"
  "float aggregate=texture2D(marketMaterials,p*.8).a;"
  "col*=.64+.34*aggregate+.20*noise(p*.24)+.18*grit;}"
  "if(regional==2 && tint.a>.2259 && tint.a<.2291){vec3 n=normalize(cross(dFdx(relativePos),dFdy(relativePos)));"
  "bool tower=abs(tint.a-.229)<.0001 || abs(tint.a-.227)<.0001;vec2 wall=vec2(tint.a>.2275?pos.x:pos.z,pos.y);"
  "vec2 uv=wall/(tower?vec2(1.65,3.65):vec2(2.8,3.15));"
  "vec2 f=fract(uv),e=abs(f-.5);float detail=1.-smoothstep(.12,.55,length(fwidth(uv)));"
  "float glass=(1.-smoothstep(.32,.36,e.x))*(1.-smoothstep(.29,.33,e.y));"
  "if(tower)glass=(1.-smoothstep(.46,.49,e.x))*(1.-smoothstep(.39,.42,e.y));"
  "float unit=hash(floor(uv));vec3 mirror=reflect(normalize(pos-waterEye),n);"
  "vec3 pane=mix(vec3(.13,.19,.22),vec3(.51,.63,.70),smoothstep(-.35,.45,mirror.y));"
  "pane*=.81+.25*unit;float blind=smoothstep(.60,.64,unit)*step(.61,f.y);"
  "pane=mix(pane,vec3(.53,.50,.44),.65*blind);"
  "float frame=smoothstep(.009,.027,e.x)*smoothstep(.009,.020,abs(f.y-.60));"
  "if(!tower){vec2 brick=wall/vec2(.24,.077);brick.x+=.5*mod(floor(brick.y),2.);"
  "vec2 edge=.5-abs(fract(brick)-.5);float joint=1.-smoothstep(.01,.08,min(edge.x,edge.y));"
  "float close=1.-smoothstep(.09,.48,length(fwidth(wall/vec2(.24,.077))));"
  "col*=.94+close*(.12*(hash(floor(brick))-.5)+.17*joint);}"
  "col*=.90+.12*noise(vec2(uv.x*1.7,uv.y*3.));"
  "col=mix(col,mix(vec3(.13,.16,.17),pane,frame),glass*detail);}"
  "if(regional==2 && tint.a>.2001 && tint.a<=.2191){vec3 photo=texture2D(forestShade,pos.xz/shadeCenter+.5).rgb;"
  "col=photo*(.93+.28*(tint.g-.30));}"
  "if(regional!=0 && animal==0 && abs(tint.a-.20)<.0001){"
  "vec2 chop=pos.xz*.26;float drift=noise(chop*.17);float fp=length(fwidth(chop));"
  "float wave=(noise(chop+vec2(waterTime*.55,drift*2.))-.5)*(1.-smoothstep(.4,2.,fp));"
  "wave+=.36*(noise(chop*3.+vec2(drift,-waterTime))-.5)*(1.-smoothstep(.12,.8,fp));"
  "float facing=abs(normalize(waterEye-pos).y);"
  "vec3 n=normalize(vec3(.18*wave,1.,.12*(drift-.5)));vec3 ray=reflect(normalize(pos-waterEye),n);"
  "col=mix(vec3(.059,.21,.24),skyColor(vec3(ray.x,max(.015,ray.y),ray.z)),.13+.56*pow(1.-facing,4.));"
  "vec3 sun=normalize(vec3(-shadowStep.x,.55+daylight,-shadowStep.y));"
  "float glint=pow(max(0.,dot(ray,sun)),90.);col+=vec3(.70,.58,.39)*glint*daylight*(1.-overcast);"
  "col+=vec3(.045,.055,.055)*wave*(1.-smoothstep(12.,70.,length(fwidth(pos.xz))));}"
  "if(regional==2 && animal==0 && tint.a>=.1969 && tint.a<=.2191){"
  "bool base=tint.a<.218;vec3 street=flightAreas[109];bool fine=street.z>0. && street.z<4096.;vec2 sd=abs(pos.xz-street.xy);"
  "vec3 nearRoad=flightAreas[110];bool closeTile=nearRoad.z>0. && nearRoad.z<4096.;vec2 nd=abs(pos.xz-nearRoad.xy);"
  "if(closeTile && (base || photoSlot!=110) && max(nd.x,nd.y)<nearRoad.z)discard;"
  "bool closeDraw=photoSlot==110 && closeTile;"
  "if(fine && !closeDraw && (base || photoSlot!=109) && max(sd.x,sd.y)<street.z)discard;"
  "if(base || (photoSlot>=25 && !closeDraw && !(fine && photoSlot==109))){"
  "vec2 cell=mod(floor(pos.xz/8192.+.5),5.);vec3 area=flightAreas[int(cell.x+5.*cell.y)];"
  "vec2 d=abs(pos.xz-area.xy);if(max(d.x,d.y)<area.z)discard;}"
  "if(base || (photoSlot>=28 && photoSlot<109)){for(int j=25;j<28;j++){vec3 a=flightAreas[j];vec2 d=abs(pos.xz-a.xy);if(max(d.x,d.y)<a.z)discard;}}"
  "if(base){vec2 cell=mod(floor(pos.xz/32768.+.5),9.);vec3 a=flightAreas[28+int(cell.x+9.*cell.y)];"
  "vec2 d=abs(pos.xz-a.xy);if(max(d.x,d.y)<a.z)discard;}}"
  "if(regional==2 && abs(tint.a-.219)<.0001 && photoArea.z>0.){vec2 extent=abs(pos.xz-photoArea.xy);if(max(extent.x,extent.y)>photoArea.z*.5)discard;"
  "col=texture2D(flightPhoto,(pos.xz-photoArea.xy)/photoArea.z+.5).rgb;}"
  // World-space clusters, shoots and needle tips. Fade subpixel octaves
  // toward their mean so distant foliage holds together during camera motion.
  "if(animal==0 && tint.a>=.499 && tint.a<.516){"
  "vec2 uv=vec2(.77*pos.x+.63*pos.z,pos.y*1.35+.35*pos.z);"
  "float footprint=length(fwidth(uv));float cluster=noise(uv*.82);"
  "float shoot=mix(noise(uv*2.9+cluster),.5,smoothstep(.12,.45,footprint));"
  "float tips=mix(noise(uv*9.7+shoot),.5,smoothstep(.035,.14,footprint));"
  "float cover=.55*cluster+.31*shoot+.14*tips;"
  "if(tint.a>.509 && cover<.42-.14*smoothstep(.4,1.8,footprint))discard;"
  "col*=.68+.65*cover;col+=vec3(.028,.047,.013)*smoothstep(.45,.77,cover);}"
  "if(regional!=0 && abs(tint.a-.815)<.003){if(season==2)discard;if(season==1)col*=vec3(1.35,.98,.70);}"
  "if(regional!=0 && abs(tint.a-.83)<.005){float drift=.65*noise(pos.xz*.13)+.35*noise(pos.xz*.46);"
  "if(season==1){vec3 leaves=mix(vec3(.30,.085,.13),vec3(.69,.16,.20),smoothstep(.26,.54,drift));"
  "col=mix(leaves,vec3(.85,.54,.13),smoothstep(.55,.74,drift))*(.70+.66*tint.g);}"
  "if(season==2)col=mix(col,vec3(.77,.82,.83),.76);}"
  "if(tint.a>.65 && tint.a<.85){float seams=noise(vec2(pos.x*.006,pos.z*.036+sin(pos.x*.007)));"
  "col*=1.-.25*smoothstep(.60,.78,seams);}"
  "if(tint.a>.52 && tint.a<.54){float gravel=noise(pos.xz*3.6);"
  "float grains=noise(pos.xz*16.)-.5;col*=.75+.44*gravel+.20*grains*(1.-smoothstep(6.,22.,distanceToEye));}"
  "if(regional==0 && tint.a>.25 && tint.a<.45){vec2 flow=vec2(tint.r*12.-6.,tint.g*4096.-waterTime*.95);"
  "float current=noise(flow*vec2(.8,.38));float riffle=sin(flow.y*5.3+4.*current+flow.x*.8);"
  "col=mix(vec3(.105,.285,.275),vec3(.25,.44,.43),current);"
  "float facing=abs(normalize(waterEye-pos).y);float calm=1.-smoothstep(2.,10.,length((pos.xz-vec2(15.,8.))*vec2(1.,.7)));"
  "alpha=mix(.23,.095,calm)+.12*overcast+.08*(1.-calm)*smoothstep(.73,.99,riffle);"
  "float chop=(.018+.028*overcast)*(1.-.65*calm);"
  "vec3 normal=normalize(vec3(chop*(riffle+.6*sin(3.*flow.x+2.*current)),1.,chop*cos(3.8*flow.y+5.*current)));"
  "vec3 ray=reflect(normalize(pos-waterEye),normal);ray.y=max(.015,ray.y);"
  "reflected=reflectedBank(normalize(ray));float fresnel=.018+.94*pow(1.-facing,mix(3.5,7.,calm));"
  "alpha=alpha+(1.-alpha)*fresnel;reflection=fresnel/alpha;"
  "float fade=1.-smoothstep(25.,110.,distanceToEye);"
  "col+=vec3(.17,.21,.20)*fade*smoothstep(.82,.99,riffle)*smoothstep(.46,.80,current);}"
  "if(highDetail!=0 && animal!=0 && distanceToEye<16.){float strands=noise(vec2((pos.x+.3*pos.z)*55.,(pos.y+.15*pos.x)*245.));"
  "col*=1.+.20*(strands-.5)*(1.-smoothstep(3.,16.,distanceToEye));}"
  "if(tint.a>.9 && animal==0){float elev=pos.y+originY;"
  "if(season==1)col=mix(col,col*vec3(1.28,1.02,.76),.65);"
  "if(season==2 || season==3){float line=season==2?520.:1600.;"
  "float cover=smoothstep(line-95.,line+150.,elev+110.*noise(pos.xz*.045));"
  "col=mix(col,vec3(.79,.85,.88),cover*.88);}}"
  "if(regional!=0 && tint.a>=.979 && pos.y+originY>2350.){"
  "float up=clamp((tint.a-.98)*50.,0.,1.);float elev=pos.y+originY;"
  "float seams=.59*noise(pos.xz*.013)+.28*noise(pos.xz*.043)+.13*noise(pos.xz*.12);"
  "float line=smoothstep(2450.,3150.,elev);float retention=up+.48*(seams-.5)+.15*line;"
  // Filter wind lines and ice grains when a screen pixel spans several periods.
  "vec2 wind=vec2(pos.x+.31*pos.z,pos.z-.31*pos.x);"
  "float phase=wind.x*2.8+3.*noise(wind*.17);"
  "float ripple=cos(phase)*(1.-smoothstep(.6,2.8,fwidth(phase)));"
  "float grain=(noise(pos.xz*9.)-.5)*(1.-smoothstep(.025,.12,length(fwidth(pos.xz))));"
  "float light=clamp(dot(tint.rgb,vec3(.30,.59,.11)),0.,1.);"
  "vec3 rock=mix(vec3(.21,.22,.27),vec3(.48,.43,.42),seams)*(.89+.22*noise(wind*.9));"
  "vec3 snow=mix(vec3(.63,.73,.84),vec3(.96,.97,.98),smoothstep(.22,.85,light));"
  "vec2 crust=vec2(wind.x+.38*pos.y,wind.y-.61*pos.y);"
  "float flecks=(noise(crust*32.)-.5)*(1.-smoothstep(.008,.045,length(fwidth(crust))));"
  "float grit=(noise(crust*6.)-.5)*(1.-smoothstep(.04,.24,length(fwidth(crust))));"
  "rock*=1.+.31*grit+.17*flecks;"
  "snow+=vec3(.021*ripple+.033*grain+.045*(seams-.5)+.040*flecks);"
  "col=mix(col,mix(rock,snow,smoothstep(.78,.94,retention)),smoothstep(2350.,2750.,elev));}"
  "col*=mix(vec3(1.),vec3(.52,.63,.72),castShade);"
  "float haze=1.-exp(-distanceToEye*hazeDensity);vec3 lit=col*mix(vec3(.24,.32,.47),vec3(1.),daylight);"
  // Nearby pendant and counter lamps illuminate surfaces in the covered arcade.
  "if(marketNear!=0){vec3 delta=pos-marketLamps[0];vec2 axis=vec2(-.5299,.8480),along=vec2(-.8480,-.5299);"
  "vec3 local=vec3(dot(delta.xz,axis),delta.y+4.25,dot(delta.xz,along)-1.45);"
  "if(local.x> -28. && local.x<57. && local.z>-.8 && local.z<8.8 && local.y<3.6){"
  "vec3 n=normalize(cross(dFdx(relativePos),dFdy(relativePos)));if(dot(n,waterEye-pos)<0.)n=-n;"
  "vec3 normal=vec3(dot(n.xz,axis),n.y,dot(n.xz,along));"
  "vec3 eyeDir=normalize(-relativePos);vec3 viewDir=vec3(dot(eyeDir.xz,axis),eyeDir.y,dot(eyeDir.xz,along));"
  "float spec=0.;float diffuse=0.;for(int i=0;i<2;i++){float spacing=i==0?4.:2.;"
  "vec3 d=vec3(spacing*floor(local.x/spacing+.5)-local.x,(i==0?2.77:2.86)-local.y,(i==0?2.69:5.15)-local.z);"
  "float dist2=max(.06,dot(d,d));vec3 lightDir=d*inversesqrt(dist2);"
  "diffuse+=max(0.,dot(normal,lightDir))*(2.1/(1.+dist2));"
  "spec+=pow(max(0.,dot(normal,normalize(lightDir+viewDir))),24.)/(1.+dist2);}"
  "lit=col*(vec3(.45,.39,.34)+daylight*vec3(.15,.22,.30)+vec3(1.,.79,.55)*diffuse);"
  "if(abs(tint.a-.256)<.0001){float bay=abs(mod(local.x+2.,4.)-2.);"
  "float post=length(vec2(bay,local.z+.825));float base=exp(-3.*post);"
  "float stall=exp(-2.*length(max(vec2(bay-1.65,abs(local.z-5.25)-.75),0.)));"
  "if(local.x> -2. && local.x<6.)stall=0.;lit*=1.-.38*stall-.24*base;}"
  "if(abs(tint.a-.256)<.0001||abs(tint.a-.244)<.0001||abs(tint.a-.259)<.0001)lit+=vec3(.67,.49,.30)*spec;}}"
  "if(regional==2 && abs(tint.a-.247)<.0001)lit=tint.rgb;lit+=marketSpec;if(marketNear!=0)lit+=lampGlow(normalize(pos-waterEye),distanceToEye);gl_FragColor=vec4(mix(mix(lit,reflected,reflection),horizon(),haze),alpha);}";
 GLuint vert=wildlife_shader(GL_VERTEX_SHADER,vs);if(!vert)return 0;
 GLuint frag=wildlife_shader(GL_FRAGMENT_SHADER,fs);if(!frag){glDeleteShader(vert);return 0;}
 GLuint program=glCreateProgram();glAttachShader(program,vert);glAttachShader(program,frag);
 glLinkProgram(program);glDeleteShader(frag);glDeleteShader(vert);
 GLint ok;glGetProgramiv(program,GL_LINK_STATUS,&ok);
 if(!ok){SDL_SetError("Rainier terrain shader link failed");glDeleteProgram(program);return 0;}
 return program;
}

/* Sample a blurred copy of the scene before drawing the sharp trail controls. */
static GLuint river_bloom_program(void){
 const char *vs="#version 120\n varying vec2 uv;void main(){uv=gl_Vertex.xy*.5+.5;gl_Position=gl_Vertex;}";
 const char *fs="#version 120\n varying vec2 uv;uniform sampler2D scene;uniform vec2 stepUV;"
  "float luma(vec3 c){return dot(c,vec3(.299,.587,.114));}"
  "void main(){vec2 px=stepUV*.25;vec3 center=texture2D(scene,uv).rgb;"
  "vec3 left=texture2D(scene,uv-vec2(px.x,0.)).rgb,right=texture2D(scene,uv+vec2(px.x,0.)).rgb;"
  "vec3 up=texture2D(scene,uv+vec2(0.,px.y)).rgb,down=texture2D(scene,uv-vec2(0.,px.y)).rgb;"
  "float gx=abs(luma(left)-luma(right)),gy=abs(luma(up)-luma(down));"
  "float diagonal=min(gx,gy)/max(.001,max(gx,gy));"
  "vec3 color=mix(center,.25*(left+right+up+down),.42*diagonal*smoothstep(.05,.22,gx+gy));"
  "vec3 blur=.25*(texture2D(scene,uv+stepUV).rgb+texture2D(scene,uv-stepUV).rgb"
  "+texture2D(scene,uv+vec2(stepUV.x,-stepUV.y)).rgb+texture2D(scene,uv+vec2(-stepUV.x,stepUV.y)).rgb);"
  "gl_FragColor=vec4(color+.08*max(blur-vec3(.72),vec3(0.)),1.);}";
 GLuint v=wildlife_shader(GL_VERTEX_SHADER,vs);if(!v)return 0;
 GLuint f=wildlife_shader(GL_FRAGMENT_SHADER,fs);if(!f){glDeleteShader(v);return 0;}
 GLuint program=glCreateProgram();glAttachShader(program,v);glAttachShader(program,f);glLinkProgram(program);
 glDeleteShader(v);glDeleteShader(f);GLint ok;glGetProgramiv(program,GL_LINK_STATUS,&ok);
 if(!ok){glDeleteProgram(program);return 0;}return program;
}

static void river_bloom(struct gpu_scene *s,int x,int y,int w,int h){
 if(!s->rainier_bloom && !s->rainier_bloom_failed){
  s->rainier_bloom=river_bloom_program();s->rainier_bloom_failed=!s->rainier_bloom;
 }
 if(!s->rainier_bloom||s->rainier_bloom_failed)return;
 glActiveTexture(GL_TEXTURE0);
 if(!s->rainier_color)glGenTextures(1,&s->rainier_color);
 glBindTexture(GL_TEXTURE_2D,s->rainier_color);
 if(s->bloom_w!=w||s->bloom_h!=h){
  glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);
  glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
  glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
  glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,w,h,0,GL_RGBA,GL_UNSIGNED_BYTE,NULL);
  GLint allocated=0;glGetTexLevelParameteriv(GL_TEXTURE_2D,0,GL_TEXTURE_WIDTH,&allocated);
  if(allocated!=w){s->rainier_bloom_failed=1;return;}
  s->bloom_w=w;s->bloom_h=h;
 }
 glCopyTexSubImage2D(GL_TEXTURE_2D,0,0,0,x,y,w,h);
 glUseProgram(s->rainier_bloom);glUniform2f(glGetUniformLocation(s->rainier_bloom,"stepUV"),4.f/w,4.f/h);
 glDisable(GL_DEPTH_TEST);glDisable(GL_BLEND);
 glBegin(GL_TRIANGLE_STRIP);glVertex2f(-1,-1);glVertex2f(1,-1);glVertex2f(-1,1);glVertex2f(1,1);glEnd();
 glDisable(GL_BLEND);
}

/* Consecutive triangles in the plant meshes are spatially coherent. Keep a
 * conservative bounding sphere per batch and combine adjacent visible draws. */
enum { RIVER_BATCH=384 };
static void river_bounds_build(struct gpu_scene *s,const float *vertices,unsigned count){
 free(s->river_blocks);s->river_blocks=calloc((count+RIVER_BATCH-1)/RIVER_BATCH,sizeof(*s->river_blocks));
 if(!s->river_blocks)return;
 for(unsigned first=0;first<count;first+=RIVER_BATCH){
  unsigned end=first+RIVER_BATCH<count?first+RIVER_BATCH:count;
  float lo[3],hi[3];memcpy(lo,vertices+7*first,sizeof(lo));memcpy(hi,lo,sizeof(hi));
  for(unsigned i=first+1;i<end;i++)for(int k=0;k<3;k++){
   float v=vertices[7*i+k];lo[k]=fminf(lo[k],v);hi[k]=fmaxf(hi[k],v);
  }
  float dx=hi[0]-lo[0],dy=hi[1]-lo[1],dz=hi[2]-lo[2];
  s->river_blocks[first/RIVER_BATCH]=(struct river_bounds){lo[0]+dx*.5f,lo[1]+dy*.5f,lo[2]+dz*.5f,.5f*sqrtf(dx*dx+dy*dy+dz*dz)+.01f};
 }
}

static int river_outside_view(struct river_bounds b,float x,float y,float z,
                             float sy,float cy,float sp,float cp,float cb,float sb,
                             float tx,float ty,float kx,float ky){
 float dx=b.x-x,dy=b.y-y,dz=b.z-z;
 float forward=sy*dx+cy*dz,depth=cp*forward-sp*dy;
 float side=cy*dx-sy*dz,up=sp*forward+cp*dy;
 return depth+b.r<.2f || fabsf(cb*side-sb*up)>depth*tx+b.r*kx ||
        fabsf(sb*side+cb*up)>depth*ty+b.r*ky;
}

static void river_draw_land(struct gpu_scene *s,unsigned count,unsigned skip,float x,float y,float z,float yaw,float pitch,float aspect,float cb,float sb){
 if(!s->river_blocks){glDrawArrays(GL_TRIANGLES,(GLint)skip,(GLsizei)(count-skip));return;}
 float sy=sinf(yaw),cy=cosf(yaw),sp=sinf(pitch),cp=cosf(pitch);
 float ty=.5543f,tx=ty*aspect,kx=sqrtf(1+tx*tx),ky=sqrtf(1+ty*ty);
 unsigned start=skip;
 for(unsigned first=skip/RIVER_BATCH*RIVER_BATCH;first<count;first+=RIVER_BATCH){
  struct river_bounds b=s->river_blocks[first/RIVER_BATCH];
  if(river_outside_view(b,x,y,z,sy,cy,sp,cp,cb,sb,tx,ty,kx,ky)){
   if(first>start)glDrawArrays(GL_TRIANGLES,(GLint)start,(GLsizei)(first-start));
   start=first+RIVER_BATCH;
  }
 }
 if(count>start)glDrawArrays(GL_TRIANGLES,(GLint)start,(GLsizei)(count-start));
}

struct rainier_animal {
 unsigned first,second,index,count,stride;
 float blend,x,y,z,heading,shadow,slope_x,slope_z;
};

static void river_hiker_band(float bottom,float top,float base,float rim,float r,float g,float b){
 glBegin(GL_QUAD_STRIP);
 for(int j=0;j<=8;j++){
  float a=j*.78539816f,x=cosf(a),z=sinf(a);
  float light=.78f+.16f*x-.06f*z;
  glColor3f(r*light,g*light,b*light);
  glVertex3f(x*base,bottom,z*base);glVertex3f(x*rim,top,z*rim);
 }
 glEnd();
}

#include "market_life.h"

/* Pilot-relative equipment pass. The central view stays open for navigation. */
static void flight_sail_vertex(int powered,float u,float chord,float puff,float light){
 float side=fabsf(u),profile=sqrtf(fmaxf(0,1-u*u));
 float depth=powered?3.7f-.55f*u*u:4.25f-1.35f*side;
 float length=powered?.26f+.95f*profile:1.45f*(1-.85f*side);
 float height=powered?2.60f-.99f*u*u:2.84f-1.24f*side;
 float camber=sinf(chord*3.14159f);
 height+=.09f*camber-(powered?.085f:.016f)*puff*camber-.10f*chord;
 float red=.86f,green=.34f,blue=.14f;
 if(chord>.72f || side>.85f){red=.12f;green=.37f;blue=.41f;}
 else if(chord>.52f){red=.91f;green=.76f;blue=.50f;}
 if(!powered){
  red=.83f;green=.85f;blue=.78f;
  if(chord<.2f){red=.91f;green=.59f;blue=.13f;}
  if(side>.72f+.13f*chord || side<.025f){red=.15f;green=.37f;blue=.39f;}
 }
 glColor3f(red*light,green*light,blue*light);
 glVertex3f(3.65f*u,height,-depth+chord*length);
}

int pocket_scene_drop_flight_photo(void *ptr,unsigned slot){
 struct gpu_scene *s=ptr;
 if(!s||slot>=111||scene_target(s,s->canvas)||SDL_RenderFlush(s->device))return -1;
 glDeleteTextures(1,&s->flight_photo[slot]);glDeleteBuffers(1,&s->flight_mesh[slot]);
 s->flight_photo[slot]=s->flight_mesh[slot]=s->flight_count[slot]=0;
 s->flight_areas[slot][2]=0;
 return 0;
}
int pocket_scene_flight_photo(void *ptr,unsigned slot,unsigned pixels,const unsigned char *rgb,float x,float z,float width,const float *mesh,unsigned count){
 struct gpu_scene *s=ptr;
 if(!s||slot>=111||(pixels!=512 && pixels!=1024 && pixels!=2048)||!mesh||!count||count>128*128*6||!rgb||scene_target(s,s->canvas)||SDL_RenderFlush(s->device))return -1;
 glPushAttrib(GL_TEXTURE_BIT);glActiveTexture(GL_TEXTURE1);
 glPushClientAttrib(GL_CLIENT_PIXEL_STORE_BIT);glBindBuffer(GL_PIXEL_UNPACK_BUFFER,0);
 glPixelStorei(GL_UNPACK_ALIGNMENT,1);glPixelStorei(GL_UNPACK_ROW_LENGTH,0);
 glPixelStorei(GL_UNPACK_SKIP_PIXELS,0);glPixelStorei(GL_UNPACK_SKIP_ROWS,0);
 if(!s->flight_photo[slot])glGenTextures(1,&s->flight_photo[slot]);
 glBindTexture(GL_TEXTURE_2D,s->flight_photo[slot]);
 glTexImage2D(GL_TEXTURE_2D,0,GL_RGB,pixels,pixels,0,GL_RGB,GL_UNSIGNED_BYTE,rgb);glGenerateMipmap(GL_TEXTURE_2D);
 glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR_MIPMAP_LINEAR);
 glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
#ifdef GL_TEXTURE_MAX_ANISOTROPY_EXT
 if(SDL_GL_ExtensionSupported("GL_EXT_texture_filter_anisotropic")){
  GLfloat limit;glGetFloatv(GL_MAX_TEXTURE_MAX_ANISOTROPY_EXT,&limit);
  glTexParameterf(GL_TEXTURE_2D,GL_TEXTURE_MAX_ANISOTROPY_EXT,fminf(8.f,limit));
 }
#endif
 glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
 glPopClientAttrib();glPopAttrib();
 GLint previous;glGetIntegerv(GL_ARRAY_BUFFER_BINDING,&previous);
 if(!s->flight_mesh[slot])glGenBuffers(1,&s->flight_mesh[slot]);
 glBindBuffer(GL_ARRAY_BUFFER,s->flight_mesh[slot]);
 glBufferData(GL_ARRAY_BUFFER,count*7*sizeof(float),mesh,GL_STATIC_DRAW);
 glBindBuffer(GL_ARRAY_BUFFER,(GLuint)previous);
 s->flight_count[slot]=(GLsizei)count;
 s->flight_areas[slot][0]=x;s->flight_areas[slot][1]=z;s->flight_areas[slot][2]=width*.5f;
 return 0;
}
int pocket_scene_market_materials(void *ptr,const unsigned char *pixels,unsigned bytes){
 struct gpu_scene *s=ptr;
 if(!s||!pixels||bytes!=512u*512u*4u)return -1;
 if(s->market_materials)return 0;
 glPushAttrib(GL_TEXTURE_BIT);glActiveTexture(GL_TEXTURE2);
 glPushClientAttrib(GL_CLIENT_PIXEL_STORE_BIT);glBindBuffer(GL_PIXEL_UNPACK_BUFFER,0);
 glPixelStorei(GL_UNPACK_ALIGNMENT,1);glPixelStorei(GL_UNPACK_ROW_LENGTH,0);
 glPixelStorei(GL_UNPACK_SKIP_ROWS,0);glPixelStorei(GL_UNPACK_SKIP_PIXELS,0);
 glGenTextures(1,&s->market_materials);glBindTexture(GL_TEXTURE_2D,s->market_materials);
 glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,512,512,0,GL_RGBA,GL_UNSIGNED_BYTE,pixels);
 glGenerateMipmap(GL_TEXTURE_2D);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR_MIPMAP_LINEAR);
 GLint w;glGetTexLevelParameteriv(GL_TEXTURE_2D,0,GL_TEXTURE_WIDTH,&w);
 glPopClientAttrib();glPopAttrib();
 if(w!=512){glDeleteTextures(1,&s->market_materials);s->market_materials=0;return -1;}
 return 0;
}
void pocket_scene_market_lights(void *ptr,const float *lamps,int glow){
 struct gpu_scene *s=ptr;
 if(lamps)memcpy(s->market_lamps,lamps,sizeof(s->market_lamps));
 s->market_glow=glow;
}

int pocket_scene_coupe(void *ptr,const unsigned *groups,const float *mesh,unsigned count){
 struct gpu_scene *s=ptr;
 if(!s||!mesh||!groups||!count||count>300000)return -1;
 if(s->coupe_mesh)return 0;
 unsigned total=0;
 for(int i=0;i<29;i++){if(groups[i]>count-total)return -1;total+=groups[i];}
 if(total!=count||scene_target(s,s->canvas)||SDL_RenderFlush(s->device))return -1;
 GLint previous,size;
 glGetIntegerv(GL_ARRAY_BUFFER_BINDING,&previous);
 glGenBuffers(1,&s->coupe_mesh);glBindBuffer(GL_ARRAY_BUFFER,s->coupe_mesh);
 glBufferData(GL_ARRAY_BUFFER,count*6*sizeof(float),mesh,GL_STATIC_DRAW);
 glGetBufferParameteriv(GL_ARRAY_BUFFER,GL_BUFFER_SIZE,&size);
 glBindBuffer(GL_ARRAY_BUFFER,(GLuint)previous);
 if(size!=(GLint)(count*6*sizeof(float))){
  glDeleteBuffers(1,&s->coupe_mesh);s->coupe_mesh=0;return -1;
 }
 memcpy(s->coupe_groups,groups,sizeof(s->coupe_groups));
 return 0;
}

int pocket_scene_snack(void *ptr,unsigned slot,const float *mesh,unsigned count){
 struct gpu_scene *s=ptr;
 if(!s||slot>1||!mesh||!count||count>100000)return -1;
 if(s->snack_mesh[slot])return 0;
 if(scene_target(s,s->canvas)||SDL_RenderFlush(s->device))return -1;
 GLint previous,size;
 glGetIntegerv(GL_ARRAY_BUFFER_BINDING,&previous);
 glGenBuffers(1,&s->snack_mesh[slot]);glBindBuffer(GL_ARRAY_BUFFER,s->snack_mesh[slot]);
 glBufferData(GL_ARRAY_BUFFER,count*6*sizeof(float),mesh,GL_STATIC_DRAW);
 glGetBufferParameteriv(GL_ARRAY_BUFFER,GL_BUFFER_SIZE,&size);
 glBindBuffer(GL_ARRAY_BUFFER,(GLuint)previous);
 if(size!=(GLint)(count*6*sizeof(float))){
  glDeleteBuffers(1,&s->snack_mesh[slot]);s->snack_mesh[slot]=0;
  return SDL_SetError("Could not upload market item");
 }
 s->snack_count[slot]=(GLsizei)count;
 return 0;
}

int pocket_scene_cockpit(void *ptr,const unsigned char *pixels,float speed,float altitude){
 struct gpu_scene *s=ptr;
 if(!s)return -1;
 s->cockpit_speed=speed;s->cockpit_altitude=altitude;
 if(s->cockpit_panel && !pixels)return 0;
 if(!pixels || scene_target(s,s->canvas) || SDL_RenderFlush(s->device))return -1;
 glPushAttrib(GL_TEXTURE_BIT);glActiveTexture(GL_TEXTURE0);
 glPushClientAttrib(GL_CLIENT_PIXEL_STORE_BIT);
 glBindBuffer(GL_PIXEL_UNPACK_BUFFER,0);glPixelStorei(GL_UNPACK_ALIGNMENT,1);
 glPixelStorei(GL_UNPACK_ROW_LENGTH,0);glPixelStorei(GL_UNPACK_SKIP_ROWS,0);glPixelStorei(GL_UNPACK_SKIP_PIXELS,0);
 if(!s->cockpit_panel)glGenTextures(1,&s->cockpit_panel);
 glBindTexture(GL_TEXTURE_2D,s->cockpit_panel);
 glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,1000,244,0,GL_RGBA,GL_UNSIGNED_BYTE,pixels);
 glGenerateMipmap(GL_TEXTURE_2D);
 glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR_MIPMAP_LINEAR);
 glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
 glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);
 glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
 GLint width;glGetTexLevelParameteriv(GL_TEXTURE_2D,0,GL_TEXTURE_WIDTH,&width);
 glPopClientAttrib();glPopAttrib();
 if(width!=1000){glDeleteTextures(1,&s->cockpit_panel);s->cockpit_panel=0;return SDL_SetError("Cockpit texture upload failed");}
 return 0;
}

static void dial_hand(float x,float angle,float reach,float half_width){
 glPushMatrix();glTranslatef(x,146,0);glRotatef(angle,0,0,1);
 glBegin(GL_TRIANGLE_FAN);
 glColor3f(.92f,.89f,.76f);glVertex2f(0,-reach);glVertex2f(half_width,0);
 glVertex2f(half_width*.62f,10);glVertex2f(-half_width*.62f,10);glVertex2f(-half_width,0);
 glEnd();glPopMatrix();
}

void pocket_scene_cockpit_look(void *ptr,float yaw,float pitch){
 struct gpu_scene *s=ptr;
 s->cockpit_look_yaw=yaw;s->cockpit_look_pitch=pitch;
}

static void instrument_panel(struct gpu_scene *s,const float *flight,int w,int h){
 glMatrixMode(GL_PROJECTION);glLoadIdentity();glOrtho(0,w,0,h,-1,1);
 glMatrixMode(GL_MODELVIEW);glLoadIdentity();
 int jet=flight[0]==9.f;
 float scale=jet?fminf(w/860.f,h/1060.f):fminf(w/815.f,h/610.f);
 float edge=w/(2.f*scale);
 glTranslatef(w*(.5f-.62f*tanf(s->cockpit_look_yaw)),h-w*.62f*tanf(s->cockpit_look_pitch),0);glScalef(scale,scale,1);glTranslatef(-500,-244,0);
 glUseProgram(0);glDisable(GL_DEPTH_TEST);glActiveTexture(GL_TEXTURE0);
 /* Enamel engine cover viewed over the padded glare shield. Its far end
    is narrower and higher in the windshield than the near shoulders. */
 glDisable(GL_TEXTURE_2D);glDisable(GL_BLEND);
 if(!jet){
  glBegin(GL_QUAD_STRIP);
  for(int i=0;i<=48;i++){
   float a=i*3.141593f/48.f,side=cosf(a),crown=sinf(a);
   float light=.51f+.24f*crown+.11f*side;
   glColor3f(light*.90f,light*.94f,light);glVertex2f(500+125*side,-2-17*crown);
   glColor3f(light*.69f,light*.74f,light*.77f);glVertex2f(500+320*side,44-20*crown);
  }
  glEnd();
 }
 glBindTexture(GL_TEXTURE_2D,s->cockpit_panel);glEnable(GL_TEXTURE_2D);
 glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);glColor4f(1,1,1,1);
 float ends[4]={fminf(0,500-edge),0,1000,fmaxf(1000,500+edge)};
 glBegin(GL_QUAD_STRIP);
 for(int i=0;i<4;i++){
  float u=i<2?.0005f:.9995f;
  glTexCoord2f(u,0);glVertex2f(ends[i],0);glTexCoord2f(u,1);glVertex2f(ends[i],244);
 }
 glEnd();glDisable(GL_TEXTURE_2D);glDisable(GL_BLEND);
 float max_knots=jet?900.f:300.f;
 dial_hand(304,-135.f+270.f*fminf(max_knots,s->cockpit_speed*1.9438445f)/max_knots,56,3);
 if(jet){
  dial_hand(159,flight[3]*57.29578f,37,2.4f);
  dial_hand(841,-130.f+260.f*flight[4],36,2.4f);
 }
 float feet=s->cockpit_altitude*3.28084f;
 dial_hand(696,feet*.0036f,22,5);dial_hand(696,feet*.036f,36,3.8f);dial_hand(696,feet*.36f,56,2.3f);
 glPushMatrix();glTranslatef(500,146,0);glRotatef(-55.f*flight[1],0,0,1);
 float pitch=-flight[2]*35.f;
 for(int ground=0;ground<=1;ground++){
  glBegin(GL_QUAD_STRIP);
  for(int i=0;i<=64;i++){
   float a=3.141593f*i/64,x=-54.f*cosf(a),cap=54.f*sinf(a),line=fminf(cap,fmaxf(-cap,pitch));
   if(ground)glColor3f(.64f,.41f,.23f);else glColor3f(.22f,.45f,.61f);
   glVertex2f(x,ground?line:-cap);
   if(ground)glColor3f(.40f,.27f,.18f);else glColor3f(.49f,.68f,.75f);
   glVertex2f(x,ground?cap:line);
  }
  glEnd();
 }
 glColor3f(.93f,.90f,.80f);glBegin(GL_LINES);
 for(int j=-2;j<=2;j++){
  float y=pitch+j*9.f;if(fabsf(y)>=54.f)continue;
  float span=j==0?sqrtf(54*54-y*y):j%2?9.f:15.f;
  glVertex2f(-span,y);glVertex2f(span,y);
 }
 glEnd();glPopMatrix();
 glColor3f(.98f,.73f,.22f);glRectf(466,144,490,148);glRectf(510,144,534,148);
 glRectf(497,144,503,149);
}
/* Swept canopy bow and combiner glass of the civilian research cockpit. */
static void research_cockpit(struct gpu_scene *s,const float *flight,int w,int h){
 glMatrixMode(GL_PROJECTION);glLoadIdentity();glOrtho(-1,1,-1,1,-1,1);
 glMatrixMode(GL_MODELVIEW);glLoadIdentity();
 glTranslatef(-1.24f*tanf(s->cockpit_look_yaw),-1.24f*w/h*tanf(s->cockpit_look_pitch),0);
 glDisable(GL_TEXTURE_2D);glDisable(GL_DEPTH_TEST);glUseProgram(0);
 glBegin(GL_QUAD_STRIP);
 for(int i=0;i<=80;i++){
  float a=i*.039269908f,x=cosf(a),y=sinf(a);
  glColor3f(.08f,.12f,.14f);glVertex2f(1.12f*x,.78f-1.76f*y);
  glColor3f(.28f,.34f,.36f);glVertex2f(1.15f*x,.78f-1.80f*y);
 }
 glEnd();
 glBegin(GL_TRIANGLE_FAN);glColor3f(.055f,.08f,.09f);
 glVertex2f(0,1.1f);glVertex2f(-1.1f,1);glVertex2f(-.49f,.78f);
 glVertex2f(-.26f,.68f);glVertex2f(.26f,.68f);glVertex2f(.49f,.78f);glVertex2f(1.1f,1);
 glEnd();
 glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);
 glColor4f(.27f,.73f,.67f,.17f);glBegin(GL_QUADS);
 glVertex2f(-.26f,.67f);glVertex2f(-.20f,.26f);glVertex2f(.20f,.26f);glVertex2f(.26f,.67f);glEnd();
 glDisable(GL_BLEND);
 glTranslatef(0,.47f,0);glScalef((float)h/w,1,1);
 glColor3f(.55f,1.f,.72f);glRectf(-.035f,-.003f,.035f,.003f);
 glRotatef(-55.f*flight[1],0,0,1);
 glTranslatef(0,-.12f*flight[2],0);
 glRectf(-.10f,-.003f,-.05f,.003f);glRectf(.05f,-.003f,.10f,.003f);
}
/* Low driver-eye silhouettes leave the street and intersections visible. */
static void street_cockpit(const float *ride,int w,int h){
 glMatrixMode(GL_PROJECTION);glLoadIdentity();glOrtho(-1,1,1,-1,-1,1);
 glMatrixMode(GL_MODELVIEW);glLoadIdentity();glDisable(GL_TEXTURE_2D);
 glDisable(GL_DEPTH_TEST);glUseProgram(0);
 if(ride[0]==12.f){
  glBegin(GL_QUAD_STRIP);
  for(int i=0;i<=48;i++){
   float x=(i-24)/24.f,rise=x*x;
   glColor3f(.29f,.39f,.44f);glVertex2f(x,-.79f-.05f*rise);
   glColor3f(.07f,.13f,.16f);glVertex2f(x,-.88f-.05f*rise);
  }
  glEnd();glColor3f(.09f,.10f,.11f);glRectf(-1,-1,1,-.91f);
  glTranslatef(-.14f,-1.12f,0);glScalef((float)h/w,1,1);
  glRotatef(-55.f*ride[1],0,0,1);
  glBegin(GL_QUAD_STRIP);
  for(int i=0;i<=64;i++){
   float a=i*.09817477f,x=cosf(a),y=sinf(a);
   glColor3f(.12f,.13f,.14f);glVertex2f(.28f*x,.28f*y);
   glColor3f(.24f,.25f,.26f);glVertex2f(.31f*x,.31f*y);
  }
  glEnd();glColor3f(.12f,.13f,.14f);glRectf(-.29f,-.018f,.29f,.018f);
 }else if(ride[0]==16.f){
  glTranslatef(0,-.82f,0);glRotatef(-8.f*ride[1],0,0,1);
  glColor3f(.14f,.16f,.16f);glRectf(-.35f,-.025f,.35f,.018f);
  glColor3f(.28f,.63f,.46f);glRectf(-.018f,-.23f,.018f,0);
 }else{
  glTranslatef(0,-.91f,0);glRotatef(-5.f*ride[1],0,0,1);
  for(int side=-1;side<=1;side+=2){
   glBegin(GL_QUAD_STRIP);
   for(int i=0;i<=16;i++){
    float t=i/16.f,y=.14f*sinf(t*1.85f);
    if(i>11)glColor3f(.07f,.08f,.08f);else glColor3f(.64f,.67f,.66f);
    glVertex2f(side*t*.75f,y);
    glColor3f(.16f,.18f,.18f);glVertex2f(side*t*.75f,y-(i>11?.047f:.028f));
   }
   glEnd();
  }
  glColor3f(.13f,.15f,.16f);
  if(ride[0]==13.f)glRectf(-.15f,-.09f,.15f,.10f);
  else glRectf(-.035f,-.10f,.035f,.025f);
 }
}
static void flight_equipment(struct gpu_scene *s,const float *flight,int w,int h){
 if(flight[0]==15.f)return;
 if((flight[0]>=12.f && flight[0]<=14.f) || flight[0]==16.f){street_cockpit(flight,w,h);return;}
 if(flight[0]==9.f){research_cockpit(s,flight,w,h);instrument_panel(s,flight,w,h);return;}
 int powered=flight[0]>.5f;
 float aspect=(float)w/h;
 glMatrixMode(GL_PROJECTION);glLoadIdentity();
 glFrustum(-.91,.91,.91/aspect,-.91/aspect,1.,12.);
 glMatrixMode(GL_MODELVIEW);glLoadIdentity();
 /* Keep the overhead equipment in view with a tall phone viewport. */
 glScalef(1,1/aspect,1);
 if(flight[0]!=2.f)glRotatef(-7.f*flight[1],0,0,1);
 glTranslatef(0,.17f*flight[2],0);
 glDisable(GL_DEPTH_TEST);glUseProgram(0);
 if(flight[0]==10.f || flight[0]==11.f){
  glDisable(GL_TEXTURE_2D);
  int balloon=flight[0]==11.f;
  for(int side=-1;side<=1;side+=2){
   float x=(float)side;
   glColor3f(.23f,.20f,.15f);glBegin(GL_QUADS);
   glVertex3f(.93f*x,-1.5f,-1.6f);glVertex3f(.97f*x,-1.5f,-1.6f);
   glVertex3f(1.22f*x,1.5f,-1.6f);glVertex3f(1.20f*x,1.5f,-1.6f);glEnd();
  }
  if(balloon){
   glColor3f(.42f,.27f,.14f);glBegin(GL_QUADS);
   glVertex3f(-1.6f,-1.f,-1.5f);glVertex3f(1.6f,-1.f,-1.5f);
   glVertex3f(1.6f,-1.5f,-1.5f);glVertex3f(-1.6f,-1.5f,-1.5f);glEnd();
  }else{
   for(int i=-8;i<8;i++){
    float x=i*.19f,xx=x+.19f;
    glColor3f(i%2?.83f:.94f,i%2?.42f:.69f,.18f);glBegin(GL_QUADS);
    glVertex3f(x,.95f-.14f*x*x,-1.4f);glVertex3f(xx,.95f-.14f*xx*xx,-1.4f);
    glVertex3f(xx,1.3f,-1.4f);glVertex3f(x,1.3f,-1.4f);glEnd();
   }
  }
  return;
 }
 if(flight[0]>=5.f){
  glTranslatef(.87f,-1.05f,-1.88f);glScalef(1,-1,1);
  if(flight[0]==5.f||flight[0]==6.f){
   unsigned slot=flight[0]==6.f;
   glScalef(3.8f,-3.8f,3.8f);glRotatef(162,0,1,0);
   glRotatef(slot?-22.f:-8.f,1,0,0);
   glPushAttrib(GL_DEPTH_BUFFER_BIT|GL_VIEWPORT_BIT|GL_TEXTURE_BIT);
   glEnable(GL_DEPTH_TEST);glDepthMask(GL_TRUE);glDepthFunc(GL_LEQUAL);glDepthRange(0.,.001);
   glActiveTexture(GL_TEXTURE0);glDisable(GL_TEXTURE_2D);
   glPushClientAttrib(GL_CLIENT_VERTEX_ARRAY_BIT);
   glBindBuffer(GL_ARRAY_BUFFER,s->snack_mesh[slot]);
   glEnableClientState(GL_VERTEX_ARRAY);glEnableClientState(GL_COLOR_ARRAY);
   glVertexPointer(3,GL_FLOAT,6*sizeof(float),0);glColorPointer(3,GL_FLOAT,6*sizeof(float),(const void *)(3*sizeof(float)));
   glDrawArrays(GL_TRIANGLES,0,s->snack_count[slot]);
   glPopClientAttrib();glPopAttrib();
  }else if(flight[0]==7.f){
   glScalef(2.f,-2.f,2.f);glTranslatef(.19f,-.91f,-.14f);
   market_flowers();
  }else if(flight[0]==8.f){
   for(int band=0;band<3;band++){
    float y=band==0?-.22f:band==1?-.15f:.08f;
    float end=band==0?-.15f:band==1?.08f:.24f,r=band==0?.157f:.15f;
    glBegin(GL_QUAD_STRIP);
    for(int i=0;i<=32;i++){
     float a=i*.19634954f,light=.8f+.18f*cosf(a);
     glColor3f((band==0?.74f:band==1?.83f:.97f)*light,
               (band==0?.64f:band==1?.43f:.83f)*light,(band==1?.12f:.44f)*light);
     glVertex3f(r*cosf(a),y,r*sinf(a));glVertex3f(r*cosf(a),end,r*sinf(a));
    }
    glEnd();
   }
   market_body(0,-.22f,0,.157f,.022f,.157f,.72f,.62f,.38f);

  }
  return;
 }
 if(flight[0]>=2.f){
  if(flight[0]==2.f){
   instrument_panel(s,flight,w,h);
  }else if(flight[0]==3.f){
   glBegin(GL_TRIANGLES);glColor3f(.67f,.74f,.72f);glVertex3f(-1.7f,-1.8f,-1.5f);
   glVertex3f(0,-.9f,-3.3f);glColor3f(.38f,.49f,.50f);glVertex3f(1.7f,-1.8f,-1.5f);glEnd();
  }else{
   /* Painted deck, bulwark, uprights and stainless top rail. */
   glBegin(GL_QUADS);
   glColor3f(.22f,.31f,.29f);glVertex3f(-3,-1.7f,-1.1f);glVertex3f(3,-1.7f,-1.1f);
   glVertex3f(3,-1.7f,-2.8f);glVertex3f(-3,-1.7f,-2.8f);
   glColor3f(.75f,.78f,.73f);glVertex3f(-3,-1.7f,-2.8f);glVertex3f(3,-1.7f,-2.8f);
   glVertex3f(3,-1.29f,-2.8f);glVertex3f(-3,-1.29f,-2.8f);
   for(int i=-2;i<=2;i++){
    float u=.58f+1.18f*i;
    glColor3f(.68f,.72f,.70f);glVertex3f(u,-1.35f,-2.8f);glVertex3f(u+.036f,-1.35f,-2.8f);
    glVertex3f(u+.036f,-.73f,-2.8f);glVertex3f(u,-.73f,-2.8f);
   }
   for(int i=0;i<2;i++){
    float v=-.75f-i*.30f;
    glColor3f(.56f,.62f,.61f);glVertex3f(-3,v,-2.8f);glVertex3f(3,v,-2.8f);
    glColor3f(.87f,.90f,.86f);glVertex3f(3,v+.034f,-2.8f);glVertex3f(-3,v+.034f,-2.8f);
   }
   glEnd();
  }
  return;
 }
 for(int side=-1;side<=1;side+=2){
  if(powered){
   glColor3f(.32f,.33f,.29f);glBegin(GL_LINES);
   for(int line=0;line<5;line++){
    float u=.30f+.15f*line;
    glVertex3f(side*1.38f,-.08f,-1.72f);
    glVertex3f(side*3.65f*u,2.60f-.99f*u*u,-3.7f+.55f*u*u);
   }
   glEnd();
   glColor3f(.15f,.19f,.18f);glBegin(GL_QUADS);
   glVertex3f(side*1.35f,-.08f,-1.72f);glVertex3f(side*1.41f,-.08f,-1.72f);
   glVertex3f(side*1.63f,-.75f,-1.72f);glVertex3f(side*1.54f,-.75f,-1.72f);glEnd();
  }else{
   glBegin(GL_QUAD_STRIP);
   for(int i=0;i<=8;i++){
    float a=i*.785398f,c=cosf(a),sn=sinf(a),shine=.65f+.25f*c;
    glColor3f(shine*.88f,shine*.95f,shine);
    glVertex3f(side*.28f+.032f*c,2.75f,-3.8f+.032f*sn);
    glVertex3f(side*1.58f+.032f*c,-1.20f,-1.55f+.032f*sn);
   }
   glEnd();
  }
 }
 const int ribs=powered?32:14;
 for(int rib=0;rib<ribs;rib++){
  for(int strip=0;strip<4;strip++){
   glBegin(GL_TRIANGLE_STRIP);
   for(int i=0;i<=10;i++){
    float chord=i*.1f;
    for(int k=0;k<2;k++){
     float t=(strip+k)*.25f,puff=sinf(t*3.14159f);
     float u=2.f*(rib+t)/ribs-1.f;
     float light=.77f+(powered?.18f:.045f)*puff+.09f*sinf(chord*3.14159f)-.07f*u;
     if(powered && i==0)light*=.50f;
     flight_sail_vertex(powered,u,chord,puff,light);
    }
   }
   glEnd();
  }
 }
}

int pocket_scene_rainier(void *ptr,int x,int y,int w,int h,const float *vertices,unsigned count,
                         unsigned terrain_count,const unsigned *indices,unsigned ni,
                         const struct rainier_animal *animals,unsigned na,
                         float east,float eye,float north,float yaw,float pitch,float age,int picked,float direction,int fed,int high,const unsigned char *shadows,const float *hikers,unsigned nh,const float *marker,const float *ripple,int lens,unsigned char *photo,int photo_animal,float focal,int camp,int season,int weather,float originY,float daylight,float sun_angle,float center_x,float center_z,const float *grove,unsigned grove_count,unsigned water_count,unsigned omit_first,unsigned omit_end,const float *aircraft,const float *market,unsigned market_count){
 struct gpu_scene *s=ptr;
 if(!s||w<1||h<1||count<3||count>4000000||(!vertices&&!s->rainier_buffer))
  return SDL_SetError("Invalid Rainier scene");
 if(market_count>32||(market_count&&!market)||omit_first>omit_end||omit_end>terrain_count||(omit_end&&water_count)||water_count>terrain_count||grove_count>250000||nh>7||(nh&&!hikers)||terrain_count>count||ni>2000000||na>64||(!animals&&na)||
    (!!vertices!=!!indices)||(!indices&&!s->rainier_indices))return SDL_SetError("Invalid Rainier wildlife buffers");
 for(unsigned i=0;i<na;i++){
  const struct rainier_animal *a=animals+i;
  if(!a->stride||a->stride>count||a->first>count-a->stride||a->second>count-a->stride||
     a->index>ni||a->count>ni-a->index)return SDL_SetError("Invalid Rainier wildlife span");
  if(indices)for(unsigned j=0;j<a->count;j++)if(indices[a->index+j]>=a->stride)return SDL_SetError("Invalid Rainier wildlife index");
 }
 if(scene_target(s,s->canvas)||SDL_RenderFlush(s->device))return -1;
 if(!s->rainier_program){s->rainier_program=rainier_program();if(!s->rainier_program)return -1;}
 GLint previous_program,previous_buffer,previous_indices,previous_depth;
 glGetIntegerv(GL_CURRENT_PROGRAM,&previous_program);
 glGetIntegerv(GL_ARRAY_BUFFER_BINDING,&previous_buffer);
 glGetIntegerv(GL_ELEMENT_ARRAY_BUFFER_BINDING,&previous_indices);
 glGetIntegerv(GL_RENDERBUFFER_BINDING,&previous_depth);
 glPushAttrib(GL_ALL_ATTRIB_BITS);glPushClientAttrib(GL_CLIENT_VERTEX_ARRAY_BIT);
 if(!s->rainier_buffer)glGenBuffers(1,&s->rainier_buffer);
 glBindBuffer(GL_ARRAY_BUFFER,s->rainier_buffer);
 if(vertices){glBufferData(GL_ARRAY_BUFFER,(size_t)count*7*sizeof(float),vertices,GL_STATIC_DRAW);river_bounds_build(s,vertices,terrain_count);}
 if(!s->rainier_indices)glGenBuffers(1,&s->rainier_indices);
 glBindBuffer(GL_ELEMENT_ARRAY_BUFFER,s->rainier_indices);
 if(indices)glBufferData(GL_ELEMENT_ARRAY_BUFFER,(size_t)ni*sizeof(*indices),indices,GL_STATIC_DRAW);
 if(!s->rainier_depth)glGenRenderbuffers(1,&s->rainier_depth);
 glBindRenderbuffer(GL_RENDERBUFFER,s->rainier_depth);
 if(s->rainier_w!=s->width||s->rainier_h!=s->height){
  glRenderbufferStorage(GL_RENDERBUFFER,GL_DEPTH_COMPONENT24,s->width,s->height);
  s->rainier_w=s->width;s->rainier_h=s->height;
 }
 glFramebufferRenderbuffer(GL_FRAMEBUFFER,GL_DEPTH_ATTACHMENT,GL_RENDERBUFFER,s->rainier_depth);
 int result=0;
 if(vertices){
  GLint vb=0,ib=0;glGetBufferParameteriv(GL_ARRAY_BUFFER,GL_BUFFER_SIZE,&vb);
  glGetBufferParameteriv(GL_ELEMENT_ARRAY_BUFFER,GL_BUFFER_SIZE,&ib);
  if(vb!=(GLint)(count*7*sizeof(float))||ib!=(GLint)(ni*sizeof(unsigned))){
   SDL_SetError("Insufficient graphics memory for Rainier geometry");result=-2;goto done;
  }
 }
 if(grove && grove_count){
  if(!s->rainier_grove)glGenBuffers(1,&s->rainier_grove);
  glBindBuffer(GL_ARRAY_BUFFER,s->rainier_grove);
  GLsizeiptr bytes=(GLsizeiptr)grove_count*7*sizeof(float);
  glBufferData(GL_ARRAY_BUFFER,bytes,grove,GL_DYNAMIC_DRAW);
  GLint allocated=0;glGetBufferParameteriv(GL_ARRAY_BUFFER,GL_BUFFER_SIZE,&allocated);
  glBindBuffer(GL_ARRAY_BUFFER,s->rainier_buffer);
  s->rainier_grove_count=allocated==bytes?grove_count:0;
 }
 if(glCheckFramebufferStatus(GL_FRAMEBUFFER)!=GL_FRAMEBUFFER_COMPLETE)
  glRenderbufferStorage(GL_RENDERBUFFER,GL_DEPTH_COMPONENT16,s->width,s->height);
 if(glCheckFramebufferStatus(GL_FRAMEBUFFER)!=GL_FRAMEBUFFER_COMPLETE){
  result=SDL_SetError("Rainier depth buffer unavailable");goto done;
 }
 glUseProgram(0);glDisable(GL_TEXTURE_2D);glDisable(GL_LIGHTING);glDisable(GL_BLEND);
 glDisable(GL_CULL_FACE);glEnable(GL_DEPTH_TEST);glDepthMask(GL_TRUE);glDepthFunc(GL_LEQUAL);
 glViewport(x,y,w,h);glEnable(GL_SCISSOR_TEST);glScissor(x,y,w,h);
 const GLfloat sky[]={.54f,.69f,.79f,1.f};
 glClearColor(sky[0],sky[1],sky[2],1);glClearDepth(1.);glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
 glDisable(GL_DEPTH_TEST);glDisable(GL_FOG);
 glMatrixMode(GL_PROJECTION);glPushMatrix();glLoadIdentity();
 glMatrixMode(GL_MODELVIEW);glPushMatrix();glLoadIdentity();
 glUseProgram(s->rainier_program);
 GLint sky_pass=glGetUniformLocation(s->rainier_program,"skyPass");
 float roll=aircraft && (aircraft[0]==2.f || aircraft[0]==9.f)?55.f*aircraft[1]:0.f;
 float cb=cosf(roll*.017453293f),sb=sinf(roll*.017453293f);
 glUniform2f(glGetUniformLocation(s->rainier_program,"bankCS"),cb,sb);
 glUniform1i(glGetUniformLocation(s->rainier_program,"underwater"),aircraft && aircraft[0]==15.f);
 int near_market=lens==-2 && s->market_glow && hypotf(east-s->market_lamps[0],north-s->market_lamps[2])<150.f;
 glUniform1i(glGetUniformLocation(s->rainier_program,"marketNear"),near_market);
 if(near_market)glUniform3fv(glGetUniformLocation(s->rainier_program,"marketLamps"),4,s->market_lamps);
 glUniform3f(glGetUniformLocation(s->rainier_program,"waterEye"),east,eye,north);
 glUniform1i(sky_pass,1);
 glUniform4f(glGetUniformLocation(s->rainier_program,"skyCamera"),yaw,pitch,(float)w/h,.5543f/fmaxf(1.f,focal));
 glUniform1f(glGetUniformLocation(s->rainier_program,"daylight"),daylight);
 glUniform1f(glGetUniformLocation(s->rainier_program,"overcast"),weather?1.f:0.f);
 glUniform1f(glGetUniformLocation(s->rainier_program,"waterTime"),age);
 glBegin(GL_TRIANGLE_STRIP);glVertex2f(-1,-1);glVertex2f(1,-1);glVertex2f(-1,1);glVertex2f(1,1);glEnd();
 glUniform1i(sky_pass,0);
 glPopMatrix();glMatrixMode(GL_PROJECTION);glPopMatrix();
 glEnable(GL_DEPTH_TEST);glUseProgram(s->rainier_program);
 glMatrixMode(GL_PROJECTION);glPushMatrix();glLoadIdentity();
 /* 58 degree vertical FOV; target texture row zero is the upper screen row. */
 double half=.2*.5543/fmaxf(1.f,focal),wide=half*w/h;
 glFrustum(-wide,wide,half,-half,.2,lens<0?330000.:85000.);
 glMatrixMode(GL_MODELVIEW);glPushMatrix();glLoadIdentity();
 glRotatef(roll,0,0,1);glScalef(1,1,-1);glRotatef(-pitch*57.29578f,1,0,0);glRotatef(-yaw*57.29578f,0,1,0);
 glTranslatef(-east,-eye,-north);
 glEnableClientState(GL_VERTEX_ARRAY);glEnableClientState(GL_COLOR_ARRAY);
 glClientActiveTexture(GL_TEXTURE0);glDisableClientState(GL_TEXTURE_COORD_ARRAY);
 glVertexPointer(3,GL_FLOAT,7*sizeof(float),0);
 glColorPointer(4,GL_FLOAT,7*sizeof(float),(const void *)(3*sizeof(float)));
 GLint blend=glGetUniformLocation(s->rainier_program,"poseBlend");
 glUniform1f(glGetUniformLocation(s->rainier_program,"hazeDensity"),(lens<0?(weather?.00018f:.000008f):.00042f*(weather?5.f:1.f)));
 glUniform1i(glGetUniformLocation(s->rainier_program,"camp"),camp&3);
 glUniform4f(glGetUniformLocation(s->rainier_program,"supplies"),(camp>>2)&1,(camp>>3)&1,(camp>>4)&1,(camp>>5)&1);
 glUniform1i(glGetUniformLocation(s->rainier_program,"season"),season);
 glUniform1f(glGetUniformLocation(s->rainier_program,"originY"),originY);
 glUniform3f(glGetUniformLocation(s->rainier_program,"picked"),picked&1,(picked>>1)&1,(picked>>2)&1);
 glUniform1f(glGetUniformLocation(s->rainier_program,"waterTime"),age);
 glActiveTexture(GL_TEXTURE2);glBindTexture(GL_TEXTURE_2D,s->market_materials);
 glUniform1i(glGetUniformLocation(s->rainier_program,"marketMaterials"),2);
 glActiveTexture(GL_TEXTURE0);
 glUniform1i(glGetUniformLocation(s->rainier_program,"flightPhoto"),1);
 GLint photo_area=glGetUniformLocation(s->rainier_program,"photoArea");
 glUniform3f(photo_area,0,0,0);
 glUniform3fv(glGetUniformLocation(s->rainier_program,"flightAreas[0]"),111,s->flight_areas[0]);
 float stretch=.55f+2.3f*(1.f-daylight);
 glUniform2f(glGetUniformLocation(s->rainier_program,"shadowStep"),cosf(sun_angle)*stretch,sinf(sun_angle)*stretch);
 glUniform2f(glGetUniformLocation(s->rainier_program,"shadeCenter"),center_x,center_z);
 glUniform1f(glGetUniformLocation(s->rainier_program,"hiddenPlane"),aircraft && aircraft[0]==2.f?.310f:aircraft && aircraft[0]==9.f?.311f:0.f);
 glUniform1i(glGetUniformLocation(s->rainier_program,"regional"),lens==-2?2:lens<0);
 if(shadows){
  if(!s->rainier_shadow)glGenTextures(1,&s->rainier_shadow);
  glBindTexture(GL_TEXTURE_2D,s->rainier_shadow);
  glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
  glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
  int canopy_size=lens<0?512:1024;
  /* SDL texture updates can leave a row pitch for a different image. */
  glPushClientAttrib(GL_CLIENT_PIXEL_STORE_BIT);
  glBindBuffer(GL_PIXEL_UNPACK_BUFFER,0);
  glPixelStorei(GL_UNPACK_ALIGNMENT,1);glPixelStorei(GL_UNPACK_ROW_LENGTH,0);
  glPixelStorei(GL_UNPACK_SKIP_PIXELS,0);glPixelStorei(GL_UNPACK_SKIP_ROWS,0);
  if(lens==-2){
   glTexImage2D(GL_TEXTURE_2D,0,GL_RGB,1280,1536,0,GL_RGB,GL_UNSIGNED_BYTE,shadows);
   glGenerateMipmap(GL_TEXTURE_2D);
   glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR_MIPMAP_LINEAR);
  }else glTexImage2D(GL_TEXTURE_2D,0,GL_LUMINANCE,canopy_size,canopy_size,0,GL_LUMINANCE,GL_UNSIGNED_BYTE,shadows);
  glPopClientAttrib();
 }else glBindTexture(GL_TEXTURE_2D,s->rainier_shadow);
 glUniform1i(glGetUniformLocation(s->rainier_program,"highDetail"),high);
 glUniform1i(glGetUniformLocation(s->rainier_program,"animal"),0);
 glUniform1f(blend,0.f);
 if(omit_end)river_draw_land(s,omit_first,0,east,eye,north,yaw,pitch,(float)w/h,cb,sb);
 if(omit_end<terrain_count)river_draw_land(s,terrain_count,omit_end?omit_end:water_count,east,eye,north,yaw,pitch,(float)w/h,cb,sb);
 if(lens==-2){
  glActiveTexture(GL_TEXTURE1);
  GLint photo_slot=glGetUniformLocation(s->rainier_program,"photoSlot");
  float sy=sinf(yaw),cy=cosf(yaw),sp=sinf(pitch),cp=cosf(pitch);
  float tx=(float)(wide/.2),ty=(float)(half/.2),kx=sqrtf(1+tx*tx),ky=sqrtf(1+ty*ty);
  for(unsigned slot=0;slot<111;slot++){
   if(!s->flight_count[slot])continue;
   float radius=s->flight_areas[slot][2];
   /* DEM samples range from sea level to 5000 metres. */
   struct river_bounds tile={s->flight_areas[slot][0],2500.f,s->flight_areas[slot][1],
                             sqrtf(2.f*radius*radius+2500.f*2500.f)};
   if(river_outside_view(tile,east,eye,north,sy,cy,sp,cp,cb,sb,tx,ty,kx,ky))continue;
   glBindTexture(GL_TEXTURE_2D,s->flight_photo[slot]);
   glUniform1i(photo_slot,(GLint)slot);
   glUniform3f(photo_area,s->flight_areas[slot][0],s->flight_areas[slot][1],2*s->flight_areas[slot][2]);
   glBindBuffer(GL_ARRAY_BUFFER,s->flight_mesh[slot]);
   glVertexPointer(3,GL_FLOAT,7*sizeof(float),0);
   glColorPointer(4,GL_FLOAT,7*sizeof(float),(const void *)(3*sizeof(float)));
   glDrawArrays(GL_TRIANGLES,0,s->flight_count[slot]);
  }
  glUniform3f(photo_area,0,0,0);
  glActiveTexture(GL_TEXTURE0);glBindBuffer(GL_ARRAY_BUFFER,s->rainier_buffer);
  glVertexPointer(3,GL_FLOAT,7*sizeof(float),0);
  glColorPointer(4,GL_FLOAT,7*sizeof(float),(const void *)(3*sizeof(float)));
 }
 if(grove_count && grove_count==s->rainier_grove_count){
  glBindBuffer(GL_ARRAY_BUFFER,s->rainier_grove);
  glVertexPointer(3,GL_FLOAT,7*sizeof(float),0);
  glColorPointer(4,GL_FLOAT,7*sizeof(float),(const void *)(3*sizeof(float)));
  glDrawArrays(GL_TRIANGLES,0,(GLsizei)grove_count);
  glBindBuffer(GL_ARRAY_BUFFER,s->rainier_buffer);
 }
 if(high){
  glUseProgram(0);glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);glDepthMask(GL_FALSE);
  for(unsigned i=0;i<na;i++){
   const struct rainier_animal *a=animals+i;if(a->shadow<=0)continue;
   float turn=a->heading*.01745329f,c=cosf(turn),sn=sinf(turn);
   glBegin(GL_TRIANGLE_FAN);glColor4f(.055f,.075f,.08f,.48f*daylight*(weather?.4f:1.f));glVertex3f(a->x,a->y+.018f,a->z);
   glColor4f(.055f,.075f,.08f,0.f);
   for(int j=0;j<=24;j++){
    float t=j*.2617994f,u=cosf(t)*a->shadow*.70f,v=sinf(t)*a->shadow*.27f;
    float dx=c*u+sn*v+cosf(sun_angle)*.22f*stretch*a->shadow,dz=-sn*u+c*v+sinf(sun_angle)*.22f*stretch*a->shadow;
    glVertex3f(a->x+dx,a->y+.018f+dx*a->slope_x+dz*a->slope_z,a->z+dz);
   }
   glEnd();
  }
  glDepthMask(GL_TRUE);glDisable(GL_BLEND);glUseProgram(s->rainier_program);
 }
 glUniform1i(glGetUniformLocation(s->rainier_program,"animal"),1);
 glEnableClientState(GL_TEXTURE_COORD_ARRAY);
 GLuint photo_query=0;
 if(photo && photo_animal>=0 && (unsigned)photo_animal<na)glGenQueries(1,&photo_query);
 for(unsigned i=0;i<na;i++){
  const struct rainier_animal *a=animals+i;
  size_t start=(size_t)a->first*7*sizeof(float);
  glVertexPointer(3,GL_FLOAT,7*sizeof(float),(const void *)start);
  glColorPointer(4,GL_FLOAT,7*sizeof(float),(const void *)(start+3*sizeof(float)));
  glTexCoordPointer(3,GL_FLOAT,7*sizeof(float),(const void *)((size_t)a->second*7*sizeof(float)));
  glUniform1f(blend,a->blend);
  glPushMatrix();glTranslatef(a->x,a->y,a->z);glRotatef(a->heading,0,1,0);
  if(photo_query && (int)i==photo_animal)glBeginQuery(GL_SAMPLES_PASSED,photo_query);
  glDrawElements(GL_TRIANGLES,(GLsizei)a->count,GL_UNSIGNED_INT,(const void *)((size_t)a->index*sizeof(unsigned)));
  if(photo_query && (int)i==photo_animal)glEndQuery(GL_SAMPLES_PASSED);
  glPopMatrix();
 }
 /* Shared family positions carry a standing pose and distinct coat colours. */
 glUseProgram(0);
 static const float coats[][3]={{.93f,.47f,.12f},{.12f,.66f,.67f},{.75f,.28f,.40f},
  {.42f,.48f,.81f},{.85f,.67f,.18f},{.50f,.63f,.27f},{.68f,.38f,.65f}};
 glPushAttrib(GL_LIGHTING_BIT);
 const GLfloat sun[]={-cosf(sun_angle),.55f+daylight,-sinf(sun_angle),0.f};
 const GLfloat ambient[]={.19f+.43f*daylight,.22f+.41f*daylight,.31f+.34f*daylight,1.f};
 glLightfv(GL_LIGHT0,GL_POSITION,sun);glLightfv(GL_LIGHT0,GL_AMBIENT,ambient);
 for(unsigned i=0;i<nh;i++){
  const float *p=hikers+i*3,*coat=coats[i];
  glPushMatrix();glTranslatef(p[0],p[1],p[2]);
  market_person_draw(&s->people[i%2],0,12.5f+.45f*sinf(age*.57f+i*1.9f),coat,0.f,0,NULL);
  glPopMatrix();
 }
 if(market_count)market_people(s,market,market_count);
 glPopAttrib();
 /* Blend the river over opaque bed, fish and banks. Depth testing leaves
    a breaching fish above the surface and hides water behind shore rocks. */
 if(water_count){
  glUseProgram(s->rainier_program);
  glUniform1i(glGetUniformLocation(s->rainier_program,"animal"),0);
  glUniform3f(glGetUniformLocation(s->rainier_program,"waterEye"),east,eye,north);
  glUniform1f(blend,0.f);glDisableClientState(GL_TEXTURE_COORD_ARRAY);
  glVertexPointer(3,GL_FLOAT,7*sizeof(float),0);
  glColorPointer(4,GL_FLOAT,7*sizeof(float),(const void *)(3*sizeof(float)));
  glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);
  glDrawArrays(GL_TRIANGLES,0,(GLsizei)water_count);
  glDisable(GL_BLEND);glUseProgram(0);
 }
 if(ripple && !weather && (season==0 || season==3) && daylight>.35f && fmodf(age,17.f)>=.8f && fmodf(age,17.f)<3.f){
  glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);glDepthMask(GL_FALSE);
  for(int ring=0;ring<3;ring++){
   float phase=(fmodf(age,17.f)-.8f-ring*.18f)/1.8f;
   if(phase<0 || phase>1)continue;
   float r=.12f+phase*.96f;
   glColor4f(.74f,.90f,.87f,.72f*(1.f-phase));glLineWidth(1.5f);glBegin(GL_LINE_LOOP);
   for(int j=0;j<40;j++){float a=j*.1570796f;glVertex3f(ripple[0]+r*cosf(a),ripple[1],ripple[2]+r*sinf(a));}
   glEnd();
  }
  glDepthMask(GL_TRUE);glDisable(GL_BLEND);
 }
 /* Wrap rain through a world-aligned volume around the eye. */
 if(weather==2){
  glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);glDepthMask(GL_FALSE);
  glLineWidth(1.f);glColor4f(.55f,.68f,.76f,.25f+.16f*daylight);glBegin(GL_LINES);
  for(int k=0;k<160;k++){
   float dx=k*7.937f+age*.9f-east,dz=k*k*.231f-north,dy=k*3.831f-age*6.f-eye;
   float px=east+dx-12.f*floorf(dx/12.f)-6.f,pz=north+dz-12.f*floorf(dz/12.f)-6.f;
   float py=eye+dy-9.f*floorf(dy/9.f)-3.f;
   glVertex3f(px,py,pz);glVertex3f(px+.033f,py-.22f,pz);
  }
  glEnd();glDepthMask(GL_TRUE);glDisable(GL_BLEND);
 }
 /* A hatch hangs over the trout pool during clear, mild daylight. */
 if(ripple && !weather && (season==0 || season==3) && daylight>.35f){
  glColor3f(.58f,.55f,.40f);glBegin(GL_TRIANGLES);
  for(int k=0;k<24;k++){
   float t=age*(.85f+.08f*(k%5))+k;
   float px=ripple[0]+1.5f*sinf(t*.64f+k),pz=ripple[2]+cosf(t*.71f+k);
   float py=ripple[1]+.12f+.18f*(1.f+sinf(t*1.6f));
   glVertex3f(px-.013f,py,pz);glVertex3f(px+.015f,py+.023f,pz);glVertex3f(px,py-.012f,pz+.011f);
  }
  glEnd();
 }
 if(marker){
  glColor3f(.94f,.75f,.40f);glLineWidth(2.f);glBegin(GL_LINE_LOOP);
  for(int j=0;j<32;j++){float a=j*.19634954f;glVertex3f(marker[0]+.25f*cosf(a),marker[1],marker[2]+.25f*sinf(a));}
  glEnd();
 }
 if(high||near_market||lens==-2)river_bloom(s,x,y,w,h);
 if(photo){
  GLuint samples=0;
  if(photo_query){glGetQueryObjectuiv(photo_query,GL_QUERY_RESULT,&samples);glDeleteQueries(1,&photo_query);}
  if(!samples){photo=NULL;result=1;}
 }
 if(photo){
  glPushClientAttrib(GL_CLIENT_PIXEL_STORE_BIT);glPixelStorei(GL_PACK_ALIGNMENT,1);
  glPixelStorei(GL_PACK_ROW_LENGTH,0);glPixelStorei(GL_PACK_SKIP_PIXELS,0);glPixelStorei(GL_PACK_SKIP_ROWS,0);
  glReadPixels(x,y,w,h,GL_RGB,GL_UNSIGNED_BYTE,photo);glPopClientAttrib();
 }
 /* Screen-space trail markers: three berries and a pointer to the next stop. */
 if(aircraft)flight_equipment(s,aircraft,w,h);
 glLoadIdentity();glMatrixMode(GL_PROJECTION);glLoadIdentity();glOrtho(0,w,0,h,-1,1);
 glUseProgram(0);glDisable(GL_DEPTH_TEST);
 float radius=(w<h?w:h)*.044f;
 if(lens>0){
  glColor3f(.94f,.92f,.76f);glLineWidth(2.f);
  glBegin(GL_LINES);
  glVertex2f(.5f*w-radius*.37f,.5f*h);glVertex2f(.5f*w+radius*.37f,.5f*h);
  glVertex2f(.5f*w,.5f*h-radius*.37f);glVertex2f(.5f*w,.5f*h+radius*.37f);
  glEnd();
  for(int k=0;k<4;k++){
   float cx=(k%2?.83f:.17f)*w,cy=(k/2?.75f:.25f)*h;
   glBegin(GL_LINE_STRIP);glVertex2f(cx+(k%2?-1:1)*radius,cy);
   glVertex2f(cx,cy);glVertex2f(cx,cy+(k/2?-1:1)*radius);glEnd();
  }
 }
 for(int i=0;i<4&&!lens;i++){
  float cx=i==3?w-radius*1.7f:radius*(1.35f+i*1.5f);
  float cy=i==3?h-radius*1.8f:radius*1.4f;
  float size=i==3?radius*1.3f:radius*.60f;
  glColor3f(.09f,.17f,.16f);
  for(int pass=0;pass<2;pass++){
   glBegin(GL_TRIANGLE_FAN);glVertex2f(cx,cy);
   for(int j=0;j<=24;j++){float a=j*6.2831853f/24.f;glVertex2f(cx+size*cosf(a),cy+size*sinf(a));}
   glEnd();
   if(i==3)break;
   size*=.76f;
   if(picked&(1<<i))glColor3f(.40f,.60f,.99f);else glColor3f(.56f,.61f,.61f);
  }
  if(i==3){
   glPushMatrix();glTranslatef(cx,cy,0);
   if(fed){
    glColor3f(.98f,.44f,.45f);
    glBegin(GL_TRIANGLE_FAN);glVertex2f(0,.76f*radius);
    for(int j=0;j<=32;j++){float a=j*6.2831853f/32.f;float sn=sinf(a);
     glVertex2f(radius*sn*sn*sn,-radius*(13*cosf(a)-5*cosf(2*a)-2*cosf(3*a)-cosf(4*a))/16.f);}
    glEnd();
   }else{
    glRotatef(direction*57.29578f,0,0,1);glColor3f(.98f,.85f,.42f);
    glBegin(GL_TRIANGLES);glVertex2f(0,-radius);glVertex2f(-radius*.68f,radius*.62f);glVertex2f(radius*.68f,radius*.62f);glEnd();
   }
   glPopMatrix();
  }
 }
 glMatrixMode(GL_MODELVIEW);
 glPopMatrix();glMatrixMode(GL_PROJECTION);glPopMatrix();
done:
 glFramebufferRenderbuffer(GL_FRAMEBUFFER,GL_DEPTH_ATTACHMENT,GL_RENDERBUFFER,0);
 glUseProgram(previous_program);glBindRenderbuffer(GL_RENDERBUFFER,previous_depth);
 glPopClientAttrib();glBindBuffer(GL_ELEMENT_ARRAY_BUFFER,previous_indices);glBindBuffer(GL_ARRAY_BUFFER,previous_buffer);glPopAttrib();
 return result;
}

static int river_image(void *ptr,int x,int y,int w,int h,int pw,int ph,const void *rgb,int fit){
 struct gpu_scene *s=ptr;
 if(!s||scene_target(s,s->canvas))return -1;
 if(rgb){
  if(pw<1||ph<1||pw>4096||ph>4096)return SDL_SetError("Invalid photo dimensions");
  SDL_Texture *image=SDL_CreateTexture(s->device,SDL_PIXELFORMAT_RGB24,SDL_TEXTUREACCESS_STATIC,pw,ph);
  if(!image)return -1;
  if(SDL_UpdateTexture(image,NULL,rgb,pw*3)){SDL_DestroyTexture(image);return -1;}
  SDL_SetTextureScaleMode(image,SDL_ScaleModeLinear);
  if(s->river_print)SDL_DestroyTexture(s->river_print);
  s->river_print=image;s->print_w=pw;s->print_h=ph;
 }
 if(!s->river_print)return -1;
 float scale=fminf((float)w/s->print_w,(float)h/s->print_h);
 SDL_Rect frame={x,y,w,h},dest={0,0,(int)(s->print_w*scale),(int)(s->print_h*scale)};
 if(!fit)return SDL_RenderCopy(s->device,s->river_print,NULL,&frame);
 dest.x=x+(w-dest.w)/2;dest.y=y+(h-dest.h)/2;
 SDL_SetRenderDrawColor(s->device,23,28,26,255);
 if(SDL_RenderFillRect(s->device,&frame))return -1;
 return SDL_RenderCopy(s->device,s->river_print,NULL,&dest);
}

int pocket_scene_river_photo(void *ptr,int x,int y,int w,int h,int pw,int ph,const void *rgb){
 return river_image(ptr,x,y,w,h,pw,ph,rgb,1);
}
int pocket_scene_river_map(void *ptr,int x,int y,int w,int h,int pw,int ph,const void *rgb){
 return river_image(ptr,x,y,w,h,pw,ph,rgb,0);
}

/* Heading-up driving inset. Segment endpoints are in local map pixels. */
int pocket_scene_drive_map(void *ptr,int x,int y,int size,const float *lines,unsigned count,unsigned ordinary,float ramp_x,float ramp_y){
 struct gpu_scene *s=ptr;
 if(!s||size<1||ordinary>count||(count&&!lines)||scene_target(s,s->canvas))return -1;
 SDL_Renderer *r=s->device;
 SDL_Rect box={x,y,size,size};
 SDL_SetRenderDrawColor(r,29,40,44,255);
 if(SDL_RenderFillRect(r,&box))return -1;
 for(unsigned i=0;i<count;i++){
  double ax=lines[4*i],ay=lines[4*i+1],bx=lines[4*i+2],by=lines[4*i+3];
  if(!scene_clip(&ax,&ay,&bx,&by,size-1,size-1))continue;
  if(i<ordinary)SDL_SetRenderDrawColor(r,155,168,167,255);
  else SDL_SetRenderDrawColor(r,255,193,85,255);
  SDL_RenderDrawLineF(r,x+ax,y+ay,x+bx,y+by);
 }
 SDL_SetRenderDrawColor(r,255,193,85,255);
 SDL_Rect ramp={x+(int)ramp_x-2,y+(int)ramp_y-2,5,5};
 SDL_RenderFillRect(r,&ramp);
 SDL_SetRenderDrawColor(r,146,173,175,255);
 SDL_RenderDrawRect(r,&box);
 SDL_SetRenderDrawColor(r,108,247,242,255);
 for(int row=0;row<9;row++)
  SDL_RenderDrawLine(r,x+size/2-row/2,y+size/2-5+row,x+size/2+row/2,y+size/2-5+row);
 return 0;
}

/* Botanical line drawings in the margin of a plant discovery page. */
int pocket_scene_plant_sketch(void *ptr,int x,int y,int w,int h,int kind){
 struct gpu_scene *s=ptr;
 if(!s||w<1||h<1||scene_target(s,s->canvas))return -1;
 float size=fminf(w,h)*.88f,cx=x+w*.5f,base=y+(h+size)*.5f;
 SDL_Renderer *r=s->device;
 SDL_SetRenderDrawBlendMode(r,SDL_BLENDMODE_BLEND);
 for(int stem=0;stem<(kind==2?1:3);stem++){
  float tilt=(stem-1)*.29f;
  if(kind==2)tilt=0;
  float len=size*(1.f-fabsf(tilt));
  float tip=cx+len*tilt;
  SDL_SetRenderDrawColor(r,58,75,48,230);
  SDL_RenderDrawLineF(r,cx,base,tip,base-len);
  int pairs=kind==2?14:kind==3?17:7;
  for(int j=1;j<pairs;j++){
   float t=(float)j/pairs;
   float ax=cx+len*tilt*t,ay=base-len*t;
   float span=len*(kind==2?.31f*(1.f-t):.19f*sinf(3.14159f*t));
   for(int sign=-1;sign<=1;sign+=2){
    float bx=ax+sign*span,by=ay+span*(kind==2?.37f:-.64f);
    SDL_SetRenderDrawColor(r,57,84,55,225);
    SDL_RenderDrawLineF(r,ax,ay,bx,by);
    if(kind==1){
     for(int k=1;k<=12;k++){
      float u=(k-.5f)/12.f;
      float mid=ay+(by-ay)*u,leaf=span*.22f*sinf(3.14159f*u);
      SDL_RenderDrawLineF(r,ax+(bx-ax)*u,mid-leaf,ax+(bx-ax)*u,mid+leaf);
     }
     if(j%2==0){
      SDL_SetRenderDrawColor(r,54,67,108,245);
      float radius=fmaxf(2.f,len*.025f);
      for(int k=-(int)radius;k<=(int)radius;k++){
       float half=sqrtf(radius*radius-k*k);
       SDL_RenderDrawLineF(r,ax+sign*span*.4f-half,ay+k,ax+sign*span*.4f+half,ay+k);
      }
     }
    }else{
     for(int k=1;k<9;k++){
      float u=k/9.f,px=ax+(bx-ax)*u,py=ay+(by-ay)*u;
      float needle=span*.20f*(1.f-u*.65f);
      SDL_RenderDrawLineF(r,px,py,px+sign*needle,py-needle);
      SDL_RenderDrawLineF(r,px,py,px+sign*needle,py+needle*.48f);
     }
    }
   }
  }
 }
 return 0;
}

/* First-person rod, bowed fly line and floating fly in the walk viewport. */
int pocket_scene_fishing_rod(void *ptr,int x,int y,int w,int h,float u,float v,float bend){
 struct gpu_scene *s=ptr;
 if(!s||scene_target(s,s->canvas))return -1;
 SDL_Renderer *r=s->device;
 SDL_Rect old,clip={x,y,w,h};
 SDL_bool clipped=SDL_RenderIsClipEnabled(r);
 SDL_RenderGetClipRect(r,&old);
 SDL_RenderSetClipRect(r,&clip);
 float bx=x+w*.60f,by=y+h,tx=x+w*.54f,ty=y+h*(.42f+.12f*bend);
 float ax=bx,ay=by;
 for(int i=1;i<=18;i++){
  float t=i/18.f,px=bx+(tx-bx)*t+.08f*w*sinf(t*3.14159f),py=by+(ty-by)*t;
  SDL_SetRenderDrawColor(r,i<5?195:95,i<5?148:84,i<5?86:66,255);
  for(int j=0;j<1+(int)(4*(1-t));j++)SDL_RenderDrawLineF(r,ax+j,ay,px+j,py);
  ax=px;ay=py;
 }
 /* The reel sits just above the cork grip. */
 float rx=bx+.010f*w,ry=by-.07f*h,radius=fminf(w,h)*.015f;
 SDL_SetRenderDrawColor(r,179,163,121,255);
 for(int i=0;i<14;i++){
  float a=i*.448799f,b=a+.448799f;
  SDL_RenderDrawLineF(r,rx+radius*cosf(a),ry+radius*sinf(a),rx+radius*cosf(b),ry+radius*sinf(b));
  if(i%3==0)SDL_RenderDrawLineF(r,rx,ry,rx+radius*cosf(a),ry+radius*sinf(a));
 }
 for(int i=1;i<=18;i++){
  float t=i/18.f,px=tx+(x+w*u-tx)*t,py=ty+(y+h*v-ty)*t+.064f*h*(1-bend)*sinf(t*3.14159f);
  SDL_SetRenderDrawColor(r,223,225,193,225);
  SDL_RenderDrawLineF(r,ax,ay,px,py);ax=px;ay=py;
 }
 SDL_SetRenderDrawColor(r,255,210,94,255);
 SDL_FRect fly={ax-3,ay-2,6,4};SDL_RenderFillRectF(r,&fly);
 SDL_RenderSetClipRect(r,clipped?&old:NULL);
 return 0;
}
