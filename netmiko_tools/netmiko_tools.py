#!/usr/bin/python

import sys, os, io, paramiko, json
import getopt
import getpass
import telnetlib
import time, datetime
import difflib
import subprocess
import re
import argparse
import glob
import socket
import six

#python 2.7 problem - hack 'pip install esptool'
import netmiko

class bcolors:
        DEFAULT    = '\033[99m'
        WHITE      = '\033[97m'
        CYAN       = '\033[96m'
        MAGENTA    = '\033[95m'
        HEADER     = '\033[95m'
        OKBLUE     = '\033[94m'
        BLUE       = '\033[94m'
        YELLOW     = '\033[93m'
        GREEN      = '\033[92m'
        OKGREEN    = '\033[92m'
        WARNING    = '\033[93m'
        RED        = '\033[91m'
        FAIL       = '\033[91m'
        GREY       = '\033[90m'
        ENDC       = '\033[0m'
        BOLD       = '\033[1m'
        UNDERLINE  = '\033[4m'

class nocolors:
        DEFAULT    = ''
        WHITE      = ''
        CYAN       = ''
        MAGENTA    = ''
        HEADER     = ''
        OKBLUE     = ''
        BLUE       = ''
        YELLOW     = ''
        GREEN      = ''
        OKGREEN    = ''
        WARNING    = ''
        RED        = ''
        FAIL       = ''
        GREY       = ''
        ENDC       = ''
        BOLD       = ''
        UNDERLINE  = ''

TODAY            = datetime.datetime.now()
VERSION          = str(TODAY.year)[2:] + '.' + str(TODAY.month) + '.' + str(TODAY.day)
HELP             = "\nTry ' --help' for more information\n"

UNKNOW_HOST     = 'Name or service not known'
TIMEOUT         = 60
try:    HOMEDIR         = os.environ['HOME']
except: HOMEDIR         = str(os.path.dirname(os.path.abspath(__file__)))
try:    PASSWORD        = os.environ['NEWR_PASS']
except: PASSWORD        = str()
try:    USERNAME        = os.environ['NEWR_USER']
except: USERNAME        = str()

print('HOMEDIR/WORKDIR: ' + HOMEDIR)

###############################################################################
#
# Generic list of commands
#
###############################################################################


# IOS-XE is only for IPsec GW
CMD_IOS_XE = [
			'show version',
            'show version'

              ]
CMD_IOS_XR = [
            'show version',
            'show version',

             ]
CMD_JUNOS = [
            'show version',
            'show version',

             ]
CMD_VRP = [
            'display version',
            'display version'
          ]
CMD_LINUX = [
            'who',
            'whoami',
            'free -m',
            'lspci'
            ]
###############################################################################
#
# Function and Class
#
###############################################################################

def netmiko_autodetect(device, debug = False):
    router_os = str()
    try: PARAMIKO_HOST = device.split(':')[0]
    except: PARAMIKO_HOST = str()
    try: PARAMIKO_PORT = device.split(':')[1]
    except: PARAMIKO_PORT = '22'
    guesser = netmiko.ssh_autodetect.SSHDetect(device_type='autodetect', ip=PARAMIKO_HOST, port=int(PARAMIKO_PORT), username=USERNAME, password=PASSWORD)
    best_match = guesser.autodetect()
    if debug:
        print('BEST_MATCH: %s\nPOTENTIAL_MATCHES:' %(best_match))
        print(guesser.potential_matches)
    router_os = best_match
    return router_os


##############################################################################
#
# BEGIN MAIN
#
##############################################################################

if __name__ != "__main__": sys.exit(0)

######## Parse program arguments #########
parser = argparse.ArgumentParser(
                description = "",
                epilog = "e.g: \n")

parser.add_argument("--version",
                    action = 'version', version = VERSION)
parser.add_argument("--device",
                    action = "store", dest = 'device',
                    default = str(),
                    help = "target router to check")
parser.add_argument("--os",
                    action = "store", dest="router_type",
                    choices = ['cisco_xr', 'cisco_xe', 'juniper', 'juniper_junos', 'huawei' ,'linux'],
                    help = "router operating system type")
parser.add_argument("--cmdfile", action = 'store', dest = "cmd_file", default = None,
                    help = "specify a file with a list of commands to execute")
parser.add_argument("--user",
                    action = "store", dest = 'username', default = str(),
                    help = "specify router user login")
