#!/usr/bin/env python
# -*- coding: utf-8 -*- 

## Copyright 2011, IOActive, Inc. All rights reserved.
##
## AndBug is free software: you can redistribute it and/or modify it under 
## the terms of version 3 of the GNU Lesser General Public License as 
## published by the Free Software Foundation.
##
## AndBug is distributed in the hope that it will be useful, but WITHOUT ANY
## WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS 
## FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for 
## more details.
##
## You should have received a copy of the GNU Lesser General Public License
## along with AndBug.  If not, see <http://www.gnu.org/licenses/>.

'''
The andbug.proto module abstracts the JDWP wire protocol into a more 
manageable request/response API using an input worker thread in the
background and a number of mutexes to control contests for output.
'''
#��JDWP �����һϵ�С�����/��Ӧ��


import socket, tempfile
from threading import Thread, Lock
from Queue import Queue, Empty as EmptyQueue


import andbug.util
from andbug import log
from andbug.jdwp import JdwpBuffer

class EOF(Exception):
    'signals that an EOF[֡����] has been encountered[����������]'
    def __init__(self, inner = None):
        Exception.__init__(
            self, str(inner) if inner else "EOF"
        )

class HandshakeError(Exception):
    'signals that the JDWP handshake failed'
    def __init__(self):
        Exception.__init__(
            self, 'handshake error, received message did not match'
        )

class ProtocolError(Exception):
    pass

HANDSHAKE_MSG = 'JDWP-Handshake'
HEADER_FORMAT = '4412'
IDSZ_REQ = (
    '\x00\x00\x00\x0B' # Length
    '\x00\x00\x00\x01' # Identifier
    '\x00'             # Flags
    '\x01\x07'         # Command 1:7  IDSizes Command (7)
)

#adb -s [dev] forward localfilesystem: [temp] jdwp [pid]
#adb -s emulator-5554 forward  localfilesystem:/tmp/tmpzeJZR5 jdwp:333 
#���������������
def forward(pid, dev=None):
    'constructs an adb forward for the context to access the pid via jdwp'
    if dev:
        dev = andbug.util.find_dev(dev)
    pid = andbug.util.find_pid(pid)
    temp = tempfile.mktemp() #����һ����ʱ�ļ�
    cmd = ('-s', dev) if dev else ()  #'-s', 'emulator-5554'
    cmd += ('forward', 'localfilesystem:' + temp,  'jdwp:%s' % pid) #'-s', 'emulator-5554', 'forward', 'localfilesystem:/tmp/tmpSSCNAl', 'jdwp:843')
    andbug.util.adb(*cmd)
    return temp

#����ʱ�ķ�ʽ��andbug.proto.connect(andbug.proto.forward(pid, dev))
#self.sess = andbug.vm.connect(self.pid, self.dev)
# addr ������һ����ʱ�ļ���·��
def connect(addr, portno = None, trace=False):
    'connects to an AF_UNIX or AF_INET JDWP transport'
    if addr and portno:
        conn = socket.create_connection((addr, portno))
    elif isinstance(addr, int):
        conn = socket.create_connection(('127.0.0.1', addr))
    else:
        conn = socket.socket(socket.AF_UNIX)
        conn.connect(addr)

	#����������ݵĺ���
    def read(amt):
        'read wrapper internal to andbug.proto.connect'
        req = amt
        buf = ''
        while req:
            pkt = conn.recv(req)
            if not pkt: raise EOF()
            buf += pkt
            req -= len(pkt)
        if trace:
            print ":: RECV:", repr(buf)
        return buf 
    
	#����д�����ݵĺ���
    def write(data):
        'write wrapper internal to andbug.proto.connect'
        try:
            if trace:
                print ":: XMIT:", repr(data)
            conn.sendall(data)
        except Exception as exc:
            raise EOF(exc)
        
    p = Connection(read, write)  #����һ��Connection����
    p.start()
    return p

