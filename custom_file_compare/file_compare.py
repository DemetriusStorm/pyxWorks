#!/usr/bin/python
import io
import os
import sys
import difflib

class bcolors:
    DEFAULT = '\033[99m'
    WHITE = '\033[97m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    BLUE = '\033[94m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    RED='\033[91m'
    GREY = '\033[90m'
    ENDC='\033[0m'
    BOLD='\033[1m'
    UNDERLINE='\033[4m'


### GET_STRING_FILE_DIFFERENCE_STRING ==========================================
def get_string_file_difference_string(old_unknown_type,new_unknown_type,print_equals=None,debug=None):
    '''
    The head of line is
    '-' for missing line,
    '+' for added line and
    '!' for line that is different.
    RED for something going Down or something missing.
    ORANGE for something going Up or something new (not present in pre-check)
    '''
    print_string = "\n('-' missing, '+' added, '!' different, '=' equal):\n"

    new_lines = new_unknown_type if type(new_unknown_type) == list else new_unknown_type.splitlines()
    old_lines = old_unknown_type if type(old_unknown_type) == list else old_unknown_type.splitlines()

    enum_new_lines = enumerate(new_lines)
    enum_old_lines = enumerate(old_lines)

    if old_lines and new_lines:
        new_first_words = [line.split(' ')[0] for line in new_lines]
        old_first_words = [line.split(' ')[0] for line in old_lines]
        if debug: print('11111 :',old_first_words,new_first_words)

        lost_lines = [item for item in old_first_words if item not in new_first_words]
        added_lines = [item for item in new_first_words if item not in old_first_words]
        if debug: print('----- :',lost_lines)
        if debug: print('+++++ :',added_lines)

        try:    j, old_line = next(enum_old_lines)
        except: j, old_line = -1, str()

        try:    i, line = next(enum_new_lines)
        except: i, line = -1, str()

        while i >= 0 and j>=0:
            go, diff_sign, color, print_line = 'void', ' ', bcolors.WHITE, str()

            # void new lines
            if not line.strip():
                while len(line.strip()) == 0 and i >= 0:
                    try:    i, line = next(enum_new_lines)
                    except: i, line = -1, str()

            # void old lines
            if not old_line.strip():
                while len(old_line.strip()) == 0 and j >= 0:
                    try:    j, old_line = next(enum_old_lines)
                    except: j, old_line = -1, str()

            # auxiliary first words
            try: first_line_word = line.strip().split()[0]
            except: first_line_word = str()
            try: first_old_line_word = old_line.strip().split()[0]
            except: first_old_line_word = str()

            # if again - lines are the same
            if line.strip() == old_line.strip():
                if print_equals: go, diff_sign, color, print_line= 'line_equals', '=', bcolors.WHITE, line
                else:            go, diff_sign, color, print_line= 'line_equals', '=', bcolors.WHITE, str()

                # In case of DOWN/FAIL write also equal values !!!
                if 'DOWN' in line.upper() or 'FAIL' in line.upper(): color, print_line = bcolors.RED, line

                try:    j, old_line = next(enum_old_lines)
                except: j, old_line = -1, str()

                try:    i, line = next(enum_new_lines)
                except: i, line = -1, str()

            # changed line
            elif first_line_word == first_old_line_word and not new_first_words[i] in added_lines:
                go, diff_sign, color, print_line = 'changed_line', '!', bcolors.YELLOW, line

                if 'DOWN' in line.upper() or 'FAIL' in line.upper(): color = bcolors.RED

                try:    j, old_line = next(enum_old_lines)
                except: j, old_line = -1, str()

                try:    i, line = next(enum_new_lines)
                except: i, line = -1, str()

            # added line
            elif first_line_word in added_lines:
                go, diff_sign, color, print_line = 'added_line','+',  bcolors.YELLOW, line

                if 'DOWN' in line.upper() or 'FAIL' in line.upper(): color = bcolors.RED

                try:    i, line = next(enum_new_lines)
                except: i, line = -1, str()

            # lost line
            elif not first_line_word in lost_lines and old_line.strip():
                go, diff_sign, color, print_line = 'lost_line', '-',  bcolors.YELLOW, old_line

                try:    j, old_line = next(enum_old_lines)
                except: j, old_line = -1, str()
            else:
                # added line on the end
                if first_line_word and not first_old_line_word:
                    go, diff_sign, color, print_line = 'added_line_on_end','+',  bcolors.YELLOW, line

                    if 'DOWN' in line.upper() or 'FAIL' in line.upper(): color = bcolors.RED

                    try:    i, line = next(enum_new_lines)
                    except: i, line = -1, str()
                # lost line on the end
                elif not first_line_word and first_old_line_word:
                    go, diff_sign, color, print_line = 'lost_line_on_end', '-',  bcolors.YELLOW, old_line

                    try:    j, old_line = next(enum_old_lines)
                    except: j, old_line = -1, str()
                else: print('!!! PARSING PROBLEM: ',j,old_line,' -- vs -- ',i,line,' !!!')

            if debug: print('####### %s  %s  %s  %s\n'%(go,color,diff_sign,print_line))

            if print_line: print_string=print_string+'%s  %s  %s\n'%(color,diff_sign,print_line)

    return print_string

def main():

    old_lines='''
    aaa fdffd hjhjgj down


bbb dfsfsd sss jyjyjtu
ddd ggggggggggggg
eee ffsgf srgwrgwfg down
ccc sfewfweg  sdgwrg
ssss ssss down
ddd ddddddddddd

sssss dsss
ddd ggggggggggggg

    '''
    new_lines='''aaa fdffd hjhjgj down
bbb dfsfsd jyjyjtu
ccc sfewfweg  sdgwrg
fff dsgg ethtq hthtyh
gggg dsvsvvsf down
ssss ssss down

dddd jjjj
ddd ggggggggggggggggg

eee gggggggggggggg

    '''
    print(get_string_file_difference_string(old_lines,new_lines))


if __name__ == "__main__": main()