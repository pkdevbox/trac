# -*- coding: utf-8 -*-
#
# Copyright (C) 2005 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
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
# Author: Christopher Lenz <cmlenz@gmx.de>

import os
import urllib

from trac.core import *
from trac.db.pool import ConnectionPool


class IDatabaseConnector(Interface):
    """Extension point interface for components that support the connection to
    relational databases."""

    def get_supported_schemes():
        """Return the connection URL schemes supported by the connector, and
        their relative priorities as an iterable of `(scheme, priority)` tuples.
        """

    def get_connection(**kwargs):
        """Create a new connection to the database."""
        
    def init_db(**kwargs):
        """Initialize the database."""

    def to_sql(table):
        """Return the DDL statements necessary to create the specified table,
        including indices."""


class DatabaseManager(Component):

    connectors = ExtensionPoint(IDatabaseConnector)

    def __init__(self):
        self._cnx_pool = None

    def init_db(self):
        connector, args = self._get_connector()
        connector.init_db(**args)

    def get_connection(self):
        if not self._cnx_pool:
            connector, args = self._get_connector()
            self._cnx_pool = ConnectionPool(5, connector, **args)
        return self._cnx_pool.get_cnx()

    def shutdown(self):
        if self._cnx_pool:
            self._cnx_pool.shutdown()
            self._cnx_pool = None

    def _get_connector(self):
        scheme, args = _parse_db_str(self.env.config.get('trac', 'database'))
        candidates = {}
        for connector in self.connectors:
            for scheme_, priority in connector.get_supported_schemes():
                if scheme_ != scheme:
                    continue
                highest = candidates.get(scheme_, (None, 0))[1]
                if priority > highest:
                    candidates[scheme] = (connector, priority)
            connector = candidates.get(scheme, [None])[0]
        if not connector:
            raise TracError, 'Unsupported database type "%s"' % scheme

        if scheme == 'sqlite':
            # Special case for SQLite to support a path relative to the
            # environment directory
            if args['path'] != ':memory:' and \
                   not args['path'].startswith('/'):
                args['path'] = os.path.join(self.env.path,
                                            args['path'].lstrip('/'))

        return connector, args


def _parse_db_str(db_str):
    scheme, rest = db_str.split(':', 1)

    if not rest.startswith('/'):
        if scheme == 'sqlite':
            # Support for relative and in-memory SQLite connection strings
            host = None
            path = rest
        else:
            raise TracError, 'Database connection string %s must start with ' \
                             'scheme:/' % db_str
    else:
        if rest.startswith('/') and not rest.startswith('//'):
            host = None
            rest = rest[1:]
        elif rest.startswith('///'):
            host = None
            rest = rest[3:]
        else:
            rest = rest[2:]
            if rest.find('/') == -1:
                host = rest
                rest = ''
            else:
                host, rest = rest.split('/', 1)
        path = None

    if host and host.find('@') != -1:
        user, host = host.split('@', 1)
        if user.find(':') != -1:
            user, password = user.split(':', 1)
        else:
            password = None
    else:
        user = password = None
    if host and host.find(':') != -1:
        host, port = host.split(':')
        port = int(port)
    else:
        port = None

    if not path:
        path = '/' + rest
    if os.name == 'nt':
        # Support local paths containing drive letters on Win32
        if len(rest) > 1 and rest[1] == '|':
            path = "%s:%s" % (rest[0], rest[2:])

    params = {}
    if path.find('?') != -1:
        path, qs = path.split('?', 1)
        qs = qs.split('&')
        for param in qs:
            name, value = param.split('=', 1)
            value = urllib.unquote(value)
            params[name] = value

    args = zip(('user', 'password', 'host', 'port', 'path', 'params'),
               (user, password, host, port, path, params))
    return scheme, dict([(key, value) for key, value in args if value])
