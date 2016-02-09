""" Various utilities used throughout this project """
import ConfigParser
import ast
import base64
import os
import novaclient
from jinja2 import Environment
from launch_configuration import LaunchConfig
from autoscale_configuration import AutoscaleConfig
from colors import bcolors, print_msg


def config_fixup(parsed_config):
    """ This function does some post-processing on variables
        we've gathered from the config file
    """

    # Translate our human-friendly list of networks into a dictionary
    # as expected by pyrax
    networks = []
    if not parsed_config.lc_config.skip_default_networks:
        networks.append({'uuid': '11111111-1111-1111-1111-111111111111'})
        networks.append({'uuid': '00000000-0000-0000-0000-000000000000'})

    if parsed_config.lc_config.networks:
        for chosen_network in parsed_config.lc_config.networks:
            networks.append({'uuid': chosen_network})

    parsed_config.lc_config.networks = networks

    # Render the cloud-init template and populate config.lc_config.user_data
    if parsed_config.lc_config.cloud_init:
        parsed_config.lc_config.cloud_init = os.path.expanduser(
            parsed_config.lc_config.cloud_init)
        try:
            cloud_init = open(parsed_config.lc_config.cloud_init, 'r').read()
            private_key_file = os.path.expanduser(
                parsed_config.ras_config.private_key)
            private_key_data = open(
                private_key_file, 'r').read()
            b64_key = b64_strip(private_key_data)
            j2_env = Environment().from_string(cloud_init)
            t = j2_env.render(private_key=b64_key,
                              admin_server=parsed_config.ras_config.admin_server)
            parsed_config.lc_config.user_data = t
        except IOError as ex:
            raise ("Unable to read or encode cloud-init"
                   " template: %s" % ex, bcolors.FAIL)

    if not parsed_config.ras_config.load_balancers:
        parsed_config.ras_config.load_balancers = []
    else:
        parsed_config.ras_config.load_balancers = \
            set(parsed_config.ras_config.load_balancers)

    # We scale DOWN, not up
    parsed_config.as_config.scale_down *= -1 \
        if parsed_config.as_config.scale_down > 0 \
        else parsed_config.as_config.scale_down


def b64_strip(data):
    return base64.encodestring(data).replace('\n', '')


def unb64(data):
    return base64.decodestring(data)


def is_readable(file_name):
    """ Determines whether a file can be opened and read from or not
        Returns True if it can and False if not
    """
    try:
        with open(os.path.expanduser(file_name), 'r') as file_handle:
            file_handle.read(1)
    except IOError:
        return False
    return True


def get_parse_error(key, section, expected_type):
    return ("Config parsing failed, key '%s' in section '%s' is not of"
            " type %s" % (key, section, expected_type))


class AutoscalerConfig(object):
    """ Holds configuration attributes for the [rax-autoscaler] part
        of the config file. Mainly populated and used when a group
        is created or changed.
    """

    def __init__(self):
        pass
    scale_up_webhook = None
    scale_up_webhook = None
    scale_down_webhook = None
    scale_down_policy = None
    scale_up_policy = None
    load_balancers = None
    private_key = None
    admin_server = None
    num_static_servers = None

    def validate(self):
        """ Iterates over class attributes and verifies that they have been set
        during the config parsing or config writing process
        """
        # In some cases, ConfigParse will think these are strings...
        if not isinstance(self.load_balancers, list):
            raise AttributeError("Config file validation failed - key"
                                 " load_balancers is missing or has no value"
                                 " in section 'rax-autoscaler' Try re-running"
                                 " with --create-config")

        expected_strs = ['private_key', 'admin_server']
        for obj in [obj for obj in dir(self) if not obj.startswith('__')]:
            if not isinstance(getattr(
                    self, obj), str) and obj in expected_strs:
                raise AttributeError("Config file validation failed - key"
                                     " %s is missing or has no value"
                                     " in section 'rax-autoscaler'"
                                     " re-running with --create-config" % obj)


