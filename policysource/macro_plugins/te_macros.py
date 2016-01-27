#
#    Written by Filippo Bonazzi
#    Copyright (C) 2016 Aalto University
#
#    This file is part of the policysource library.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as
#    published by the Free Software Foundation, either version 2.1 of
#    the License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with this program.  If not, see
#    <http://www.gnu.org/licenses/>.
#
"""Plugin to parse the te_macros file"""

import policysource.macro
import os
import re
import logging

MACRO_FILE = "te_macros"
LOG = logging.getLogger(__name__)
MDL = r"^#\s[a-zA-Z][a-zA-Z0-9_]*\((?:[a-zA-Z0-9_]+,\s?)*(?:[a-zA-Z0-9_]+)\)$"
BLK_SEP = r"^##+$"


class TEBlock(object):
    """Helper class to handle a macro block in the te_macros file."""

    def __init__(self, start, end, content):
        """Construct a TEBlock object.

        Keyword arguments:
        start   -- The starting line index, indexed from 0
        end     -- The non-inclusive end line index, indexed from 0
        content -- A list containing the block lines, i.e. lines[start, end)
        """
        # Sanity check
        if start + len(content) != end:
            raise ValueError("Invalid range for the supplied content.")
        self._start = start
        self._end = end
        self._content = content
        # Check if the macro definition line is correct
        if re.match(MDL, content[1]):
            self._valid = True
            # Tokenize the macro definition line, removing empy tokens
            # "# macro(arg1,arg2)" -> ["macro", "arg1", "arg2"]
            definition = [x for x in re.split(r'\W+', content[1]) if x]
            self._name = definition[0]    # ["macro"]
            self._args = definition[1:]   # ["arg1", "arg2"]
        else:
            self._valid = False
        # Get comments
        self._comments = []
        for line in content[1:]:
            if line.startswith('#'):
                self._comments.append(line)

    def start(self, line_number=True):
        """Return the starting position of the block.

        Keyword arguments:
        line_number -- if True, return the line number in the file,
                       i.e. indexed from 1.
                       if False, return the index in the array,
                       i.e. indexed from 0."""
        if line_number:
            return self._start + 1
        else:
            return self._start

    def end(self, line_number=True, inclusive=False):
        """Return the ending position of the block.

        Keyword arguments:
        line_number -- if True, return the line number in the file,
                       i.e. indexed from 1.
                       if False, return the index in the array,
                       i.e. indexed from 0.
        inclusive   -- if True, return an inclusive value, i.e. end]
                       if False, return a non inclusive value, i.e. end)"""
        pos = self._end
        if line_number:
            pos += 1
        if inclusive:
            pos -= 1
        return pos

    def is_valid(self):
        """Check if the block contains the correct macro definition line
         # name(arg0, arg1, ...)"""
        return self._valid

    @property
    def mdl(self):
        """Return the macro definition line."""
        return self.content[1]

    @property
    def name(self):
        """Return the macro name.

        If the macro is not valid the name may be None."""
        return self._name

    @property
    def args(self):
        """Return a list containing the macro args.

        If the macro is not valid, the list may be None."""
        return self._args

    @property
    def nargs(self):
        """Return the number of macro arguments."""
        return len(self.args)

    @property
    def content(self):
        """Return the full block content as a list of lines."""
        return self._content

    @property
    def comments(self):
        """Return the comments in the block."""
        return self._comments

    def __len__(self):
        return len(self.content)

    def __repr__(self):
        return "\n".join(self.content)


def expects(expected_file):
    """Return True/False depending on whether the plugin can handle the file"""
    if expected_file and os.path.basename(expected_file) == MACRO_FILE:
        return True
    else:
        return False


def __split__(file_lines):
    """Split the file in blocks."""
    blocks = []
    start = 0
    previous_is_empty = False
    for i, line in enumerate(file_lines):
        if line == "":
            # Mark if we find a blank line
            previous_is_empty = True
        elif previous_is_empty:
            if re.match(BLK_SEP, line):
                # The current line is a block separator following an empty line
                # We have a block behind us, process it
                # List slicing syntax: list[start:end] means [start, end)
                tmpblk = TEBlock(start, i, file_lines[start:i])
                blocks.append(tmpblk)
                LOG.debug("Found block at lines %d-%d (inclusive)",
                          tmpblk.start(), tmpblk.end(inclusive=True))
                # Mark the start of the new block
                start = i
            # Reset the previous empty line
            previous_is_empty = False
    # Handle the last block
    tmpblk = TEBlock(start, len(file_lines), file_lines[start:])
    blocks.append(tmpblk)
    LOG.debug("Found block at lines %d-%d (inclusive)",
              tmpblk.start(), tmpblk.end(inclusive=True))
    return blocks


def parse(f_to_parse, macro_expander):
    """Parse the file and return a dictionary of macros.

    Raise ValueError if unable to handle the file."""
    # Check that we can handle the file we're served
    if not f_to_parse or not expects(f_to_parse):
        raise ValueError("{} can't handle {}.".format(MACRO_FILE, f_to_parse))
    macros = {}
    # Parse the te_macros file
    # Read the te_macros file in as a list of lines
    with open(f_to_parse) as ftp:
        file_lines = ftp.read().splitlines()
    # Split the file in blocks
    blocks = __split__(file_lines)
    # Parse the macros from the blocks
    for block in blocks:
        # Check that the block contains a valid macro definition line
        # We currently do not care about invalid blocks
        if not block.is_valid():
            # Log the failure and skip this block
            LOG.warning("Bad macro definition at %s:%s",
                        f_to_parse, block.start())
            continue
        # If the expansion succeeded, construct the new macro object
        try:
            new_macro = policysource.macro.M4Macro(block.name, macro_expander,
                                                   f_to_parse, block.args,
                                                   block.comments)
        except policysource.macro.M4MacroError as e:
            # Log the failure and skip
            LOG.warning("%s", e.message)
        else:
            # Add the macro to the macro dictionary
            macros[block.name] = new_macro
    return macros
