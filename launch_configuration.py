import utils

class LaunchConfig(object):
    """ Holds configuration attributes for the [launch-configuratoin] part
        of the config file. Describes the desired launch configuration
        configuration.
    """

    def __init__(self):
        pass
    name = None
    networks = None
    key_name = None
    disk_config = None
    cloud_init = ''
    metadata = {'rax-autoscaler-setup': '1.0',
                'build_config': 'rack_user_only, monitoring_agent_only'}
    flavor = None
    image = None
    user_data = None
    config_drive = True
    skip_default_networks = None
    type = 'launch_server'

    def validate(self):
        """ Iterates over class attributes and verifies that they have been set
        during the config parsing or config writing process
        """

        ok_missing = ['user_data', 'networks']
        for obj in [obj for obj in dir(self) if not
                    obj.startswith('__') and obj not in ok_missing]:
            if getattr(self, obj) is None:
                raise AttributeError("Config file parsing failed - key %s"
                                     " is missing or has no value in section"
                                     " 'launch-configuration'"
                                     " Try re-running with --create-config" %
                                     obj)

        if not isinstance(self.metadata, dict):
            raise AttributeError(utils.get_parse_error('metadata',
                                                       'launch-configuration',
                                                       'dictionary'))
        if not isinstance(self.image, str):
            raise AttributeError(utils.get_parse_error('image',
                                                       'launch-configuration',
                                                       'string'))

        if not isinstance(self.networks, list):
            raise AttributeError(utils.get_parse_error('networks',
                                                       'launch-configuration',
                                                       'list'))

        if not isinstance(self.skip_default_networks, bool):
            raise AttributeError(utils.get_parse_error('skip_default_networks',
                                                       'launch-configuration',
                                                       'boolean'))

        if self.cloud_init and self.cloud_init is not '':
            if not utils.is_readable(self.cloud_init):
                raise AttributeError(
                    "Config file validation failed cloud_init"
                    " file not readable")
            self.config_drive = True
        else:
            self.cloud_init = None
        return True


