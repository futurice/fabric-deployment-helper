import unittest, copy, os
import shutil

from soppa.ingredients import *
from soppa.alias import mlcd
from soppa.local import aslocal

from .moda import moda
from .modb import modb
from .modc import modc

env.TESTING = True

class BaseSuite(unittest.TestCase):
    pass

TARGET_TO_SPOIL="""
something here
"""

SAMPLE_SPOIL="""

#=target.operations.api.run
i am
in the code
#>

#=target.operations.api.sudo
hello world
#>
"""

SAMPLE_SPOIL_UPDATE="""
#=target.operations.api.sudo
hello sunny world
#>
"""

class TaskClass(object):
    def task_method(self):
        return 50
taskclass = TaskClass()

@task
def my(cmd=None):
    return 60

@task
def seq(a, b):
    return '{0}={1}'.format(a, b)

def three():
    return 3

class SoppaTest(BaseSuite):
    def setUp(self):
        self.base = copy.deepcopy(env)

    def tearDown(self):
        env = self.base

    def test_mlcd(self):
        base_dir = os.getcwd()
        there = here()
        with mlcd('../soppa/supervisor/'):
            self.assertEquals(os.getcwd(), os.path.join(base_dir, 'soppa/supervisor'))
            self.assertEquals(os.getcwd(), os.path.normpath(os.path.join(there, '../soppa/supervisor/')))

    def test_scoped_env(self):
        p = pip()
        v = virtualenv()
        v.is_active = True
        self.assertEquals(
                '{virtualenv.is_active}'.format(**p.get_ctx()),
                str(v.is_active))
        self.assertTrue(p.virtualenv.is_active)
        self.assertTrue(v.is_active)
        self.assertTrue(p.get_ctx()['packages_to'])

    def test_formatting(self):
        self.assertEquals(formatloc('{foo}{bar}', {}), '{foo}{bar}')
        ctx = {'foo':'FOO'}
        self.assertEquals(formatloc('{foo}{bar}', ctx), 'FOO{bar}')
        self.assertEquals(formatloc('{foo}{bar}', ctx, bar='BAR'), 'FOOBAR')

        ctx['foo'] = '{bar}'
        self.assertEquals(formatloc('{foo}', ctx), '{bar}')
        ctx['bar'] = '{town}'
        self.assertEquals(formatloc('{foo}', ctx), '{town}')
        ctx['town'] = 'Helsinki'
        self.assertEquals(formatloc('{foo}', ctx), 'Helsinki')

        self.assertEquals(formatloc('{foo_bar}', {'foo_bar': 'oh'}), 'oh')
        c = {'foo': LocalDict({'bar': 'oh.oh'})}
        self.assertEquals(formatloc('{foo.bar}', c), 'oh.oh')

        u = Upload('config/statsd_supervisor.conf', '{packages_from}', instance=pip(), caller_path='/tmp/')
        self.assertTrue(all('{' not in k for k in u.args))

        s = 'mkdir -p {basepath}{packages,releases,media,static,dist,logs,config/vassals/,pids,cdn}'
        self.assertTrue('/x/' in formatloc(s, dict(basepath='/x/')))

    def test_formatting_bash(self):
        ctx = {'foo': 'FOO'}
        self.assertEquals(formatloc('{foo} {"print $2"}', ctx), 'FOO {"print $2"}')
        self.assertEquals(formatloc('{foo}', {}), '{foo}')

    def test_formatting_invalid_string(self):
        s = """'ifconfig -a eth1|grep "inet addr"|awk '{gsub("addr:","",$2); print $2}'"""
        self.assertEquals(formatloc(s, {}), s)

    def test_formatting_fun(self):
        def lalafun(kw):
            rs = 100
            return rs
        ctx = {'lala': lalafun}
        r = formatloc('{lala}', ctx)
        self.assertTrue('<function' not in r)
        self.assertEquals(r, '100')

    def test_set_setting(self):
        aslocal(prompt=False)
        start_str = """hello world\nhawai\n"""
        ff = file({})
        f = ff.tmpfile(start_str)
        f.seek(0)
        ff.set_setting(f.name, 'foobar', su=False)
        f.seek(0)
        self.assertEqual(f.read(), start_str + "foobar\n")

    def test_target_filename(self):
        template = Template({})
        self.assertEquals(template.determine_target_filename('/1/foo.txt', '/tmp/'), '/tmp/foo.txt')
        self.assertEquals(template.determine_target_filename('/1/foo.txt', '/tmp/bar.txt'), '/tmp/bar.txt')
        self.assertEquals(template.determine_target_filename('/1/foo.txt', '/tmp'), '/tmp')

def overwrite(f, data):
    f.seek(0)
    f.write(data)
    f.truncate()

class PatchTest(BaseSuite):
    def test_env_function(self):
        def _(kw={}):
            return 100
        env.fntest = _
        self.assertEqual(formatloc(env.fntest, {}), _())

class ModuleTest(BaseSuite):

    def test_package(self):
        self.assertEquals(package({}).dummy('John'), 'John')

    def test_module_packages(self):
        env.ctx = {
            'moda':
                {'project': 'name_moda'},
            'modb':
                {'project': 'name_modb'},
        }
        ma = moda()
        mb = modb()
        ma.setup()
        self.assertNotEqual(ma.version, mb.version)
        self.assertEquals(ma.project, 'name_moda')
        self.assertEquals(ma.modb.project, 'name_modb')
        ma = moda({'project': 'king'})
        self.assertEquals(ma.project, 'king')

class WaterTest(BaseSuite):
    def test_settings_layers(self):
        i = modc({'modc_hello': 'world', 'external': 'ok'})
        self.assertEqual(i.modc_left, 'left')
        self.assertEqual(i.modc_hello, 'world')
        self.assertEqual(i.external, 'ok')

        i = modc(ctx={'modc_hello': 'world', 'modc_left': 'right'})
        self.assertEqual(i.modc_left, 'right')
        self.assertEqual(i.modc_hello, 'world')

        env.ctx['modc'] = {}
        env.ctx['modc']['modc_left'] = 'up'
        i = modc()
        self.assertEqual(i.modc_left, 'up')