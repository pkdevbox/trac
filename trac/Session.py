# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2004 Edgewall Software
# Copyright (C) 2004 Daniel Lundin <daniel@edgewall.com>
#
# Trac is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# Trac is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
# Author: Daniel Lundin <daniel@edgewall.com>

from util import hex_entropy, TracError

import sys
import time
from UserDict import UserDict


DEPARTURE_INTERVAL = 3600 # If you're idle for an hour, you left
PURGE_AGE = 3600*24*90 # Purge session after 90 days idle
COOKIE_KEY = 'trac_session'


class Session(UserDict):
    """Basic session handling and per-session storage."""

    sid = None
    req = None
    env = None
    db = None
    _old = {}

    def __init__(self, env, db, req, newsession = 0):
        UserDict.__init__(self)
        self.env = env
        self.db = db
        self.req = req
        self.sid = None
        self._old = {}
        if newsession:
            self.create_new_sid()
        else:
            try:
                sid = req.incookie[COOKIE_KEY].value
                self.get_session(sid)
            except KeyError:
                self.create_new_sid()

    def bake_cookie(self):
        self.req.outcookie[COOKIE_KEY] = self.sid
        self.req.outcookie[COOKIE_KEY]['path'] = self.req.cgi_location
        self.req.outcookie[COOKIE_KEY]['expires'] = 420000000

    def get_session(self, sid):
        self.sid = sid
        curs = self.db.cursor()
        curs.execute("SELECT username,var_name,var_value FROM session"
                    " WHERE sid=%s", self.sid)
        rows = curs.fetchall()
        if (not rows                              # No session data yet
            or rows[0][0] == 'anonymous'          # Anon session
            or rows[0][0] == self.req.authname):  # Session is mine
            for u,k,v in rows:
                self.data[k] = v
            self._old.update(self.data)
            self.bake_cookie()
            return
        if self.req.authname == 'anonymous':
            err = ('Session cookie requires authentication. <p>'
                   'Please choose action:</p>'
                   '<ul><li><a href="%s">Log in and continue session</a></li>'
                   '<li><a href="%s?newsession=1">Create new session (no login required)</a></li>'
                   '</ul>'
                   % (self.env.href.login(), self.env.href.settings()))
        else:
            err = ('Session belongs to another authenticated user.'
                   '<p><a href="%s?newsession=1">'
                   'Create new session</a></p>' % self.env.href.settings())
        raise TracError(err, 'Error accessing authenticated session')

    def create_new_sid(self):
        self.sid = hex_entropy(24)
        self.bake_cookie()

    def change_sid(self, newsid):
        if newsid == self.sid:
            return
        curs = self.db.cursor()
        curs.execute("SELECT sid FROM session WHERE sid=%s", newsid)
        if curs.fetchone():
            raise TracError("Session '%s' already exists.<br />"
                            "Please choose a different session id." % newsid,
                            "Error renaming session")
        curs.execute("UPDATE session SET sid=%s WHERE sid=%s",
                     newsid, self.sid)
        self.db.commit()
        self.sid = newsid
        self.bake_cookie()

    def save(self):
        if not self._old and not self.data:
            # The session doesn't have associated data, so there's no need to
            # persist it
            return

        now = int(time.time())

        # Update the session last visit time if it is over an hour old, so that
        # session doesn't get purged
        last_visit = int(self.data.get('last_visit', 0))
        if now - last_visit > DEPARTURE_INTERVAL:
            self.data['last_visit'] = now

        changed = 0
        cursor = self.db.cursor()

        # Find all new or modified session variables and persist their values to
        # the database
        for k,v in self.data.items():
            if not self._old.has_key(k):
                cursor.execute("INSERT INTO session(sid,username,var_name,"
                               "var_value) VALUES(%s,%s,%s,%s)",
                               self.sid, self.req.authname, k, v)
                changed = 1
            elif v != self._old[k]:
                cursor.execute("UPDATE session SET var_value=%s WHERE sid=%s "
                               "AND var_name=%s", v, self.sid, k)
                changed = 1

        # Find all variables that have been deleted and also remove them from
        # the database
        for k in [k for k in self._old.keys() if not self.data.has_key(k)]:
            cursor.execute("DELETE FROM session WHERE sid=%s AND var_name=%s",
                           self.sid, k)
            changed = 1

        if changed:
            # Purge expired sessions. We do this only when the session was
            # changed as to minimize the purging.
            mintime = now - PURGE_AGE
            self.env.log.debug('Purging old, expired, sessions.')
            cursor.execute("DELETE FROM session WHERE sid IN"
                           " (SELECT sid FROM session"
                           "  WHERE var_name='last_visit' AND var_value < %s)",
                           mintime)

            self.db.commit()
