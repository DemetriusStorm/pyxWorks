#!/usr/bin/python

import sys, os, io, paramiko, json , copy
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
import collections

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

START_EPOCH      = time.time()
TODAY            = datetime.datetime.now()
script_name      = sys.argv[0]
TIMEOUT          = 60

remote_connect = True

KNOWN_OS_TYPES = ['cisco_xr', 'cisco_ios', 'juniper', 'juniper_junos', 'huawei' ,'linux']

try:    WORKDIR         = os.environ['HOME']
except: WORKDIR         = str(os.path.dirname(os.path.abspath(__file__)))
if WORKDIR: LOGDIR      = os.path.join(WORKDIR,'logs')

try:    PASSWORD        = os.environ['NEWR_PASS']
except: PASSWORD        = str()
try:    USERNAME        = os.environ['NEWR_USER']
except: USERNAME        = str()
try:    EMAIL_ADDRESS   = os.environ['NEWR_EMAIL']
except: EMAIL_ADDRESS   = str()

default_problemline_list   = []
default_ignoreline_list    = [r' MET$', r' UTC$']
default_linefilter_list    = []
default_compare_columns    = []
default_printalllines_list = []

print('LOGDIR: ' + LOGDIR)

###############################################################################
#
# Generic list of commands
#
###############################################################################


# IOS-XE is only for IPsec GW
CMD_IOS_XE = []