parser.add_argument("--pass",
                    action = "store", dest = 'password', default = str(),
                    help = "specify router user password")
parser.add_argument("--nocolors",
                    action = 'store_true', dest = "nocolors", default = False,
                    help = "print mode with no colors.")
parser.add_argument("--rcmd",
                    action = "store", dest = 'rcommand', default = str(),
                    help = "command to run on remote device")
args = parser.parse_args()

if args.nocolors: bcolors = nocolors
device_list = [args.device]

####### Set USERNAME if needed
if args.username: USERNAME = args.username
if not USERNAME:
    print(bcolors.MAGENTA + " ... Please insert your username by cmdline switch --user username !" + bcolors.ENDC )
    sys.exit(0)

# SSH (default)
if not PASSWORD:
    if args.password: PASSWORD = args.password
    else:             PASSWORD = getpass.getpass("TACACS password: ")

for device in device_list:
    if device:
        router_prompt = None
        try: PARAMIKO_HOST = device.split(':')[0]
        except: PARAMIKO_HOST = str()
        try: PARAMIKO_PORT = device.split(':')[1]
        except: PARAMIKO_PORT = '22'
        print('\nDEVICE %s (host=%s, port=%s) START.........................'\
            %(device,PARAMIKO_HOST, PARAMIKO_PORT))

        ####### Figure out type of router OS
        if not args.router_type:
            #router_type , router_prompt = detect_router_by_ssh(device,debug = False)
            router_type = netmiko_autodetect(device,debug = False)
            print('DETECTED ROUTER_TYPE: %s' % (router_type))
        else:
            router_type = args.router_type
            print('FORCED ROUTER_TYPE: ' + router_type)

        ######## Create logs directory if not existing  #########
        if not os.path.exists(os.path.join(HOMEDIR,'logs')): os.makedirs(os.path.join(HOMEDIR,'logs'))
        filename_prefix = os.path.join(HOMEDIR,'logs',device)
        filename_suffix = 'log'
        now = datetime.datetime.now()
        filename = "%s-%.2i%.2i%i-%.2i%.2i%.2i-%s" % \
            (filename_prefix,now.year,now.month,now.day,now.hour,now.minute,now.second,filename_suffix)

        ######## Find command list file (optional)
        list_cmd, line_list= [], []
        if args.cmd_file:
            if not os.path.isfile(args.cmd_file):
                print(bcolors.MAGENTA + " ... Can't find command file: %s " + bcolors.ENDC) \
                        % args.cmd_file
                sys.exit()
            else:
                with open(args.cmd_file) as cmdf:
                    list_cmd = cmdf.read().replace('\x0d','').splitlines()

        if args.rcommand: list_cmd = args.rcommand.replace('\'','').replace('"','').replace('[','').replace(']','').split(',')

        if len(list_cmd)>0:
            CMD = list_cmd
        else:
            # Collect pre/post check information
            if router_type == 'cisco_ios':  CMD = CMD_IOS_XE
            elif router_type == 'cisco_xr': CMD = CMD_IOS_XR
            elif router_type == 'juniper':  CMD = CMD_JUNOS
            elif router_type == 'huawei' :  CMD = CMD_VRP
            elif router_type == 'linux':    CMD = CMD_LINUX
            else: CMD = list_cmd

        ssh_connection = None
        try:
            ssh_connection = netmiko.ConnectHandler(device_type=router_type, ip=PARAMIKO_HOST,\
                port=int(PARAMIKO_PORT), username=USERNAME, password=PASSWORD)
            with open(filename,"w") as fp:
                for cli_items in CMD:
                    try:
                        item = cli_items[0] if type(cli_items) == list else cli_items
                        print(bcolors.GREEN + "COMMAND: %s" % (item) + bcolors.ENDC )
                        output = ssh_connection.send_command(item)
                        print(bcolors.GREY + "%s" % (output) + bcolors.ENDC )
                        fp.write('COMMAND: '+item+'\n'+output+'\n')
                    except: pass

        except () as e:
            print(bcolors.FAIL + " ... EXCEPTION: (%s)" % (e) + bcolors.ENDC )
            sys.exit()
        finally:
            if ssh_connection: ssh_connection.disconnect()

        if os.path.exists(filename): print('%s file created.'%filename)
        print('\nDEVICE %s DONE.'%(device))
print('\nEND.')
