#!/usr/bin/env python
# coding: utf-8

# In[1]:


f = open('../com.zulong.yslzm.ios-1.5.3-1552333447-855749158/Payload/Azure.app/StreamingAssets/res_base/package_dec/data/achievement_essence.bcfg', 'rb')
bcfgContent = f.read()


# In[8]:


import io
class IOHelper(io.BytesIO):
    def readS16(self):
        return int.from_bytes(self.read(2), 'big', signed=True)
    
    def readU16(self):
        return int.from_bytes(self.read(2), 'big')
    
    def readS32(self):
        return int.from_bytes(self.read(4), 'big', signed=True)
    
    def readU32(self):
        return int.from_bytes(self.read(4), 'big')
    
    def eof(self):
        if self.tell() >= len(self.getvalue()):
            return True
    
    def read(self, l):
        ret = super().read(l)
        assert len(ret) == l
        return ret

    def readVarint(self):
        b0 = self.read(1)[0]
        if b0 & 0x80 == 0: # 0XXXXXXX
            return b0 & 0x7f
        elif b0 & 0x40 == 0: # 10XXXXXX XXXXXXXX
            return int.from_bytes(bytes([b0 & 0x3f]) + self.read(1), 'big')
        elif b0 & 0x20 == 0: # 110XXXXX XXXXXXXX XXXXXXXX XXXXXXXX
            return int.from_bytes(bytes([b0 & 0x1f]) + self.read(2), 'big')
        elif b0 & 0x10 == 0: # 1110XXXX XXXXXXXX XXXXXXXX XXXXXXXX
            return int.from_bytes(bytes([b0 & 0xf]) + self.read(3), 'big')
        else: # 1111XXXX XXXXXXXX XXXXXXXX XXXXXXXX
            return int.from_bytes(read(4), 'big')

    def readSignedVarint(self):  # used in doRowUnmarshalSimpleVar signed int32
        val = self.readVarint()
        return -(val & 1) ^ (val >> 1)

# In[25]:


import logging
from typing import *
import io
import dataclasses
import struct

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(filename)s %(levelname)s %(message)s',
                    datefmt='%a %d %b %Y %H:%M:%S',
                    )
# logging.getLogger().setLevel(logging.DEBUG)
logger = logging.getLogger('bcfg_parser')

@dataclasses.dataclass(init=False)
class BCFGHeader:
    '''
    struct BCFGHeader {
        char magic[2];
        uint16 defNum;
        uint32 rowNum;
        uint32 oriDataSize;
        uint16 tailSize;
        uint16 chunkNum;
        uint32 tableId;
    } bcfgHeader;
    '''
    magic: str
    defNum: int
    rowNum: int
    oriDataSize: int
    tailSize: int
    chunkNum: int
    tableId: int

@dataclasses.dataclass(init=False)
class BCFGDef:
    '''
    struct Def {
        varint defType;
        varint namelen;
        char name[VarintValue(namelen)];
        varint varnum;
        struct VarInfo {
            varint vartype;
            varint varNameLen;
            char varName[VarintValue(varNameLen)];
        } vars[VarintValue(varnum)] <optimize=false>;
    } defs[bcfgHeader.defNum] <optimize=false>;
    '''
    defType: int
    defName: str
    @dataclasses.dataclass(init=False)
    class BCFGVar:
        varType: int
        varName: str
    defVars: List[BCFGVar]

@dataclasses.dataclass(init=False)
class BCFGRow:
    rowId: int
    rowOffset: int
    # rowData: Any

        
