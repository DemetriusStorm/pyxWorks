#!/usr/bin/python

import sys, os, io, paramiko, json, platform
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
script_name      = sys.argv[0]

KNOWN_OS_TYPES = ['cisco_xr', 'cisco_ios', 'juniper', 'juniper_junos', 'huawei' ,'linux']

try:    WORKDIR         = os.environ['HOME']
except: WORKDIR         = str(os.path.dirname(os.path.abspath(__file__)))
if WORKDIR: LOGDIR      = os.path.join(WORKDIR,'logs')

try:    PASSWORD        = os.environ['NEWR_PASS']
except: PASSWORD        = str()
try:    USERNAME        = os.environ['NEWR_USER']
except: USERNAME        = str()

print('LOGDIR: ' + LOGDIR)

###############################################################################
#
# Generic list of commands
#
###############################################################################


# IOS-XE is only for IPsec GW
CMD_IOS_XE = [
			'sh run int loopback 200 | i /128',
            {'call_function': 'stop_if_ipv6_found','input':'last_output', 'if_output_is_void':'exit'},
            'sh run int loopback 200 | i 172',
            {'call_function': 'parse_ipv4_from_text','input':'last_output', 'output':'converted_ipv4','if_output_is_void':'exit'},
            'conf t',
            'interface loopback 200',
            ('ipv6 address', {'variable':'converted_ipv4'}, '/128'),
            'exit',
			'exit',
			'write',
            'sh int loopback 200 | i /128'
              ]
CMD_IOS_XR = [
            'sh run int loopback 200 | i /128',
            {'call_function': 'stop_if_ipv6_found', 'input':'last_output', 'if_output_is_void':'exit'},
			'sh run int loopback 200 | i 172',
            {'call_function': 'parse_ipv4_from_text','input':'last_output', 'output':'converted_ipv4','if_output_is_void':'exit'},
            'conf',
			'interface loopback 200',
            ('ipv6 address ', {'variable':'converted_ipv4'}, '/128'),
            'router isis PAII',
            'interface Loopback200',
            'address-family ipv6 unicast',
            'commi',
            'exit',
			'exit',
            'sh int loopback 200 | i /128'
             ]
CMD_JUNOS = [
            'show configuration interfaces lo0 | match /128',
            {'call_function': 'stop_if_two_ipv6_found', 'if_output_is_void':'exit'},
            'show configuration interfaces lo0 | display set | match 128',
            {'call_function': 'parse_whole_set_line_from_text', 'if_output_is_void':'exit'},
			'show configuration interfaces lo0 | match 172.25.4',
            {'call_function': 'parse_ipv4_from_text','input':'last_output', 'output':'converted_ipv4','if_output_is_void':'exit'},
             'configure private',
             #'__var_set_ipv6line__',
             ('set interfaces lo0 unit 0 family inet6 address ', {'variable':'converted_ipv4'}, '/128'),
             'show configuration interfaces lo0 | match /128',
    		 'commi',
    		 'exit',
             'show configuration interfaces lo0 | match /128',
             ]
CMD_VRP = [
            'disp current-configuration interface LoopBack 200 | include /128',
            {'call_function': 'stop_if_ipv6_found', 'input':'last_output', 'if_output_is_void':'exit'},
			'disp current-configuration interface LoopBack 200 | include 172',
            {'call_function': 'parse_ipv4_from_text', 'input':'last_output', 'output':'converted_ipv4','if_output_is_void':'exit'},
            'sys',
			'interface loopback 200',
            'ipv6 enable',
			('ipv6 address ', {'variable':'converted_ipv4'}, '/128'),
            'isis ipv6 enable 5511',
			'commit',
            'quit',
			'quit',
            'disp current-configuration interface LoopBack 200 | include /128'
          ]
CMD_LINUX = [
            'hostname',
            ('echo ', {'variable':'last_output'}),
            ('echo ', {'variable':'notexistent'},{'if_output_is_void':'exit'}),
            'free -m'
            ]
###############################################################################
#
# Function and Class
#
###############################################################################

def netmiko_autodetect(device, debug = None):
    router_os = str()
    try: DEVICE_HOST = device.split(':')[0]
    except: DEVICE_HOST = str()
    try: DEVICE_PORT = device.split(':')[1]
    except: DEVICE_PORT = '22'
    guesser = netmiko.ssh_autodetect.SSHDetect(device_type='autodetect', \
        ip=DEVICE_HOST, port=int(DEVICE_PORT), username=USERNAME, password=PASSWORD)
    best_match = guesser.autodetect()
    if debug:
        print('BEST_MATCH: %s\nPOTENTIAL_MATCHES:' %(best_match))
        print(guesser.potential_matches)
    router_os = best_match
    return router_os


