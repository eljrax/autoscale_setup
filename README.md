**Please note that this is work in progress. While the scripts will work fine, the documentation is added to continuously as I find the time.**

Rackspace Autoscale Tools
================

This repository is currently a dumping ground for various scripts and tools I use when implementing Autoscaling at Rackspace. Not all scripts are suitable or required in all scenarios. Tools and implementation will vary on a case-by-case basis.

I prefer to use [rax-autoscaler](https://github.com/rackerlabs/rax-autoscaler) with the [raxmon_autoscale plugin](https://github.com/rackerlabs/rax-autoscaler/blob/devel/raxas/core_plugins/raxmon_autoscale.py) in devel branch at the time of writing) to trigger the relevant scaling policy webhooks.


Autoscaler - main.py
================

To get started, run:
```
pip install -r requirements.txt
vim config.ini.sample
cp config.ini.sample /opt/autoscale/autoscaler.ini
./main.py
```
Alternatively you can save the file somewhere else and specify the
--config-file parameter when executing main.py


load_balancing/add_self_to_lb.py
-----------------
If you let Autoscale manage the load balancer for you, it will add nodes as soon as the server is built, potentially before any bootstrapping and configuration has taken place. It will also add it as ENABLED/ONLINE. So if you use a default health check, you run the risk of serving stale or non-existing content for up to 20 seconds. 
This script lets the nodes add themselves to the load balancer as a final step of a configuration process. 

It will query the defined loadbalancer(s) for their health checks, and replicate those locally in an attempt to verify that configuration was successful before sending traffic to it.
So if your load balancer health check is set to request /health.php and expect a 200 with "AUTOSCALE" in the body, this script will make a request to /health.php and look for those values. Only if this check is successful will the node be added to the load balancer. 
Just note that this does NOT take firewalls into account, since the health check runs locally.

Configuration is done in-script toward the top of the file.
~~~
$ python load_balancing/add_node_lb.py
Node added to LB 147757
Node added to LB 136249

# It's safe to run multiple times
$ python load_balancing/add_node_lb.py
Node 10.181.98.11:80 already in LB 147757..
Node 10.181.98.11:22 already in LB 136249..
~~~

load_balancing/remove_dead_nodes.py
--------------------
Similarly, if you don't use Autoscale to manage the load balancer for you, it also won't remove nodes when they are scaled down. This menas you may hit the 25 node limit reasonably quickly, unless you frequently clean up.

This script is meant to run in a scheduler (such as crontab), and queries the autoscale group for its active nodes. It then gathers all IP addresses of those nodes, and compares them to the IP addresses in the load balancer's node list. 
If there are any nodes which aren't in the autoscale group but is in the load balancer and is NOT online, those will be drained and on the subsequent execution removed from the loadbalancer pool.

~~~
$ python load_balancing/remove_dead_nodes.py
INFO:root:10.181.98.11 (status: OFFLINE) not found in scaling group or whitelist, draining node in loadbalancer 147757...
INFO:root:10.181.98.11 (status: OFFLINE) not found in scaling group or whitelist, draining node in loadbalancer 136249...
$ python load_balancing/remove_dead_nodes.py
INFO:root:10.181.98.11 (status: OFFLINE) not found in scaling group or whitelist, and is in draining mode - deleting from loadbalancer 147757...
INFO:root:10.181.98.11 (status: OFFLINE) not found in scaling group or whitelist, and is in draining mode - deleting from loadbalancer 136249...
~~~
You can optionally override this behaviour by instructing the script to not delete nodes as long as they are online, regardless of whether they are in the autoscale group or not.
There is also a whitelist facility, which prevents those IP addresses from ever being removed, regardless of being present in the autoscale group or status. This is useful if you have permanent nodes, which aren't scaled up or down, but still serve your application.