CMD_IOS_XR = [
    {'remote_command':['sh run | in "router bgp"',{'output_variable':'router_bgp_text'}]
    },
    {'eval':['True if "router bgp 5511" in glob_vars.get("router_bgp_text","") else None',{'output_variable':'OTI_5511'}]
    },
    {'eval':'glob_vars.get("OTI_5511","")',},

    {'if':'glob_vars.get("NOSHUT","")',
        "eval":"return_bgp_data_json()"
    },

    {'if':'glob_vars.get("NOSHUT","") and len(bgp_data.get("OTI_EXT_IPS_V4",""))>0',
        'exec':'glob_vars["OTI_EXT_IPS_V4"] = bgp_data["OTI_EXT_IPS_V4"]'},
    {'if':'glob_vars.get("NOSHUT","") and len(bgp_data.get("OTI_EXT_IPS_V6",""))>0',
        'exec':'glob_vars["OTI_EXT_IPS_V6"] = bgp_data["OTI_EXT_IPS_V6"]'},

    {'if':'glob_vars.get("NOSHUT","") and len(bgp_data.get("OTI_INT_IPS_V4",""))>0',
        'exec':'glob_vars["OTI_INT_IPS_V4"] = bgp_data["OTI_INT_IPS_V4"]'},
    {'if':'glob_vars.get("NOSHUT","") and len(bgp_data.get("OTI_INT_IPS_V6",""))>0',
        'exec':'glob_vars["OTI_INT_IPS_V6"] = bgp_data["OTI_INT_IPS_V6"]'},

    {'if':'glob_vars.get("SHUT","") and glob_vars.get("OTI_5511","")',
        'remote_command':['conf t',{'sim':'glob_vars.get("SIM_CMD","")'}],
        'remote_command_2':['router isis PAII',{'sim':'glob_vars.get("SIM_CMD","")'}],
        'remote_command_3':['set-overload-bit',{'sim':'glob_vars.get("SIM_CMD","")'}],
        'remote_command_4':['Commit',{'sim':'glob_vars.get("SIM_CMD","")'}],
        'remote_command_5':['Exit',{'sim':'glob_vars.get("SIM_CMD","")'}],
        'remote_command_6':['Exit',{'sim':'glob_vars.get("SIM_CMD","")'}],
        'exec':'time.sleep(120)',
    },

    {'if':'glob_vars.get("SHUT","") and glob_vars.get("OTI_5511","")',
        'remote_command':['show bgp summary'],
        'exec':['try: \
            \n  temp_ipv4 = glob_vars.get("last_output","").split("St/PfxRcd")[1].strip().splitlines() \
            \n  previous_line, ext_list, int_list = None , [], [] \
            \n  for line in temp_ipv4: \
            \n    if len(line.split())==1: previous_line = line; continue \
            \n    if previous_line: line = previous_line + line; previous_line = None \
            \n    try: \
            \n      if "5511" in line.split()[2] and "." in line.split()[0]: int_list.append(line.split()[0]) \
            \n      elif "." in line.split()[0]: ext_list.append(line.split()[0]) \
            \n    except: pass \
            \n  glob_vars["OTI_INT_IPS_V4"] = int_list; glob_vars["OTI_EXT_IPS_V4"] = ext_list \
            \nexcept: pass' \
               ],
    },
    {'if':'glob_vars.get("SHUT","") and glob_vars.get("OTI_5511","")',
        'remote_command':['show bgp ipv6 unicast summary'],
        'exec':['try: \
            \n  temp_ipv6 = glob_vars.get("last_output","").split("St/PfxRcd")[1].strip().splitlines() \
            \n  previous_line, ext_list, int_list = None , [], [] \
            \n  for line in temp_ipv6: \
            \n    if len(line.split())==1: previous_line = line; continue \
            \n    if previous_line: line = previous_line + line; previous_line = None \
            \n    try: \
            \n      if "5511" in line.split()[2] and ":" in line.split()[0]: int_list.append(line.split()[0]) \
            \n      elif ":" in line.split()[0]: ext_list.append(line.split()[0]) \
            \n    except: pass \
            \n  glob_vars["OTI_INT_IPS_V6"] = int_list; glob_vars["OTI_EXT_IPS_V6"] = ext_list \
            \nexcept: pass' \
               ],
    },

    {'eval':'glob_vars.get("OTI_EXT_IPS_V4","")'},
    {'eval':'glob_vars.get("OTI_EXT_IPS_V6","")'},

    {'eval':'glob_vars.get("OTI_INT_IPS_V4","")'},
    {'eval':'glob_vars.get("OTI_INT_IPS_V6","")'},

    {'if':'glob_vars.get("SHUT","") and glob_vars.get("OTI_EXT_IPS_V4","")',
        'exec':'bgp_data["OTI_EXT_IPS_V4"] = glob_vars.get("OTI_EXT_IPS_V4","")'},
    {'if':'glob_vars.get("SHUT","") and glob_vars.get("OTI_EXT_IPS_V6","")',
        'exec':'bgp_data["OTI_EXT_IPS_V6"] = glob_vars.get("OTI_EXT_IPS_V6","")'},

    {'if':'glob_vars.get("SHUT","") and glob_vars.get("OTI_INT_IPS_V4","")',
        'exec':'bgp_data["OTI_INT_IPS_V4"] = glob_vars.get("OTI_INT_IPS_V4","")'},
    {'if':'glob_vars.get("SHUT","") and glob_vars.get("OTI_INT_IPS_V6","")',
        'exec':'bgp_data["OTI_INT_IPS_V6"] = glob_vars.get("OTI_INT_IPS_V6","")'},

    ### SHUT -------------------------------------------------------------------
    {'pre_loop_if':'glob_vars.get("SHUT","") and glob_vars.get("OTI_5511","") and (glob_vars.get("OTI_EXT_IPS_V4","") or glob_vars.get("OTI_EXT_IPS_V6",""))',
        'pre_loop_remote_command':['conf t',{'sim':'glob_vars.get("SIM_CMD","")'}],
        'pre_loop_remote_command_2':['router bgp 5511',{'sim':'glob_vars.get("SIM_CMD","")'}],
    },
    {'pre_loop_if':'glob_vars.get("SHUT","") and glob_vars.get("OTI_5511","") and glob_vars.get("OTI_EXT_IPS_V4","")',
        'loop_glob_var':"OTI_EXT_IPS_V4",
            'remote_command':['neighbor ',{'eval':'loop_item'},' shutdown',{'sim':'glob_vars.get("SIM_CMD","")'}]
    },
    {'pre_loop_if':'glob_vars.get("SHUT","") and glob_vars.get("OTI_5511","") and glob_vars.get("OTI_EXT_IPS_V6","")',
        'loop_glob_var':"OTI_EXT_IPS_V6",
            'remote_command':['neighbor ',{'eval':'loop_item'},' shutdown',{'sim':'glob_vars.get("SIM_CMD","")'}]
    },
    {'pre_loop_if':'glob_vars.get("SHUT","") and glob_vars.get("OTI_5511","") and (glob_vars.get("OTI_EXT_IPS_V4","") or glob_vars.get("OTI_EXT_IPS_V6",""))',
        'remote_command':['Commit',{'sim':'glob_vars.get("SIM_CMD","")'}],
        'remote_command_2':['Exit',{'sim':'glob_vars.get("SIM_CMD","")'}],
        'remote_command_3':['Exit',{'sim':'glob_vars.get("SIM_CMD","")'}]
    },

    {'if':'glob_vars.get("SHUT","")',
        'exec':'time.sleep(200)'
    },

    {'pre_loop_if':'glob_vars.get("SHUT","") and glob_vars.get("OTI_5511","") and (glob_vars.get("OTI_INT_IPS_V4","") or glob_vars.get("OTI_INT_IPS_V6",""))',
        'pre_loop_remote_command':['conf t',{'sim':'glob_vars.get("SIM_CMD","")'}],
        'pre_loop_remote_command_2':['router bgp 5511',{'sim':'glob_vars.get("SIM_CMD","")'}],
    },
    {'pre_loop_if':'glob_vars.get("SHUT","") and glob_vars.get("OTI_5511","") and glob_vars.get("OTI_INT_IPS_V4","")',
        'loop_glob_var':"OTI_INT_IPS_V4",
            'remote_command':['neighbor ',{'eval':'loop_item'},' shutdown',{'sim':'glob_vars.get("SIM_CMD","")'}],
    },
    {'pre_loop_if':'glob_vars.get("SHUT","") and glob_vars.get("OTI_5511","") and glob_vars.get("OTI_INT_IPS_V6","")',
        'loop_glob_var':"OTI_INT_IPS_V6",
            'remote_command':['neighbor ',{'eval':'loop_item'},' shutdown',{'sim':'glob_vars.get("SIM_CMD","")'}],
    },
    {'pre_loop_if':'glob_vars.get("SHUT","") and glob_vars.get("OTI_5511","") and (glob_vars.get("OTI_INT_IPS_V4","") or glob_vars.get("OTI_INT_IPS_V6",""))',
        'remote_command':['Commit',{'sim':'glob_vars.get("SIM_CMD","")'}],
        'remote_command_2':['Exit',{'sim':'glob_vars.get("SIM_CMD","")'}],
        'remote_command_3':['Exit',{'sim':'glob_vars.get("SIM_CMD","")'}]
    },

    ### NOSHUT -----------------------------------------------------------------
    {'pre_loop_if':'glob_vars.get("NOSHUT","") and glob_vars.get("OTI_5511","") and (glob_vars.get("OTI_INT_IPS_V4","") or glob_vars.get("OTI_INT_IPS_V6",""))',
        'pre_loop_remote_command':['conf t',{'sim':'glob_vars.get("SIM_CMD","")'}],
        'pre_loop_remote_command_2':['router bgp 5511',{'sim':'glob_vars.get("SIM_CMD","")'}],
    },
    {'pre_loop_if':'glob_vars.get("NOSHUT","") and glob_vars.get("OTI_5511","") and glob_vars.get("OTI_INT_IPS_V4","")',
        'loop_glob_var':"OTI_INT_IPS_V4",
            'remote_command':['no neighbor ',{'eval':'loop_item'},' shutdown',{'sim':'glob_vars.get("SIM_CMD","")'}]
    },
    {'pre_loop_if':'glob_vars.get("NOSHUT","") and glob_vars.get("OTI_5511","") and glob_vars.get("OTI_INT_IPS_V6","")',
        'loop_glob_var':"OTI_INT_IPS_V6",
            'remote_command':['no neighbor ',{'eval':'loop_item'},' shutdown',{'sim':'glob_vars.get("SIM_CMD","")'}]
    },
    {'pre_loop_if':'glob_vars.get("NOSHUT","") and glob_vars.get("OTI_5511","") and (glob_vars.get("OTI_INT_IPS_V4","") or glob_vars.get("OTI_INT_IPS_V6",""))',
        'remote_command':['Commit',{'sim':'glob_vars.get("SIM_CMD","")'}],
        'remote_command_2':['Exit',{'sim':'glob_vars.get("SIM_CMD","")'}],
        'remote_command_3':['Exit',{'sim':'glob_vars.get("SIM_CMD","")'}]
    },

    {'if':'glob_vars.get("NOSHUT","")',
        'exec':'time.sleep(200)'
    },

    {'if':'glob_vars.get("NOSHUT","") and glob_vars.get("OTI_5511","")',
        'remote_command':['show bgp summary'],
        'exec':['try: \
            \n  temp_ipv4 = glob_vars.get("last_output","").split("St/PfxRcd")[1].strip().splitlines() \
            \n  previous_line, int_list, error = None, [], None \
            \n  for line in temp_ipv4: \
            \n    if len(line.split())==1: previous_line = line; continue \
            \n    if previous_line: line = previous_line + line; previous_line = None \
            \n    try: \
            \n      if "5511" in line.split()[2] and "." in line.split()[0]: \
            \n          try: dummy = int(line.split()[9]) \
            \n          except: error = True \
            \n    except: pass \
            \n  glob_vars["IPV4_ERROR"] = error \
            \nexcept: pass' \
               ],
    },
    {'if':'glob_vars.get("NOSHUT","") and glob_vars.get("OTI_5511","")',
        'remote_command':['show bgp ipv6 unicast summary'],
        'exec':['try: \
            \n  temp_ipv6 = glob_vars.get("last_output","").split("St/PfxRcd")[1].strip().splitlines() \
            \n  previous_line, int_list, error = None, [], None \
            \n  for line in temp_ipv6: \
            \n    if len(line.split())==1: previous_line = line; continue \
            \n    if previous_line: line = previous_line + line; previous_line = None \
            \n    try: \
            \n      if "5511" in line.split()[2] and "." in line.split()[0]: \
            \n          try: dummy = int(line.split()[9]) \
            \n          except: error = True \
            \n    except: pass \
            \n  glob_vars["IPV6_ERROR"] = error \
            \nexcept: pass' \
               ],
    },

    {'if':'glob_vars.get("IPV4_ERROR","") or glob_vars.get("IPV6_ERROR","")',
         'exec':'print("WARNING: Possible problem in internal BGP! Please manually check status of iBGP.")',
         'exec_2':'glob_vars["CONTINUE_AFTER_IBGP_PROBLEM"] = raw_input("Do you want to proceed with eBGP UNSHUT? (Y/N) [Enter]:")',
    },
    {'if':'(glob_vars.get("IPV4_ERROR","") or glob_vars.get("IPV6_ERROR","")) and glob_vars.get("CONTINUE_AFTER_IBGP_PROBLEM","").upper() != "Y"',
         'exec':'print("File %s created." % logfilename)',
         'exec_2':'try: send_me_email(logfilename.replace("\\\\","/").split("/")[-1], file_name=logfilename)\nexcept: pass',
         'exec_3':'sys.exit(0)'
    },


    {'pre_loop_if':'glob_vars.get("NOSHUT","") and glob_vars.get("OTI_5511","") and (glob_vars.get("OTI_EXT_IPS_V4","") or glob_vars.get("OTI_EXT_IPS_V6",""))',
        'pre_loop_remote_command':['conf t',{'sim':'glob_vars.get("SIM_CMD","")'}],
        'pre_loop_remote_command_2':['router bgp 5511',{'sim':'glob_vars.get("SIM_CMD","")'}],
    },
    {'pre_loop_if':'glob_vars.get("NOSHUT","") and glob_vars.get("OTI_5511","") and glob_vars.get("OTI_EXT_IPS_V4","")',
        'loop_glob_var':"OTI_EXT_IPS_V4",
            'remote_command':['no neighbor ',{'eval':'loop_item'},' shutdown',{'sim':'glob_vars.get("SIM_CMD","")'}]
    },
    {'pre_loop_if':'glob_vars.get("NOSHUT","") and glob_vars.get("OTI_5511","") and glob_vars.get("OTI_EXT_IPS_V6","")',
        'loop_glob_var':"OTI_EXT_IPS_V6",
            'remote_command':['no neighbor ',{'eval':'loop_item'},' shutdown',{'sim':'glob_vars.get("SIM_CMD","")'}]
    },
    {'pre_loop_if':'glob_vars.get("NOSHUT","") and glob_vars.get("OTI_5511","") and (glob_vars.get("OTI_EXT_IPS_V4","") or glob_vars.get("OTI_EXT_IPS_V6",""))',
        'remote_command':['Commit',{'sim':'glob_vars.get("SIM_CMD","")'}],
        'remote_command_2':['Exit',{'sim':'glob_vars.get("SIM_CMD","")'}],
        'remote_command_3':['Exit',{'sim':'glob_vars.get("SIM_CMD","")'}]
    },

    {'if':'glob_vars.get("NOSHUT","")',
        'exec':'time.sleep(120)'
    },

    {'if':'glob_vars.get("NOSHUT","") and glob_vars.get("OTI_5511","")',
        'remote_command':['conf t',{'sim':'glob_vars.get("SIM_CMD","")'}],
        'remote_command_2':['router isis PAII',{'sim':'glob_vars.get("SIM_CMD","")'}],
        'remote_command_3':['no set-overload-bit',{'sim':'glob_vars.get("SIM_CMD","")'}],
        'remote_command_4':['Commit',{'sim':'glob_vars.get("SIM_CMD","")'}],
        'remote_command_5':['Exit',{'sim':'glob_vars.get("SIM_CMD","")'}],
        'remote_command_6':['Exit',{'sim':'glob_vars.get("SIM_CMD","")'}]
    },

    {'if':'glob_vars.get("SHUT","")',
        "eval":"return_bgp_data_json()"
    },
]

