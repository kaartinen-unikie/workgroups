#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2019 Bayerische Motoren Werke Aktiengesellschaft (BMW AG)
#
# SPDX-License-Identifier: GPL-2.0-only

import sys
import os
import argparse
import subprocess

###############################################################################


def parse_objdump(infile, outfile, linux_dir):
    dirtable = []
    fileset = set()
    s_dirtable = False
    s_filenametable = False
    skiplines = 0

    for line in infile:
        emptyline = False
        if ' The Directory Table' in line:
            s_dirtable = True
            dirtable = []
            skiplines = 1
        elif ' The File Name Table' in line:
            s_filenametable = True
            skiplines = 2
        elif line.strip() == '':
            emptyline = True

        if skiplines > 0:
            skiplines -= 1
            continue

        if s_dirtable:
            if emptyline:
                s_dirtable = False
                continue
            dirtable.append(line.split())
            # Possible makefiles that exist under each directory
            dirname = dirtable[-1][1]
            if os.path.isfile(os.path.join(linux_dir, dirname, 'Makefile')):
                fileset.add(dirname + '/Makefile')
            if os.path.isfile(os.path.join(linux_dir, dirname, 'Kconfig')):
                fileset.add(dirname + '/Kconfig')
        elif s_filenametable:
            if emptyline:
                s_filenametable = False
                continue
            fileinfo = line.split()
            diridx = int(fileinfo[1]) - 1
            # In case compiled file is in the root we need to check
            # the pathindex
            if diridx >= 0:
                if dirtable[diridx][1][0] == '/':
                    # Directory points outside kernel tree; skip it
                    continue
                fileset.add("%s/%s" % (dirtable[diridx][1], fileinfo[4]))
            else:
                fileset.add(fileinfo[4])

    for item in sorted(fileset):
        outfile.write("%s\n" % item)


def exec_cmd(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE):
    pipe = subprocess.Popen(
        cmd, shell=True, stdout=stdout, stderr=stderr, encoding='utf-8')
    stdout, stderr = pipe.communicate()
    if pipe.returncode != 0:
        raise ValueError(stderr)
    return stdout if stdout else None

###############################################################################


def getargs():
    desc =\
        "Script calls objdump for vmlinux and all modules (*.ko) "\
        "found under LINUX_DIR, parses the output, and produces a list of "\
        "patches in range REV that modified the kernel source files relevant "\
        "for the specific kernel build. "\
        "The script can be used to reduce the patches in the range REV to "\
        "those that are relevant for the kernel configuration that was used "\
        "in building the vmlinux and the modules."

    epil = "Example: ./%s --linux-dir ~/linux-stable v4.19..v4.19.80" % \
        os.path.basename(__file__)
    parser = argparse.ArgumentParser(description=desc, epilog=epil)

    help = "revision specifier, see git-rev-parse for viable options. "
    parser.add_argument('REV', nargs=1, help=help)

    help = \
        "file path to built kernel tree, defaults to current working directory"
    parser.add_argument('--linux-dir', nargs='?', help=help, default='./')

    return parser.parse_args()

###############################################################################


if __name__ == '__main__':
    if sys.version_info[0] < 3:
        sys.stderr.write("Error: script requires Python 3.x\n")
        sys.exit(1)

    args = getargs()
    linux_dir = args.linux_dir
    rev = args.REV[0]
    repo = os.path.join(linux_dir, ".git")
    vmlinux = os.path.join(linux_dir, "vmlinux")

    if not os.path.exists(linux_dir):
        sys.stderr.write(
            "Error: cannot access '%s': no such directory\n" % linux_dir)
        sys.exit(1)
    if not os.path.exists(repo):
        sys.stderr.write(
            "Error: not a git repository: '%s'\n" % linux_dir)
        sys.exit(1)
    if not os.path.exists(vmlinux):
        sys.stderr.write(
            "Error: cannot access '%s': is it compiled?\n" % vmlinux)
        sys.exit(1)

    objdumpfile = 'objdump.txt'
    filelistfile = 'filelist.txt'
    patchlistfile = 'patchlist.txt'

    print("[+] Reading objects from: %s" % linux_dir)

    # Collect objdump
    with open(objdumpfile, 'w') as outfile:
        cmd = 'find %s -name *.ko -exec objdump -Wl {} +' % linux_dir
        exec_cmd(cmd, stdout=outfile)
    with open(objdumpfile, 'a') as outfile:
        cmd = 'objdump -Wl %s' % vmlinux
        exec_cmd(cmd, stdout=outfile)
    print("[+] Wrote: %s" % objdumpfile)

    # Parse objdump
    with open(objdumpfile, 'r') as infile, open(filelistfile, 'w') as outfile:
        parse_objdump(infile, outfile, linux_dir)
    print("[+] Wrote: %s" % filelistfile)

    # Generate patchlist
    with open(filelistfile, 'r') as infile, open(patchlistfile, 'w') as outfile:
        cmd = \
            'git --git-dir=%s log --oneline '\
            '--no-merges %s -- `cat %s`' % (repo, rev, filelistfile)
        exec_cmd(cmd, stdout=outfile)
    print("[+] Wrote: %s" % patchlistfile)

###############################################################################
