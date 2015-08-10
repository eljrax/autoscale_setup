import requests
import utils
import difflib
from colors import bcolors
from colors import print_msg


class autoscale:

    def __init__(self, config, pyrax):
        self.pyrax = pyrax
        self.config = config
        self.as_config = config.get_autoscale_config()
        # Launch config as read from the config file
        self.lc_config = config.get_launch_config()
        self.autoscale = self.pyrax.autoscale

        self.scaling_group = None
        self.scale_up_policy = None
        self.scale_down_policy = None
        # Launch config set on the scaling group
        self.launch_config = None

        self.group_id = self.as_config.id
        if not self.group_id:
            self.create_group()
            self.launch_config = self.scaling_group.get_launch_config()
            print_msg("Created - %s - %s " %
                      (self.scaling_group.name, self.scaling_group.id),
                      bcolors.OKGREEN)

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
        return utils.ask_str("Do you want to update the running"
                             " config to match the config file? (y/n): ",
                             yesno=True)

    def update_group(self, diffs):
        if not diffs:
            return
        try:
            self.scaling_group.update(name=self.as_config.name,
                                      cooldown=self.as_config.cooldown,
                                      min_entities=self.as_config.min_entities,
                                      max_entities=self.as_config.max_entities)
            print_msg("Group successfully updated", bcolors.OKGREEN)
        except Exception as ex:
            print_msg("Failed to update group - %s" % ex, bcolors.FAIL)

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
                                                server_name=self.lc_config.name,
                                                flavor=self.lc_config.flavor,
                                                disk_config=self.lc_config.disk_config,
                                                metadata=self.lc_config.metadata,
                                                key_name=self.lc_config.key_name,
                                                user_data=self.lc_config.user_data,
                                                config_drive=self.lc_config.config_drive,
                                                networks=self.lc_config.networks)

    def update_policy(self, policy, change):
        policy.update(cooldown=self.as_config.cooldown,
                      change=change)

    def get_user_data_from_file(self):
        file_name = self.lc_config.cloud_init
        if not file_name:
            return None
        if not utils.is_readable(file_name):
            print_msg("Can't open cloud-init file %s for reading" %
                      file_name, bcolors.FAIL)
        return open(file_name, 'r').read()

    def create_group(self):
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
                                                   key_name=self.lc_config.key_name,
                                                   user_data=self.lc_config.user_data,
                                                   config_drive=self.lc_config.config_drive,
                                                   networks=self.lc_config.networks)

        up_policy = self.scaling_group.add_policy('scale_up', 'webhook',
                                                  self.as_config.cooldown,
                                                  self.as_config.scale_up)
        down_policy = self.scaling_group.add_policy('scale_down', 'webhook',
                                                    self.as_config.cooldown,
                                                    self.as_config.scale_down)
        up_policy.add_webhook('scale_up_webhook')
        down_policy.add_webhook('scale_down_webhook')

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
        """ Returns the ID of the scaling group in this object """
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
        headers = {"x-auth-token": self.pyrax.identity.auth_token,
                   "content-type": 'application/json'}
        url = "%s/groups/%s/policies/%s/webhooks/%s" % (
              endpoint,
              group_id,
              policy_id,
              webhook_id)

        result = requests.get(url, headers=headers)
        if result.status_code != 200:
            raise Exception("Unable to get webhook URLs API returned: "
                            "%s - %s" % (result.status_code, result.text))
        for url in result.json().get('webhook').get('links'):
            if url.get('rel') == 'capability':
                return url.get('href')
        return None

    def diff_autoscale(self):
        """ Compare autoscale configuration from file with what's on current
            group. scale_up and scale_down
            are actually policy properties, not scaling group.
            So we handle those separately
        """
        diff_found = False
        autoscale_keys = [key for key in self.config.get_keys('autoscale')
                          if not key.startswith('scale_')]
        for key in autoscale_keys:
            if getattr(self.scaling_group, key) !=\
               getattr(self.as_config, key):
                print_msg("Difference detected in key %s: %s != %s" % (key,
                                                                       getattr(
                                                                           self.scaling_group, key),
                                                                       getattr(self.as_config, key)),
                          bcolors.FAIL)
                diff_found = True
        return diff_found

    def diff_scale_up_policy(self):
        diff_found = False
        policy = self.get_scale_up_policy()
        if int(policy.change) != int(self.as_config.scale_up):
            print_msg("Difference detected in key scale_up: %s != %s" % (
                      policy.change,
                      self.as_config.scale_up),
                      bcolors.FAIL)
            diff_found = True
        return diff_found

    def diff_scale_down_policy(self):
        diff_found = False
        policy = self.get_scale_down_policy()
        if int(policy.change) != int(self.as_config.scale_down):
            print_msg("Difference detected in key scale_down: %s != %s" % (
                      policy.change,
                      self.as_config.scale_down),
                      bcolors.FAIL)
            diff_found = True
        return diff_found

    def diff_launch_config(self):
        diff_found = False
        for key in self.launch_config:
            if key == 'name':
                if str(self.launch_config.get(key)) != \
                   str(getattr(self.lc_config, key)):
                    print_msg("Difference detected in key name in section"
                              " 'launch-configuration': %s != %s" % (
                                  self.launch_config.get(key),
                                  getattr(self.lc_config, key)),
                              bcolors.FAIL)
                    diff_found = True
            elif key == 'load_balancers':
                # We don't let Autoscale manage load balancers for us
                pass
            elif key == 'user_data':
                if getattr(self.lc_config, (key)) \
                        != utils.unb64(self.launch_config.get(key)):
                    print_msg("Difference detected in key user_data in section"
                              " launch-configuration' (new config at the"
                              " bottom):", bcolors.FAIL)
                    ud_diffs = difflib.context_diff(
                        utils.unb64(self.launch_config.get(key)).splitlines(),
                        getattr(self.lc_config, (key)).splitlines())
                    for a in ud_diffs:
                        print a

                    diff_found = True

            else:
                if self.launch_config.get(key) != getattr(self.lc_config, key):
                    print_msg("Difference detected in key %s in section"
                              " 'launch-configuration': %s != %s" % (
                                  key,
                                  self.launch_config.get(key),
                                  getattr(self.lc_config, key)),
                              bcolors.FAIL)
                    diff_found = True
        return diff_found

    def diff_group(self):
        """ Compares an existing group with the config variables.
            Returns a tuple of dicts containing the parameters that
            are different in the scaling group and launch configuration
            from what's defined in the config file or None if they match
        """

        diffs = {}
        diffs['scaling_group'] = self.diff_autoscale()
        diffs['scale_up_policy'] = self.diff_scale_up_policy()
        diffs['scale_down_policy'] = self.diff_scale_down_policy()
        diffs['launch_config'] = self.diff_launch_config()

        if any(k[1] for k in diffs.iteritems()):
            return diffs

        print_msg("Running scaling group config matches"
                  " that of config file...", bcolors.OKGREEN)
        return None
