# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2006 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2004-2005 Christopher Lenz <cmlenz@gmx.de>
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
#         Christopher Lenz <cmlenz@gmx.de>

import os
import re
import StringIO

from trac.attachment import attachments_data, Attachment, AttachmentModule
from trac.core import *
from trac.perm import IPermissionRequestor
from trac.Search import ISearchSource, search_to_sql, shorten_result
from trac.Timeline import ITimelineEventProvider
from trac.util import get_reporter_id
from trac.util.html import html, Markup
from trac.util.text import shorten_line
from trac.versioncontrol.diff import get_diff_options, diff_blocks
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor
from trac.web import HTTPNotFound, IRequestHandler
from trac.wiki.api import IWikiPageManipulator, WikiSystem
from trac.wiki.model import WikiPage
from trac.wiki.formatter import wiki_to_html, wiki_to_oneliner
from trac.mimeview.api import Mimeview, IContentConverter


class InvalidWikiPage(TracError):
    """Exception raised when a Wiki page fails validation."""


class WikiModule(Component):

    implements(INavigationContributor, IPermissionRequestor, IRequestHandler,
               ITimelineEventProvider, ISearchSource, IContentConverter)

    page_manipulators = ExtensionPoint(IWikiPageManipulator)

    # IContentConverter methods
    def get_supported_conversions(self):
        yield ('txt', 'Plain Text', 'txt', 'text/x-trac-wiki', 'text/plain', 9)

    def convert_content(self, req, mimetype, content, key):
        return (content, 'text/plain;charset=utf-8')

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'wiki'

    def get_navigation_items(self, req):
        if not req.perm.has_permission('WIKI_VIEW'):
            return
        yield ('mainnav', 'wiki',
               html.A('Wiki', href=req.href.wiki(), accesskey=1))
        yield ('metanav', 'help',
               html.A('Help/Guide', href=req.href.wiki('TracGuide'),
                      accesskey=6))

    # IPermissionRequestor methods

    def get_permission_actions(self):
        actions = ['WIKI_CREATE', 'WIKI_DELETE', 'WIKI_MODIFY', 'WIKI_VIEW']
        return actions + [('WIKI_ADMIN', actions)]

    # IRequestHandler methods

    def match_request(self, req):
        match = re.match(r'^/wiki(?:/(.*))?', req.path_info)
        if match:
            if match.group(1):
                req.args['page'] = match.group(1)
            return 1

    def process_request(self, req):
        action = req.args.get('action', 'view')
        pagename = req.args.get('page', 'WikiStart')
        version = req.args.get('version')

        if pagename.endswith('/'):
            req.redirect(req.href.wiki(pagename.strip('/')))

        db = self.env.get_db_cnx()
        page = WikiPage(self.env, pagename, version, db)

        add_stylesheet(req, 'common/css/wiki.css')

        if req.method == 'POST':
            if action == 'edit':
                latest_version = WikiPage(self.env, pagename, None, db).version
                if req.args.has_key('cancel'):
                    req.redirect(req.href.wiki(page.name))
                elif int(version) != latest_version:
                    return self._render_editor(req, db, page, 'collision')
                elif req.args.has_key('preview'):
                    return self._render_editor(req, db, page, 'preview')
                else:
                    self._do_save(req, db, page)
            elif action == 'delete':
                self._do_delete(req, db, page)
            elif action == 'diff':
                get_diff_options(req)
                req.redirect(req.href.wiki(
                    page.name, version=page.version,
                    old_version=req.args.get('old_version'), action='diff'))
        elif action == 'delete':
            return self._render_confirm(req, db, page)
        elif action == 'edit':
            return self._render_editor(req, db, page)
        elif action == 'diff':
            return self._render_diff(req, db, page)
        elif action == 'history':
            return self._render_history(req, db, page)
        else:
            format = req.args.get('format')
            if format:
                Mimeview(self.env).send_converted(req, 'text/x-trac-wiki',
                                                  page.text, format, page.name)
            return self._render_view(req, db, page)

    def page_data(self, page, action=''):
        title = page_name = WikiSystem(self.env).format_page_name(page.name)
        if action:
            title += ' (%s)' % action
        return {'page': page,
                'action': action,
                'page_name': page_name,
                'title': title}

    # Internal methods

    def _do_delete(self, req, db, page):
        if page.readonly:
            req.perm.assert_permission('WIKI_ADMIN')
        else:
            req.perm.assert_permission('WIKI_DELETE')

        if req.args.has_key('cancel'):
            req.redirect(req.href.wiki(page.name))

        version = int(req.args.get('version', 0)) or None
        old_version = int(req.args.get('old_version', 0)) or version

        if version and old_version and version > old_version:
            # delete from `old_version` exclusive to `version` inclusive:
            for v in range(old_version, version):
                page.delete(v + 1, db)
        else:
            # only delete that `version`, or the whole page if `None`
            page.delete(version, db)
        db.commit()

        if not page.exists:
            req.redirect(req.href.wiki())
        else:
            req.redirect(req.href.wiki(page.name))

    def _do_save(self, req, db, page):
        if page.readonly:
            req.perm.assert_permission('WIKI_ADMIN')
        elif not page.exists:
            req.perm.assert_permission('WIKI_CREATE')
        else:
            req.perm.assert_permission('WIKI_MODIFY')

        page.text = req.args.get('text')
        if req.perm.has_permission('WIKI_ADMIN'):
            # Modify the read-only flag if it has been changed and the user is
            # WIKI_ADMIN
            page.readonly = int(req.args.has_key('readonly'))

        # Give the manipulators a pass at post-processing the page
        for manipulator in self.page_manipulators:
            for field, message in manipulator.validate_wiki_page(req, page):
                if field:
                    raise InvalidWikiPage("The Wiki page field %s is invalid: %s"
                                          % (field, message))
                else:
                    raise InvalidWikiPage("Invalid Wiki page: %s" % message)

        page.save(get_reporter_id(req, 'author'), req.args.get('comment'),
                  req.remote_addr)
        req.redirect(req.href.wiki(page.name))

    def _render_confirm(self, req, db, page):
        if page.readonly:
            req.perm.assert_permission('WIKI_ADMIN')
        else:
            req.perm.assert_permission('WIKI_DELETE')

        version = None
        if 'delete_version' in req.args:
            version = int(req.args.get('version', 0))
        old_version = int(req.args.get('old_version') or 0) or version

        data = self.page_data(page, 'delete')
        if version is not None:
            num_versions = 0
            for v,t,author,comment,ipnr in page.get_history():
                if v >= old_version:
                    num_versions += 1;
                    if num_versions > 1:
                        break
            data.update({'new_version': version, 'old_version': old_version,
                         'num_versions': num_versions})
        return 'wiki_delete.html', data, None

    def _render_diff(self, req, db, page):
        req.perm.assert_permission('WIKI_VIEW')

        if not page.exists:
            raise TracError("Version %s of page %s does not exist" %
                            (req.args.get('version'), page.name))

        old_version = req.args.get('old_version')
        if old_version:
            old_version = int(old_version)
            if old_version == page.version:
                old_version = None
            elif old_version > page.version: # FIXME: what about reverse diffs?
                old_version, page = page.version, \
                                    WikiPage(self.env, page.name, old_version)
        latest_page = WikiPage(self.env, page.name)
        new_version = int(page.version)

        date = author = comment = ipnr = None
        num_changes = 0
        old_page = None
        prev_version = next_version = None
        for version,t,a,c,i in latest_page.get_history():
            if version == new_version:
                date = t
                author = a or 'anonymous'
                comment = wiki_to_html(c or '--', self.env, req, db)
                ipnr = i or ''
            else:
                if version < new_version:
                    num_changes += 1
                    if not prev_version:
                        prev_version = version
                    if (old_version and version == old_version) or \
                            not old_version:
                        old_version = version
                        old_page = WikiPage(self.env, page.name, old_version)
                        break
                else:
                    next_version = version

        # -- text diffs
        diff_style, diff_options, diff_data = get_diff_options(req)

        oldtext = old_page and old_page.text.splitlines() or []
        newtext = page.text.splitlines()
        context = 3
        for option in diff_options:
            if option.startswith('-U'):
                context = int(option[2:])
                break
        if context < 0:
            context = None
        diffs = diff_blocks(oldtext, newtext, context=context,
                            ignore_blank_lines='-B' in diff_options,
                            ignore_case='-i' in diff_options,
                            ignore_space_changes='-b' in diff_options)

        # -- prev/up/next links
        if prev_version:
            add_link(req, 'prev', req.href.wiki(page.name, action='diff',
                                                version=prev_version),
                     'Version %d' % prev_version)
        add_link(req, 'up', req.href.wiki(page.name, action='history'),
                 'Page history')
        if next_version:
            add_link(req, 'next', req.href.wiki(page.name, action='diff',
                                                version=next_version),
                     'Version %d' % next_version)

        add_stylesheet(req, 'common/css/diff.css')

        data = self.page_data(page, 'diff')

        def version_info(v):
            return {'path': data['page_name'], 'rev': v, 'shortrev': v,
                    'href': req.href.wiki(page.name, version=v)}
                    
        changes = [{'diffs': diffs, 'props': [],
                    'new': version_info(new_version),
                    'old': version_info(old_version)}]

        data.update({ 
            'date': date, 'author': author, 'comment': comment, 'ipnr': ipnr,
            'new_version': new_version, 'old_version': old_version,
            'latest_version': latest_page.version,
            'num_changes': num_changes,
            'norobots': True, # Ask web spiders to not index old versions
            'longcol': 'Version', 'shortcol': 'v',
            'changes': changes,
            'diff': diff_data,
            })
        return 'wiki_diff.html', data, None

    def _render_editor(self, req, db, page, action='edit'):
        req.perm.assert_permission('WIKI_MODIFY')

        if 'text' in req.args:
            page.text = req.args.get('text')
        if action == 'preview':
            page.readonly = 'readonly' in req.args

        author = get_reporter_id(req, 'author')
        comment = req.args.get('comment', '')
        editrows = req.args.get('editrows')
        
        if editrows:
            pref = req.session.get('wiki_editrows', '20')
            if editrows != pref:
                req.session['wiki_editrows'] = editrows
        else:
            editrows = req.session.get('wiki_editrows', '20')

        data = self.page_data(page, action)
        data.update({
            'author': author,
            'comment': comment,
            'edit_rows': editrows,
            'scroll_bar_pos': req.args.get('scroll_bar_pos', '')
        })
        if action == 'preview':
            data.update({
            'page_html': wiki_to_html(page.text, self.env, req, db),
            'comment_html': wiki_to_oneliner(comment, self.env, db)
            })
        return 'wiki_edit.html', data, None

    def _render_history(self, req, db, page):
        """Extract the complete history for a given page.

        This information is used to present a changelog/history for a given
        page.
        """
        req.perm.assert_permission('WIKI_VIEW')

        if not page.exists:
            raise TracError, "Page %s does not exist" % page.name

        data = self.page_data(page, 'history')

        history = []
        for version, date, author, comment, ipnr in page.get_history():
            history.append({
                'version': version,
                'date': date,
                'author': author,
                'comment': wiki_to_oneliner(comment or '', self.env, db),
                'ipnr': ipnr
            })
        data['history'] = history
        return 'wiki_history.html', data, None

    def _render_view(self, req, db, page):
        req.perm.assert_permission('WIKI_VIEW')

        version = req.args.get('version')

        # Add registered converters
        for conversion in Mimeview(self.env).get_supported_conversions(
                                             'text/x-trac-wiki'):
            conversion_href = req.href.wiki(page.name, version=version,
                                            format=conversion[0])
            add_link(req, 'alternate', conversion_href, conversion[1],
                     conversion[3])

        data = self.page_data(page)
        if page.name == 'WikiStart':
            data['title'] = ''

        page_html = comment_html = attach_href = ''
        latest_page = WikiPage(self.env, page.name)

        if page.exists:
            page_html = wiki_to_html(page.text, self.env, req, db)
            if version:
                comment_html = wiki_to_oneliner(page.comment or '--',
                                                self.env, db)
        else:
            if not req.perm.has_permission('WIKI_CREATE'):
                raise HTTPNotFound('Page %s not found', page.name)
            page_html = html.P('Describe "%s" here' % data['page_name'])

        # Show attachments
        attachments = attachments_data(self.env, req, db, 'wiki', page.name)
        if req.perm.has_permission('WIKI_MODIFY'):
            attach_href = req.href.attachment('wiki', page.name)

        data.update({'action': 'view',
                     'page_html': page_html,
                     'comment_html': comment_html,
                     'latest_version': latest_page.version,
                     'attachments': attachments,
                     'attach_href': attach_href,
                     # Ask web spiders to not index old versions
                     'norobots': bool(version),
                     })
        return 'wiki_view.html', data, None

    # ITimelineEventProvider methods

    def get_timeline_filters(self, req):
        if req.perm.has_permission('WIKI_VIEW'):
            yield ('wiki', 'Wiki changes')

    def get_timeline_events(self, req, start, stop, filters):
        if 'wiki' in filters:
            wiki = WikiSystem(self.env)
            format = req.args.get('format')
            href = format == 'rss' and req.abs_href or req.href
            db = self.env.get_db_cnx()
            cursor = db.cursor()
            cursor.execute("SELECT time,name,comment,author,version "
                           "FROM wiki WHERE time>=%s AND time<=%s",
                           (start, stop))
            for t,name,comment,author,version in cursor:
                title = Markup('<em>%s</em> edited by %s',
                               wiki.format_page_name(name), author)
                diff_link = html.A('diff', href=href.wiki(name, action='diff',
                                                          version=version))
                if format == 'rss':
                    comment = wiki_to_html(comment or '--', self.env, req, db,
                                           absurls=True)
                else:
                    comment = wiki_to_oneliner(comment, self.env, db,
                                               shorten=True)
                if version > 1:
                    comment = html(comment, ' (', diff_link, ')')
                yield 'wiki', href.wiki(name), title, t, author, comment

            # Attachments
            def display(id):
                return Markup('ticket ', html.EM('#', id))
            att = AttachmentModule(self.env)
            for event in att.get_timeline_events(req, db, 'wiki', format,
                                                 start, stop,
                                                 lambda id: html.EM(id)):
                yield event

    # ISearchSource methods

    def get_search_filters(self, req):
        if req.perm.has_permission('WIKI_VIEW'):
            yield ('wiki', 'Wiki')

    def get_search_results(self, req, terms, filters):
        if not 'wiki' in filters:
            return
        db = self.env.get_db_cnx()
        sql_query, args = search_to_sql(db, ['w1.name', 'w1.author', 'w1.text'],
                                        terms)
        cursor = db.cursor()
        cursor.execute("SELECT w1.name,w1.time,w1.author,w1.text "
                       "FROM wiki w1,"
                       "(SELECT name,max(version) AS ver "
                       "FROM wiki GROUP BY name) w2 "
                       "WHERE w1.version = w2.ver AND w1.name = w2.name "
                       "AND " + sql_query, args)

        for name, date, author, text in cursor:
            yield (req.href.wiki(name), '%s: %s' % (name, shorten_line(text)),
                   date, author, shorten_result(text, terms))
