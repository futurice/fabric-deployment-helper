import copy, tempfile

from soppa.contrib import *

from jinja2 import Template as JinjaTemplate


class Template(Soppa):
    def determine_target_filename(self, a, b):
        af = a.split('/')[-1]
        filename = b + af
        if not b.endswith('/'):
            filename = b
        return filename

    def up(self, tpl, to, context={}, use_sudo=True):
        """ Render a template and upload to server
        - Jinja uses {{foo}} for formatting, Python uses {foo}
        """
        filename = self.determine_target_filename(
                formatloc(tpl, context),
                formatloc(to, context))
        to = formatloc(to, context)
        assert '{' not in filename
        for k,v in context.iteritems():
            context[k] = formatloc(v, context)
        use_sudo = use_sudo or context.get('use_sudo', False)
        with open(tpl, 'r') as f:
            data = JinjaTemplate(f.read()).render(**context)
            with tempfile.NamedTemporaryFile() as tf:
                tf.write(data)
                tf.flush()
                self.put(tf.name, filename, use_sudo=use_sudo)

template_task, template = register(Template)
