""" This module checks the config for missing keys, and offers
    prompts to write them out to the file.
    Invoked by --create-config
"""
import utils
from colors import bcolors, print_msg
from jinja2 import Environment
import os


def write_config(config, pyrax):
    """ Prompt for missing keys in the config file and writes a new one out """

    config.parse_config()
    try:
        if config.lc_config.validate() and \
           config.as_config.validate() and \
           config.as_config.id:
            utils.print_msg(
                "Config defined in %s passes validation."
                " Checking for misconfiguration and missing"
                " optional keys.." % (
                    config.config_file), bcolors.OKGREEN)
    except AttributeError:
        pass

    ##
    # Write [autoscale] config
    ##
    if not config.as_config.id:
        group = utils.get_object_from_list(
            pyrax.autoscale, "group", create_new_option=True)
        if group is not None:
            config.set_config_option('autoscale', 'id', group)

    if not config.as_config.name:
        group_name = utils.ask_str("Name of autoscale_group: ")
        config.set_config_option('autoscale', 'name', group_name)

    if not isinstance(config.as_config.scale_up, int):
        scale_up = utils.ask_integer(
            "Number of servers to scale up by when triggered: ")
        config.set_config_option('autoscale', 'scale_up', scale_up)

    if not isinstance(config.as_config.scale_down, int):
        scale_down = utils.ask_integer(
            "Number of servers to scale down by when triggered: ")
        config.set_config_option('autoscale', 'scale_down', scale_down)

    if not isinstance(config.as_config.max_entities, int):
        max_entities = utils.ask_integer(
            "Max number of servers to scale up to (max_entities): ")
        config.set_config_option('autoscale', 'max_entities', max_entities)

    if not isinstance(config.as_config.min_entities, int):
        max_entities = config.as_config.max_entities
        min_entities = utils.ask_integer(
            "Never scale down below this number of servers (min_entities): ")
        if min_entities > max_entities:
            print_msg("min_entities must be smaller than or equal"
                      "to max_entities (%d)" %
                      max_entities, bcolors.FAIL)
            min_entities = utils.ask_integer("Never scale down below this "
                                             "number of servers"
                                             " (min_entities): ",
                                             allowed_input=xrange(0,
                                                                  max_entities))
        config.set_config_option('autoscale', 'min_entities', min_entities)
    if not isinstance(config.as_config.cooldown, int):
        cooldown = utils.ask_integer(
            "Do not process scale event more frequent than"
            " this (cooldown, seconds): ")
        config.set_config_option('autoscale', 'cooldown', cooldown)

    ##
    # Write [launch-config] config
    ##
    if not config.lc_config.image:
        image = utils.get_object_from_list(pyrax.images, "image")
        config.set_config_option('launch-configuration', 'image', image)

    if not config.lc_config.flavor:
        flavor = utils.get_object_from_list(
            pyrax.cloudservers.flavors, "flavor")
        config.set_config_option('launch-configuration', 'flavor', flavor)

    if not config.lc_config.key_name:
        key_name = utils.get_object_from_list(
            pyrax.cloudservers.keypairs, "ssh-key to add to"
                                         " /root/.ssh/authorized_keys on"
                                         " the servers",
                                         create_new_option=True)
        if key_name is None:
            key_name = utils.add_new_key(pyrax)
        config.set_config_option('launch-configuration', 'key_name', key_name)

    if not config.lc_config.name:
        name = utils.ask_str(
            "Server name (note that an 11 character suffix"
            " will be added to this name): ")
        config.set_config_option('launch-configuration', 'name', name)

    if config.get('launch-configuration', 'cloud_init') is None:
        print("When servers are booted up, the contents of the cloud-init"
              " script will be executed on the server. This is a way to"
              " install and configure the software the machine needs"
              " in order to serve its purpose.\n"
              "To use the default - input: templates/cloud-init.yml.j2")
        cloud_init = utils.ask_file("Path to cloud-init script: ")
        config.set_config_option(
            'launch-configuration', 'cloud_init', cloud_init)

    if not isinstance(config.lc_config.networks, list):
        networks = []
        utils.print_msg("Supply one or more networks you wish to"
                        "attach the cloud servers to", bcolors.QUESTION)
        while True:
            network = utils.get_object_from_list(
                pyrax.cloud_networks, "network", quit_option=True)
            if network and network not in networks:
                networks.append(str(network))
            elif network:
                pass
            else:
                break
        config.set_config_option('launch-configuration', 'networks', networks)

    if not config.get('launch-configuration', 'skip_default_networks'):
        print ("By default, the launch config will contain the default"
               " networks (PublicNet and ServiceNet). You can optionally"
               " disable these, but some Rackspace services will not function"
               " properly without them, and they are obligatory on Managed"
               " service levels")
        keep = utils.ask_str("Keep default networks? (y/n): ", yesno=True)
        if keep:
            config.set_config_option(
                'launch-configuration', 'skip_default_networks', False)
        else:
            config.set_config_option(
                'launch-configuration', 'skip_default_networks', True)

    if not config.get('launch-configuration', 'disk_config'):
        disk_config = utils.ask_str("Disk config method (AUTO or MANUAL): ",
                                    allowed_input=['AUTO', 'MANUAL',
                                                   'auto', 'manual'])
        config.set_config_option(
            'launch-configuration', 'disk_config', disk_config.upper())

    ##
    # Write [rax-autoscaler] config
    ##

    if not isinstance(config.ras_config.load_balancers, list):
        load_balancers = []
        utils.print_msg("Supply one or more load balancers you wish to"
                        " attach the cloud servers to", bcolors.QUESTION)
        while True:
            load_balancer = utils.get_object_from_list(
                pyrax.cloud_loadbalancers, "load balancer", quit_option=True)
            if load_balancer and load_balancer not in load_balancers:
                load_balancers.append(load_balancer)
            elif load_balancer:
                pass
            else:
                break
        config.set_config_option(
            'rax-autoscaler', 'load_balancers', load_balancers)

    if not isinstance(config.ras_config.private_key, str) or \
       not utils.is_readable(config.ras_config.private_key):
        print("When scaled up, the servers need to log in to the admin server"
              " in order to download the playbook, or perform other tasks as"
              " laid out in the cloud-init template.\nSupply a private key"
              " which can be used to log in as the user 'autoscale' on the"
              " admin server")
        private_key = utils.ask_file("Private key to inject"
                                     " into /root/.ssh/id_rsa on servers: ")
        config.set_config_option('rax-autoscaler', 'private_key', private_key)

    if not isinstance(config.ras_config.admin_server, str):
        admin_server = utils.ask_str("IP or host-name of admin server to"
                                     " download playbook from: ")
        config.set_config_option('rax-autoscaler', 'admin_server',
                                 admin_server)

    # Re-parse the file on-disk and validate
    config.parse_config()
    config.validate()


