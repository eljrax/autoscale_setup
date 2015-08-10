#!/usr/bin/env python

import pyrax
import utils
import autoscale
import argparse
import create_config
from colors import bcolors


def main():
    parser = argparse.ArgumentParser('Set up and manage autoscale groups')
    parser.add_argument('--no-create-config', required=False,
                        action="store_true",
                        help='Fail rather than prompt for'
                             ' missing config variables')

    parser.add_argument('--config-file', type=str,
                        default='/opt/autoscale/autoscaler.ini',
                        help='Path to config file (default'
                             ' /opt/autoscale/autoscaler.ini)')
    args = parser.parse_args()

    """ We need to parse the config file first of all, since we need a pyrax
    client for creating and further parsing the config file we require
    a minimal config with at least cloud credentials in it
    """
    config = utils.config(args.config_file, credentials_only=True)
    username, api_key, region = config.get_credentials()

    pyrax.set_setting('identity_type', 'rackspace')
    pyrax.set_setting('region', region)
    pyrax.set_credentials(username, api_key)

    if not args.no_create_config:
        create_config.write_config(config, pyrax)

    # Re-read config if changed and run through validation
    config = utils.config(args.config_file)

    # Converts CSV user input to structures used by pyrax and names to IDs etc.
    utils.config_fixup(config)

    while True:
        try:
            auto_scale = autoscale.autoscale(config, pyrax)
            break
        except pyrax.exceptions.NotFound:
            question = (bcolors.FAIL + "You specified a scaling group"
                        " with ID %s, which does not appear to exist on"
                        " this account. Would you "
                        " like to create it? (y/n): " % (
                            config.as_config.id) + bcolors.ENDC)
            if not utils.ask_str(question, yesno=True):
                exit(0)
            else:
                # If given an empty ID, __init__ in autoscale will create a
                # group
                config.as_config.id = None
        except Exception:
            raise

    scale_down = auto_scale.get_scale_down_policy()
    scale_up = auto_scale.get_scale_up_policy()

    config.set_config_option('rax-autoscaler', 'scale_up_webhook',
                             auto_scale.get_webhook_url(scale_up))
    config.set_config_option('rax-autoscaler', 'scale_down_webhook',
                             auto_scale.get_webhook_url(scale_down))
    config.set_config_option('rax-autoscaler', 'scale_down_policy',
                             auto_scale.get_scale_up_policy().id)
    config.set_config_option('rax-autoscaler', 'scale_up_policy',
                             auto_scale.get_scale_down_policy().id)
    config.set_config_option('autoscale', 'id', auto_scale.get_id())

if __name__ == '__main__':
    main()
