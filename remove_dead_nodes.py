#!/usr/bin/env python

###################################################################################
#                                                                                 #
# This script should be crontabbed, or otherwise periodically executed            #
# It will query the autoscale group for its active members, and collect           #
# their IP addresses and compare these against the active nodes in one            #
# or more load balancers defined below. Any nodes not found in the                #
# autoscale group will be removed from the loadbalancer.                          #
#                                                                                 #
# This will allow for autoscaled nodes to be added and removed without            #
# hitting any limits                                                              #
#                                                                                 #
# Author: Erik Ljungstrom                                                         #
# License: Apache License Version 2.0 http://www.apache.org/licenses/LICENSE-2.0  #
###################################################################################

from __future__ import print_function

import sys
import pyrax
import logging

####################### CONFIGURATION #######################

# LOAD BALANCER(S)  (REQUIRED)
#
# Single Load Balancer
# lbs = [254784]
# Multiple Load balancers
# e.g. lbs = [254784, 854574]
# (list)
lbs = []

# Autoscale group UUID (REQUIRED)
# e.g. as_group = '1234-4567-8910-abcd-efg'
# (string)
as_group = ''

# Path where customer's credentials are stored (REQUIRED)
# e.g. credentials = '/opt/autoscale/.cloud_credentials'
# File format:
#
# [rackspace_cloud]
# username =
# api_key =
# (string)
credentials = ''

# Nodes that should never be removed from the loadbalancer, even if they're not in the scaling group
# Useful if you have one or more permanent nodes outside the group that still serve the same application
# e.g. whitelist = ['127.0.0.1', '999.999.999.999']
# (list)
whitelist = None


# Log file name
# e.g log_file = '/opt/autoscale/remove_dead_nodes.log'
# (string)
log_file = None

# Delete nodes from the pool if they are not in the autoscale group, even if 
# they are online in the load balancer. In standard operation, this condition should be rare.
# Whitelisting should be used in favour of relying on this for permanent nodes!
# (bool)
delete_online = False

######################################################################


log_root = logging.getLogger()
logging.basicConfig(filename=log_file, level=logging.INFO)
logging.getLogger("urllib3").setLevel(logging.WARNING)
if log_file:
    console_log = logging.StreamHandler(sys.stdout)
    console_log.setLevel(logging.DEBUG)
    log_root.addHandler(console_log)


def main():
    pyrax.set_setting("identity_type", "rackspace")
    pyrax.set_credential_file(credentials)
    clb = pyrax.cloud_loadbalancers
    csrv = pyrax.cloudservers
    asg = pyrax.autoscale.get(as_group)

    # Pretend that all whitelisted servers are in the group
    addresses_in_grp = whitelist if whitelist else []

    for server_id in asg.get_state().get('active'):
        server = csrv.servers.get(server_id)
        for network in server.networks:
            for address in server.networks.get(network):
                addresses_in_grp.append(address)

    for id in lbs:
        lb = clb.get(id)
        try:
            nodes = lb.nodes
        except AttributeError as e:
            # This is thrown when there are no nodes under an LB
            continue
        for node in nodes:
            if node.address not in addresses_in_grp and (node.status != "ONLINE" or delete_online):
                pyrax.utils.wait_until(
                    lb, "status", "ACTIVE", interval=1, attempts=30, verbose=False)
                if node.condition != 'DRAINING':
                    log_root.info("%s (status: %s) not found in scaling group or whitelist, "
                                    "draining node in loadbalancer %s..." % (
                                    node.address, node.status, id))
                    node.condition = 'DRAINING'
                    node.update()
                else:
                    log_root.info("%s (status: %s) not found in scaling group or whitelist, "
                                    "and is in draining mode - deleting from "
                                    "loadbalancer %s..." % (
                                                        node.address,
                                                        node.status,
                                                        id))
                    node.delete()
            elif node.address not in addresses_in_grp and (node.status == "ONLINE" and not delete_online):
                print("Node %s in LB %s not in autoscale group, but is online and we are not overriding." % (
                        node.address, id))

if __name__ == "__main__":
    main()
