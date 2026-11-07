"""Independent readback checks for the first TA allocator driver stage."""
import struct
import hashlib

SIZE = 180288
SEPARATE_SEED_SIZE = 184384


def validate(blob):
    if len(blob) not in (SIZE,SEPARATE_SEED_SIZE):
        raise ValueError('wrong allocator capture length')
    magic, size, ta, core, revision, events, writes, quiet, table, target, guard, product, part, param, tiles, tag = struct.unpack_from('<16I', blob)
    if (magic, size) != (0x3142584d, len(blob)) or tag not in (0x31534154, 0x32534154, 0x33534154, 0x34534154, 0x35534154, 0x36534154, 0x37534154, 0x38534154, 0x41534154, 0x42534154, 0x43534154, 0x44534154,0x45534154,0x46534154,0x47534154,0x48534154,0x49534154,0x4a534154,0x4b534154,0x4c534154,0x4d534154,0x4e534154,0x4f534154,0x50534154,0x51534154,0x52534154,0x53534154,0x54534154,0x55534154,0x56534154):
        raise ValueError('wrong allocator capture format')
    separate_seed = tag in (0x38534154,0x41534154,0x42534154,0x43534154,0x44534154,0x45534154,0x46534154,0x47534154,0x48534154,0x49534154,0x4a534154,0x4b534154,0x4c534154,0x4d534154,0x4e534154,0x4f534154,0x50534154,0x51534154,0x52534154,0x53534154,0x54534154,0x55534154,0x56534154)
    if len(blob) != (SEPARATE_SEED_SIZE if separate_seed else SIZE):
        raise ValueError('tag/capture extent mismatch')
    if (core, revision, product, part) != (0x01010003, 83952391, 0, 0):
        raise ValueError('wrong MBX identity')
    context = tag in (0x32534154, 0x33534154, 0x34534154, 0x35534154, 0x36534154, 0x37534154, 0x38534154, 0x41534154, 0x42534154, 0x43534154, 0x44534154,0x45534154,0x46534154,0x47534154,0x48534154,0x49534154,0x4a534154,0x4b534154,0x4c534154,0x4d534154,0x4e534154,0x4f534154,0x50534154,0x51534154,0x52534154,0x53534154,0x54534154,0x55534154,0x56534154)
    geometry = tag in (0x34534154, 0x35534154, 0x36534154, 0x37534154, 0x38534154, 0x41534154, 0x42534154, 0x43534154, 0x44534154,0x45534154,0x46534154,0x47534154,0x48534154,0x49534154,0x4a534154,0x4b534154,0x4c534154,0x4d534154,0x4e534154,0x4f534154,0x50534154,0x51534154,0x52534154,0x53534154,0x54534154,0x55534154,0x56534154)
    if writes != (163 if tag in (0x52534154,0x53534154,0x54534154,0x55534154,0x56534154) else 157 if tag == 0x51534154 else 108 if tag == 0x50534154 else 110 if tag == 0x4f534154 else 88 if tag in (0x4d534154,0x4e534154) else 68 if tag == 0x4c534154 else 67 if tag == 0x4b534154 else 68 if tag == 0x4a534154 else 66 if tag in (0x45534154,0x47534154,0x48534154,0x49534154,0x4a534154,0x4b534154,0x4c534154,0x4d534154,0x4e534154,0x4f534154,0x50534154,0x51534154,0x52534154,0x53534154,0x54534154,0x55534154,0x56534154) else 47 if tag in (0x44534154,0x46534154,0x47534154,0x48534154,0x49534154,0x4a534154,0x4b534154,0x4c534154,0x4d534154,0x4e534154,0x4f534154,0x50534154,0x51534154,0x52534154,0x53534154,0x54534154,0x55534154,0x56534154) else 50 if separate_seed else 50 if tag == 0x37534154 else 48 if tag == 0x36534154 else 47 if tag == 0x35534154 else 46 if geometry else 13 if context else 6) or quiet != 1 or not events & (0x100 if context else 0x40) or events & 0x2a0 or events == 0xffffffff:
        raise ValueError('missing allocator completion or quiescence')
    allocations = ((table, 32768), (target, 4096), (guard, 4096), (param, 65536), (tiles, 4096), (ta, 36864 if separate_seed else 32768))
    for index, (address, length) in enumerate(allocations):
        if not address or address % 4096 or address + length > 2**32:
            raise ValueError('invalid DMA allocation')
        for other, extent in allocations[index + 1:]:
            if address < other + extent and other < address + length:
                raise ValueError('overlapping DMA allocations')
    rendered = tag in (0x52534154,0x53534154,0x54534154,0x55534154,0x56534154)
    if rendered:
        if blob[64:4160]!=b'\x3c'*4096 or blob[6208:8256]!=b'\x3c'*2048:
            raise ValueError('initial target or RGB565 allocation tail changed')
        if not events&4:raise ValueError('fresh ISP render completion missing')
        pixels=struct.unpack('<1024H',blob[4160:6208])
        for y in range(32):
            for x in range(32):
                pixel=pixels[y*32+x]
                if pixel not in (0,0x07e0):raise ValueError('unexpected triangle pixel color')
                if x>1 and y>1 and x+y<29 and pixel!=0x07e0:
                    raise ValueError('GPU triangle interior was not rendered green')
                if (x<1 or y<1 or x+y>31) and pixel!=0:
                    raise ValueError('GPU triangle exterior differs from black background')
    elif blob[64:8256] != b'\x3c' * 8192:
        raise ValueError('allocator unexpectedly changed render target')
    if blob[8256:12352] != b'\xa5' * 4096:
        raise ValueError('GPU guard page changed')
    pages = [guard] * 8192
    pages[1] = target
    pages[16:32] = [param + i * 4096 for i in range(16)]
    pages[32] = tiles
    pages[128:132] = [ta + i * 4096 for i in range(4)]
    pages[144], pages[146], pages[148] = ta + 16384, ta + 20480, ta + 24576
    if separate_seed: pages[152] = ta + 28672
    expected = struct.pack('<8192I', *pages)
    if blob[12352:45120] != expected or blob[45120:77888] != expected:
        raise ValueError('page tables changed or escaped owned mappings')
    parameters = [0] * 16384
    parameters[:5] = (0xe0000000, 0xa8804000, 0x0e080410, 0xd6887610, 0x22220e80)
    parameters[7] = parameters[10] = 0x43000000
    parameters[11:17] = [0x3f800000] * 6
    parameters[21] = parameters[25] = 0x3d800000
    if (blob[77888:77992] != struct.pack('<26I', *parameters[:26]) if geometry else blob[77888:143424] != struct.pack('<16384I', *parameters)):
        raise ValueError('allocator changed immutable background parameters')
    region_list = [0] * 1024
    region_list[:32:2] = [0x22000000] * 16
    region_list[30] |= 0x80000000
    if (blob[143424+128:147520] != bytes(4096-128) if geometry else blob[143424:147520] != struct.pack('<1024I', *region_list)):
        raise ValueError('allocator changed region list or bitmap')
    state = blob[147520:]
    if context:
        unused=(state[16384+192:20480] if geometry else state[16384:20480])+state[20480+260:24576]+state[24576+520:28672]
    else:unused=state[16384:28672]
    if unused != bytes(len(unused)) or state[32768 if separate_seed else 28672:] != b'\x5a' * 4096:
        raise ValueError('TA wrote outside its declared state objects')
    if separate_seed:
        expected_seed=struct.pack('<2I',*( (17|(10<<13),26) if tag in (0x43534154,0x44534154,0x45534154,0x46534154,0x47534154,0x48534154,0x49534154,0x4a534154,0x4b534154,0x4c534154,0x4d534154,0x4e534154,0x4f534154,0x50534154,0x51534154,0x52534154,0x53534154,0x54534154,0x55534154,0x56534154) else (28|(4<<13),31) ))+bytes(4088)
        if state[28672:32768]!=expected_seed:
            raise ValueError('separate allocator seed context changed')
    if tag == 0x33534154 and struct.unpack_from('<2I',state,24576)!=(28|(4<<13),31):
        raise ValueError('DPM load/save did not preserve the original seeded free-page header')
    entries = struct.unpack('<8192H', state[:16384])
    if (any(x>8191 for x in entries) if geometry else entries != tuple((i+1)&8191 for i in range(8192))):
        raise ValueError('allocator free-page chain differs from the verified layout')
    if geometry and (events & 0x110)!=0x110:
        raise ValueError('TA and context completion are both required')
    if geometry and not any(blob[77992:143424]):
        raise ValueError('Context finish completed without producing triangle parameter data')
    return dict(status='GPU_TRIANGLE_RASTER_PIXELS_BOUNDS_PASS' if rendered else 'TA_TRIANGLE_PARAMETER_BOUNDS_PASS' if geometry else 'TA_CONTEXT_ROUNDTRIP_BOUNDS_PASS' if context else 'TA_ALLOCATOR_INITIALIZED_BOUNDS_PASS', events=events,
                free_list_nonzero_count=sum(bool(value) for value in entries),
                free_list_sha256=hashlib.sha256(state[:16384]).hexdigest(),
                sha256=hashlib.sha256(blob).hexdigest(),
                geometry_rendering_verified=rendered,
                full_opengl_or_gears_verified=False,
                requires_module_boot_log_binding=True)