def ask_integer(msg, allowed_input=None):
    """ Prompts for input, and ensures input is an integer """
    while True:
        try:
            ret = int(raw_input(bcolors.QUESTION + msg + bcolors.ENDC))
            if allowed_input and ret in allowed_input:
                return ret
            elif allowed_input and ret not in allowed_input:
                print_msg("Answer not in range", bcolors.FAIL)
            else:
                return ret
        except ValueError:
            print_msg("Value must be a number", bcolors.FAIL)


def ask_str(msg, allowed_input=None, yesno=False):
    """ Prompts for input, and ensures input is acceptable.
        allowed_input is a list containing expected inputs.
        Optionally set yesno to True, and this function will
        be set up to expect input to a yes or no question and
        return a string containing 'yes' for a positive answer
        and None to a negative one.
    """
    if yesno:
        positive = ['yes', 'y']
        negative = ['no', 'n']
        allowed_input = positive + negative
    while True:
        ret = raw_input(bcolors.QUESTION + msg + bcolors.ENDC)
        if yesno and ret.lower() in allowed_input:
            if ret.lower() in positive:
                return 'yes'
            elif ret.lower() in negative:
                return None
            else:
                print_msg("Answer not valid", bcolors.FAIL)
                continue
        elif allowed_input and ret in allowed_input:
            return ret
        elif not allowed_input:
            return ret
        else:
            print_msg("Answer not valid", bcolors.FAIL)


def ask_file(msg):
    while True:
        file_name = ask_str(msg)
        if not is_readable(file_name):
            print_msg("Unable to open file %s for reading, please try again" %
                      file_name, bcolors.FAIL)
        else:
            return file_name


def add_new_key(pyrax):
    name = None
    while True:
        public_name = ask_str("Path to public key file: ")
        name = raw_input("Keypair name: ")
        try:
            with open(os.path.expanduser(public_name)) as keyfile:
                pyrax.cloudservers.keypairs.create(name, keyfile.read())
            break
        except IOError as ex:
            print_msg("Unable to read file: %s  Please try again..." %
                      ex, bcolors.FAIL)
        except novaclient.exceptions.Conflict:
            print_msg("A key with that name already exists", bcolors.FAIL)
    return name


def get_object_from_list(obj, name, create_new_option=False,
                         quit_option=False, extra_options=None):
    """ Takes a pyrax object and calls list() on that, and presents
        the output as a numbered list for user to choose from.
        Returns the ID part of the chosen pyrax object unless
        get_name is set to True.
    """
    cnt = 0
    index = {}
    objects = []
    try:
        # Most objects have a list_all method, but fall back to .list() if not
        objects = obj.list_all()
    except AttributeError:
        objects = obj.list()

    for entry in objects:
        cnt += 1
        print "%d - %s (%s)" % (cnt, entry.name, entry.id)
        index[cnt] = entry.id
    if extra_options:
        for k in extra_options:
            cnt += 1
            print "%d - %s" % (cnt, k)
            index[cnt] = extra_options.get(k)
    if create_new_option:
        cnt += 1
        print "%d - Create new" % cnt
        index[cnt] = None
    if quit_option:
        cnt += 1
        print "%d - Done" % cnt
        index[cnt] = None

    prompt = "Select %s: " % name
    ret = index.get(ask_integer(prompt, allowed_input=xrange(1, cnt + 1)))
    return ret


