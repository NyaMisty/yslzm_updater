#!/usr/bin/env python
# coding: utf-8

from socket import *
from io import BytesIO
import sys

platform = 'zh-ios-ob-formal'
addr = "tc-projecti-zdir.zulong.com:52002"
if len(sys.argv) > 1:
    args = sys.argv[1:]
    platform = args[0]
    addr = args[1]

addrname, addrport = addr.split(':')
addrtuple = (addrname, int(addrport))
s = socket()
s.connect(addrtuple)
stream = s.makefile('rb')

def read_uint(read):
    b0 = read(1)[0]
    if b0 & 0x80 == 0: # 0XXXXXXX
        return b0
    elif b0 & 0x40 == 0: # 10XXXXXX XXXXXXXX
        return int.from_bytes(bytes([b0 & 0x7f]) + read(1), 'big')
    elif b0 & 0x20 == 0: # 110XXXXX XXXXXXXX XXXXXXXX XXXXXXXX
        return int.from_bytes(bytes([b0 & 0x3f]) + read(3), 'big')
    else: # 111XXXXX XXXXXXXX XXXXXXXX XXXXXXXX
        return int.from_bytes(read(4), 'big')

def read_packet(stream):
    pktID = read_uint(lambda n: stream.read(n))
    pktLen = read_uint(lambda n: stream.read(n))
    pktContent = stream.read(pktLen)
    return pktID, pktContent

def read_octet(pktstream):
    bufLen = read_uint(lambda n: pktstream.read(n))
    buf = pktstream.read(bufLen)
    return buf

pktID, pktContent = read_packet(stream)
assert pktID == 7101

import zlib
def parseDirInfo(pktstream):
    serverList = read_octet(pktstream)
    version = read_octet(pktstream)
    versionList = read_octet(pktstream)
    
    serverListLength = int.from_bytes(pktstream.read(4), 'big')
    versionLength = int.from_bytes(pktstream.read(4), 'big')
    versionListLength = int.from_bytes(pktstream.read(4), 'big')
    
    serverList = zlib.decompress(serverList)[:serverListLength]
    version = zlib.decompress(version)[:versionLength]
    versionList = zlib.decompress(versionList)[:versionListLength]
    return {
        'serverList': serverList,
        'version': version,
        'versionList': versionList,
    }

dirInfo = parseDirInfo(BytesIO(pktContent))

with open(f'{platform}-serverList.xml', 'wb') as f:
    f.write(dirInfo['serverList'])

with open(f'{platform}-version.xml', 'wb') as f:
    f.write(dirInfo['version'])

with open(f'{platform}-versionList.txt', 'wb') as f:
    f.write(dirInfo['versionList'])
