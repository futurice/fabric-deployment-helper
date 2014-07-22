from soppa.contrib import *

class Celery(Soppa):
    needs=[
        'soppa.template',
        'soppa.supervisor',
    ]

    def hook_post(self):
        self.up('config/celery_supervisor.conf',
                '{supervisor.conf_dir}celery_supervisor_{project}.conf')

celery_task, celery = register(Celery)