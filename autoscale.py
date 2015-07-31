import requests
import base64

class autoscale:
    def __init__(self, config, pyrax):
        self.pyrax = pyrax
        self.config = config
        self.as_config = config.get_autoscale_config()
        self.lc_config = config.get_launch_config()
        self.autoscale = self.pyrax.autoscale

        self.scaling_group = None
        self.scale_up_policy = None
        self.scale_down_policy = None
        self.launch_config = None

        self.group_id = self.as_config.id
        if not self.group_id:
            self.create_group()
            self.launch_config = self.scaling_group.get_launch_config()

        else:
            self.scaling_group = self.autoscale.get(self.group_id)
            self.launch_config = self.scaling_group.get_launch_config()
            diffs = self.diff_group()
            if self.check_and_confirm_change(diffs):
                self.update_group(diffs.get('scaling_group', None))
                self.update_launch_config(diffs.get('launch_config', None))
                self.update_policies(diffs)

    def check_and_confirm_change(self, diffs):
        """ Checks whether there are any changes detected between
            running config and config file, and prompts whether
            to update the running config or not
        """
        if not diffs:
            return False
        resp = raw_input("Do you want to update the running config to match the config file? (y/n): ")
        if resp.lower() == 'y':
            return True
        elif resp.lower() == 'n':
            return False
        else:
            return self.check_and_confirm_change(diffs)

    def update_group(self, diffs):
        if not diffs:
            return
        self.scaling_group.update(name=self.as_config.name,
                                  cooldown=self.as_config.cooldown,
                                  min_entities=self.as_config.min_entities,
                                  max_entities=self.as_config.max_entities)


    def update_policies(self, diffs):
        if diffs.get('scale_up_policy'):
            self.update_policy(self.get_scale_up_policy(),
                               self.as_config.scale_up)
        if diffs.get('scale_down_policy'):
            self.update_policy(self.get_scale_down_policy(),
                               self.as_config.scale_down)

    def update_launch_config(self, diffs):
        if not diffs:
            return
        self.scaling_group.update_launch_config(image=self.lc_config.image,
                                                flavor=self.lc_config.flavor,
                                                disk_config=self.lc_config.disk_config,
                                                metadata=self.lc_config.metadata,
                                                load_balancers=self.lc_config.load_balancers,
                                                key_name=self.lc_config.key_name,
                                                user_data=self.get_user_data_from_file(),
                                                config_drive=self.lc_config.config_drive,
                                                networks=self.lc_config.networks)

    def update_policy(self, policy, change):
        policy.update(cooldown=self.as_config.cooldown,
                     change=change)

    def get_user_data_from_file(self):
        file_name = self.lc_config.cloud_init
        if not file_name:
            return None

        return open(file_name, 'r').read()

    def create_group(self):
        user_data = self.get_user_data_from_file()
        config_drive = True if user_data else None

        self.scaling_group = self.autoscale.create(self.as_config.name,
                      cooldown=self.as_config.cooldown,
                      min_entities=self.as_config.min_entities,
                      max_entities=self.as_config.max_entities,
                      launch_config_type=self.lc_config.type,
                      server_name=self.lc_config.name,
                      flavor=self.lc_config.flavor,
                      image=self.lc_config.image,
                      disk_config=self.lc_config.disk_config,
                      metadata=self.lc_config.metadata,
                      load_balancers=self.lc_config.load_balancers,
                      key_name=self.lc_config.key_name,
                      user_data=self.get_user_data_from_file(),
                      config_drive=self.lc_config.config_drive,
                      networks=self.lc_config.networks)

        up_policy = self.scaling_group.add_policy('scale_up', 'webhook',
                                                self.as_config.cooldown,
                                                self.as_config.scale_up)
        down_policy = self.scaling_group.add_policy('scale_down', 'webhook',
                                                self.as_config.cooldown,
                                                self.as_config.scale_down)
        up_webhook = up_policy.add_webhook('scale_up_webhook')
        down_webhook = down_policy.add_webhook('scale_down_webhook')


    def get_policies(self):
        return self.scaling_group.list_policies()

    def get_scale_up_policy(self):
        for policy in self.get_policies():
            if policy.name == 'scale_up':
                return policy
        return None

    def get_scale_down_policy(self):
        for policy in self.get_policies():
            if policy.name == 'scale_down':
                return policy
        return None

    def get_id(self):
        """ Returns the ID of the scaling group in this object
        """
        return self.scaling_group.id

    def get_webhook(self, policy):
        """  Returns the webhook object for a given policy.
        We know we only have one, since we created it.
        All bets are off if edits have been made to the policy post-setup
        """
        return policy.list_webhooks()[0]

    def get_webhook_url(self, policy):
        """ Returns string containing webhook URL for a given policy """
        endpoint = self.autoscale.management_url
        policy_id = policy.id
        group_id = self.scaling_group.id
        webhook_id = self.get_webhook(policy).id
        headers = { "x-auth-token": self.pyrax.identity.auth_token,
                    "content-type": 'application/json'}
        url = "%s/groups/%s/policies/%s/webhooks/%s" % (endpoint, group_id, policy_id, webhook_id)

        result = requests.get(url, headers=headers)
        if result.status_code != 200:
            raise Exception("Unable to get webhook URLs API returned: %s - %s" % (result.status_code, result.text))
        for url in result.json().get('webhook').get('links'):
            if url.get('rel') == 'capability':
                return url.get('href')
        return None

    def get_user_data_from_config(self):
        data = open(self.lc_config.cloud_init).read()
        return base64.decodestring(data)

    def diff_group(self):
        """ Compares an existing group with the config variables.
            Returns a tuple of dicts containing the parameters that
            are different in the scaling group and launch configuration
            from what's defined in the config file or None if they match
        """

        diffs = { "scaling_group": False,
                  "launch_config": False,
                  "scale_up_policy": False,
                  "scale_down_policy": False
        }

        # Compare autoscale configuration from file with what's on current group. scale_up and scale_down
        # are actually policy properties, not scaling group. So we handle those separately
        for key in [opt for opt in self.config.get_keys('autoscale') if not opt.startswith('scale_')]:
            if getattr(self.scaling_group, key) != getattr(self.as_config, key):
                print "Difference detected in key %s: %s != %s" % (key, getattr(self.scaling_group, key), getattr(self.as_config, key))
                diffs['scaling_group'] = True

        if self.get_scale_up_policy().change != self.as_config.scale_up:
            print "Difference detected in key scale_up: %s != %s" % (
                            self.get_scale_up_policy().change,
                            self.as_config.scale_up)
            diffs['scale_up_policy'] = True
        if self.get_scale_down_policy().change != self.as_config.scale_down:
            print "Difference detected in key scale_down: %s != %s" % (
                            self.get_scale_down_policy().change,
                            self.as_config.scale_down)
            diffs['scale_down_policy'] = True

        for key in self.launch_config:
            if key == 'load_balancers':
                if self.lc_config.load_balancers:
                    fields = ['loadBalancerId', 'port']
                    requested_lbs = [ dict(zip(fields, lb)) for lb in self.lc_config.load_balancers ]
                    if requested_lbs != self.launch_config.get(key):
                        print "Difference detected in key load_balancers: %s != %s" % (
                                self.launch_config.get(key),
                                requested_lbs)
                        diffs['launch_config'] = True
                else:
                    if [] != self.launch_config.get(key):
                        print "Difference detected in key load_balancers: %s != %s" % (
                                self.launch_config.get(key),
                                requested_lbs)
                        diffs['launch_config'] = True

            elif key == 'name':
                if str(self.launch_config.get(key)) != str(getattr(self.lc_config, key)):
                    print "Difference detected in key name: %s != %s" % (
                                self.launch_config.get(key),
                                getattr(self.lc_config, key))
                    diffs['launch_config'] = True
            else:
                if self.launch_config.get(key) != getattr(self.lc_config, key):
                    print "Difference detected in key %s: %s != %s" % (
                                key,
                                self.launch_config.get(key),
                                getattr(self.lc_config, key))
                    diffs['launch_config'] = True

        if any(k[1] for k in diffs.iteritems()):
            return diffs
        return None



