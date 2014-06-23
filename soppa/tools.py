import os, sys, inspect
from importlib import import_module
import fnmatch

from soppa.fmt import formatloc

def here(path=None, fn=None, instance=None):
    """ Evaluate path relative to where function was called
    fn = provide scope ('source')
    """
    if instance:
        calling_file = inspect.getfile(instance.__class__)
    elif fn:
        calling_file = fn
    else:
        calling_file = inspect.getfile(sys._getframe(1)) # relative or absolute return value
    calling_file = os.path.abspath(calling_file)
    subfolder = path.lstrip('/') if path else ''
    return os.path.join(os.path.dirname(calling_file), subfolder)

def import_string(dotted_path):
    """ Import something, eg. 'soppa.pip', or 'x.y.z' """
    try:
        module_path, class_name = dotted_path.rsplit('.', 1)
    except (ValueError, AttributeError) as e:
        module_path = dotted_path
    try:
        return import_module(dotted_path)
    except ImportError, e:
        module = import_module(module_path)
        try:
            return getattr(module, class_name)
        except ImportError, e:
            log.debug(e)

class Upload(object):
    """ Upload a template """
    def __init__(self, frm, to, instance, caller_path):
        self.env = instance.get_ctx()
        self.args = (frm, to)
        self.caller_path = caller_path

        self.up()

    def find(self, path, needle):
        matches = []
        for root, dirnames, filenames in os.walk(path):
            for filename in fnmatch.filter(filenames, needle):
                matches.append(os.path.join(root, filename))
        return matches

    def choose_template(self):
        filename = self.args[0].split('/')[-1]
        filepath = '{0}{1}'.format(self.caller_path, self.args[0])
        rs = []
        def wrapper(p):
            if p.startswith('/'):
                return p
            p = os.path.join(self.env['local_project_root'], p)
            return p
        for k in self.env['config_dirs']:
            rs += self.find(wrapper(k), filename)
        if rs:
            filepath = '{0}'.format(rs[0])
        return filepath

    def up(self):
        from_path = formatloc(self.args[0], self.env)
        if not from_path.startswith('/'):
            filepath = self.choose_template()
            self.args = (filepath,) + self.args[1:]
        self.args = tuple([formatloc(k, self.env) for k in self.args])

class LocalDict(dict):
    """ Format variables against context on return """
    def __getattr__(self, key):
        try:
            if key.startswith('__'):
                return self[key]
            return formatloc(self[key], self)
        except KeyError:
            # to conform with __getattr__ spec
            raise AttributeError(key)

    def __setattr__(self, key, value):
        self[key] = value
