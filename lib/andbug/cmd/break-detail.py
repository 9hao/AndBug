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

'implementation of the "break" command'

import andbug.command, andbug.screed, andbug.options
from Queue import Queue

'''
�������������ٴ����ϵ�ʱ����������Ϣ
'''

def parse_frame_detail(frame):
    '''
    �������ܣ�����һ����ջ֡����ϸ���
    '''
    all_var_infor = frame.values
    for var_name in all_var_infor:
        #print "%s = %s" %(var_name, all_var_infor[var_name])
        andbug.screed.item(var_name + ":" + str(all_var_infor[var_name]))

def report_hit(t):
    '''
    ����METHOD_ENTRY�¼��ص�������
    t�������������ֱ�  t[0] thread
                    t[1] Location
    '''
    t = t[0] #t��һ��Thread���͵ı���
    with andbug.screed.section("Breakpoint hit in %s, process suspended." % t):
        t.sess.suspend() #��ͣ��ǰ�߳�
        for f in t.frames: #t.frames�Ƿ��ص�ǰ�Ķ�ջ��Ϣ
            name = str(f.loc)
            if f.native:  #�ж϶�ջ�к��������ͣ��Ƿ����ڲ���������dalvik.system.NativeStart.main([Ljava/lang/String;)V <native>
                name += ' <native>'
            with andbug.screed.refer(name):
                parse_frame_detail(f)
               
               
def cmd_break_methods(ctxt, cpath, mpath):
    for c in ctxt.sess.classes(cpath):
        for m in c.methods(mpath):
            l = m.firstLoc   #��������jdwp������
            if l.native:  #����true���޷����öϵ�
                andbug.screed.item('Could not hook native %s' % l)
                continue
            l.hook(func = report_hit) #���öϵ����ú���
            andbug.screed.item('Hooked %s' % l)

def cmd_break_classes(ctxt, cpath):
    for c in ctxt.sess.classes(cpath): #cΪvm.py�У�Class���һ������
        c.hookEntries(func = report_hit)
        andbug.screed.item('Hooked %s' % c)

@andbug.command.action(
    '<class> [<method>]', name='break-detail', aliases=('b',), shell=True
)
def cmd_break(ctxt, cpath, mquery=None):
    'suspends the process when a method is called'
    cpath, mname, mjni = andbug.options.parse_mquery(cpath, mquery)
    #print "cpath=" + cpath + "\t mname=" + mname + "\t mjni=" + mjni 
    #����Ľ���ǣ�cpath=Lcom/example/test/MainActivity$1;     mname=onClick     mjni=(Landroid/view/View;)V
    with andbug.screed.section('Setting Hooks'):
        if mname is None:
            cmd_break_classes(ctxt, cpath)
        else:
            cmd_break_methods(ctxt, cpath, mname)

    ctxt.block_exit()
