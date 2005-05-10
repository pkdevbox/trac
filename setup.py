#!/usr/bin/env python

import os
import os.path
import sys
import string
from glob import glob
from distutils.core import setup
from distutils.command.install import install
from distutils.command.install_data import install_data
from distutils.command.install_scripts import install_scripts
from stat import ST_MODE, S_ISDIR

import trac

PACKAGE = 'Trac'
VERSION = str(trac.__version__)
URL = trac.__url__
LICENSE = trac.__license__

if sys.version_info<(2,1):
    print >>sys.stderr, "You need at least Python 2.1 for %s %s" % (PACKAGE, VERSION)
    sys.exit(3)

def _p(unix_path):
     return os.path.normpath(unix_path)

class my_install (install):
     def run (self):
         self.siteconfig()

     def siteconfig(self):
         templates_dir = os.path.join(self.prefix, 'share', 'trac', 'templates')
         htdocs_dir = os.path.join(self.prefix, 'share', 'trac', 'htdocs')
         wiki_dir = os.path.join(self.prefix, 'share', 'trac', 'wiki-default')
         macros_dir = os.path.join(self.prefix, 'share', 'trac', 'wiki-macros')
         f = open(_p('trac/siteconfig.py'),'w')
         f.write("""
# PLEASE DO NOT EDIT THIS FILE!
# This file was autogenerated when installing %(trac)s %(ver)s.
#
__default_templates_dir__ = %(templates)r
__default_htdocs_dir__ = %(htdocs)r
__default_wiki_dir__ = %(wiki)r
__default_macros_dir__ = %(macros)r

""" % {'trac':PACKAGE, 'ver':VERSION, 'templates':_p(templates_dir),
       'htdocs':_p(htdocs_dir), 'wiki':_p(wiki_dir), 'macros':_p(macros_dir)})
         f.close()

         # Run actual install
         install.run(self)

         print
         print "Thank you for choosing Trac %s. Enjoy your stay!" % VERSION
         print trac.__credits__

class my_install_scripts (install_scripts):
    def initialize_options (self):
        install_scripts.initialize_options(self)
        self.install_data = None
        
    def finalize_options (self):
        install_scripts.finalize_options(self)
        self.set_undefined_options('install',
                                   ('install_data', 'install_data'))
          
    def run (self):
        if not self.skip_build:
            self.run_command('build_scripts')

        self.outfiles = []

        self.mkpath(os.path.normpath(self.install_dir))
        ofile, copied = self.copy_file(os.path.join(self.build_dir,
                                                     'trac-admin'),
                                        self.install_dir)
        if copied:
            self.outfiles.append(ofile)
        ofile, copied = self.copy_file(os.path.join(self.build_dir,
                                                     'tracd'),
                                        self.install_dir)
        if copied:
            self.outfiles.append(ofile)
        ofile, copied = self.copy_file(os.path.join(self.build_dir,
                                                     'tracdb2env'),
                                        self.install_dir)
        if copied:
            self.outfiles.append(ofile)
            
        cgi_dir = os.path.join(self.install_data, 'share', 'trac', 'cgi-bin')
        if not os.path.exists(cgi_dir):
            os.makedirs(cgi_dir)
            
        ofile, copied = self.copy_file(os.path.join(self.build_dir,
                                                    'trac.cgi'), cgi_dir)
        if copied:
            self.outfiles.append(ofile)
        
        if os.name == 'posix':
            # Set the executable bits (owner, group, and world) on
            # all the scripts we just installed.
            for file in self.get_outputs():
                if not self.dry_run:
                    mode = ((os.stat(file)[ST_MODE]) | 0555) & 07777
                    os.chmod(file, mode)


class my_install_data (install_data):
    def run (self):
        install_data.run(self)

        if os.name == 'posix' and not self.dry_run:
            # Make the data files we just installed world-readable,
            # and the directories world-executable as well.
            for path in self.get_outputs():
                mode = os.stat(path)[ST_MODE]
                if S_ISDIR(mode):
                    mode |= 011
                mode |= 044
                os.chmod(path, mode)


