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

'implementation of the "statics" command'

import andbug.command, andbug.options

@andbug.command.action('<class-path>')
def statics(ctxt, cpath):
    'lists the methods of a class'
    cpath = andbug.options.parse_cpath(cpath)
    for c in ctxt.sess.classes(cpath):  #c的类型为vm.Class类，它的父类型为RefType
        andbug.screed.section("Static Fields, %s" % c)
        for k, v in c.statics.iteritems():
            andbug.screed.item("%s = %s" % (k, v)) #在这里会到用vm.String类中的__str__函数，进而调用data(self)发起"call jdwp 0x0A 01"命令
