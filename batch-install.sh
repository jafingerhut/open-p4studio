#! /bin/bash

# Copyright 2024 Intel Corporation

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# On x86_64 Ubuntu 20.04.6 system, with no build-essential package installed.
# Note that having at least 4 GBytes of RAM per CPU core,
# i.e. the output of the `nproc` command, is probably close
# to the minimum amount of RAM you should have for parts of the build to succeed.

# Remember the current directory when the script was started:
INSTALL_DIR="${PWD}"

THIS_SCRIPT_FILE_MAYBE_RELATIVE="$0"
THIS_SCRIPT_DIR_MAYBE_RELATIVE="${THIS_SCRIPT_FILE_MAYBE_RELATIVE%/*}"
THIS_SCRIPT_DIR_ABSOLUTE=`readlink -f "${THIS_SCRIPT_DIR_MAYBE_RELATIVE}"`

linux_version_warning() {
    1>&2 echo "Found ID ${ID} and VERSION_ID ${VERSION_ID} in /etc/os-release"
    1>&2 echo "This script only supports these:"
    1>&2 echo "    ID ubuntu, VERSION_ID in 20.04 22.04"
    1>&2 echo ""
    1>&2 echo "Proceed installing manually at your own risk of"
    1>&2 echo "significant time spent figuring out how to make it all"
    1>&2 echo "work, or consider getting VirtualBox and creating a"
    1>&2 echo "virtual machine with one of the tested versions."
}

abort_script=0

if [ ! -r /etc/os-release ]
then
    1>&2 echo "No file /etc/os-release.  Cannot determine what OS this is."
    linux_version_warning
    exit 1
fi
source /etc/os-release
PROCESSOR=`uname --machine`

supported_distribution=0
tried_but_got_build_errors=0
if [ "${ID}" = "ubuntu" ]
then
    case "${VERSION_ID}" in
	20.04)
	    supported_distribution=1
	    ;;
	22.04)
	    supported_distribution=1
	    ;;
    esac
fi

if [ ${supported_distribution} -eq 1 ]
then
    echo "Found supported ID ${ID} and VERSION_ID ${VERSION_ID} in /etc/os-release"
else
    linux_version_warning
    if [ ${tried_but_got_build_errors} -eq 1 ]
    then
	1>&2 echo ""
	1>&2 echo "This OS has been tried at least once before, but"
	1>&2 echo "there were errors during a compilation or build"
	1>&2 echo "step that have not yet been fixed.  If you have"
	1>&2 echo "experience in fixing such matters, your help is"
	1>&2 echo "appreciated."
    fi
    exit 1
fi

# Minimum recommended system memory is 4 GBytes times the number of
# CPU cores, i.e. the output of the command `nproc`, because many
# build commands in open-p4studio use `nproc` to decide how many
# parallel build processes to run.  In at least one of those, the peak
# memory usage of some C++ compiler runs is over 3 GBytes.

num_procs=`nproc`
min_mem_MBytes=`expr ${num_procs} \* \( 4096 - 256 \)`
memtotal_KBytes=`head -n 1 /proc/meminfo | awk '{print $2;}'`
memtotal_MBytes=`expr ${memtotal_KBytes} / 1024`

if [ "${memtotal_MBytes}" -lt "${min_mem_MBytes}" ]
then
    memtotal_comment="too low"
    abort_script=1
else
    memtotal_comment="enough"
fi

echo "Number of processor cores detected:            ${num_procs}"
echo "Minimum recommended memory to run this script: ${min_mem_MBytes} MBytes"
echo "Memory on this system from /proc/meminfo:      ${memtotal_MBytes} MBytes -> $memtotal_comment"

if [ "${abort_script}" == 1 ]
then
    1>&2 echo ""
    1>&2 echo "Aborting script because system has too little RAM."
    1>&2 echo ""
    1>&2 echo "If you are running this system in a VM, and can:"
    1>&2 echo ""
    1>&2 echo "+ reduce the number of virtual CPUs allocated to the VM
    1>&2 echo "+ increase the RAM available to the VM
    1>&2 echo ""
    1>&2 echo "or some combination of those two that gives you 4 GBytes"
    1>&2 echo "of RAM per CPU core, then you should be able to run"
    1>&2 echo "the installation."
    1>&2 echo ""
    1>&2 echo "If you are interested in reducing the RAM required to"
    1>&2 echo "install this software, consider helping with this issue:"
    1>&2 echo "+ https://github.com/p4lang/open-p4studio/issues/17"
    exit 1
fi

get_used_disk_space_in_mbytes() {
    echo $(df --output=used --block-size=1M . | tail -n 1)
}

echo "------------------------------------------------------------"
echo "Time and disk space used before installation begins:"
DISK_USED_START=`get_used_disk_space_in_mbytes`
date
TIME_START=$(date +%s)
set -x

# This is required for some of the build steps, but is not installed
# by any later commands.
sudo apt-get install --yes ccache

set +x
echo "Version of p4lang/open-p4studio repo used:"
set -x
cd "${THIS_SCRIPT_DIR_ABSOLUTE}"
git log -n 1 | head -n 3
git submodule update --init --recursive
cd .git/modules/pkgsrc/p4-compilers/p4c
set +x
echo "Version of p4lang/p4c repo used:"
set -x
git log -n 1 | head -n 3
cd "${THIS_SCRIPT_DIR_ABSOLUTE}"

sudo -E ./p4studio/p4studio profile apply ./p4studio/profiles/testing.yaml

set +x
echo "------------------------------------------------------------"
echo "Time and disk space used when installation was complete:"
date
TIME_END=$(date +%s)
DISK_USED_END=`get_used_disk_space_in_mbytes`
echo ""
echo "Elapsed time for various install steps:"
echo "Total time             : $(($TIME_END-$TIME_START)) sec"
echo "All disk space utilizations below are in MBytes:"
echo ""
echo  "DISK_USED_START                ${DISK_USED_START}"
echo  "DISK_USED_END                  ${DISK_USED_END}"
echo  "DISK_USED_END - DISK_USED_START : $((${DISK_USED_END}-${DISK_USED_START})) MBytes"

set +x
cd "${HOME}"
cp /dev/null setup-open-p4studio.bash
echo "export SDE=\"${THIS_SCRIPT_DIR_ABSOLUTE}\"" >> setup-open-p4studio.bash
echo "export SDE_INSTALL=\"\${SDE}/install\"" >> setup-open-p4studio.bash
echo "export LD_LIBRARY_PATH=\"\${SDE_INSTALL}/lib\"" >> setup-open-p4studio.bash
echo "export PATH=\"\${SDE_INSTALL}/bin:\${PATH}\"" >> setup-open-p4studio.bash

echo "If you use a Bash-like command shell, you may wish to add a line like"
echo "the following to your .bashrc or other shell rc file:"
echo ""
echo "    source \$HOME/setup-open-p4studio.bash"
