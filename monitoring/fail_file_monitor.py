#!/usr/bin/env python

""" This file is a Rackspace Cloud Monitoring plugin, which will monitor
    for the existence of /tmp/rax_autoscale_failure, which is created by
    wrapper.sh if rax-autoscaler detects that there are nodes in the
    autoscale group that isn't in the load balancer.
    In that case, rax-autoscaler will refuse to scale down, and we should be
    alerted in that scenario.

    Set up a normal cloud monitor check on the server running rax-autoscaler
    of type agent.plugin (API only), and add an alert if the metric is 1.

    This is completely optional, and you may have other ways of being alerted
    in the event of servers failing to be bootstrapped.
"""

fail_file = "/tmp/rax_autoscale_failure"

try:
    fp = open(fail_file, 'r')
    fp.close()
    print "metric rax_autoscale_fail int64 1"
except IOError:
    print "metric rax_autoscale_fail int64 0"