class config(object):
    """ Holds all variables related to our configuration as attributes
        Parses configuration file and populates instances of AutoscaleConfig,
        and LaunchConfig.
    """

    def __init__(self, config_file, validate=True, credentials_only=False):
        self.config_file = config_file
        self.cfg = ConfigParser.ConfigParser()
        self.read_config()
        self.as_config = AutoscaleConfig()
        self.lc_config = LaunchConfig()
        self.ras_config = AutoscalerConfig()
        self.username = None
        self.api_key = None
        self.region = None
        self.credentials_file = None

        self.parse_credentials()
        if not credentials_only:
            self.parse_config()
        if validate and not credentials_only:
            self.validate()

    def validate(self):
        self.lc_config.validate()
        self.as_config.validate()
        self.ras_config.validate()

    def get(self, section, key):
        try:
            ret = self.cfg.get(section, key)
            if isinstance(ret, str):
                return ret.strip()
            return ret
        except (ConfigParser.NoOptionError, ConfigParser.ConfigParser):
            return None

    def get_credentials(self):
        return (self.username, self.api_key, self.region)

    def set_config_option(self, section, key, value):
        """ Sets an attribute of a config class and
            writes they key and value out to the config file
            under the appropriate section
        """
        if not self.cfg.has_section(section):
            self.cfg.add_section(section)

        if isinstance(value, str) or isinstance(value, unicode):
            value = "'%s'" % value
        if section == 'autoscale':
            setattr(self.as_config, key, value)
        elif section == 'launch_configuration':
            setattr(self.lc_config, key, value)
        elif section == 'rax-autoscaler':
            setattr(self.ras_config, key, value)
        self.cfg.set(section, key, value)
        self.cfg.write(open(self.config_file, 'w'))

    def get_keys(self, section):
        ret = []
        try:
            for k, v in self.cfg.items(section):
                ret.append(k)
        except (AttributeError, ConfigParser.NoSectionError):
            return []

        return ret

    def read_config(self, config_file=None):
        """ Reads the config file into self.cfg instance """
        config_file = config_file if config_file else self.config_file
        try:
            self.cfg.readfp(open(config_file, 'r'))
        except IOError as ex:
            raise Exception("Unable to open config file: %s" % ex)

    def parse_credentials(self, config_file=None):
        if self.username and self.api_key and self.region:
            return

        config_file = config_file if config_file else self.config_file
        self.read_config(config_file)
        # We need to be able to read both our config as well as a pyrax one
        section = 'rackspace_cloud' if self.cfg.has_section('rackspace_cloud')\
                  else 'cloud'

        # First check whether credentials are specified explicitly
        try:
            self.username = self.cfg.get(section, 'username').strip("'")
            self.api_key = self.cfg.get(section, 'api_key').strip("'")
            self.region = self.cfg.get(section, 'region').strip("'")
            # We don't want to write these out to the config file...
            self.cfg.remove_section(section)
            return
        except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
            # Ignore if they aren't
            pass

        # And check for a credentials_file key, and re-parse using that file
        # if found. If it isn't, bomb out, we have no credentials
        try:
            self.credentials_file = ast.literal_eval(self.cfg.get(section,
                                                     'credentials_file'))
            self.parse_credentials(self.credentials_file)
        except ConfigParser.NoSectionError:
            print_msg("Config file %s does not contain a 'cloud' or"
                      " 'rackspace_cloud' section" % config_file,
                      bcolors.FAIL)
            exit(1)
        except ConfigParser.NoOptionError:
            print_msg("Config file %s does not contain the keys username,"
                      " api_key, region or credentials_file" % config_file,
                      bcolors.FAIL)
            exit(1)

        self.cfg.remove_section(section)

    def parse_config(self):

        self.read_config()
        conf = {}

        for section in self.cfg.sections():
            if section not in conf:
                conf[section] = {}
            for key, val in self.cfg.items(section):
                try:
                    if section == 'cloud':
                        getattr(self, key)
                        setattr(self, key, ast.literal_eval(val))

                    elif section == 'autoscale':
                        getattr(self.as_config, key)
                        setattr(self.as_config, key, ast.literal_eval(val))

                    elif section == 'launch-configuration':
                        getattr(self.lc_config, key)
                        setattr(self.lc_config, key, ast.literal_eval(val))

                    elif section == 'rax-autoscaler':
                        getattr(self.ras_config, key)
                        setattr(self.ras_config, key, ast.literal_eval(val))

                    conf[section][key] = val
                except AttributeError:
                    raise Exception("Config file parsing failed. Unknown key"
                                    " '%s' found in section '%s'" % (
                                        key, section))
                except (ValueError, SyntaxError):
                    raise Exception("Config file parsing failed. Key '%s' in"
                                    " section %s appears to have a malformed"
                                    " value (enclose strings in quotes, lists"
                                    " in [] and dictionaries in {} ): %s" % (
                                        key, section, val))
        return conf

    def get_autoscale_config(self):
        return self.as_config

    def get_launch_config(self):
        return self.lc_config
