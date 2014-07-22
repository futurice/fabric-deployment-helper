import time

from soppa.contrib import *

class Vagrant(Soppa):
    needs=[
        'soppa.file',
    ]
    def guest_ip(self):
        return self.sudo("""ifconfig -a eth1|grep "inet addr"|awk '{gsub("addr:","",$2); print $2}'""", tkw=dict(raw=True))

    def enable_host(self, name):
        """
        Romain forwarding for local development with Vagrant.
        domain (host) -> domain (guest)
        """
        self.guest_ip = self.guest_ip()
        self.guest_host_name = name
        # Host (remote) change
        self.file.set_setting('/etc/hosts', '{0} {1}'.format('127.0.0.1', self.guest_host_name))
        # local change
        aslocal()
        self.file.set_setting('/etc/hosts', '{0} {1}'.format(self.guest_ip, name))

vagrant_task, vagrant = register(Vagrant)