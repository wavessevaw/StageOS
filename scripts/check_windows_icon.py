"""Verify the final PE contains the approved multi-size application icon."""
from pathlib import Path
import struct, json

ROOT=Path(__file__).resolve().parent.parent

def verify(executable,icon):
    data=Path(executable).read_bytes();ico=Path(icon).read_bytes()
    if ico[:4]!=b'\x00\x00\x01\x00':raise ValueError('Invalid ICO')
    frames=struct.unpack_from('<H',ico,4)[0]
    pe=struct.unpack_from('<I',data,0x3c)[0]
    if data[pe:pe+4]!=b'PE\x00\x00':raise ValueError('Invalid PE')
    machine,sections=struct.unpack_from('<HH',data,pe+4)
    if machine!=0x8664:raise ValueError('Expected x64 executable')
    optional=pe+24
    if struct.unpack_from('<H',data,optional)[0]!=0x20b:raise ValueError('Expected PE32+')
    rva,size=struct.unpack_from('<II',data,optional+112+16)
    if not rva or not size:raise ValueError('Missing PE resources')
    optional_size=struct.unpack_from('<H',data,pe+20)[0]
    section_table=optional+optional_size
    root=None
    for i in range(sections):
        section=section_table+40*i
        virtual_size,address,raw_size,raw_pointer=struct.unpack_from('<IIII',data,section+8)
        if address<=rva<address+max(virtual_size,raw_size):root=raw_pointer+rva-address
    if root is None:raise ValueError('Resource section not found')
    def entries(offset):
        pos=root+offset;named,count=struct.unpack_from('<HH',data,pos+12)
        return [struct.unpack_from('<II',data,pos+16+8*i) for i in range(named+count)]
    types=dict(entries(0))
    if not {3,14,16}<=types.keys():raise ValueError('Missing icon, group icon or version resource')
    icon_entries=entries(types[3]&0x7fffffff)
    icon_count=len(icon_entries)
    payloads=[]
    for _,directory in icon_entries:
        languages=entries(directory&0x7fffffff)
        for _,leaf in languages:
            image_rva,image_size=struct.unpack_from('<II',data,root+leaf)
            image_offset=root+image_rva-rva
            payloads.append(data[image_offset:image_offset+image_size])
    expected=[]
    for i in range(frames):
        image_size,image_offset=struct.unpack_from('<II',ico,6+16*i+8)
        expected.append(ico[image_offset:image_offset+image_size])
    if sorted(payloads)!=sorted(expected):raise ValueError('Embedded icon differs from the approved ICO')
    if icon_count!=frames or frames<7:raise ValueError('Not all icon sizes embedded')
    return {'status':'PASS','machine':'x64','icon_frames':frames,'group_icon':True,'version_resource':True,'approved_icon_bytes':'MATCH'}

if __name__=='__main__':
    print(json.dumps(verify(ROOT/'windows/StageOS.exe',ROOT/'windows/StageOS.ico')))