CMD_JUNOS = []

CMD_VRP = []

CMD_LINUX = []

CMD_LOCAL = [
     {'eval':'glob_vars.get("SIM_CMD","")'},
     {"local_command":['hostname', {"output_variable":"hostname"},{'sim':'glob_vars.get("SIM_CMD","")'}]
     },
]

#
# ################################################################################
bgp_data = collections.OrderedDict()

### Start of BASIC STRUCTURES OF JSON
bgp_json_txt_template = '''
 {
      "OTI_EXT_IPS_V4": [],
      "OTI_EXT_IPS_V6": [],
      "OTI_INT_IPS_V4": [],
      "OTI_INT_IPS_V6": []
 }
'''
### End of BASIC STRUCTURES OF JSON

### BASIC BGP_DATA OBJECT with 1 neihbor and 1 vfr
bgp_data = json.loads(bgp_json_txt_template, object_pairs_hook = collections.OrderedDict)

###############################################################################
#
# Function and Class
#
###############################################################################

### UNI-tools ###
def return_indexed_list(data_list = None):
    if data_list and isinstance(data_list, (list,tuple)):
        return zip(range(len(data_list)),data_list)
    return []


def get_first_row_after(text = None, split_text = None, delete_text = None, split_text_index = None):
    output = str()
    if text:
        try:
            if split_text_index == None: output = text.strip().split(split_text)[1].split()[0].strip()
            else: output = text.strip().split(split_text)[int(split_text_index)+1].split()[0].strip()
            if delete_text: output = output.replace(delete_text,'')
        except: pass
    return output


