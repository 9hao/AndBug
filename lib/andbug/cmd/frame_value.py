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

'implementation of the "frame_value" command'

import andbug.command, andbug.screed, andbug.options

@andbug.command.action('<threadName frameInfor>', aliases=('fv',))
def frame_value(ctxt, threadName, frameName):
    '''
    �������ܣ�����ָ�����߳����ƣ���ջλ�ã���ȡ��Ӧ��ջ�в�������Ϣ
    '''
    
    thread = ctxt.sess.threads(threadName)
    frames = thread.frames()  #!!!!!!����ʧ�ܣ���û�ҵ�ԭ��
    for f in thread.frames: #t.frames�Ƿ��ص�ǰ�Ķ�ջ��Ϣ
        name = str(f.loc)
        if name.find(frameName)==-1:
            continue
        if f.native:  #�ж϶�ջ�к��������ͣ��Ƿ����ڲ���������dalvik.system.NativeStart.main([Ljava/lang/String;)V <native>
            name += ' <native>'
        with andbug.screed.refer(name):
            for var_name in f:                             
                andbug.screed.item(var_name + ":" + str(f[var_name]))
     

    