class Connection(Thread):
    '''
    The JDWP Connection is a thread which abstracts the asynchronous[�첽] JDWP protocol
    into a more synchronous one.  The thread will listen for packets using the
    supplied[�ṩ] read function, and transmit[����] them using the write function.  

    Requests are sent by the processor using the calling thread, with a mutex 
    used to protect the write function from concurrent[������] access.  The requesting
    thread is then blocked waiting on a response from the processor thread.

    The Connectionor will repeatedly use the read function to receive packets, which
    will be dispatched based on whether they are responses to a previous request,
    or events.  Responses to requests will cause the requesting thread to be
    unblocked, thus simulating a synchronous request.
    '''

    def __init__(self, read, write):
        Thread.__init__(self)
        self.xmitbuf = JdwpBuffer()  #����ʵ����jdwp�ļ��У���C����ʵ�֣������Ҫ�˽�C����Ƕ��python���Ե�֪ʶ
        self.recvbuf = JdwpBuffer()
        self._read = read
        self.write = write
        self.initialized = False
        self.next_id = 3  #��һ������id��������ÿ������������ŵġ�
        self.bindqueue = Queue()  #����һ���Ƚ��ȳ��Ķ���
        self.qmap = {}   #��ʼ��һ���յ��ֵ�
        self.rmap = {}   #��ʼ��һ���յ��ֵ�
        self.xmitlock = Lock()  #��һ��������

    #�����ݵĺ�����sz׼����ȡ���ݵĳ��ȣ�
    def read(self, sz):
        'read size bytes'
        if sz == 0: return ''
        pkt = self._read(sz)  #����ֵ�Ƕ���������
        if not len(pkt): raise EOF()   #������������ݵĳ���Ϊ0���׳�EOF�쳣
        return pkt

    ###################################################### INITIALIZATION STEPS
    
    #д��id������Ϣ
    def writeIdSzReq(self):
        'write an id size request'
        return self.write(IDSZ_REQ)

	#��ȡ��id�ĳ�����Ϣ
    def readIdSzRes(self):
        'read an id size response'
        head = self.readHeader()  #������header��ֵ�ǣ�list: [20L, 1L, 128L, 0L] ��Length, Id��Flags, Error Code��
        if head[0] != 20: #id size����ķ������ݰ��ĳ���Ϊ20�ֽڣ����а���11�ֽڵİ�ͷ���ȡ�
            raise ProtocolError('expected size of an idsize response') #�׳�Э������쳣
        if head[2] != 0x80:  #���ذ���ͷ�е�Flags�ֶε�ֵ�ǹ̶��ľ�Ϊ0x80��128
            raise ProtocolError(
                'expected first server message to be a response' #�׳�Э������쳣
            )
        if head[1] != 1: #���ڷ���id size�������id�����1�����ԺϷ��ķ��ذ��ı��ҲӦ����1
            raise ProtocolError('expected first server message to be 1')  #�׳�Э������쳣

        sizes = self.recvbuf.unpack( 'iiiii', self.read(20) )
        self.sizes = sizes #��ȡ����sizes��ֵ�� list: [4L, 4L, 8L, 8L, 8L] ��¼�¸����Ͷ�����ռ�ռ�ĳ���
        self.recvbuf.config(*sizes) 
        self.xmitbuf.config(*sizes)
        return None

	#������������
    def readHandshake(self):
        'read the jdwp handshake'
        data = self.read(len(HANDSHAKE_MSG))
        if data != HANDSHAKE_MSG:
            raise HandshakeError()  #�׳�����ʧ���쳣
    #������������    
    def writeHandshake(self):
        'write the jdwp handshake'
        return self.write(HANDSHAKE_MSG)

    ############################################### READING / PROCESSING PACKETS
    
    #��ȡͷ����readIdSzRes(self)�����б�����
    def readHeader(self):
        'reads a header and returns [size, id, flags, event]'
        head = self.read(11)  
        data = self.recvbuf.unpack(HEADER_FORMAT, head)  #unpack������jdwp�ļ���ʵ��
        data[0] -= 11
        return data
    #�����µ��̣߳��������������з��ص���Ϣ��process����������һ����ѭ���в��ϵ���
    def process(self):
        'invoked repeatedly by the processing thread'

        size, ident, flags, code = self.readHeader() #TODO: HANDLE CLOSE  #��ȡ����ͷ������һ��Ԫ��size��ident��flags��code
        log.debug("study", "In Connection(Thread).process size=" + str(size) + "\t ident="+ str(ident) + "\t flags=" +str(flags) + "\t code=" + str(code))
        data = self.read(size) #TODO: HANDLE CLOSE  #����Header�еĳ�����Ϣ����ȡ�������ݡ�
        try: # We process binds[��] after receiving messages to prevent a race
            while True:
                self.processBind(*self.bindqueue.get(False)) #bindqueue.get(False)����ΪFalse�����н�����Empty�쳣
        except EmptyQueue:
            log.debug("study", "Except for Empty Queue")
            pass

        #TODO: update binds with all from bindqueue
        #����������������¼���Ϣ��self.processBind(*self.bindqueue.get(False))�������ã�ֱ�Ӵ���EmptyQueue�쳣����������processRequest����
        if flags == 0x80:  
            self.processResponse(ident, code, data)  #�����ݰ���flag��0x80
        else:
            self.processRequest(ident, code, data)  #�������ݰ���flag��0x00
    #�������õĲ���Ϊ��qr="r" ident=16484=0x4064 chan ��һ����Session���ж����һ�����С�qr="q" ident=3 ����ident������ı��id�������������������id��3��ʼ
    def processBind(self, qr, ident, chan):
        'internal[�ڲ���] to i/o thread; performs a query or request bind'
		#����qrֵ�Ĳ�ͬ����identΪ�ؼ��֣���chanΪֵ�����벻ͬ���ֵ���
        log.debug("study", "In Connection(Thread).processBind qr=" + str(qr) + "\t ident=" + str(ident) + "\t chan=" + str(chan))
        log.debug("study", "++bindqueue.get  FOR q ++")
        if qr == 'q':
            self.qmap[ident] = chan  
        elif qr == 'r':
            self.rmap[ident] = chan
           

	#��������
    ##�������ݰ���flag��0x00
    def processRequest(self, ident, code, data):
        'internal to the i/o thread w/ recv ctrl; processes incoming request'
        log.debug("study", "In Connection.processRequest ident=" + str(ident) + "\t code=" + str(code) + "\t data=")
        chan = self.rmap.get(code)  #�����ж϶��ɸ�chan���д���ÿ��ֻ�Ǵ�rmap�������ݣ���û�н�rmap��Ӧ��chan���
        if not chan: return #TODO
        buf = JdwpBuffer()
        buf.config(*self.sizes)
        buf.prepareUnpack(data)
        return chan.put((ident, buf)) #�������������ѹ�������
     
	#������Ӧ��chan������ʲô���͵���Ҫ��ע��������Ķ��г�Ա����self.bindqueue�й�
    #�����ݰ���flag��0x80   
    def processResponse(self, ident, code, data):
        'internal to the i/o thread w/ recv ctrl; processes incoming response'
        log.debug("study", "In Connection.processResponse ident=" + str(ident) + "\t code=" + str(code) + "\t data=")
        chan = self.qmap.pop(ident, None) #���ֵ��ж�ȡ����ɾ��������
        if not chan: return
        buf = JdwpBuffer()
        buf.config(*self.sizes)
        buf.prepareUnpack(data)
        return chan.put((code, buf))

	#���õ�ʵ�����Ϊ��conn.hook(0x4064, self.evtq)������self.evtq��һ������
    def hook(self, code, chan):
        '''
        when code requests are received, they will be put in chan for
        processing
        '''

		#ʹ����
        with self.xmitlock:
            self.bindqueue.put(('r', code, chan)) #����һ���Ƚ��ȳ��Ķ���
            log.debug("study", "++ for hook function bindqueue.put  FOR r ++ code=" + str(code))
        
    ####################################################### TRANSMITTING PACKETS
    
	#����һ������id
    def acquireIdent(self):
        'used internally by the processor; must have xmit[����] control'
        ident = self.next_id
        self.next_id += 2
        return ident

	#����[д��]ָ��������
    def writeContent(self, ident, flags, code, body):
        'used internally by the processor; must have xmit control'

        size = len(body) + 11
        self.xmitbuf.preparePack(11)
        data = self.xmitbuf.pack(
            HEADER_FORMAT, size, ident, flags, code
        )
        self.write(data)
        return self.write(body)

	#��������
    def request(self, code, data='', timeout=None):
        'send a request, then waits for a response; returns response'
        queue = Queue()
        log.debug("study", "In Connection.request code=" + str(code) + "\t data=" + str(data))
        with self.xmitlock:
            ident = self.acquireIdent()
            self.bindqueue.put(('q', ident, queue)) #ÿ����һ��������bindqueue��ѹ��һ������
            log.debug("study", "++bindqueue.put  FOR q ++")
            self.writeContent(ident, 0x0, code, data)
        
        try:
            log.debug("study", "wait_code:" + str(code))
            return queue.get(1, timeout)  #�����������ָ���һֱ���ڵȴ�״̬��֪��queue�����г��ַ�����Ϣ������������
        except EmptyQueue:
            return None, None

    def buffer(self):
        'returns a JdwpBuffer configured for this connection'
        buf = JdwpBuffer()
        buf.config(*self.sizes)
        return buf
        
    ################################################################# THREAD API
    
    def start(self):
        'performs handshaking and solicits[����] configuration information'
        self.daemon = True  #�ػ��߳�

        if not self.initialized: #���Ϊfalse��ʼ����δ��ɣ���������ʼ������
            self.writeHandshake()
            self.readHandshake()
            self.writeIdSzReq()
            self.readIdSzRes()
            self.initialized = True #ȷ����ɳ�ʼ��
            Thread.start(self)
        return None

    def run(self):
        'runs forever; overrides the default Thread.run()'
        try:
            while True:
                self.process()
        except EOF:
            return
    
