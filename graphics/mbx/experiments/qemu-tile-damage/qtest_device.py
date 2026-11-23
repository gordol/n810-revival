from pathlib import Path
import subprocess
import ctypes
import time


def capture(repo, directory, viewport, terrain=None, scale=8):
    mbx = repo / 'mbx'
    source = (mbx/'tools/mbxtri.c').read_text()
    # Emit CPU writes only. The GPU's memory writes must come from QEMU.
    replacements = [
        ('mbxemu_reg_write(E, reg, v);', 'printf("w %x %x\\n", 0x50000000+reg, v); mbxemu_reg_write(E, reg, v);'),
        ('return mbxemu_reg_read(E, reg);', 'uint32_t v=mbxemu_reg_read(E, reg); printf("r %x %x\\n", 0x50000000+reg, v); return v;'),
        ('memcpy(ram + va, &v, 4);','printf("m %x %x\\n", RAM_BASE+va,v); memcpy(ram + va, &v, 4);'),
        ('memcpy(&v, ram + va, 4); return v;', 'memcpy(&v, ram + va, 4); printf("r %x %x\\n", RAM_BASE+va,v); return v;'),
        ('mbxemu_ta_write(E, 0, v);', 'printf("w 50008000 %x\\n", v); mbxemu_ta_write(E, 0, v);'),
        ('mbxemu_ta_ctl_write(E, stream[i + 1 + k]);', '{printf("w 5000c000 %x\\n",stream[i+1+k]); mbxemu_ta_ctl_write(E,stream[i+1+k]);}'),
        ('for (i = 0; i < 8; i++)', 'for(i=0;i<PT_OFF/4096;i++) printf("m %x %x\\n",RAM_BASE+PT_OFF+4*i,((uint32_t *)(ram+PT_OFF))[i]);\n\tfor (i = 0; i < 8; i++)'),
        ('((uint32_t *)(ram + surf))[i] = TRI_CLEAR;', 'c_wr32(NULL,surf+4*i,TRI_CLEAR);'),
    ]
    header = (mbx/'tools/tri_frame.h').read_text()
    x,y = viewport
    old = 'tri_taf(&s, TRI_W / 2.0f); tri_taf(&s, TRI_W / 2.0f);'
    assert header.count(old)==1
    header = header.replace(old,f'tri_taf(&s, {scale}); tri_taf(&s, {x});')
    old = 'tri_taf(&s, TRI_H / 2.0f); tri_taf(&s, -TRI_H / 2.0f);'
    assert header.count(old)==1
    (directory/'tri_frame.h').write_text(header.replace(old,f'tri_taf(&s, {y}); tri_taf(&s, -{scale});'))
    if terrain is not None:
        # Replace only the example's three vertex payloads, keeping its TA setup.
        begin = source.index('uint32_t stream[128]')
        source = source[:begin] + source[begin:].replace('stream[128]', f'stream[{128 + len(terrain)*4}]', 1)
        path = directory/'tri_frame.h'
        header = path.read_text()
        begin = header.index('for (i = 0; i < 3; i++) {', header.index('/* a triangle list, no culling */'))
        end = header.index('tri_put(&s, CH_CTL, 1)', begin)
        rows = ','.join('{%s,%s,%s,%su}' % vertex for vertex in terrain)
        payload = ('static const struct {float x,y,z;uint32_t color;} vtx[]={' + rows +
                   '}; for(unsigned j=0;j<sizeof(vtx)/sizeof(*vtx);j++){ tri_taf(&s,vtx[j].x);tri_taf(&s,vtx[j].y);tri_taf(&s,vtx[j].z);tri_ta(&s,vtx[j].color); }\n')
        path.write_text(header[:begin] + payload + header[end:])
    for old,new in replacements:
        if source.count(old) != 1:
            raise ValueError('Unsupported mbxtri version at ' + old)
        source = source.replace(old,new)
    src = directory/'capture.c'
    src.write_text(source)
    subprocess.run(['make','-s','-C',mbx,'libmbxemu.a'],check=True)
    exe = directory/'capture'
    subprocess.run(['cc','-O2','-I',mbx/'tools',src,mbx/'libmbxemu.a','-lm','-o',exe],check=True)
    expected = directory/'expected.ppm'
    commands = subprocess.check_output([exe,'-a','0','-o',expected],text=True)
    return commands, expected.read_bytes()


def render(qemu,commands,prior=None,dirty_tiles=None):
    proc = subprocess.Popen([qemu,'-M','n810','-S','-display','none','-serial','none',
                             '-monitor','none','-qtest','stdio','-qtest-log','/dev/null'],
                            stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    def send(command):
        proc.stdin.write(command+'\n')
        proc.stdin.flush()
        response = proc.stdout.readline().strip().split()
        if not response or response[0] != 'OK':
            raise RuntimeError((command[:70],response))
        return response[1:]

    try:
        clock_id = ctypes.c_int()
        errno = ctypes.CDLL(None).clock_getcpuclockid(proc.pid, ctypes.byref(clock_id))
        if errno:
            raise OSError(errno, "clock_getcpuclockid")
        kick_us = None
        start = None
        data = bytearray()
        def flush():
            if data:
                send(f'write {start:#x} {len(data)} 0x{data.hex()}')
                data.clear()
        for line in commands.splitlines():
            op, addr, value = line.split()
            addr, value = int(addr,16), int(value,16)
            if op == 'm' and prior is not None and 0x80010000 <= addr < 0x80014000:
                pixel = (addr-0x80010000)//4
                if (pixel%64//16, pixel//64//16) not in dirty_tiles:
                    value = int.from_bytes(prior[4*pixel:4*pixel+4],'little')
            if op == 'm' and dirty_tiles is not None and 0x80020000 <= addr < 0x80020080 and addr%8==0 and value&(1<<30):
                if (value&255,(value>>8)&255) not in dirty_tiles:
                    value |= 1<<25
            if op == 'm':
                if start is None or addr != start+len(data) or len(data)>=4096:
                    flush()
                    start = addr
                data.extend(value.to_bytes(4,'little'))
            else:
                flush()
                if op == 'r':
                    actual = int(send(f'readl {addr:#x}')[0],16)
                    if actual != value:
                        raise ValueError(f'{addr:#x}: expected {value:#x}, got {actual:#x}')
                else:
                    if addr == 0x50000680:
                        before = time.clock_gettime_ns(clock_id.value)
                    send(f'writel {addr:#x} {value:#x}')
                    if addr == 0x50000680:
                        kick_us = (time.clock_gettime_ns(clock_id.value)-before)/1000
        flush()
        surface = bytes.fromhex(send('read 0x80010000 16384')[0][2:])
        rgb = b''.join(surface[i:i+3][::-1] for i in range(0,len(surface),4))
        return b'P6\n64 64\n255\n'+rgb, surface, kick_us
    finally:
        proc.terminate()
        proc.wait(timeout=10)
