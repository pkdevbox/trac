# -*- coding: iso-8859-1 -*-
#
# Copyright (C) 2004-2005 Edgewall Software
# Copyright (C) 2004 Francois Harvey <fharvey@securiweb.net>
# Copyright (C) 2005 Matthew Good <trac@matt-good.net>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Francois Harvey <fharvey@securiweb.net>
#         Matthew Good <trac@matt-good.net>

from __future__ import generators
from trac.versioncontrol import Authorizer

def SubversionAuthorizer(env, authname):
    authz_file = env.config.get('trac','authz_file')    
    if not authz_file:
        return Authorizer()

    module_name = env.config.get('trac','authz_module_name','')
    db = env.get_db_cnx()
    return RealSubversionAuthorizer(db, authname, module_name, authz_file)

def parent_iter(path):
    path = path.strip('/')
    if path:
        path = '/' + path + '/'
    else:
        path = '/'

    while 1:
        yield path
        if path == '/':
            raise StopIteration()
        path = path[:-1]
        yield path
        idx = path.rfind('/')
        path = path[:idx + 1]

class RealSubversionAuthorizer(Authorizer):

    auth_name = ''
    module_name = ''
    conf_authz = None

    def __init__(self, db, auth_name, module_name, cfg_file, cfg_fp=None):
        self.db = db
        self.auth_name = auth_name
        self.module_name = module_name
                                
        from ConfigParser import ConfigParser
        self.conf_authz = ConfigParser()
        if cfg_fp:
            self.conf_authz.readfp(cfg_fp, cfg_file)
        elif cfg_file:
            self.conf_authz.read(cfg_file)

        self.groups = self._groups()

    def has_permission(self, path):
        if path is None:
            return 1

        for p in parent_iter(path):
            if self.module_name:
                for perm in self._get_section(self.module_name + ':' + p):
                    if perm is not None:
                        return perm
            for perm in self._get_section(p):
                if perm is not None:
                    return perm

        return 0

    def has_permission_for_changeset(self, rev):
        cursor = self.db.cursor()
        cursor.execute("SELECT path FROM node_change WHERE rev=%s", (rev,))
        for row in cursor:
            if self.has_permission(row[0]):
                return 1
        return 0

    # Internal API

    def _groups(self):
        if not self.conf_authz.has_section('groups'):
            return []

        grp_parents = {}
        usr_grps = []

        for group in self.conf_authz.options('groups'):
            for member in self.conf_authz.get('groups', group).split(','):
                member = member.strip()
                if member == self.auth_name:
                    usr_grps.append(group)
                elif member.startswith('@'):
                    grp_parents.setdefault(member[1:], []).append(group)

        expanded = {}

        def expand_group(group):
            if group in expanded:
                return
            expanded[group] = True
            for parent in grp_parents.get(group, []):
                expand_group(parent)

        for g in usr_grps:
            expand_group(g)

        # expand groups
        return expanded.keys()

    def _get_section(self, section):
        if not self.conf_authz.has_section(section):
            return

        yield self._get_permission(section, self.auth_name)

        group_perm = None
        for g in self.groups:
            p = self._get_permission(section, '@' + g)
            if p is not None:
                group_perm = p

            if group_perm:
                yield 1

        yield group_perm

        yield self._get_permission(section, '*')

    def _get_permission(self, section, subject):
        if self.conf_authz.has_option(section, subject):
            return 'r' in self.conf_authz.get(section, subject)
        return None

