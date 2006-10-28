# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2006 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2005-2006 Christian Boos <cboos@neuf.fr>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Author: Jonas Borgström <jonas@edgewall.com>
#         Christian Boos <cboos@neuf.fr>

import re
import urllib

from trac.core import TracError
from trac.util.datefmt import pretty_timedelta
from trac.util.html import escape, html, Markup
from trac.util.text import shorten_line
from trac.versioncontrol.api import NoSuchNode, NoSuchChangeset
from trac.wiki import wiki_to_html, wiki_to_oneliner

__all__ = ['get_changes', 'get_path_links', 'parse_path_link',
           'get_existing_node', 'render_node_property']

def get_changes(env, repos, revs, full=None, req=None, format=None):
    db = env.get_db_cnx()
    changes = {}
    for rev in revs:
        try:
            changeset = repos.get_changeset(rev)
        except NoSuchChangeset:
            changes[rev] = {}
            continue

        wiki_format = env.config['changeset'].getbool('wiki_format_messages')
        message = changeset.message or '--'
        absurls = (format == 'rss')
        if wiki_format:
            shortlog = wiki_to_oneliner(message, env, db,
                                        shorten=True, absurls=absurls)
        else:
            shortlog = Markup.escape(shorten_line(message))

        if full:
            if wiki_format:
                message = wiki_to_html(message, env, req, db,
                                       absurls=absurls, escape_newlines=True)
            else:
                message = html.PRE(message)
        else:
            message = shortlog

        if format == 'rss':
            if isinstance(shortlog, Markup):
                shortlog = u' '.join(shortlog.striptags().splitlines())
            message = unicode(message)

        changes[rev] = {
            'date': changeset.date,
            'author': changeset.author or 'anonymous',
            'message': message, 'shortlog': shortlog,
        }
    return changes

def get_path_links(href, fullpath, rev):
    links = [{'name': 'root', 'href': href.browser(rev=rev)}]
    path = ''
    for part in [p for p in fullpath.split('/') if p]:
        path += part + '/'
        links.append({'name': part, 'href': href.browser(path, rev=rev)})
    return links


PATH_LINK_RE = re.compile(r"([^@#:]*)"     # path
                          r"[@:]([^#:]+)?" # rev
                          r"(?::(\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*))?" # marks
                          r"(?:#L(\d+))?"  # anchor line
                          )

def parse_path_link(path):
    """Analyse repository source path specifications.

    Valid forms are simple paths (/dir/file), paths at a given revision
    (/dir/file@234), paths with line number marks (/dir/file@234:10,20-30)
    and paths with line number anchor (/dir/file@234#L100).
    Marks and anchor can be combined.
    The revision must be present when specifying line numbers.
    In the few cases where it would be redundant (e.g. for tags), the
    revision number itself can be omitted: /tags/v10/file@100-110#L99

    Return a `(path, rev, marks, line)` tuple.
    """
    rev = marks = line = None
    match = PATH_LINK_RE.search(path)
    if match:
        path, rev, marks, line = match.groups()
        line = line and int(line) or None
    path = urllib.unquote(path) # TODO: this should probably go away...
    return path, rev, marks, line

def get_existing_node(req, repos, path, rev):
    try: 
        return repos.get_node(path, rev) 
    except NoSuchNode, e:
        raise TracError(Markup('%s<br><p>You can <a href="%s">search</a> ' 
                               'in the repository history to see if that path '
                               'existed but was later removed.</p>', e.message,
                               req.href.log(path, rev=rev,
                                            mode='path_history')))

def render_node_property(env, name, value):
    """Renders a node property value to HTML.

    Currently only handle multi-line properties. See also #1601.
    """
    if value and '\n' in value:
        value = Markup(''.join(['<br />%s' % escape(v)
                                for v in value.split('\n')]))
    return value
