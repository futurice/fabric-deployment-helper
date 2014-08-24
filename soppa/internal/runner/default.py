import os, copy
from pprint import pprint as pp
import itertools

from fabric.api import env, execute, task

from soppa.internal.mixins import DeployMixin, NeedMixin
from soppa.internal.tools import import_string
from soppa.internal.logs import dlog

class Runner(DeployMixin, NeedMixin):
    """
    A Runner allows more control over deployments that share multiple modules,
    by centralizing things like eg. service restarts
    """
    needs = ['soppa.operating',
            'soppa.remote',
            'soppa.git',]
    def __init__(self, config={}, hosts={}, roles={}, recipe={}, *args, **kwargs):
        super(Runner, self).__init__(*args, **kwargs)
        self.config = config
        if not self.config.get('defer_handlers'):
            self.config['defer_handlers'] = '*'
        self.hosts = hosts
        self.roles = roles
        self.recipe = recipe

    _modules = None
    def get_module_classes(self):
        if not self._modules:
            modules = []
            for m in self.current_recipe.get('modules', []):
                module = import_string(m)
                name = m.split('.')[-1]
                fn = getattr(module, name)
                modules.append(fn)
            self._modules = modules
        return self._modules
    
    def get_module(self):
        return self.get_modules()[0]

    def get_roles_for_host(self, name):
        print "GET_ROLES",name,self.roles
        roles = []
        for k,v in self.roles.iteritems():
            if name in v.get('hosts', []):
                roles.append(k)
        return roles

    def get_hosts_for(self, name):
        """ resolve roles to hosts """
        def as_list(data):
            if isinstance(data, basestring):
                data = [data]
            return list(data)
        all_hosts = list(set(itertools.chain.from_iterable([as_list(v['hosts']) for k,v in self.roles.iteritems()])))
        if name in ['*', 'all']:
            return list(all_hosts)
        if self.roles.get(name):
            return as_list(self.roles[name].get('hosts', []))
        return name

    def run(self):
        """ A run lives in a Fabric execution (env.host_string) context """
        print "RUN: {}".format(self)
        if not all([self.get_hosts_for(ingredient['roles']) for ingredient in self.recipe]):
            raise Exception("No hosts configured for {}".format(ingredient))

        for ingredient in self.recipe:
            pp(ingredient)
            hosts = self.get_hosts_for(ingredient['roles'])
            modules = ingredient['modules']
            # create a new standalone instance for execution
            runner = Runner(
                    config=self.config,
                    hosts=self.hosts,
                    roles=self.roles,
                    recipe=self.recipe)
            runner.current_recipe = ingredient
            execute(runner._run, hosts=hosts)

    def _run(self, ingredient={}):
        """ At this point in time execution is on a specific host. Configuration prepared accordingly """
        print "host_string: {}, recipe: {}".format(env.host_string, self.current_recipe)
        config = copy.deepcopy(self.config)
        # Configuration: hosts > roles > config > classes
        role_config = {}
        for role in self.get_roles_for_host(env.host_string):
            role_config.update(self.roles[role].get('config', {}))
        config.update(role_config)
        config.update(self.hosts.get(env.host_string, {}))

        needs_all = set()
        module_classes = self.get_module_classes()
        # instantiate with configuration
        modules = []
        for module in module_classes:
            modules.append(module(config))

        if not modules:
            print "Nothing to do, exiting."
            return

        self.ask_sudo_password(modules[0], capture=False)
        
        # configure, prepare dependent modules
        for module in modules:
            needs = module.get_needs()
            for need in needs:
                needs_all.add(need)

            if module.project:
                module.dirs()
            module.ownership()

            # configure everything
            self.configure(needs)

            # setup everything, except self
            for need in needs:
                need.setup_needs()

        # configure self (modules)
        for module in modules:
            self.configure([module])
            self.packages(module)

        # setup self (modules)
        for module in modules:
            module.setup()

        self.restart(needs_all)

    def configure(self, needs):
        """ Prepare pre-requisitives a module has, before it can be setup """
        newProject = False
        for need in needs:
            if not os.path.exists(os.path.join(need.soppa.local_conf_path)):
                newProject = True
            need.configure()
            need.copy_configuration()

        if newProject:
            raise Exception("""NOTICE: Default Configuration generated into {}.
            Review settings and configure any changes. Next run is live""".format('$local_conf_path'))

    def packages(self, module):
        """ Package handling bundled between all modules, executed once per server.
        - Runner needs packages instances
        """
        pm = module.packman()
        packages = pm.get_packages()
        pm.write_packages(packages)
        pm.download_packages(packages)
        pm.sync_packages(packages)
        pm.install_packages(packages)

    def ask_sudo_password(self, module, capture=False):
        if module.env.get('password') is None:
            print "SUDO PASSWORD PROMPT (leave blank, if none needed)"
            module.env.password = getpass.getpass('Sudo password ({0}):'.format(env.host))

    def restart(self, needs):
        for k,v in dlog.data['hosts'][env.host_string].iteritems():
            if k == 'all':
                for deferred in v.get('defer'):
                    # TODO: instance == instance method
                    handler, instance, data = deferred
                    if data['modified']:
                        instance()
                        #instance.restart()
