#!/usr/bin/env python

import pyrax
import utils
import autoscale
import json

config = utils.config('./config.ini')


username, api_key, region = config.get_credentials()

pyrax.set_setting('identity_type', 'rackspace')
pyrax.set_setting('region', region)
pyrax.set_credentials(username, api_key)

# Converts CSV user input to structures used by pyrax and names to IDs etc.
utils.merge_config(config, pyrax)


while True:
    try:
        autoscale = autoscale.autoscale(config, pyrax)
        break
    except pyrax.exceptions.NotFound:
        resp = raw_input( "You specified a scaling group with ID %s, which does not appear"
        " to exist in this account. Would you like to create it? (y/n): " % config.as_config.id)
        if resp.lower() == 'n':
            exit(1)
        else:
            config.as_config.id = None
    except Exception:
        raise


scale_down = autoscale.get_scale_down_policy()
scale_up = autoscale.get_scale_up_policy()

config.set_config_option('rax-autoscaler', 'scale_up_webhook', autoscale.get_webhook_url(scale_up))
config.set_config_option('rax-autoscaler', 'scale_down_webhook', autoscale.get_webhook_url(scale_down))
config.set_config_option('rax-autoscaler', 'scale_down_policy', autoscale.get_scale_up_policy().id)
config.set_config_option('rax-autoscaler', 'scale_up_policy', autoscale.get_scale_down_policy().id)
config.set_config_option('autoscale', 'id', "'%s'" % autoscale.get_id())

