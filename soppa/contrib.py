import os, sys, copy, re
from contextlib import contextmanager
import inspect

# import and prefix fabric functions to not inadvertedly use them
from fabric.api import cd as fabric_cd, local as fabric_local, run as fabric_run, sudo as fabric_sudo, task as fabric_task, put as fabric_put, execute as fabric_execute, hide as fabric_hide, lcd as fabric_lcd, get as fabric_get, put as fabric_put
from fabric.contrib.files import exists as fabric_exists
from fabric.context_managers import prefix as fabric_prefix, settings
from fabric.decorators import with_settings
from fabric.operations import prompt as fabric_prompt

from soppa import *
from soppa.fmt import formatloc
from soppa.tools import import_string, Upload, LocalDict

env.possible_bugged_strings = []
env.ctx_failure = []

class Soppa(object):
    # static
    soppa_modules_installed = set()
    needs = []
    packages = {}

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        # class(dict()) == class(ctx=dict())
        if self.args\
                and isinstance(self.args[0], dict)\
                and len(self.args)==1\
                and not self.kwargs.get('ctx'):
            self.kwargs['ctx'] = self.args[0]

        Soppa.soppa_modules_installed.add(self.get_name())

        # Configuration
        context = LocalDict()
        # global variables, if not available
        # TODO: scope to self.env, in templates {env.X} ?
        envcopy = {}
        for k,v in env.iteritems():
            if not hasattr(self, k):
                envcopy[k] = v
        context.update(**envcopy)

        # parent variables
        context.update(**kwargs.get('ctx_parent', {}))

        # Do not pass internal Soppa variables onward from parent
        ignored_internal_variables = ['needs', 'packages']
        for k in ignored_internal_variables:
            if context.get(k):
                del context[k]

        # global class variables
        context.update(**env.ctx.get(self.get_name(), {}))

        # instance variables
        context.update(**kwargs.get('ctx', {}))

        # set initial state based on context
        for k,v in context.iteritems():
            # TODO: throw exception, if settings a needs=[] var
            setattr(self, k, v)

    def parent_context(self):
        """ Context to pass onto dependencies """
        c = {
            'project': self.project,
        }
        return c

    # Local extensions to Fabric
    def local_sudo(self, cmd, capture=True, **kwargs):
        """
        with bash -l virtualenv-wrapper not activate
        sudo -E required for environment variables to be passed in
        """
        cmd = cmd.replace('"','\\"').replace('$','\\$')
        return self.local('sudo -E -S -p \'sudo password:\' /bin/bash -c "{0}"'.format(cmd), capture=capture, **kwargs)

    def local_put(self, local_path, remote_path, capture=True, **kwargs):
        if kwargs.get('use_sudo'):
            return self.sudo('cp {0} {1}'.format(local_path, remote_path))
        kw = dict(
                capture=kwargs.get('capture', True),
                shell=kwargs.get('shell', None))
        return self.local('cp {0} {1}'.format(local_path, remote_path), **kw)
    local_get = local_put

    # Fabric API
    def hide(self, *groups):
        return fabric_hide(*groups)

    def sudo(self, command, *args, **kwargs):
        if env.local_deployment:
            return self.local_sudo(command, *args, **kwargs)
        return fabric_sudo(self.fmt(command), *args, **kwargs)

    def run(self, command, **kwargs):
        if env.local_deployment:
            return self.local(command, **kwargs)
        if kwargs.get('use_sudo'):
            return self.sudo(command, **kwargs)
        else:
            return fabric_run(self.fmt(command), **kwargs)

    def local(self, command, capture=False, shell=None):
        return fabric_local(self.fmt(command), capture=capture, shell=shell)

    def put(self, local_path, remote_path, **kwargs):
        local_path = getattr(local_path, 'name', local_path)
        if env.local_deployment:
            return self.local_put(self.fmt(local_path), self.fmt(remote_path), **kwargs)
        if env.get('use_sudo'):
            kwargs['use_sudo'] = True
        return fabric_put(self.fmt(local_path), self.fmt(remote_path), **kwargs)

    # NOTE: get collides with Python dictionaries
    def get_file(self, remote_path, local_path, **kwargs):
        local_path = getattr(local_path, 'name', local_path)
        if env.local_deployment:
            return self.local_get(self.fmt(remote_path), self.fmt(local_path), **kwargs)
        if env.use_sudo:
            kwargs['use_sudo'] = True
        return fabric_get(self.fmt(remote_path), self.fmt(local_path), **kwargs)

    def cd(self, path):
        return fabric_cd(self.fmt(path))

    def prefix(self, command):
        return fabric_prefix(self.fmt(command))

    def exists(self, path, use_sudo=False, verbose=False):
        return fabric_exists(self.fmt(path), use_sudo=use_sudo, verbose=verbose)
    
    # END Fabric API

    @contextmanager
    def mlcd(self, path):
        """ Really move to a local directory, unlike lcd """
        calling_file = inspect.getfile(sys._getframe(2))
        d = here(path, fn=calling_file)
        try:
            yield os.chdir(d)
        finally:
            os.chdir(self.fmt('{basedir}'))

    def has_need(self, string):
        return any([string == k.split('.')[-1] for k in self.needs])

    def find_need(self, string):
        for k in self.needs:
            if re.findall(string, k):
                return k
        return None

    def install_packages(self, recipe):
        for k,v in recipe.env.get('packages', {}).iteritems():
            print "Installing recipe packages",recipe,v
            if k=='pip':
                if isinstance(v, basestring): # requirements.txt
                    source = here(instance=recipe)
                    rpath = os.path.join(source, v)
                    self.pip.prepare_python_packages(rpath)
                elif isinstance(v, list): # list of packages
                    self.pip.prepare_python_packages(v)
                else:
                    raise Exception("unknown pip listing format")
            if k=='apt':
                if isinstance(v, basestring):
                    v = [v]
                if not env.TESTING:
                    if self.operating.is_linux():
                        self.apt.update()
                        self.apt.install(v)

    def install_all_packages(self):
        recipe = self
        self.install_packages(self)
        for recipe in self.get_needs():
            self.install_packages(recipe)
        if not self.TESTING:
            self.pip.synchronize_python_packages()

    def add_need(self, string):
        """ Add additional 'need' dynamically """
        self.needs.append(string)
        self.get_and_load_need(string)

    def fmt(self, string, **kwargs):
        """ Format a string.
        self.fmt(string) vs string.format(**self.get_ctx())
        self.fmt(string, foo=2) vs string.format(foo=2, **self.get_ctx())
        """
        ctx = self.get_ctx(**kwargs)
        result = formatloc(string, ctx)
        possible_unfilled_vars = ('{' in result)
        if possible_unfilled_vars:
            env.possible_bugged_strings.append([string,result])
        return result

    def up(self, frm, to, ctx={}):
        """ Upload a template, with arguments relative to calling path """
        caller_path = here(fn=inspect.getfile(sys._getframe(1)))
        upload = Upload(frm, to, instance=self, caller_path=caller_path)
        self.template.up(*upload.args, context=self.get_ctx(**ctx))

    def setup(self):
        return {}

    def get_name(self):
        return self.__class__.__name__.lower()

    def get_class_settings(self):
        """ Get all class and instance variables.
        - __dict__ is not enough.
        """
        rs = {}
        def is_valid(key, value):
            # TODO: only allow strings, numbers?
            if not key.startswith('__')\
                and not inspect.ismethod(value)\
                and not inspect.isfunction(value)\
                and not inspect.isclass(value):
                return True
            return False
        values = inspect.getmembers(self)
        for key,value in values:
            if is_valid(key, value):
                rs[key] = value
        return rs

    def get_ctx(self, **kwargs):
        rs = LocalDict()
        self.get_needs()
        rs.update(**self.get_class_settings())
        rs.update(**kwargs)
        return rs
    
    def get_needs(self):
        """ Assigns dependencies to instance, and returns as list """
        rs = []
        for k in self.needs:
            name = k.split('.')[-1]
            rs.append(getattr(self, name))
        return rs

    def settings(self):
        return {}

    def apply_settings(self, action=None):
        """ package settings are defaults, that globals can override """
        defaults = self.get_ctx()
        if defaults.get('required_settings'):
            if not all([getattr(env, k, False) for k in defaults.required_settings]):
                raise Exception("Configuration required")
        if defaults.get('actions'):
            if not action in defaults.actions:
                raise Exception("Usage: {0}:{1}".format(self.get_name(), '|'.join(defaults.actions)))

    def cli_interface(self, action=None, *args, **kwargs):
        raise Exception("TODO")

    def get_need(self, name):
        for k in self.needs:
            if k.endswith(name):
                return k
        return None

    def get_and_load_need(self, key, *args, **kwargs):
        """ On-demand needs=[] resolve """
        # remove instance specific kwargs.ctx
        name = key.split('.')[-1]
        module = import_string(key)
        fn = getattr(module, name)

        instance = fn(ctx_parent=self.parent_context())
        setattr(self, name, instance)

        return instance

    def __getattr__(self, key):
        try:
            return self.__dict__[key]
        except:
            # lazy-load dependencies
            if self.has_need(key):
                return self.get_and_load_need(self.find_need(key),
                        *self.args,
                        **self.kwargs)
            raise

    def __unicode__(self):
        return unicode(self.get_name())

def register(klass, *args, **kwargs):
    """ Add as Fabric task, to be visible in 'fab -l' listing """
    name = klass.__name__.lower()

    fabric_task = None
    def task_instantiate():
        klass().cli_interface()

    fabric_task = task(name=name)(task_instantiate)

    return fabric_task, klass