# Our custom bdist_wininst
import distutils.command.bdist_wininst
from distutils.command.bdist_wininst import bdist_wininst
class my_bdist_wininst(bdist_wininst):
    def initialize_options(self):
        bdist_wininst.initialize_options(self)
        self.title = "Trac %s" % VERSION
        self.bitmap = "setup_wininst.bmp"
distutils.command.bdist_wininst.bdist_wininst = my_bdist_wininst


# parameters for various rpm distributions
rpm_distros = {
    'suse_options': { 'version_suffix': 'SuSE',
                      'requires': """python >= 2.1
                        subversion >= 1.0.0
                        pysqlite >= 0.4.3
                        clearsilver >= 0.9.3
                        httpd""" },

    'fedora_options': { 'version_suffix': 'fc'}
    }


# Our custom bdist_rpm
import distutils.command.bdist_rpm
from distutils.command.bdist_rpm import bdist_rpm
class generic_bdist_rpm(bdist_rpm):

    def __init__(self, dist, distro):
        self.distro = distro
        bdist_rpm.__init__(self, dist)

    def initialize_options(self):
        bdist_rpm.initialize_options(self)
        self.title = "Trac %s" % VERSION
        self.packager = "Edgewall Software <info@edgewall.com>"
        for x in rpm_distros[self.distro].keys():
            setattr(self, x, rpm_distros[self.distro][x])

    def run(self):
        bdist_rpm.run(self)
        if hasattr(self, 'version_suffix'):
            prefix = os.path.join(self.dist_dir, string.lower(PACKAGE)+'-'+VERSION+'-1')
            os.rename(prefix+'.noarch.rpm', prefix+self.version_suffix+'.noarch.rpm')
            os.rename(prefix+'.src.rpm', prefix+self.version_suffix+'.src.rpm')

class proxy_bdist_rpm(bdist_rpm):

    def __init__(self, dist):
        bdist_rpm.__init__(self, dist)
        self.dist = dist

    def initialize_options(self):
        bdist_rpm.initialize_options(self)

    def run(self):
        for distro in rpm_distros.keys():
            r = generic_bdist_rpm(self.dist, distro)
            r.initialize_options()
            self.dist._set_command_options(r, self.dist.command_options['bdist_rpm'])
            r.finalize_options()
            r.run()

distutils.command.bdist_rpm.bdist_rpm = proxy_bdist_rpm

setup(name="trac",
      description="Integrated scm, wiki, issue tracker and project environment",
      long_description=\
"""
Trac is a minimalistic web-based software project management and bug/issue
tracking system. It provides an interface to the Subversion revision control
systems, an integrated wiki, flexible issue tracking and convenient report
facilities.
""",
      version=VERSION,
      author="Edgewall Software",
      author_email="info@edgewall.com",
      license=LICENSE,
      url=URL,
      packages=['trac', 'trac.mimeview', 'trac.scripts', 'trac.upgrades',
                'trac.versioncontrol', 'trac.web', 'trac.wiki'],
      data_files=[(_p('share/trac/templates'), glob('templates/*')),
                  (_p('share/trac/htdocs'), glob(_p('htdocs/*.*')) + [_p('htdocs/README')]),
                  (_p('share/trac/htdocs/css'), glob(_p('htdocs/css/*'))),
                  (_p('share/trac/htdocs/js'), glob(_p('htdocs/js/*'))),
                  (_p('share/man/man1'), glob(_p('scripts/*.1'))),
                  (_p('share/trac/wiki-default'), glob(_p('wiki-default/[A-Z]*'))),
                  (_p('share/trac/wiki-macros'), glob(_p('wiki-macros/*.py')))],
      scripts=[_p('scripts/trac-admin'),
               _p('scripts/tracd'),
               _p('scripts/tracdb2env'),
               _p('cgi-bin/trac.cgi')],
      cmdclass = {'install': my_install,
                  'install_scripts': my_install_scripts,
                  'install_data': my_install_data})