def get_first_row_before(text = None, split_text = None, delete_text = None, split_text_index = None):
    output = str()
    if text:
        try:
            if split_text_index == None: output = text.strip().split(split_text)[0].split()[-1].strip()
            else: output = text.strip().split(split_text)[int(split_text_index)].split()[-1].strip()
            if delete_text: output = output.replace(delete_text,'')
        except: pass
    return output

def does_text_contains_string(text = None, contains_string = None):
    output = str()
    if text and contains_text:
        if contains_string in text: output = contains_string
    return output

def return_bgp_data_json():
    return json.dumps(bgp_data, indent=2)


def read_bgp_data_json_from_logfile(filename = None, printall = None):
    bgp_data_loaded, text = None, None
    with open(filename,"r") as fp:
        text = fp.read()
    if text:
        try: bgp_data_json_text = text.split('EVAL_COMMAND: return_bgp_data_json()')[1]
        except: bgp_data_json_text = str()
        if bgp_data_json_text:
            try:
                bgp_data_loaded = json.loads(bgp_data_json_text, object_pairs_hook = collections.OrderedDict)
            except: pass
            #print("LOADED_BGP_DATA: ",bgp_data_loaded)
            if printall: print("\nLOADED JSON BGP_DATA: ")
            if printall: print(json.dumps(bgp_data_loaded, indent=2))
    return bgp_data_loaded


def detect_router_by_ssh(device, debug = False):
    # detect device prompt
    def ssh_detect_prompt(chan, debug = False):
        output, buff, last_line, last_but_one_line = str(), str(), 'dummyline1', 'dummyline2'
        chan.send('\t \n\n')
        while not (last_line and last_but_one_line and last_line == last_but_one_line):
            if debug: print('FIND_PROMPT:',last_but_one_line,last_line)
            buff = chan.recv(9999)
            output += buff.decode("utf-8").replace('\r','').replace('\x07','').replace('\x08','').\
                      replace('\x1b[K','').replace('\n{master}\n','')
            if '--More--' or '---(more' in buff.strip(): chan.send('\x20')
            if debug: print('BUFFER:' + buff)
            try: last_line = output.splitlines()[-1].strip().replace('\x20','')
            except: last_line = 'dummyline1'
            try: last_but_one_line = output.splitlines()[-2].strip().replace('\x20','')
            except: last_but_one_line = 'dummyline2'
        prompt = output.splitlines()[-1].strip()
        if debug: print('DETECTED PROMPT: \'' + prompt + '\'')
        return prompt

    # bullet-proof read-until function , even in case of ---more---
    def ssh_read_until_prompt_bulletproof(chan,command,prompts,debug = False):
        output, buff, last_line, exit_loop = str(), str(), 'dummyline1', False
        # avoid of echoing commands on ios-xe by timeout 1 second
        flush_buffer = chan.recv(9999)
        del flush_buffer
        chan.send(command)
        time.sleep(0.3)
        output, exit_loop = '', False
        while not exit_loop:
            if debug: print('LAST_LINE:',prompts,last_line)
            buff = chan.recv(9999)
            output += buff.decode("utf-8").replace('\r','').replace('\x07','').replace('\x08','').\
                      replace('\x1b[K','').replace('\n{master}\n','')
            if '--More--' or '---(more' in buff.strip(): chan.send('\x20')
            if debug: print('BUFFER:' + buff)
            try: last_line = output.splitlines()[-1].strip()
            except: last_line = str()
            for actual_prompt in prompts:
                if output.endswith(actual_prompt) or \
                    last_line and last_line.endswith(actual_prompt): exit_loop = True
        return output
    # Detect function start
    router_os = str()
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try: DEVICE_HOST = device.split(':')[0]
    except: DEVICE_HOST = str()
    try: DEVICE_PORT = device.split(':')[1]
    except: DEVICE_PORT = '22'

    try:
        #connect(self, hostname, port=22, username=None, password=None, pkey=None, key_filename=None, timeout=None, allow_agent=True, look_for_keys=True, compress=False)
        client.connect(DEVICE_HOST, port=int(DEVICE_PORT), username=USERNAME, password=PASSWORD)
        chan = client.invoke_shell()
        chan.settimeout(TIMEOUT)
        # prevent --More-- in log banner (space=page, enter=1line,tab=esc)
        # \n\n get prompt as last line
        prompt = ssh_detect_prompt(chan, debug=False)

        #test if this is HUAWEI VRP
        if prompt and not router_os:
            command = 'display version | include (Huawei)\n'
            output = ssh_read_until_prompt_bulletproof(chan, command, [prompt], debug=debug)
            if 'Huawei Versatile Routing Platform Software' in output: router_os = 'vrp'

        #test if this is CISCO IOS-XR, IOS-XE or JUNOS
        if prompt and not router_os:
            command = 'show version\n'
            output = ssh_read_until_prompt_bulletproof(chan, command, [prompt], debug=debug)
            if 'iosxr-' in output or 'Cisco IOS XR Software' in output: router_os = 'ios-xr'
            elif 'Cisco IOS-XE software' in output: router_os = 'ios-xe'
            elif 'JUNOS OS' in output: router_os = 'junos'

        if prompt and not router_os:
            command = 'uname -a\n'
            output = ssh_read_until_prompt_bulletproof(chan, command, [prompt], debug=debug)
            if 'LINUX' in output.upper(): router_os = 'linux'

        if not router_os:
            print(bcolors.MAGENTA + "\nCannot find recognizable OS in %s" % (output) + bcolors.ENDC)

    except (socket.timeout, paramiko.AuthenticationException) as e:
        print(bcolors.MAGENTA + " ... Connection closed: %s " % (e) + bcolors.ENDC )
        sys.exit()
    finally:
        client.close()

    netmiko_os = str()
    if router_os == 'ios-xe': netmiko_os = 'cisco_ios'
    if router_os == 'ios-xr': netmiko_os = 'cisco_xr'
    if router_os == 'junos': netmiko_os = 'juniper'
    if router_os == 'linux': netmiko_os = 'linux'
    if router_os == 'vrp': netmiko_os = 'huawei'
    return netmiko_os
    #return router_os, prompt


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
            if '172.25.4' in json_raw_data['OTI_ALL'][router]['LSRID']:
                oti_routers.append(router)
    return oti_routers


