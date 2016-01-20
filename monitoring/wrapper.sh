#!/usr/bin/env bash

# This file executes rax-autoscaler and checks whether the
# output indicates that there were autoscale nodes NOT in 
# the load balancer.
# If that happens, create /tmp/rax_autoscale_failure
# This file is monitored by fail_file_monitor.py (check
# header of this file for more information)
# 

fail_file=/tmp/rax_autoscale_failure
log_file=$(mktemp)
/usr/bin/autoscale --config /opt/autoscale/autoscale_setup/rax-autoscaler-config.json > $log_file 2>&1
grep "Consensus was to scale down" $log_file 1>/dev/null 2>&1 && cat $log_file > $fail_file

# Merge log file for this run with the usual log
cat $log_file >> /var/log/rax-autoscaler/logging.log
rm -f $log_file
