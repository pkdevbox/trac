#!/usr/bin/env python

import os
import os.path
import sys
from glob import glob
from distutils.core import setup
from distutils.command.install import install
from distutils.command.install_scripts import install_scripts
from stat import ST_MODE

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
         templates_dir = os.path.join(self.prefix, 'share','trac','templates')
         htdocs_dir = os.path.join(self.prefix, 'share','trac','htdocs')
         wiki_dir = os.path.join(self.prefix, 'share','trac','wiki-default')
         f = open(_p('trac/siteconfig.py'),'w')
         f.write("""
# PLEASE DO NOT EDIT THIS FILE!
# This file was autogenerated when installing %(trac)s %(ver)s.
#
__default_templates_dir__ = %(templates)r
__default_htdocs_dir__ = %(htdocs)r
__default_wiki_dir__ = %(wiki)r

""" % {'trac':PACKAGE, 'ver':VERSION, 'templates':_p(templates_dir),
       'htdocs':_p(htdocs_dir), 'wiki':_p(wiki_dir)})
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



# Our custom bdist_wininst
import distutils.command.bdist_wininst
from distutils.command.bdist_wininst import bdist_wininst
class my_bdist_wininst(bdist_wininst):
    def initialize_options(self):
        bdist_wininst.initialize_options(self)
        self.title = "Trac %s" % VERSION
        self.bitmap = "setup_wininst.bmp"
distutils.command.bdist_wininst.bdist_wininst = my_bdist_wininst


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
      packages=['trac', 'trac.wikimacros'],
      data_files=[(_p('share/trac/templates'), glob('templates/*')),
                  (_p('share/trac/htdocs'), glob(_p('htdocs/*.*')) + [_p('htdocs/README')]),
                  (_p('share/trac/htdocs/css'), glob(_p('htdocs/css/*'))),
                  (_p('share/trac/wiki-default'), glob(_p('wiki-default/[A-Z]*')))],
      scripts=[_p('scripts/trac-admin'), _p('cgi-bin/trac.cgi')],
      cmdclass = {'install': my_install,
                  'install_scripts': my_install_scripts})



