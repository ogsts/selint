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
"""Configuration file for the unnecessary_rules plugin."""

# Do not make suggestions on rules coming from files in these paths
#
# e.g. to ignore AOSP:
# RULE_IGNORE_PATHS = ["external/sepolicy"]
RULE_IGNORE_PATHS = ["external/sepolicy",
                     "build/target/board/generic/sepolicy"]

# Tuples of rules that must always be found together. If the first rule in the
# tuple is found in the policy, report any other rule in the tuple which is
# not in the policy.
#
# The plugin supports searching with placeholder arguments, e.g. you can
# specify such a tuple:
# ("type_transition @@ARG0@@ @@ARG1@@:process @@ARG2@@;",
#  "allow @@ARG0@@ @@ARG1@@:file execute;",
#  "allow @@ARG2@@ @@ARG1@@:file entrypoint;",
#  "allow @@ARG0@@ @@ARG2@@:process transition;")
# which will match the following set of rules:
#
#   type_transition initrc_t acct_exec_t:process acct_t;
#   allow initrc_t acct_exec_t:file execute;
#   allow acct_t acct_exec_t:file entrypoint;
#   allow initrc_t acct_t:process transition;
#
# N.B. the first rule in the tuple MUST contain all the placeholder arguments
#      used in later rules.
RULES_TUPLES = [("type_transition @@ARG0@@ @@ARG1@@:process @@ARG2@@;",
                 "allow @@ARG0@@ @@ARG1@@:file execute;",
                 "allow @@ARG2@@ @@ARG1@@:file entrypoint;",
                 "allow @@ARG0@@ @@ARG2@@:process transition;")]
