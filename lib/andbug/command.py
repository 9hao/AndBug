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
The andbug.command module underpins the andbug command system by providing 
context and a central registry to command modules in the andbug.cmd package.

Commands for andbug are typically defined as ::

    @andbug.action(
        '<used-argument> [<extra-argument>]'
        (('debug', 'sets the debug level'))
    )
    def sample(ctxt, used, extra=None):
        ...

'''

import os, os.path, sys, getopt, inspect
import andbug.vm, andbug.cmd, andbug.source, andbug.util,andbug.screed
import traceback
from time import sleep
from andbug.errors import *

#TODO: make short_opts, long_opts, opt_table a dynamic parsing derivative.

OPTIONS = (
    ('pid', 'the process to be debugged, by pid or name'),
    ('dev', 'the device or emulator to be debugged (see adb)'),
    ('src', 'adds a directory where .java or .smali files could be found')
)

class Context(object):
    '''
    Commands in AndBug are associated with a command Context, which contains
    options and environment information for the command.  This information
    may be reused for multiple commands within the AndBug shell.
    '''

    def __init__(self):
        self.sess = None
        self.pid = None
        self.dev = None
        self.shell = False  #��ʶ�����Ƿ������andbug������shell
    
    def connect(self):
        'connects using vm.connect to the process if not already connected'
        if self.sess is not None: return
        self.sess = andbug.vm.connect(self.pid, self.dev)

    #�Դ����ض�����Ĳ������н���
    def parseOpts(self, args, options=OPTIONS, proc=True):
        'parse command options in OPTIONS format'
        short_opts = ''.join(opt[0][0] + ':' for opt in options)  #str: p:d:s:
        long_opts = list(opt[0] + '=' for opt in options)  #list: ['pid=', 'dev=', 'src=']
        opt_table = {}

		#opt_table��ֵΪ��
		#	--dev    str: dev
		#	--pid	str: pid
		#	--src	str: src
		#	-d	str: dev
		#	-p	str: pid
		#	-s	str: src
        for opt in options:
            opt_table['-' + opt[0][0]] = opt[0]
            opt_table['--' + opt[0]] = opt[0]

		#�ֽ����opts���� ����������ֵ�Ķԣ�  args����ʣ��Ĳ���֮
		#"xxx.py -h -o file --help --output=out file1 file2" ���������
		#opts��ֵ [('-h',''),('-o','file'),('--help',''),('--output','out')]
		#args��ֵ ['file1','file2']
        opts, args = getopt.gnu_getopt(args, short_opts, long_opts)

        opts = list((opt_table[k], v) for k, v in opts) #�����������������ȫ��
        t = {}
        for k, v in opts: 
            if k == 'src': #����src����²���Դ��������
                andbug.source.add_srcdir(v)
            else:
                t[k] = v
        
        if proc:
            pid = t.get('pid')  #��ȡ��ǰҪ���Գ����pid��ֵ
            dev = t.get('dev')	#��ȡ��ǰҪ���Գ����dev��ֵ
        
            self.findDev(dev)
            self.findPid(pid)

        return args, opts

    def findDev(self, dev=None):
        'determines the device for the command based on dev'
        if self.dev is not None: return  #���Context������dev�Ѿ�����Ч��ֵ�ˣ��Ͳ�ȥҪ�ٵ��û�ȡdev�ĺ���andbug.util.find_dev
        self.dev = andbug.util.find_dev(dev)

    def findPid(self, pid=None):
        'determines the process id for the command based on dev, pid and/or name'        
        if self.pid is not None: return  ##���Context������pid�Ѿ�����Ч��ֵ�ˣ��Ͳ�ȥҪ�ٵ��û�ȡpid�ĺ���andbug.util.find_pid
        cur_pid = andbug.util.find_pid(pid, self.dev)
        count =0
        while cur_pid == None:
            if count%4==0:
                andbug.screed.item("wait......")
                
            sleep(1) #sleep 1���к������»�ȡpid��ֵ
            count=count+1
            cur_pid = andbug.util.find_pid(pid, self.dev)

            
            if count==60:
                raise OptionError('could not find process ' + str(pid))
        self.pid = cur_pid
        
        
    #�ж������Ƿ����ִ�У�����������������shell����Ϊtrue����ô�������Ϳ���ֱ�Ӹ���andbug��
    #��Ϊһ������ֱ������
    def can_perform(self, act):
        'uses the act.shell property to determine if it makes sense'
        if self.shell:
            return act.shell != False  #ֵ������true����false
        return act.shell != True  #ֵ������false������true

    def block_exit(self):
        'prevents termination outside of shells'

        if self.shell:
            # we do not need to block_exit, readline is doing a great
            # job of that for us.
            return

        while True:
            # the purpose of the main thread becomes sleeping forever
            # this is because Python's brilliant threading model only
            # allows the main thread to perceive CTRL-C.
            sleep(3600)
        

    #�������ܣ�ִ�о�������
    #������	cmd ����Ҫִ�е�����
    #		args ����Ĳ���
    def perform(self, cmd, args):
        'performs the named command with the supplied arguments'
        act = ACTION_MAP.get(cmd) #��ȡ��Ӧ����Ĵ�����

        if not act:
            perr('!! command not supported: "%s."' % cmd)
            return False

        if not self.can_perform(act): #��������false�˳�
            if self.shell:
                perr('!! %s is not available in the shell.' % cmd)
            else:
                perr('!! %s is only available in the shell.' % cmd)
            return False

        #�����������ǰ����Ĳ���
        args, opts = self.parseOpts(args, act.opts, act.proc)
        argct = len(args) + 1 

        if argct < act.min_arity:  #���С����С�Ĳ����������˳�
            perr('!! command "%s" requires more arguments.' % cmd)
            return False
        elif argct > act.max_arity:#����������Ĳ����������˳�
            perr('!! too many arguments for command "%s."' % cmd)
            return False

        opts = filter(lambda opt: opt[0] in act.keys, opts)
        kwargs  = {}
        for k, v in opts: 
            kwargs[k] = v

        if act.proc: self.connect()
        try:
            act(self, *args, **kwargs)
        except Exception as exc:
            dump_exc(exc)
            return False

        return True

def dump_exc(exc):       
    tp, val, tb = sys.exc_info()
    with andbug.screed.section("%s: %s" % (tp.__name__, val)):
        for step in traceback.format_tb(tb):
            step = step.splitlines()
            with andbug.screed.item(step[0].strip()):
                for line in step[1:]:
                    andbug.screed.line(line.strip())

ACTION_LIST = []
ACTION_MAP = {}

#����ʵ�ֽ�������Ϣ���浽List��Map��
def bind_action(name, fn, aliases):
    ACTION_LIST.append(fn)
    ACTION_MAP[name] = fn
    for alias in aliases:
        ACTION_MAP[alias] = fn

def action(usage, opts = (), proc = True, shell = None, name = None, aliases=()):
    'decorates a command implementation with usage and argument information'
    def bind(fn):
        fn.proc = proc
        fn.shell = shell
        fn.usage = usage   #ʹ�÷���
        fn.opts = OPTIONS[:] + opts   #��ǰ����Ĳ�������Щ
        fn.keys = list(opt[0] for opt in opts) #����Ķ������ֵ
        fn.aliases = aliases    #��ǰ����ı���
        spec = inspect.getargspec(fn)   #�����ǻ�ȡ����fn������Ĳ������ƣ���fn���н���������������ĸ���������Ĭ��ֵ�����ĸ������Ӷ������ÿ�����������Ҫ���ٸ�������������Ҫ���ٸ�����
                                        #�����ڷ�������ȡ���������Ĳ���������Ԫ�飬�ֱ���(��ͨ���������б�, *������, **������, Ĭ��ֵԪ��)�����û��ֵ�����ǿ��б��3��None�������2.6���ϰ汾��������һ������Ԫ��(Named Tuple)�������������⻹����ʹ������������Ԫ���е�Ԫ�ء�
        defct = len(spec.defaults) if spec.defaults else 0
        argct = len(spec.args) if spec.args else 0
        fn.min_arity = argct - defct   #��ǰ����������С��������
        fn.max_arity = argct	##��ǰ������������������
        fn.name = name or fn.__name__.replace('_', '-')

        bind_action(fn.name, fn, aliases)
    return bind

CMD_DIR_PATH = os.path.abspath(os.path.join( os.path.dirname(__file__), "cmd" )) #�ñ��������·��Ϊ"~/andbug/lib/andbug/cmd"

#��cmdĿ¼�£�����*.py�ļ���import��������̬����ģ��ĳ����е�һ������
def load_commands():
    'loads commands from the andbug.cmd package'  
    for name in os.listdir(CMD_DIR_PATH):
        if name.startswith( '__' ):
            continue
        if name.endswith( '.py' ):
            name = 'andbug.cmd.' + name[:-3]
            try:
                __import__( name )  #��̬��������ģ�飬���ǻ�ִ�У�ָ��python�ļ��е�@andbug.command.action����
            except andbug.errors.DependencyError:
                pass # okay, okay..


#ִ�е������ÿ��������������������ʼ
#����:	args ����������Լ���ز���
#	ctxt = None   ����֧������ִ�е����Ա��ϸ��δ֪
def run_command(args, ctxt = None):
    'runs the specified command with a new context'
    if ctxt is None:
        ctxt = Context()
            
    for item in args:
        if item in ('-h', '--help', '-?', '-help'):
            args = ('help', args[0])
            break
    
    return ctxt.perform(args[0], args[1:])

#���屾�ļ��������ļ����Ե����ĺ���������������
__all__ = (
    'run_command', 'load_commands', 'action', 'Context', 'OptionError'
)



'''
inspect.getargspec(fn) ������ʹ��

��example.py�ļ���
def module_level_function(arg1, arg2='default', *args, **kwargs):
	#This function is declared in the module.
	local_variable = arg1

��use_inspect�ļ���
import inspect
import example

argspec = inspect.getargspec(example.module_level_function)
print 'Names', argsec[0]
print '*��'�� argspec[1]
print '**:', argspec[2]
print 'default:', argspec[3]
arg_with_defaults= argspec[0][-len(argspec[3]):]
print 'arg & defaults:', zip(arg_with_defaults, argspec[3])

���к�Ľ����
Names: ['arg1', 'arg2']
*: args
**: kwargs
default: ('default',)
arg & defaults: [('arg2', 'default')]



'''