# def parse_json_file_and_get_oti_routers_list():
#     oti_routers = []
#     json_filename = '/home/dpenha/perl_shop/NIS9TABLE_BLDR/node_list.json'
#     with io.open(json_filename) as json_file: json_raw_data = json.load(json_file)
#     if json_raw_data:
#         for router in json_raw_data['results']:
#            if router['namings']['type']=='OTI':
#                oti_routers.append(router['name'])
#     return oti_routers


def run_remote_and_local_commands(CMD, logfilename = None, printall = None, \
    printcmdtologfile = None, debug = None):
    ### RUN_COMMAND - REMOTE or LOCAL ------------------------------------------
    def run_command(ssh_connection,cmd_line_items,loop_item=None,run_remote = None,\
        logfilename = logfilename,printall = printall, printcmdtologfile = printcmdtologfile):
        global glob_vars
        cli_line, name_of_output_variable, simulate_command, sim_text = str(), None, None, str()
        ### LIST,TUPPLE,STRINS ARE REMOTE REMOTE/LOCAL DEVICE COMMANDS
        if isinstance(cmd_line_items, (six.string_types,list,tuple)):
            if isinstance(cmd_line_items, six.string_types): cli_line = cmd_line_items
            elif isinstance(cmd_line_items, (list,tuple)):
                for cli_item in cmd_line_items:
                    if isinstance(cli_item, dict):
                        if cli_item.get('output_variable',''):
                            name_of_output_variable = cli_item.get('output_variable','')
                        elif cli_item.get('eval',''):
                            cli_line += str(eval(cli_item.get('eval','')))
                        elif cli_item.get('sim',''):
                            simulate_command = True if str(eval(cli_item.get('sim',''))).upper()=='ON' else None
                            if simulate_command: sim_text = '(SIM)'
                    else: cli_line += str(cli_item)
            if run_remote:
                print(bcolors.GREEN + "REMOTE_COMMAND%s: %s" % (sim_text,cli_line) + bcolors.ENDC )
                ### NETMIKO
                if simulate_command: last_output = str()
                else: last_output = ssh_connection.send_command(cli_line)

                ### PARAMIKO
                #last_output, new_prompt = ssh_send_command_and_read_output(ssh_connection,DEVICE_PROMPTS,cli_line)
                #if new_prompt: DEVICE_PROMPTS.append(new_prompt)
            else:
                print(bcolors.CYAN + "LOCAL_COMMAND%s: %s" % (sim_text,cli_line) + bcolors.ENDC )
                ### LOCAL COMMAND - SUBPROCESS CALL
                if simulate_command: last_output = str()
                else:
                    try:
                        last_output = subprocess.check_output(str(cli_line),shell=True)
                    except: last_output = str()

            ### FILTER LAST_OUTPUT
            if isinstance(last_output, six.string_types):
                last_output = last_output.decode("utf-8").replace('\x07','').\
                    replace('\x08','').replace('\x0d','').replace('\x1b','').replace('\x1d','')

                ### NETMIKO-BUG (https://github.com/ktbyers/netmiko/issues/1200)
                if len(str(cli_line))>80 and run_remote:
                    first_bugged_line = last_output.splitlines()[0]
                    #print('NOISE:',first_bugged_line)
                    last_output = last_output.replace(first_bugged_line+'\n','')
                    if(last_output.strip() == first_bugged_line): last_output = str()

            if printall: print(bcolors.GREY + "%s" % (last_output) + bcolors.ENDC )
            if printcmdtologfile:
                if run_remote: fp.write('REMOTE_COMMAND: ' + cli_line + '\n'+last_output+'\n')
                else: fp.write('LOCAL_COMMAND: ' + cli_line + '\n'+last_output+'\n')
            else: fp.write(last_output)
            ### Result will be allways string, so rstrip() could be done
            glob_vars['last_output'] = last_output.rstrip()
            if name_of_output_variable:
                glob_vars[name_of_output_variable] = last_output.rstrip()
        return None
    ### EVAL_COMMAND -----------------------------------------------------------
    def eval_command(ssh_connection,cmd_line_items,loop_item=None,\
        logfilename = logfilename,printall = printall, printcmdtologfile = printcmdtologfile):
        global glob_vars
        cli_line, name_of_output_variable = str(), None
        ### LIST,TUPPLE,STRINS ARE REMOTE REMOTE/LOCAL DEVICE COMMANDS
        if isinstance(cmd_line_items, (six.string_types,list,tuple)):
            if isinstance(cmd_line_items, six.string_types): cli_line = cmd_line_items
            elif isinstance(cmd_line_items, (list,tuple)):
                for cli_item in cmd_line_items:
                    if isinstance(cli_item, dict):
                        if cli_item.get('output_variable',''):
                            name_of_output_variable = cli_item.get('output_variable','')
                        elif cli_item.get('eval',''):
                            cli_line += str(eval(cli_item.get('eval','')))
                    else: cli_line += str(cli_item)
            print(bcolors.CYAN + "EVAL_COMMAND: %s" % (cli_line) + bcolors.ENDC )
            try: local_output = eval(cli_line)
            except: local_output = str()
            print(bcolors.GREY + str(local_output) + bcolors.ENDC )
            if printcmdtologfile: fp.write('EVAL_COMMAND: ' + cli_line + '\n' + str(local_output) + '\n')
            if name_of_output_variable:
                glob_vars[name_of_output_variable] = local_output
            glob_vars['last_output'] = local_output
        return None
    ### EXEC_COMMAND -----------------------------------------------------------
    def exec_command(ssh_connection,cmd_line_items,loop_item=None,\
        logfilename = logfilename,printall = printall, printcmdtologfile = printcmdtologfile):
        global glob_vars, global_env
        cli_line, name_of_output_variable = str(), None
        ### LIST,TUPPLE,STRINS ARE REMOTE REMOTE/LOCAL DEVICE COMMANDS
        if isinstance(cmd_line_items, (six.string_types,list,tuple)):
            if isinstance(cmd_line_items, six.string_types): cli_line = cmd_line_items
            elif isinstance(cmd_line_items, (list,tuple)):
                for cli_item in cmd_line_items:
                    if isinstance(cli_item, dict):
                        if cli_item.get('output_variable',''):
                            name_of_output_variable = cli_item.get('output_variable','')
                        elif cli_item.get('eval',''):
                            cli_line += str(eval(cli_item.get('eval','')))
                    else: cli_line += str(cli_item)
            print(bcolors.CYAN + "EXEC_COMMAND: %s" % (cli_line) + bcolors.ENDC )
            ### EXEC CODE for PYTHON>v2.7.9
            # code_object = compile(cli_line, 'sumstring', 'exec')
            # local_env = {}
            # for item in eval('dir()'): local_env[item] = eval(item)
            # exec(code_object,global_env,local_env)
            ### EXEC CODE WORKAROUND for OLD PYTHON v2.7.5
            edict = {}; eval(compile(cli_line, '<string>', 'exec'), globals(), edict)
            if printcmdtologfile: fp.write('EXEC_COMMAND: ' + cli_line + '\n')
        return None
    ### IF_FUNCTION (simple eval) ----------------------------------------------
    def if_function(ssh_connection,cmd_line_items,loop_item=None,\
        logfilename = logfilename,printall = printall, printcmdtologfile = printcmdtologfile):
        global glob_vars
        cli_line, name_of_output_variable, success = str(), None, False
        if isinstance(cmd_line_items, (int,float,six.string_types)):
            condition_eval_text = cmd_line_items
            ret_value = eval(str(condition_eval_text))
            if ret_value: success = True
            else: success = False
            print(bcolors.CYAN + "IF_CONDITION(%s)" % (condition_eval_text) + " --> " +\
                str(success).upper() + bcolors.ENDC )
            if printcmdtologfile: fp.write('IF_CONDITION(%s): ' % (condition_eval_text) +\
                 " --> "+ str(success).upper() + '\n')
        return success
    ### MAIN_DO_STEP -----------------------------------------------------------
    def main_do_step(cmd_line_items,loop_item=None):
        command_range=10
        global glob_vars
        condition_result = True
        if isinstance(cmd_line_items, (six.string_types,list,tuple)):
            if run_command(ssh_connection,cmd_line_items,loop_item,run_remote = True): return None
        if isinstance(cmd_line_items, (dict)):
            if cmd_line_items.get('pre_if_remote_command','') and remote_connect:
                if run_command(ssh_connection,cmd_line_items.get('pre_if_remote_command',''),loop_item,run_remote = True): return None
            if cmd_line_items.get('pre_if_local_command',''):
                if run_command(ssh_connection,cmd_line_items.get('pre_if_local_command',''),loop_item): return None
            if cmd_line_items.get('pre_if_exec',''):
                if exec_command(ssh_connection,cmd_line_items.get('pre_if_exec',''),loop_item): return None
            if cmd_line_items.get('pre_if_eval',''):
                if eval_command(ssh_connection,cmd_line_items.get('pre_if_eval',''),loop_item): return None
            if cmd_line_items.get('if',''):
                condition_result = if_function(ssh_connection,cmd_line_items.get('if',''),loop_item)
            if condition_result:
                if cmd_line_items.get('remote_command','') and remote_connect:
                    if run_command(ssh_connection,cmd_line_items.get('remote_command',''),loop_item,run_remote = True): return None
                for i in range(command_range):
                    if cmd_line_items.get('remote_command_'+str(i),'') and remote_connect:
                        if run_command(ssh_connection,cmd_line_items.get('remote_command'+str(i),''),loop_item,run_remote = True): return None
                if cmd_line_items.get('local_command',''):
                    if run_command(ssh_connection,cmd_line_items.get('local_command',''),loop_item): return None
                for i in range(command_range):
                    if cmd_line_items.get('local_command_'+str(i),''):
                        if run_command(ssh_connection,cmd_line_items.get('local_command_'+str(i),''),loop_item): return None
                if cmd_line_items.get('exec',''):
                    if exec_command(ssh_connection,cmd_line_items.get('exec',''),loop_item): return None
                for i in range(command_range):
                    if cmd_line_items.get('exec_'+str(i),''):
                        if exec_command(ssh_connection,cmd_line_items.get('exec_'+str(i),''),loop_item): return None
                if cmd_line_items.get('eval',''):
                    if eval_command(ssh_connection,cmd_line_items.get('eval',''),loop_item): return None
                for i in range(command_range):
                    if cmd_line_items.get('eval_'+str(i),''):
                        if eval_command(ssh_connection,cmd_line_items.get('eval_'+str(i),''),loop_item): return None
        return True

    ### RUN_REMOTE_AND_LOCAL_COMMANDS START ====================================
    global remote_connect, glob_vars
    ssh_connection, output= None, None
    command_range = 10
    try:
        if remote_connect:
            ssh_connection = netmiko.ConnectHandler(device_type = router_type, \
                ip = DEVICE_HOST, port = int(DEVICE_PORT), \
                username = USERNAME, password = PASSWORD)
        # ### paramiko
        #           global DEVICE_PROMPTS
        #           client = paramiko.SSHClient()
        #           client.load_system_host_keys()
        #           client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        #           client.connect(DEVICE_HOST, port=int(DEVICE_PORT), \
        #                          username=USERNAME, password=PASSWORD)
        #           ssh_connection = client.invoke_shell()
        #           ssh_connection.settimeout(TIMEOUT)
        #           output, forget_it = ssh_send_command_and_read_output(ssh_connection,DEVICE_PROMPTS,TERM_LEN_0)
        #           output2, forget_it = ssh_send_command_and_read_output(ssh_connection,DEVICE_PROMPTS,"")
        #           output += output2

        ### WORK REMOTE or LOCAL ===============================================
        if not logfilename:
            if 'WIN32' in sys.platform.upper(): logfilename = 'nul'
            else: logfilename = '/dev/null'
        with open(logfilename,"w") as fp:
            if output and not printcmdtologfile: fp.write(output)
            for cmd_line_items in CMD:
                if debug: print('----> ',cmd_line_items)
                pre_condition_result = True
                if isinstance(cmd_line_items, dict) and cmd_line_items.get('pre_loop_if',''):
                    pre_condition_result = if_function(ssh_connection, \
                        cmd_line_items.get('pre_loop_if',''))
                if pre_condition_result:
                    if isinstance(cmd_line_items, (dict)):
                        if cmd_line_items.get('pre_loop_remote_command','') and remote_connect:
                            if run_command(ssh_connection,cmd_line_items.get('pre_loop_remote_command',''),run_remote = True): return None
                    for ii in range(command_range):
                        if cmd_line_items.get('pre_loop_remote_command_'+str(ii),'') and remote_connect:
                            if run_command(ssh_connection,cmd_line_items.get('pre_loop_remote_command'+str(ii),''),run_remote = True): return None
                        if cmd_line_items.get('pre_loop_local_command',''):
                            if run_command(ssh_connection,cmd_line_items.get('pre_loop_local_command',''),loop_item): return None
                        if cmd_line_items.get('pre_loop_exec',''):
                            if exec_command(ssh_connection,cmd_line_items.get('pre_loop_exec',''),loop_item): return None
                        if cmd_line_items.get('pre_loop_eval',''):
                            if eval_command(ssh_connection,cmd_line_items.get('pre_if_eval',''),loop_item): return None
                    if isinstance(cmd_line_items, dict) and cmd_line_items.get('loop_glob_var',''):
                        for loop_item in glob_vars.get(cmd_line_items.get('loop_glob_var',''),''):
                            main_do_step(cmd_line_items,loop_item)
                    elif isinstance(cmd_line_items, dict) and cmd_line_items.get('loop',''):
                        for loop_item in eval(cmd_line_items.get('loop','')):
                            main_do_step(cmd_line_items,loop_item)
                    else: main_do_step(cmd_line_items)
                ### DIRECT REMOTE CALL WITHOUT PRE_IF --------------------------
                elif isinstance(cmd_line_items, (list,tuple,six.string_types)):
                    main_do_step(cmd_line_items)
    except () as e:
        print(bcolors.FAIL + " ... EXCEPTION: (%s)" % (e) + bcolors.ENDC )
        sys.exit()
    finally:
        if remote_connect and ssh_connection: ssh_connection.disconnect()
    # ### paramiko
    #        client.close()

    return None


