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

'implementation of the "classes" command'

import andbug.command, andbug.screed
import types

@andbug.command.action('[<partial class name>]')
def classes(ctxt, expr=None):
    'lists loaded classes. if no partial class name supplied, list all classes.չʾһ���������'
    with andbug.screed.section('Loaded Classes'):
        
        #classesInfor = ctxt.sess.classes() 
        #print type(classesInfor) classesInfor ��������<class 'andbug.data.view'>
        for c in ctxt.sess.classes(): #ctxt.sess.classes()��������ȡ�����Ϣ
            #print type(c) ���ص�������<class 'andbug.vm.Class'>            
            n = c.jni  #��ȡ���е�jni��Ա����
            if n.startswith('L') and n.endswith(';'):
                n = n[1:-1].replace('/', '.')
            else:
                continue

            if expr is not None:
                #ͨ�������ж�Ҫ���������Ϣ
                if n.find(expr) >= 0:
                    andbug.screed.item(n)
            else:
                andbug.screed.item(n)
            
