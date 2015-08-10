import utils


class AutoscaleConfig(object):
    """ Holds configuration attributes for the [autoscale] part
        of the config file. Describes the desired autoscale group
        configuration.
    """

    def __init__(self):
        pass
    name = None
    id = None
    scale_up = None
    scale_down = None
    max_entities = None
    min_entities = None
    cooldown = None

    def validate(self):
        """ Iterates over class attributes and verifies that they have been set
        during the config parsing or config writing process
        """
        ok_missing = ['id']
        expected_ints = ['scale_up', 'scale_down', 'max_entities',
                         'min_entities', 'cooldown']
        for obj in [obj for obj in dir(self)
                    if not obj.startswith('__') and obj not in ok_missing]:
            if getattr(self, obj) is None:
                raise AttributeError(
                    "Config file parsing failed - key %s missing or has no"
                    " value in section 'autoscale' Try re-running"
                    " with --create-config" % obj)
            if not isinstance(getattr(self, obj), int) \
               and obj in expected_ints:
                raise AttributeError(utils.get_parse_error(obj, 'autoscale',
                                                           'int'))
        if not isinstance(self.name, str):
            raise AttributeError(utils.get_parse_error('name', 'autoscale',
                                                       'str'))

        return True