def get_version_from_file_last_modification_date(path_to_file = str(os.path.abspath(__file__))):
    file_time = None
    if 'WIN32' in sys.platform.upper():
        file_time = os.path.getmtime(path_to_file)
    else:
        stat = os.stat(path_to_file)
        file_time = stat.st_mtime
    struct_time = time.gmtime(file_time)
    return str(struct_time.tm_year)[2:] + '.' + str(struct_time.tm_mon) + '.' + str(struct_time.tm_mday)

def append_variable_to_bashrc(variable_name=None,variable_value=None):
    forget_it = subprocess.check_output('echo export %s=%s >> ~/.bashrc'%(variable_name,variable_value), shell=True)

def send_me_email(subject='testmail', file_name='/dev/null'):
    if not 'WIN32' in sys.platform.upper():
        my_account = subprocess.check_output('whoami', shell=True)
        my_finger_line = subprocess.check_output('finger | grep "%s"'%(my_account.strip()), shell=True)
        try:
            my_name = my_finger_line.splitlines()[0].split()[1]
            my_surname = my_finger_line.splitlines()[0].split()[2]
            if EMAIL_ADDRESS: my_email_address = EMAIL_ADDRESS
            else: my_email_address = '%s.%s@orange.com' % (my_name, my_surname)
            mail_command = 'echo | mutt -s "%s" -a %s -- %s' % (subject,file_name,my_email_address)
            #mail_command = 'uuencode %s %s | mail -s "%s" %s' % (file_name,file_name,subject,my_email_address)
            forget_it = subprocess.check_output(mail_command, shell=True)
            print(' ==> Email "%s" sent to %s.'%(subject,my_email_address))
        except: pass


