# SPDX-License-Identifier: MIT
"""Build separate base-ABI normal kernels without changing projection code."""
from pathlib import Path
import argparse,subprocess,json,hashlib
def run(args):
    p=subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=45)
    if p.returncode:raise RuntimeError(p.stdout+p.stderr)
    return p.stdout
def main():
    p=argparse.ArgumentParser();p.add_argument("--out",type=Path,required=True)
    p.add_argument("--prefix",default="arm-linux-gnueabi-");a=p.parse_args()
    here=Path(__file__).resolve().parent;out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    cc=a.prefix+"gcc";base=["-O3","-std=c11","-Wall","-Wextra","-Werror","-mcpu=arm1136jf-s","-marm",
        "-fPIC","-ffp-contract=off","-fno-fast-math","-fno-tree-vectorize","-fno-builtin-sqrt"]
    commands=[]
    def call(argv):commands.append(list(map(str,argv)));return run(argv)
    for name,flags in (("soft",["-mfloat-abi=soft"]),("vfp",["-mfpu=vfpv2","-mfloat-abi=softfp"])):
        call([cc,*base,*flags,"-DACCUM_NAME=normals_accum_"+name,"-DFINISH_NAME=normals_finish_"+name,
              "-c",here/"kernels.c","-o",out/(name+".o")])
    call([cc,*base,"-mfloat-abi=soft","-DN810_ARM_VFP","-c",here/"dispatch.c","-o",out/"dispatch.o"])
    call([cc,*base,"-mfpu=vfpv2","-mfloat-abi=softfp","-c",here/"fpscr.S","-o",out/"fpscr.o"])
    objects=[out/(n+".o") for n in ("soft","vfp","dispatch","fpscr")]
    call([cc,"-mfloat-abi=soft","-shared",*objects,"-lm","-o",out/"libn810normals.so"])
    call([cc,*base,"-mfloat-abi=soft","-static",here/"probe.c",*objects,"-lm","-o",out/"normals-check"])
    attrs=call([a.prefix+"readelf","-h","-A",out/"libn810normals.so"])
    assert "soft-float ABI" in attrs and "VFP registers" not in attrs
    (out/"elf-attributes.txt").write_text(attrs)
    (out/"versions.txt").write_text(call([a.prefix+"readelf","-V",out/"libn810normals.so"]))
    for n in ("soft","vfp","dispatch","fpscr"):
        (out/(n+".dis")).write_text(call([a.prefix+"objdump","-dr",out/(n+".o")]))
    vfp=json.loads(call(["qemu-arm","-cpu","arm1136",out/"normals-check"]))
    soft=json.loads(call(["qemu-arm","-cpu","arm1136,vfp=off",out/"normals-check"]))
    assert vfp["status"]==soft["status"]=="PASS" and vfp["vfp"] and not soft["vfp"]
    report=dict(status="PASS",hardware_execution=False,vfp=vfp,soft=soft,commands=commands,
        library=dict(bytes=(out/"libn810normals.so").stat().st_size,
        sha256=hashlib.sha256((out/"libn810normals.so").read_bytes()).hexdigest()))
    (out/"build-validation.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report))
if __name__=="__main__":main()
