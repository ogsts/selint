#
# Written by Filippo Bonazzi
# Copyright (C) 2016 Aalto University
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""TODO: file docstring"""

import logging
import re
import os.path
import config.unnecessary_rules as plugin_conf
import policysource
import setools
from setools.terulequery import TERuleQuery as TERuleQuery
import policysource.mapping

# Global variable to hold the log
LOG = None

# Global variable to hold the mapper
MAPPER = None

# Global variable to hold the full ignored paths
FULL_IGNORE_PATHS = None

# Global variable to hold the supported non-ignored rules mapping
NON_IGNORED_MAPPING = {}

# Regex for a valid argument in m4
VALID_ARG_R = r"[a-zA-Z0-9_-]+"


def query_for_rule(policy, r):
    """Query a policy for rules matching a given rule.
    The rule may contain regex fields."""
    global NON_IGNORED_MAPPING
    # Mark whether a query parameter is a regex or a string
    sr = r"[a-zA-Z0-9_-]+" in r.source
    tr = r"[a-zA-Z0-9_-]+" in r.target
    cr = r"[a-zA-Z0-9_-]+" in r.tclass
    # Handle self
    if r.target == "self":
        # Override the target to match everything
        xtarget = VALID_ARG_R
        tr = True
    else:
        xtarget = r.target
    # Query for an AV rule
    if r.rtype in policysource.mapping.AVRULES:
        query = TERuleQuery(policy=policy.policy, ruletype=[r.rtype],
                            source=r.source, source_regex=sr,
                            source_indirect=False,
                            target=xtarget, target_regex=tr,
                            target_indirect=False,
                            tclass=[r.tclass], tclass_regex=cr,
                            perms=r.permset, perms_subset=True)
    # Query for a TE rule
    elif r.rtype in policysource.mapping.TERULES:
        dr = r"[a-zA-Z0-9_-]+" in r.deftype
        query = TERuleQuery(policy=policy.policy, ruletype=[r.rtype],
                            source=r.source, source_regex=sr,
                            source_indirect=False,
                            target=xtarget, target_regex=tr,
                            target_indirect=False,
                            tclass=[r.tclass], tclass_regex=cr,
                            default=r.deftype, default_regex=dr)
    else:
        # We should have no other rules, as they are already filtered
        # when creating the list with the rule_factory method
        LOG.warning("Unsupported rule: \"%s\"", r)
        return None
    # Filter all rules
    if r.target == "self":
        # Discard rules whose mask contained "self" as a target,
        # but whose result's source and target are different
        results = [x for x in query.results() if x.source == x.target]
    else:
        results = list(query.results())
    filtered_results = []
    # Discard rules coming from explicitly ignored paths
    for x in results:
        x_str = str(x)
        rule = MAPPER.rule_factory(x_str)
        rutc = rule.up_to_class
        # Get the MappedRule(s) corresponding to this rutc
        rls = [y for y in policy.mapping.rules[rutc]]
        if len(rls) == 1:
            # If this rule comes from a single place, this is easy.
            # Drop the rule if the path it comes from is ignored
            if not rls[0].fileline.startswith(FULL_IGNORE_PATHS):
                filtered_results.append(x)
                NON_IGNORED_MAPPING[x_str] = [rls[0].fileline]
        else:
            # If this rule comes from multiple places, this is more complex.
            # Check that all rules that make up the specific rule we found
            # come from non-ignored paths. If not, drop the rule.
            if rule.rtype in policysource.mapping.AVRULES:
                # Check that the permission set of the "x" rule is covered by
                # non-ignored rules. If not, drop the rule.
                tmpset = set()
                for each in rls:
                    if not each.fileline.startswith(FULL_IGNORE_PATHS):
                        prmstr = MAPPER.rule_split_after_class(each.rule)[1]
                        tmpset.update(prmstr.strip(" {};").split())
                        if x_str in NON_IGNORED_MAPPING:
                            NON_IGNORED_MAPPING[x_str].append(each.fileline)
                        else:
                            NON_IGNORED_MAPPING[x_str] = [each.fileline]
                if tmpset >= rule.permset:
                    # The set of permissions created by non-ignored rules is
                    # sufficient
                    filtered_results.append(x)
                else:
                    NON_IGNORED_MAPPING.pop(x_str, None)
            elif rule.rtype in policysource.mapping.TERULES:
                # Check for every type_transition rule individually
                for each in rls:
                    if not each.fileline.startswith(FULL_IGNORE_PATHS):
                        filtered_results.append(x)
                        if x_str in NON_IGNORED_MAPPING:
                            NON_IGNORED_MAPPING[x_str].append(each.fileline)
                        else:
                            NON_IGNORED_MAPPING[x_str] = [each.fileline]
    return filtered_results


def substitute_args(rule, args):
    """Substitute placeholder arguments in a rule with their actual values.

    The rule must be passed in as a string.
    e.g.
    rule = "allow @@ARG0@@ sometype:class perm;"
    args = {"arg0": "somedomain"}
    -> returns "allow somedomain sometype:class perm;"
    """
    modified_args = {}
    for k, v in args.iteritems():
        modified_args["@@" + k.upper() + "@@"] = v
    for k, v in modified_args.iteritems():
        rule = rule.replace(k, v)
    return rule


def main(policy, config):
    """Find unnecessary or missing rules in the policy."""
    # Check that we have been fed a valid policy
    if not isinstance(policy, policysource.policy.SourcePolicy):
        raise ValueError("Invalid policy")
    # Setup logging
    log = logging.getLogger(__name__)
    global LOG
    LOG = log

    # Compute the absolute ignore paths
    FULL_BASE_DIR = os.path.abspath(os.path.expanduser(config.BASE_DIR_GLOBAL))
    global FULL_IGNORE_PATHS
    FULL_IGNORE_PATHS = tuple(os.path.join(FULL_BASE_DIR, p)
                              for p in plugin_conf.RULE_IGNORE_PATHS)

    # Valid argument for a regex query
    VALID_ARG_R = r"[a-zA-Z0-9_-]+"

    # Create a global mapper to expand the rules
    global MAPPER
    MAPPER = policysource.mapping.Mapper(
        policy.policyconf, policy.attributes, policy.types, policy.classes)

    # Compile the regex for speed
    rule_w_placeholder_r = re.compile(
        r".*" + ArgExtractor.placeholder_r + r".*")
    # Look for missing rules in predetermined tuples
    for t in plugin_conf.RULES_TUPLES:
        log.debug("Checking tuple containing these rules:")
        for x in t:
            log.debug(x)
        placeholder_sub = False
        # Ignore tuples with a single element. We should not have any, anyway
        if len(t) < 2:
            continue
        # Ignore tuples that begin with an unsupported rule
        if not t[0].startswith(policysource.mapping.ONLY_MAP_RULES):
            continue
        # If the first rule in the tuple contains at least one placeholder
        if rule_w_placeholder_r.match(t[0]):
            placeholder_sub = True
            # Initialise an extractor with the placeholder rule
            e = ArgExtractor(t[0])
            # Substitute the positional placeholder arguments with a
            # regex matching valid argument characters
            l_r = re.sub(r"@@ARG[0-9]+@@", VALID_ARG_R, t[0])
            tmp = MAPPER.rule_factory(l_r)
            # Get the rules matching the query for the rule with regexes
            rules = query_for_rule(policy, tmp)
            if not rules:
                continue
            log.debug("Found rules:")
            for x in rules:
                log.debug(str(x))
        else:
            rules = [t[0]]
        # For each rule matching the query
        for r in rules:
            missing_rules = []
            if placeholder_sub:
                # Get the arguments from the rule
                args = e.extract(r)
            # For each additional rule in the tuple, check that it is in the
            # policy, substituting placeholders if necessary.
            for each_rule in t[1:]:
                # Ignore unsupported rules
                if not each_rule.startswith(policysource.mapping.ONLY_MAP_RULES):
                    continue
                if placeholder_sub:
                    nec_rule = substitute_args(each_rule, args)
                else:
                    nec_rule = each_rule
                nec_rule_full = MAPPER.rule_factory(nec_rule)
                # Shorter variable name
                nrfutc = nec_rule_full.up_to_class
                # If the rule up to the class is in the mapping
                if nrfutc in policy.mapping.rules:
                    # Check if the rule is actually present by possibly
                    # combining the existing rules in the mapping
                    if nec_rule_full.rtype in policysource.mapping.AVRULES:
                        # If we are looking for an allow rule, combine
                        # existing allow rules and check if the resulting
                        # rule is a superset of the rule we are looking
                        # for
                        permset = set()
                        for x in policy.mapping.rules[nrfutc]:
                            x_f = MAPPER.rule_factory(x.rule)
                            permset.update(x_f.permset)
                        # If not a subset, print the rule and the missing
                        # permissions
                        if not nec_rule_full.permset <= permset:
                            missing = ": missing \""
                            missing += " ".join(nec_rule_full.permset -
                                                permset)
                            missing += "\""
                            missing_rules.append(nec_rule + missing)
                    if nec_rule_full.rtype in policysource.mapping.TERULES:
                        if nec_rule not in policy.mapping.rules[nrfutc]:
                            missing_rules.append(nec_rule)
                else:
                    missing_rules.append(nec_rule)
            if missing_rules:
                # TODO: print fileline
                print "Rule:"
                print r
                print "is missing associated rule(s):"
                print "\n".join(missing_rules)


class ArgExtractor(object):
    """Extract macro arguments from an expanded rule according to a regex."""
    placeholder_r = r"@@ARG[0-9]+@@"

    def __init__(self, rule):
        """Initialise the ArgExtractor with the rule expanded with the named
        placeholders.

        e.g.: "allow @@ARG0@@ @@ARG0@@_tmpfs:file execute;"
        """
        self.rule = rule
        # Convert the rule to a regex that matches it and extracts the groups
        self.regex = re.sub(self.placeholder_r,
                            "(" + VALID_ARG_R + ")", self.rule)
        self.regex_blocks = policysource.mapping.Mapper.rule_parser(self.regex)
        self.regex_blocks_c = {}
        # Save precompiled regex blocks
        for blk in self.regex_blocks:
            if VALID_ARG_R in blk:
                self.regex_blocks_c[blk] = re.compile(blk)
        # Save pre-computed rule permission set
        if self.regex_blocks[0] in policysource.mapping.AVRULES:
            if any(x in self.regex_blocks[4] for x in "{}"):
                self.regex_perms = set(
                    self.regex_blocks[4].strip("{}").split())
            else:
                self.regex_perms = set([self.regex_blocks[4]])
        else:
            self.regex_perms = None
        # Save the argument names as "argN"
        self.args = [x.strip("@").lower()
                     for x in re.findall(self.placeholder_r, self.rule)]

    def extract(self, rule):
        """Extract the named arguments from a matching rule."""
        matches = self.match_rule(rule)
        retdict = {}
        if matches:
            # The rule matches the regex: extract the matches
            for i in xrange(len(matches)):
                # Handle multiple occurrences of the same argument in a rule
                # If the occurrences don't all have the same value, this rule
                # does not actually match the placeholder rule
                if self.args[i] in retdict:
                    # If we have found this argument already
                    if retdict[self.args[i]] != matches[i]:
                        # If the value we just found is different
                        # The rule does not actually match the regex
                        raise ValueError("Rule does not match ArgExtractor"
                                         "expression: \"{}\"".format(
                                             self.regex))
                else:
                    retdict[self.args[i]] = matches[i]
            return retdict
        else:
            # The rule does not match the regex
            raise ValueError("Rule does not match ArgExtractor expression: "
                             "\"{}\"".format(self.regex))

    def match_rule(self, rule):
        """Perform a rich comparison between the provided rule and the rule
        expected by the extractor.
        The rule must be passed in as a string.

        Return True if the rule satisfies (at least) all constraints imposed
        by the extractor."""
        matches = []
        rule_objname = None
        # Shorter name -> shorter lines
        regex_blocks = self.regex_blocks
        regex_blocks_c = self.regex_blocks_c
        # Only call the rule methods once, cache values locally
        rule_blocks = []
        rule_blocks.append(str(rule.ruletype))
        if rule_blocks[0] == "type_transition":
            if len(regex_blocks) == 6:
                # Name transition
                try:
                    rule_objname = str(rule.filename)
                except:
                    return None
        elif rule_blocks[0] not in policysource.mapping.AVRULES:
            # Not an allow rule, not a type_transition rule
            return None
        # Match the rule block by block
        ##################### Match block 0 (ruletype) ######################
        # No macro arguments here, no regex match
        if rule_blocks[0] != regex_blocks[0]:
            return None
        ##################################################################
        rule_blocks.append(str(rule.source))
        ##################### Match block 1 (source) #####################
        if regex_blocks[1] in regex_blocks_c:
            # The domain contains an argument, match the regex
            m = regex_blocks_c[regex_blocks[1]].match(rule_blocks[1])
            if m:
                matches.append(m.group(1))
            else:
                return None
        else:
            # The domain contains no argument, match the string
            if rule_blocks[1] != regex_blocks[1]:
                return None
        ##################################################################
        rule_blocks.append(str(rule.target))
        ##################### Match block 2 (target) #####################
        if regex_blocks[2] in regex_blocks_c:
            # The type contains an argument, match the regex
            m = regex_blocks_c[regex_blocks[2]].match(rule_blocks[2])
            if m:
                matches.append(m.group(1))
            else:
                return None
        else:
            # The type contains no argument, match the string
            if regex_blocks[2] == "self" and rule_blocks[2] != "self":
                # Handle "self" expansion case
                # TODO: check if this actually happens
                if rule_blocks[2] != rule_blocks[1]:
                    return None
            elif rule_blocks[2] != regex_blocks[2]:
                return None
        ##################################################################
        rule_blocks.append(str(rule.tclass))
        ##################### Match block 3 (tclass) #####################
        if regex_blocks[3] in regex_blocks_c:
            # The class contains an argument, match the regex
            # This should never happen, however
            m = regex_blocks_c[regex_blocks[3]].match(rule_blocks[3])
            if m:
                matches.append(m.group(1))
            else:
                return None
        else:
            # The class contains no argument
            # Match a (super)set of what is required by the regex
            if rule_blocks[3] != regex_blocks[3]:
                # Simple class, match the string
                return None
        ##################################################################
        ##################### Match block 4 (variable) ###################
        if rule_blocks[0] in policysource.mapping.AVRULES:
            ################ Match an AV rule ################
            # Block 4 is the permission set
            # Match a (super)set of what is required by the regex
            if not self.regex_perms <= rule.perms:
                # If the perms in the rule are not at least those in
                # the regex
                return None
            ##################################################
        elif rule_blocks[0] == "type_transition":
            ################ Match a type_transition rule #################
            # Block 4 is the default type
            rule_default = str(rule.default)
            if regex_blocks[4] in regex_blocks_c:
                # The default type contains an argument, match the regex
                m = regex_blocks_c[regex_blocks[4]].match(rule_default)
                if m:
                    matches.append(m.group(1))
                else:
                    return None
            else:
                # The default type contains no argument, match the string
                if rule_default != regex_blocks[4]:
                    return None
            ##################################################
        ##################################################################
        ##################### Match block 5 (name trans) #################
        if rule_objname:
            # If this type transition has 6 fields, it is a name transition
            # Block 5 is the object name
            if regex_blocks[5] in regex_blocks_c:
                # The object name contains an argument, match the regex
                m = regex_blocks_c[regex_blocks[5]].match(rule_objname)
                if m:
                    matches.append(m.group(1))
                else:
                    return None
            else:
                # The object name contains no argument, match the string
                if rule_objname.strip("\"") != regex_blocks[5].strip("\""):
                    return None
        ##################################################################
        ######################## All blocks match ########################
        return matches
