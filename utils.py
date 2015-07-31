import ConfigParser
import utils
import ast
import base64

def merge_config(config, pyrax):
    """ This functions translates human input to structures used by Pyrax,
        translates human readable names to UUIDs etc.
    """
    networks = []
    num_default_networks = 0
    if not config.lc_config.skip_default_networks:
        num_default_networks = 2
        networks.append({ 'uuid': '11111111-1111-1111-1111-111111111111'})
        networks.append({ 'uuid': '00000000-0000-0000-0000-000000000000'})

    if config.lc_config.networks:
        requested_networks = config.lc_config.networks.strip().split(',')
        nws = pyrax.cloud_networks
        available_networks = nws.list()
        networks +=[ { 'uuid': str(net.id) } for net in available_networks if net.name in requested_networks  ]

        if len(networks) < len(requested_networks)+num_default_networks:
            raise Exception("One or more requested networks were not found")

    config.lc_config.networks = networks

    # We read loadbalancers in as a string in parse_config, but need it as list of tuples for pyrax
    if config.lc_config.load_balancers:
        load_balancers = config.lc_config.load_balancers
        config.lc_config.load_balancers = []
        for lb in load_balancers.strip('"').split(','):
            (lb_id, port) = lb.strip().split(':')
            config.lc_config.load_balancers.append((int(lb_id), int(port)))

    # We scale DOWN, not up
    config.as_config.scale_down *= -1 if config.as_config.scale_down > 0 else config.as_config.scale_down


class as_config:
    name = None
    id = None
    scale_up = None
    scale_down = None
    max_entities = None
    min_entities = None

    def validate(self):
        ok_missing = ['id']
        for obj in [ obj for obj in dir(utils.as_config) if not obj.startswith('__') and obj not in ok_missing]:
            if getattr(self, obj) is None:
                raise Exception("Config file parsing failed - key %s missing or has no value" % obj)

class launch_config:
    name = None
    networks = None
    load_balancers = None
    key_name = None
    disk_config = 'MANUAL'
    cloud_init = None
    metadata = {'rax-autoscaler-setup': '1.0'}
    flavor = None
    image = None
    user_data = None
    config_drive = None
    skip_default_networks = False
    type = 'launch_server'

    def validate(self):
        if not isinstance(self.skip_default_networks, bool):
            raise Exception("Config file parsing failed - key skip_default_networks must be a boolean!")
        ok_missing = ['user_data', 'config_drive', 'load_balancers', 'networks']
        for obj in [ obj for obj in dir(utils.launch_config) if not obj.startswith('__') and obj not in ok_missing]:
            if getattr(self, obj) is None:
                raise Exception("Config file parsing failed - key %s missing or has no value" % obj)
        if self.cloud_init:
            self.config_drive = True

class autoscaler_config:
    scale_up_webhook = None

class config:

    def __init__(self, config_file=None):
        self.config_file = config_file if config_file else './config.ini'
        self.cfg = ConfigParser.ConfigParser()
        self.as_config = utils.as_config()
        self.lc_config = utils.launch_config()
        self.config = self.parse_config(self.config_file)

        self.as_config.validate()
        self.lc_config.validate()

        self.set_user_data()

        self.username = None
        self.api_key = None
        self.region = None
        self.set_credentials()


        if any(not var for var in [self.username, self.api_key, self.region]):
            raise Exception("Unable to obtain cloud credentials. "
                            "Please check your INI file and specify username and api_key "
                            "or credentials_file under the [cloud] section")

    def get(self, section, key):
        if self.has_section(section):
            ret = self.config.get(section).get(key, None)
            if isinstance(ret, str):
                return ret.strip()
            return ret
        return None

    def get_credentials(self):
        return (self.username, self.api_key, self.region)

    def get_section(self, section):
        return self.config.get(section, None)

    def set_credentials(self):
        """ Credentials can either be given with username and api_key
        in the ini-file, or through a credentials file. This function sets
        self.username and self.api_key accordingly, so other functions can
        work independently of how credentials were obtained
        """
        if self.username and self.api_key and self.region:
            return

        # Explicitly defined username and api_key trumps credentials_file 
        username = self.get('cloud', 'username')
        api_key = self.get('cloud', 'api_key')
        region = self.get('cloud', 'region')
        if username and api_key and region:
            self.username = username
            self.api_key = api_key
            self.region = region
            return

        credentials_file = self.get('cloud', 'credentials_file')
        if not credentials_file:
            return

        credentials = self.parse_config(credentials_file)
        try:
            self.username = credentials.get('rackspace_cloud').get('username')
            self.api_key = credentials.get('rackspace_cloud').get('api_key')
            self.region = credentials.get('rackspace_cloud').get('region')
        except AttributeError:
            return

    def set_config_option(self, section, key, value):
        if not self.has_section(section):
            self.cfg.add_section(section)
            self.config[section] = {}
        self.cfg.set(section, key, value)
        self.config[section][key] = value
        self.cfg.write(open(self.config_file, 'w'))

    def get_keys(self, section):
        try:
            return self.config.get(section).keys()
        except Exception as e:
            return None

    def has_section(self, section):
        try:
            return self.config.has_key(section)
        except AttributeError:
            return False

    def parse_config(self, config_file):
        config = {}
        try:
            self.cfg.readfp(open(config_file, 'r'))
            for section in self.cfg.sections():
                for key, val in self.cfg.items(section):
                    if section == 'autoscale':
                        try:
                            setattr(self.as_config, key, ast.literal_eval(val))
                        except (ValueError, SyntaxError):
                            raise Exception("Config file parsing failed. Key '%s' appears to have a malformed value (enclose strings in '): %s" % (key, val))
                    elif section == 'launch-configuration':
                        try:
                            if key == 'load_balancers':
                                setattr(self.lc_config, key, str(val))
                                # ast.literal_eval can't handle the format we get load balancers in
                            else:
                                setattr(self.lc_config, key, ast.literal_eval(val))
                        except (ValueError, SyntaxError):
                            raise Exception("Config file parsing failed. Key '%s' appears to have a malformed value (enclose strings in '): %s" % (key, val))

                    if not config.has_key(section):
                        config[section] = {}
                    config[section][key] = val
        except IOError:
            return None
        return config

    def set_user_data(self):
        try:
            data = open(self.lc_config.cloud_init).read()
            # This is how we get it back from pyrax
            self.lc_config.user_data = str(base64.encodestring(data).replace('\n',''))
        except Exception:
            print "Unable to read cloud-init file %s" % self.lc_config.cloud_init
            exit(1)

    def get_autoscale_config(self):
        return self.as_config

    def get_launch_config(self):
        return self.lc_config