def generate_file_name(prefix = None, suffix = None , directory = None):
    filenamewithpath = None
    if not directory:
        try:    DIR         = os.environ['HOME']
        except: DIR         = str(os.path.dirname(os.path.abspath(__file__)))
    else: DIR = str(directory)
    if DIR: LOGDIR      = os.path.join(WORKDIR,'logs')
    if not os.path.exists(LOGDIR): os.makedirs(LOGDIR)
    if os.path.exists(LOGDIR):
        if not prefix: filename_prefix = os.path.join(LOGDIR,'device')
        else: filename_prefix = prefix
        if not suffix: filename_suffix = 'log'
        else: filename_suffix = suffix
        now = datetime.datetime.now()
        filename = "%s-%.2i%.2i%i-%.2i%.2i%.2i-%s-%s-%s" % \
            (filename_prefix,now.year,now.month,now.day,now.hour,now.minute,\
            now.second,script_name.replace('.py','').replace('./','').\
            replace(':','_').replace('.','_').replace('\\','/')\
            .split('/')[-1],USERNAME,filename_suffix)
        filenamewithpath = str(os.path.join(LOGDIR,filename))
    return filenamewithpath

##############################################################################
#
# BEGIN MAIN
#
##############################################################################

if __name__ != "__main__": sys.exit(0)