def ipv4_to_ipv6_obs(ipv4address):
    ip4to6, ip6to4 = str(), str()
    try: v4list = ipv4address.split('/')[0].split('.')
    except: v4list = []
    if len(v4list) == 4:
        try:
            if int(v4list[0])<256 and int(v4list[1])<256 and int(v4list[2])<256 \
                and int(v4list[3])<256 and int(v4list[0])>=0 and \
                int(v4list[1])>=0 and int(v4list[2])>=0 and int(v4list[3])>=0:
                ip4to6 = 'fd00:0:0:5511::%02x%02x:%02x%02x' % \
                    (int(v4list[0]),int(v4list[1]),int(v4list[2]),int(v4list[3]))
                ip6to4 = '2002:%02x%02x:%02x%02x:0:0:0:0:0' % \
                    (int(v4list[0]),int(v4list[1]),int(v4list[2]),int(v4list[3]))
        except: pass
    return ip4to6, ip6to4

def parse_ipv4_from_text(text):
    #global converted_ipv4
    try: ipv4 = text.split('address')[1].split()[0].replace(';','')
    except: ipv4 = str()
    converted_ipv4 = ipv4_to_ipv6_obs(ipv4)[0]
    return converted_ipv4

def stop_if_ipv6_found(text):
    try: ipv6 = text.split('address')[1].split()[0].replace(';','')
    except: ipv6 = str()
    if ipv6: return str()
    else: return "NOT_FOUND"

def stop_if_two_ipv6_found(text):
    try: ipv6 = text.split('address')[1].split()[0].replace(';','')
    except: ipv6 = str()
    try: ipv6two = text.split('address')[2].split()[0].replace(';','')
    except: ipv6two = str()
    if ipv6 and ipv6two: return str()
    else: return "NOT_FOUND"

def parse_whole_set_line_from_text(text):
    #global set_ipv6line
    try: set_text = text.split('set')[1].split('\n')[0]
    except: set_text = str()
    if set_text: set_ipv6line = 'set' + set_text + ' primary\n'
    else: set_ipv6line = str()
    return set_ipv6line

def parse_json_file_and_get_oti_routers_list():
    oti_routers, json_raw_data = [], str()
    json_filename = '/usr/local/iptac/oti_all.pl'
    with io.open(json_filename,'r') as json_file:
        data = json_file.read()
        data_converted = data.split('%oti_all =')[1].replace("'",'"')\
            .replace('=>',':').replace('(','{').replace(')','}').replace(';','')
        data_converted='{\n  "OTI_ALL" : ' + data_converted + '\n}'
        json_raw_data = json.loads(data_converted)
    if json_raw_data:
        for router in json_raw_data['OTI_ALL']:
            if '172.25.4' in json_raw_data['OTI_ALL'][router]['LSRID']: oti_routers.append(router)
    return oti_routers


def run_remote_and_local_commands(CMD, logfilename = None):
    ssh_connection = None
    try:
        ssh_connection = netmiko.ConnectHandler(device_type = router_type, \
            ip = DEVICE_HOST, port = int(DEVICE_PORT), \
            username = USERNAME, password = PASSWORD)
        if not logfilename:
            if 'LINUX' in platform.system().upper(): logfilename = '/dev/null'
            else: logfilename = 'nul'
        with open(logfilename,"w") as fp:
            dictionary_of_pseudovariables = {}
            for cli_items in CMD:
                cli_line = str()
                # list,tupple,strins are remote device commands
                if isinstance(cli_items, six.string_types) or \
                    isinstance(cli_items, list) or isinstance(cli_items, tuple):
                    if isinstance(cli_items, six.string_types): cli_line = cli_items
                    if isinstance(cli_items, list) or isinstance(cli_items, tuple):
                        for cli_item in cli_items:
                           if isinstance(cli_item, dict): cli_line += dictionary_of_pseudovariables.get(cli_item.get('variable',''),'')
                           else: cli_line += cli_item
                    print(bcolors.GREEN + "COMMAND: %s" % (cli_line) + bcolors.ENDC )
                    last_output = ssh_connection.send_command(cli_line)
                    last_output = last_output.replace('\x0d','')
                    print(bcolors.GREY + "%s" % (last_output) + bcolors.ENDC )
                    fp.write('COMMAND: ' + cli_line + '\n'+last_output+'\n')
                    dictionary_of_pseudovariables['last_output'] = last_output.rstrip()
                    for cli_item in cli_items:
                        if isinstance(cli_item, dict) and \
                            last_output.strip() == str() and \
                            cli_item.get('if_output_is_void','') in ['exit','quit','stop']:
                            print("%sSTOP (VOID OUTPUT).%s" % \
                                (bcolors.RED,bcolors.ENDC))
                            return None
                # HACK: use dictionary for running local python code functions
                elif isinstance(cli_items, dict):
                    if cli_items.get('call_function',''):
                        local_function = cli_items.get('call_function','')
                        local_input = dictionary_of_pseudovariables.get('input','')
                        output_to_pseudovariable = dictionary_of_pseudovariables.get('output','')
                        local_output = locals()[local_function](local_input)
                        if output_to_pseudovariable:
                            dictionary_of_pseudovariables[output_to_pseudovariable] = local_output
                        print("%sCALL_LOCAL_FUNCTION: %s'%s' = %s(%s)\n%s" % \
                            (bcolors.GREEN,bcolors.YELLOW,local_output,local_function,local_input,bcolors.ENDC))
                        if local_output.strip() == str() and \
                            cli_items.get('if_output_is_void') in ['exit','quit','stop']:
                            print("%sSTOP (VOID LOCAL OUTPUT).%s" % \
                                (bcolors.RED,bcolors.ENDC))
                            return None
                    elif cli_items.get('local_command',''):
                        local_process = cli_items.get('local_command','')
                        local_input = dictionary_of_pseudovariables.get('input','')
                        output_to_pseudovariable = dictionary_of_pseudovariables.get('output','')
                        local_output = subprocess.call(local_process+' '+local_input if local_input else local_process, shell=True)
                        if output_to_pseudovariable:
                            dictionary_of_pseudovariables[output_to_pseudovariable] = local_output
                        print("%sLOCAL_COMMAND: %s'%s' = %s(%s)\n%s" % \
                            (bcolors.GREEN,bcolors.YELLOW,local_output,local_function,local_input,bcolors.ENDC))
                        if local_output.strip() == str() and \
                            cli_items.get('if_output_is_void') in ['exit','quit','stop']:
                            print("%sSTOP (VOID LOCAL OUTPUT).%s" % \
                                (bcolors.RED,bcolors.ENDC))
                            return None
                else: print('%sUNSUPPORTED_TYPE %s of %s!%s' % \
                            (bcolors.MAGENTA,type(item),str(cli_items),bcolors.ENDC))
    except () as e:
        print(bcolors.FAIL + " ... EXCEPTION: (%s)" % (e) + bcolors.ENDC )
        sys.exit()
    finally:
        if ssh_connection: ssh_connection.disconnect()
    return None