def generate_rax_as_config(config):
    input_template = os.getcwd() + '/templates/rax-autoscaler.json.j2'
    output_file = os.getcwd() + '/rax-autsocaler-config.json'
    try:
        with open(input_template, 'r') as fp:
            j2_env = Environment().from_string(fp.read())
    except IOError as ex:
        print_msg("Failed to open rax-autoscaler config template: %s" % ex,
                  bcolors.FAIL)
        exit(1)

    scale_up_policy = config.cfg.get('rax-autoscaler',
                                     'scale_up_policy').strip("'")
    scale_down_policy = config.cfg.get('rax-autoscaler',
                                       'scale_down_policy').strip("'")
    load_balancers = config.cfg.get('rax-autoscaler',
                                    'load_balancers').strip("'")
    autoscale_group = config.as_config.id.strip("'")

    t = j2_env.render(username=config.username,
                      api_key=config.api_key,
                      region=config.region,
                      autoscale_group=autoscale_group,
                      scale_up_policy=scale_up_policy,
                      scale_down_policy=scale_down_policy,
                      load_balancers=load_balancers)

    try:
        with open(output_file, 'r+') as fp:
            fp.write(t)
            print_msg("Wrote rax-autoscaler to file %s" % output_file,
                      bcolors.OKGREEN)
    except IOError as ex:
        print_msg("Failed to write rax-autoscaler config: %s" % ex,
                  bcolors.FAIL)