VERSION = get_version_from_file_last_modification_date()
glob_vars = {}

# global_env = {}
# for item in eval('dir()'): global_env[item] = eval(item)

global_env = globals()

######## Parse program arguments #########
parser = argparse.ArgumentParser(
                description = "Script v.%s" % (VERSION),
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
parser.add_argument("--readlog",
                    action = "store", dest = 'readlog', default = None,
                    help = "name of the logfile to read json.")
parser.add_argument("--readlognew",
                    action = "store", dest = 'readlognew', default = None,
                    help = "name of the logfile to read json.")
parser.add_argument("--emailaddr",
                    action = "store", dest = 'emailaddr', default = '',
                    help = "insert your email address once if is different than name.surname@orange.com,\
                    it will do NEWR_EMAIL variable record in your bashrc file and \
                    you do not need to insert it any more.")
# parser.add_argument("--vpnlist",
#                     action = "store", dest = 'vpnlist', default = str(),
#                     help = "'vpn' or ['list of vpns',...] to compare")
parser.add_argument("--printall",action = "store_true", default = False,
                    help = "print all lines, changes will be coloured")
# parser.add_argument("--difffile",
#                     action = 'store_true', dest = "diff_file", default = False,
#                     help = "do file-diff logfile (name will be generated and printed)")
parser.add_argument("--alloti",
                    action = 'store_true', dest = "alloti", default = None,
                    help = "do action on all oti routers")
parser.add_argument("--shut",
                    action = 'store_true', dest = "shut", default = None,
                    help = "switch-off bgp traffic")
parser.add_argument("--noshut",
                    action = 'store_true', dest = "noshut", default = None,
                    help = "switch-on bgp traffic")
parser.add_argument("--sim",
                    action = 'store_true', dest = "sim", default = None,
                    help = "simulate critical command runs")
args = parser.parse_args()

if args.nocolors or 'WIN32' in sys.platform.upper(): bcolors = nocolors

COL_DELETED = bcolors.RED
COL_ADDED   = bcolors.GREEN
COL_DIFFDEL = bcolors.BLUE
COL_DIFFADD = bcolors.YELLOW
COL_EQUAL   = bcolors.GREY
COL_PROBLEM = bcolors.RED

if args.emailaddr:
    append_variable_to_bashrc(variable_name='NEWR_EMAIL',variable_value=args.emailaddr)
    EMAIL_ADDRESS = args.emailaddr

if args.alloti: device_list = parse_json_file_and_get_oti_routers_list()
else: device_list = [args.device]

device_list = [args.device]

if args.shut and args.noshut:
    print(bcolors.MAGENTA + " ... BGP traffic-on or traffic-off is allowed, not both!" + bcolors.ENDC )
    sys.exit(0)

if args.shut: glob_vars["SHUT"] = True
if args.noshut: glob_vars["NOSHUT"] = True

if args.sim: glob_vars["SIM_CMD"] = 'ON';

if args.device == str():
    remote_connect = None
    local_hostname = str(subprocess.check_output('hostname',shell=True)).strip().replace('\\','').replace('/','')
    device_list = [local_hostname]


if args.readlog:
    bgp_data = read_bgp_data_json_from_logfile(args.readlog)
    if not bgp_data:
        print(bcolors.MAGENTA + " ... Please insert shut session log! (Inserted log seems to be noshut log.)" + bcolors.ENDC )
        sys.exit(0)

if remote_connect:
    ####### Set USERNAME if needed
    if args.username: USERNAME = args.username
    if not USERNAME:
        print(bcolors.MAGENTA + " ... Please insert your username by cmdline switch \
            --user username !" + bcolors.ENDC )
        sys.exit(0)

    # SSH (default)
    if not PASSWORD:
        if args.password: PASSWORD = args.password
        else:             PASSWORD = getpass.getpass("TACACS password: ")

logfilename, router_type = None, None
if not args.readlognew:
    for device in device_list:
        if device:
            router_prompt = None
            try: DEVICE_HOST = device.split(':')[0]
            except: DEVICE_HOST = str()
            try: DEVICE_PORT = device.split(':')[1]
            except: DEVICE_PORT = '22'
            print('DEVICE %s (host=%s, port=%s) START.........................'\
                %(device,DEVICE_HOST, DEVICE_PORT))
            if remote_connect:
                ####### Figure out type of router OS
                if not args.router_type:
                    #router_type = netmiko_autodetect(device)
                    router_type = detect_router_by_ssh(device)
                    if not router_type in KNOWN_OS_TYPES:
                        print('%sUNSUPPORTED DEVICE TYPE: %s , BREAK!%s' % \
                            (bcolors.MAGENTA,router_type, bcolors.ENDC))
                        continue
                    else: print('DETECTED DEVICE_TYPE: %s' % (router_type))
                else:
                    router_type = args.router_type
                    print('FORCED DEVICE_TYPE: ' + router_type)

            ######## Create logs directory if not existing  #########
            if not os.path.exists(LOGDIR): os.makedirs(LOGDIR)
            logfilename = generate_file_name(prefix = device, suffix = 'log')
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
                else: CMD = CMD_LOCAL

            run_remote_and_local_commands(CMD, logfilename, printall = True , \
                printcmdtologfile = True)

            if logfilename and os.path.exists(logfilename):
                print('%s file created.' % (logfilename))
                try: send_me_email(subject = logfilename.replace('\\','/').\
                         split('/')[-1], file_name = logfilename)
                except: pass
            print('\nDEVICE %s DONE.'%(device))

print('\nEND [script runtime = %d sec].'%(time.time() - START_EPOCH))