##############################################################################
#
# BEGIN MAIN
#
##############################################################################

if __name__ != "__main__": sys.exit(0)

######## Parse program arguments #########
parser = argparse.ArgumentParser(
                description = "",
                epilog = "e.g: \n" )

parser.add_argument("--version",
                    action = 'version', version = VERSION)
parser.add_argument("--device",
                    action = "store", dest = 'device',
                    default = str(),
                    help = "target router to check")
parser.add_argument("--os",
                    action = "store", dest="router_type",
                    choices = KNOWN_OS_TYPES,
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
                    action = 'store_true', dest = "nocolors", default = None,
                    help = "print mode with no colors.")
parser.add_argument("--nolog",
                    action = 'store_true', dest = "nolog", default = None,
                    help = "no logging to file.")
parser.add_argument("--rcmd",
                    action = "store", dest = 'rcommand', default = str(),
                    help = "'command' or ['list of commands',...] to run on remote device")
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
        try: DEVICE_HOST = device.split(':')[0]
        except: DEVICE_HOST = str()
        try: DEVICE_PORT = device.split(':')[1]
        except: DEVICE_PORT = '22'
        print('DEVICE %s (host=%s, port=%s) START.........................'\
            %(device,DEVICE_HOST, DEVICE_PORT))

        ####### Figure out type of router OS
        if not args.router_type:
            router_type = netmiko_autodetect(device)
            if not router_type in KNOWN_OS_TYPES:
                print('%sUNSUPPORTED DEVICE TYPE: %s , BREAK!%s' % \
                    (bcolors. MAGENTA,router_type, bcolors.ENDC))
            else: print('DETECTED DEVICE_TYPE: %s' % (router_type))
        else:
            router_type = args.router_type
            print('FORCED DEVICE_TYPE: ' + router_type)

        ######## Create logs directory if not existing  #########
        if not os.path.exists(LOGDIR): os.makedirs(LOGDIR)
        filename_prefix = os.path.join(LOGDIR,device)
        filename_suffix = 'log'
        now = datetime.datetime.now()
        logfilename = "%s-%.2i%.2i%i-%.2i%.2i%.2i-%s-%s-%s" % \
            (filename_prefix,now.year,now.month,now.day,now.hour,now.minute,\
            now.second,script_name.replace('.py',''),USERNAME,filename_suffix)
        if args.nolog: logfilename = None

        ######## Find command list file (optional)
        list_cmd = []
        if args.cmd_file:
            if not os.path.isfile(args.cmd_file):
                print("%s ... Can't find command file: %s%s") % \
                    (bcolors.MAGENTA, args.cmd_file, bcolors.ENDC)
                sys.exit()
            else:
                with open(args.cmd_file) as cmdf:
                    list_cmd = cmdf.read().replace('\x0d','').splitlines()

        if args.rcommand: list_cmd = args.rcommand.replace('\'','').\
            replace('"','').replace('[','').replace(']','').split(',')

        if len(list_cmd)>0: CMD = list_cmd
        else:
            if router_type == 'cisco_ios':  CMD = CMD_IOS_XE
            elif router_type == 'cisco_xr': CMD = CMD_IOS_XR
            elif router_type == 'juniper':  CMD = CMD_JUNOS
            elif router_type == 'huawei' :  CMD = CMD_VRP
            elif router_type == 'linux':    CMD = CMD_LINUX
            else: CMD = list_cmd

        run_remote_and_local_commands(CMD, logfilename)

        if logfilename and os.path.exists(logfilename):
            print('%s file created.' % (logfilename))
        print('\nDEVICE %s DONE.'%(device))
print('\nEND.')

