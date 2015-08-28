#!/usr/bin/env python
#
#  svnfsfs_tests.py:  testing the 'svnfsfs' tool.
#
#  Subversion is a tool for revision control.
#  See http://subversion.apache.org for more information.
#
# ====================================================================
#    Licensed to the Apache Software Foundation (ASF) under one
#    or more contributor license agreements.  See the NOTICE file
#    distributed with this work for additional information
#    regarding copyright ownership.  The ASF licenses this file
#    to you under the Apache License, Version 2.0 (the
#    "License"); you may not use this file except in compliance
#    with the License.  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing,
#    software distributed under the License is distributed on an
#    "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#    KIND, either express or implied.  See the License for the
#    specific language governing permissions and limitations
#    under the License.
######################################################################

# General modules
import os
import logging
import re
import shutil
import sys
import threading
import time
import gzip

logger = logging.getLogger()

# Our testing module
import svntest
from svntest.verify import SVNExpectedStdout, SVNExpectedStderr
from svntest.verify import SVNUnexpectedStderr
from svntest.verify import UnorderedOutput
from svntest.main import SVN_PROP_MERGEINFO

# (abbreviation)
Skip = svntest.testcase.Skip_deco
SkipUnless = svntest.testcase.SkipUnless_deco
XFail = svntest.testcase.XFail_deco
Issues = svntest.testcase.Issues_deco
Issue = svntest.testcase.Issue_deco
Wimp = svntest.testcase.Wimp_deco
SkipDumpLoadCrossCheck = svntest.testcase.SkipDumpLoadCrossCheck_deco
Item = svntest.wc.StateItem

#----------------------------------------------------------------------

# How we currently test 'svnfsfs' --
#
#   'svnfsfs load-index': Create a greek repo but set shard to 2 and pack
#                         it so we can load into a packed shard with more
#                         than one revision to test ordering issues etc.
#                         r1 also contains a non-trival number of items such
#                         that parser issues etc. have a chance to surface.
#
#                         The idea is dump the index of the pack, mess with
#                         it to cover lots of UI guarantees but keep the
#                         semantics of the relevant bits. Then feed it back
#                         to load-index and verify that the result is still
#                         a complete, consistent etc. repo.
#
######################################################################
# Helper routines

def patch_format(repo_dir, shard_size):
  """Rewrite the format of the FSFS repository REPO_DIR so
  that it would use sharding with SHARDS revisions per shard."""

  format_path = os.path.join(repo_dir, "db", "format")
  contents = open(format_path, 'rb').read()
  processed_lines = []

  for line in contents.split("\n"):
    if line.startswith("layout "):
      processed_lines.append("layout sharded %d" % shard_size)
    else:
      processed_lines.append(line)

  new_contents = "\n".join(processed_lines)
  os.chmod(format_path, 0666)
  open(format_path, 'wb').write(new_contents)

######################################################################
# Tests

#----------------------------------------------------------------------

@SkipUnless(svntest.main.is_fs_type_fsfs)
@SkipUnless(svntest.main.fs_has_pack)
@SkipUnless(svntest.main.is_fs_log_addressing)
def load_index_sharded(sbox):
  "load-index in a packed repo"

  # Configure two files per shard to trigger packing.
  sbox.build()
  patch_format(sbox.repo_dir, shard_size=2)

  # With --fsfs-packing, everything is already packed and we
  # can skip this part.
  if not svntest.main.options.fsfs_packing:
    expected_output = ["Packing revisions in shard 0...done.\n"]
    svntest.actions.run_and_verify_svnadmin(expected_output, [],
                                            "pack", sbox.repo_dir)

  # Read P2L index using svnfsfs.
  exit_code, items, errput = \
    svntest.actions.run_and_verify_svnfsfs(None, [], "dump-index", "-r0",
                                           sbox.repo_dir)

  # load-index promises to deal with input that
  #
  # * uses the same encoding as the dump-index output
  # * is not in ascending item offset order
  # * ignores lines with the full table header
  # * ignores the checksum column and beyond
  # * figures out the correct target revision even if the first item
  #   does not match the first revision in the pack file
  #
  # So, let's mess with the ITEMS list to call in on these promises.

  # not in ascending order
  items.reverse()

  # multiple headers (there is already one now at the bottom)
  items.insert(0, "       Start       Length Type   Revision     Item Checksum\n")

  # make columns have a variable size
  # mess with the checksums
  # add a junk column
  # keep header lines as are
  for i in range(0, len(items)):
    if items[i].find("Start") == -1:
      columns = items[i].split()
      columns[5] = columns[5].replace('f','-').replace('0','9')
      columns.append("junk")
      items[i] = ' '.join(columns) + "\n"

  # first entry is for rev 1, pack starts at rev 0, though
  assert(items[1].split()[3] == "1")

  # Reload the index
  exit_code, output, errput = svntest.main.run_command_stdin(
    svntest.main.svnfsfs_binary, [], 0, False, items,
    "load-index", sbox.repo_dir)

  # Run verify to see whether we broke anything.
  expected_output = ["* Verifying metadata at revision 0 ...\n",
                     "* Verifying repository metadata ...\n",
                     "* Verified revision 0.\n",
                     "* Verified revision 1.\n"]
  svntest.actions.run_and_verify_svnadmin(expected_output, [],
                                          "verify", sbox.repo_dir)

########################################################################
# Run the tests


# list all tests here, starting with None:
test_list = [ None,
              load_index_sharded,
             ]

if __name__ == '__main__':
  svntest.main.run_tests(test_list)
  # NOTREACHED


### End of file.