class BCFGParser:
    def __init__(self, bcfgContent):
        self.bcfgContent = bcfgContent
        self.bcfgReader = IOHelper(self.bcfgContent)
    
    def parseBcfgHeader(self):
        logger.info("parseBcfgHeader!")
        
        read = self.bcfgReader.read
        readU16 = self.bcfgReader.readU16
        readU32 = self.bcfgReader.readU32
        
        self.bcfgHeader = BCFGHeader()
        self.bcfgHeader.magic = read(2).hex()
        assert self.bcfgHeader.magic == b'cx'.hex()
        self.bcfgHeader.defNum = readU16()
        self.bcfgHeader.rowNum = readU32()
        self.bcfgHeader.oriDataSize = readU32()
        self.bcfgHeader.tailSize = readU16()
        self.bcfgHeader.chunkNum = readU16()
        self.bcfgHeader.tableId = readU32()
        self.oriData = read(self.bcfgHeader.oriDataSize)
        self.oriDataIO = IOHelper(self.oriData)
    
    def parseBcfgDef(self):
        logger.info("parseBcfgDef!")
        read = self.bcfgReader.read
        readU16 = self.bcfgReader.readU16
        readU32 = self.bcfgReader.readU32
        readVarint = self.bcfgReader.readVarint
        
        self.defs = {}
        for i in range(self.bcfgHeader.defNum):
            logger.info("parseBcfgDef, def %d", i)
            curDef = BCFGDef()
            curDef.defType = readVarint()
            curDef.defName = read(readVarint()).decode()
            varNum = readVarint()
            curDef.defVars = []
            for j in range(varNum):
                curVar = BCFGDef.BCFGVar()
                curVar.varType = readVarint()
                curVar.varName = read(readVarint()).decode()
                curDef.defVars.append(curVar)
            self.defs[curDef.defType] = curDef
    
    def parseRows(self):
        read = self.bcfgReader.read
        readU16 = self.bcfgReader.readU16
        readU32 = self.bcfgReader.readU32
        readVarint = self.bcfgReader.readVarint
        
        self.rows = []
        for i in range(self.bcfgHeader.rowNum):
            curRow = BCFGRow()
            curRow.rowId = readVarint()
            curRow.rowOffset = readVarint()
            self.rows.append(curRow)
        
        '''
        In Azure framework:
            - each object in lua is userdata with a custom __index function
            - has some kind of lazyloading
        I believe bcfg is used to compact runtime data table memory usage, 
         because pure Lua object may occupy much more space.
        '''

        self.dataTable = {}
        for row in self.rows: 
            def isListOrBean(vartype):
                if (vartype & 0xF) == 0xF:
                    return 'list'
                elif (vartype & 0xF0) == 0xA0: # bean
                    return 'bean'
                else:
                    return 'other'
                
            def parseBeanType(reader, beanType):
                logger.debug("parseBeanType %x", beanType)
                ret = {}
                curDef = self.defs[beanType]
                for defVar in curDef.defVars:
                    ret[defVar.varName] = parseType(reader, defVar.varType)
                logger.debug("parseBeanType %x fin: %s", beanType, ret)
                return ret
            
            def parseListType(reader, vartype):
                logger.debug("parseListType %x", vartype)
                assert (vartype & 0xF) == 0xF
                elemVarType = vartype & ~0xF
                
                # the logic is in rowUnmarshalList
                # [varint ListLength] [elem] [elem]
                # for bean elem, it's [beanlength][...] (we implement this in parseType)
                # for string & other elem, it's simply one by one
                listLength = reader.readVarint()
                ret = []
                for i in range(listLength):
                    logger.debug("parseListType %x  elem %d", vartype, i)
                    
                    elemReader = reader
                    ret.append(parseType(elemReader, elemVarType))
                logger.debug("parseListType %x fin: %s", vartype, ret)
                return ret
                
            def parseType(reader, vartype):
                logger.debug("parseType %x off %x", vartype, reader.tell())
                if vartype == 0x10: # boolean
                    return int.from_bytes(reader.read(1), 'big')
                elif vartype == 0x20: # int16
                    return reader.readS16()
                elif vartype == 0x30: # uint16
                    return reader.readU16()
                elif vartype == 0x40: # int32
                    return reader.readSignedVarint()
                elif vartype == 0x50: # uint32
                    return reader.readVarint()
                elif vartype == 0x80: # float
                    return struct.unpack('>f', reader.read(4))[0]
                elif vartype == 0x90: # string
                    return reader.read(reader.readVarint()).decode()
                else:
                    if (vartype & 0xF) == 0xF: # list
                        data = reader.read(reader.readVarint())
                        reader = IOHelper(data)
                        return parseListType(reader, vartype)
                    elif (vartype & 0xF0) == 0xA0: # bean
                        data = reader.read(reader.readVarint())
                        reader = IOHelper(data)
                        return parseBeanType(reader, vartype)
                    
            self.oriDataIO.seek(row.rowOffset)
            rowData = parseBeanType(self.oriDataIO, 0)
            logger.info("Got row: %s", rowData)
            self.dataTable[row.rowId] = rowData
            
    
    def doParse(self):
        self.parseBcfgHeader()
        self.parseBcfgDef()
        self.parseRows()
    
    def to_dict(self):
        return {
            "dataTable": self.dataTable,
            "bcfgHeader": self.bcfgHeader,
            "defs": self.defs,
            "rows": self.rows,
        }

p = BCFGParser(bcfgContent)
p.doParse()

import json
class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return super().default(o)

print(json.dumps(p.to_dict(), indent=4, cls=EnhancedJSONEncoder))