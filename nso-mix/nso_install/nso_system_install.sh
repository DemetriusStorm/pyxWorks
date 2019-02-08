#!/bin/bash
VERSIONDIR="ncs-4.7.2.1"

# unpack file
sh ./nso-*.signed.bin --skip-verification

# start installer bin file
sudo sh ./nso-*.installer.bin --system-install

# create user groups
sudo groupadd ncsadmin
sudo groupadd ncsoper

# add user to group
sudo usermod -a -G ncsadmin `whoami`
sudo usermod -a -G ncsoper `whoami`

# enable overcommit memory
sudo echo 2 > /proc/sys/vm/overcommit_memory

# nso start
sudo source /etc/profile.d/ncs.sh
sudo /etc/init.d/ncs start







