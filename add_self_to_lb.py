#!/usr/bin/env python

###################################################################################
# 									  	  #
# This script should be executed as the last thing that happens during    	  #
# the configuration phase of a server. It will perform the health check   	  #
# defined in the load balanceri(s) configured below, and add itself as a  	  #
# node if successful. 							  	  #
# For example: if the load balancer has a HTTP health check expecting a   	  #
# 200 response from a request to /, it will make this call and verify the 	  #
# status code before adding itself as an ENABLED/ONLINE node.		  	  #
#									  	  #
# Please modify the variables in the CONFIGURATION section below before executing #
# Author: Erik Ljungstrom                                                         #
# License: Apache License Version 2.0 http://www.apache.org/licenses/LICENSE-2.0  #
###################################################################################
from __future__ import print_function

import os
import pyrax
import netifaces as ni
import urllib2
import socket
import re
import random
from time import sleep

####################### CONFIGURATION #######################

# Network interface to grab the IP address from. This is the IP address
# that will be used in the health check and ultimately added to the
# load balancer. (REQUIRED)
# e.g. iface = "eth1"
iface = ""

# LOAD BALANCER(S) (REQUIRED)
#
# e.g.
# Single Load Balancer
#  lbs = [1234]
# Multiple Load balancers
#  lbs = [1234, 5678]
lbs = []

# Path to file containing credentials (REQUIRED)
# e.g. credentials = '/opt/autoscale/.cloud_credentials'
# File format:
#
# [rackspace_cloud]
# username =
# api_key =
#
credentials = ''

# Name to send as Host: header with health check request (optional)
host_header = None

# Protocol to utilise in url check (override LB health check) (optional)
protocol = None

######################################################################


def get_addr(iface):
    ni.ifaddresses(iface)
    ip = ni.ifaddresses(iface)[2][0]['addr']
    return ip

def health_check(health_check, port=80):
    addr = get_addr(iface)
    if not health_check.has_key('type'):
        print ("No health check present on load balancer")
        return

    if health_check.get('type') == 'CONNECT':
        check_port(addr, port, health_check.get('timeout'))
    elif health_check.get('type') in ['HTTP', 'HTTPS']:
        check_url(health_check, addr)
    else:
        raise Exception("Unsupported health check, please implement your own")

def check_port(addr, port, timeout):
   sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
   sock.settimeout(timeout)
   result = sock.connect_ex((addr, port))
   if result != 0:
       raise Exception("Error connecting to port %s: error: %s" % (port, result))
   return result

def check_url(health_check, addr):
    global host_header
    expected_resp = re.compile(health_check.get('bodyRegex', '.*'))
    expected_code = re.compile(health_check.get('statusRegex', '.*'))
    proto = protocol if protocol else health_check.get('type').lower()
    url = ("%s://%s/%s" % (proto, addr, health_check.get('path', '/')))

    if not host_header:
        host_header = addr
    headers = { 'Host': host_header }

    req = urllib2.Request(url, headers=headers)
    response = urllib2.urlopen(req)

    contents_result = expected_resp.search(response.read())
    status_result = expected_code.match(str(response.getcode()))

    if not contents_result or not status_result:
        raise Exception("check_url(): Response content does not match expected result")

    return True


def main():

    pyrax.set_setting("identity_type", "rackspace")
    pyrax.set_credential_file(credentials)
    clb = pyrax.cloud_loadbalancers
    my_ip = get_addr(iface)



    for lb_id in lbs:
        retry = 5
        lb=clb.get(lb_id)
        try:
            health_check(lb.get_health_monitor(), lb.port)
        except Exception as e:
            print("Health check for LB %s failed with error: %s  Not adding..." % (lb_id, str(e)))
            continue

        while retry > 0:
            try:
                pyrax.utils.wait_until(lb, "status", "ACTIVE", interval=1, attempts=30, verbose=False)
                node = clb.Node(address = my_ip, port = lb.port, condition = "ENABLED")
                res = lb.add_nodes([node])
                print ("Node added to LB %s" % lb_id)
                break
            except pyrax.exceptions.ClientException as e:
                if "PENDING" in e.message:
                    print ("Race condition hit, another server is adding itself. Retrying...")
                    sleep(random.random())
                if "Duplicate nodes" in e.message:
                    print ("Node %s:%s already in LB %s.." % (my_ip, lb.port, lb_id))
                    break
                else:
                    print ("Exception: %s" % e.message)
                    break
            retry -= 1


if __name__ == "__main__":
        main()
