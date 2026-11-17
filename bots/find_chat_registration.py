"""Read only static instruction references to the ordinary speech handler."""
import mmap
import struct
with open('/root/hxsy/ZoneServer/ZoneServer','rb') as stream:
    with mmap.mmap(stream.fileno(),0,access=mmap.ACCESS_READ) as data:
        offset=0
        for _ in range(20):
            offset=data.find(struct.pack('<I',0x8fdff0),offset+1,0xb00000)
            if offset<0:break
            print(hex(offset+0x400000),data[max(0,offset-6):offset+8].hex())
