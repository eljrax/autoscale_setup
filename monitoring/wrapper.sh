#!/usr/bin/env bash

# ============================================================ #
# This file executes 'rax-autoscaler' and checks whether the
# output indicates that there is a need to 'scale down' but NOT
# all the nodes in the autoscale group are in the load balancer.
#
# This could be simply because rax-autoscaler checked while the
# new server was still building/configuring or a real issue and
# we need a way to be notified if this keeps happening for too 
# long, to avoid to get autoscale stuck with the autoscale 
# max_nodes limit reached without actually serving traffic and
# the inability to scale down.
#
# Script looks for the string "Consensus was to scale down" in
# the output of rax-autoscaler.
# If that happens, it tracks the number of failure and in case
# it goes over the number set in MAXFAILURES variable, it will
# create /tmp/rax_autoscale_failure. This file is monitored by 
# fail_file_monitor.py
# (check header of this file for more information)
# Once the status goes back to normal (scale_up, scale_down or
# do_nothing), it will reset counters and alert file.
# ============================================================ #

# Please set this variable accordingly with your setup
MAXFAILURES=15

# MAXFAILURES should be calculated in this way:
# ((av_time_new_server_ready / rax-autoscaler_cron_time)) x2 
# 
# the 'x2' is more as a precaution to allow some buffer in case
# a server requires more time. We allow DOUBLE time.
#
# Example:
# 15 minutes average time to have a server built and configured
# rax-autoscaler set in cron to run every 2 minutes
# this means => ~7-8 runs x 2 = 14-16 MAXFAILURES 
# ============================================================ #


# Define log files
FAIL_FILE=/tmp/rax_autoscale_failure
LOG_FAILURES=/tmp/rax_autoscale_failures_report
TMP_LOG_FILE=$(mktemp)
RAX_LOG_FILE=/var/log/rax-autoscaler/logging.log

touch $LOG_FAILURES
FAILS=$(cat $LOG_FAILURES)
[[ -z "$FAILS" ]] && FAILS=0

# Execute rax-autoscaler and get the output
/usr/bin/autoscale --config /opt/autoscale/autoscale_setup/rax-autoscaler-config.json > $TMP_LOG_FILE 2>&1

# Check output of rax-autoscaler:
# if "Consensus was to scale down" found => log +1 failure
# for any other output => reset all

if [[ $(grep "Consensus was to scale down" $TMP_LOG_FILE) ]]
    then
	((FAILS++))
	echo $FAILS > $LOG_FAILURES
    else 
	FAILS=0
	rm -f $LOG_FAILURES > /dev/null 2>&1
	rm -f $FAIL_FILE > /dev/null 2>&1
fi


# Generate FAIL_FILE if failures > MAXFAILURES limit
[ $FAILS -gt $MAXFAILURES ] && cat $TMP_LOG_FILE > $FAIL_FILE


# Merge output log file from this run with the cummulative rax-autoscaler log
cat $TMP_LOG_FILE >> $RAX_LOG_FILE
rm -f $TMP_LOG_FILE

