import os
import inspect
import StringIO
import unittest

from trac.core import *
from trac.wiki.api import IWikiSyntaxProvider, Context
from trac.wiki.formatter import Formatter, OneLinerFormatter
from trac.wiki.macros import WikiMacroBase
from trac.test import Mock, EnvironmentStub
from trac.util.html import html
from trac.util.text import to_unicode

# We need to supply our own macro because the real macros
# can not be loaded using our 'fake' environment.

class HelloWorldMacro(WikiMacroBase):
    """A dummy macro used by the unit test."""

    def expand_macro(self, formatter, name, content):
        return 'Hello World, args = ' + content

class DivHelloWorldMacro(WikiMacroBase):
    """A dummy macro returning a div block, used by the unit test."""

    def expand_macro(self, formatter, name, content):
        return '<div>Hello World, args = %s</div>' % content

class DivCodeMacro(WikiMacroBase):
    """A dummy macro returning a div block, used by the unit test."""

    def expand_macro(self, formatter, name, content):
        return '<div class="code">Hello World, args = %s</div>' % content

class DivCodeElementMacro(WikiMacroBase):
    """A dummy macro returning a div block, used by the unit test."""

    def expand_macro(self, formatter, name, content):
        return html.DIV('Hello World, args = ', content, class_="code")

class NoneMacro(WikiMacroBase):
    """A dummy macro returning `None`, used by the unit test."""

    def expand_macro(self, formatter, name, content):
        return None

class SampleResolver(Component):
    """A dummy macro returning a div block, used by the unit test."""

    implements(IWikiSyntaxProvider)

    def get_wiki_syntax(self):
        return []

    def get_link_resolvers(self):
        yield ('link', self._format_link)

    def _format_link(self, formatter, ns, target, label):
        kind, module = 'text', 'stuff'
        try:
            kind = int(target) % 2 and 'odd' or 'even'
            module = 'thing'
        except ValueError:
            pass
        return html.A(label, class_='%s resolver' % kind,
                      href=formatter.href(module, target))


class WikiTestCase(unittest.TestCase):

    def __init__(self, input, correct, file, line, setup=None, teardown=None,
                 context=None):
        unittest.TestCase.__init__(self, 'test')
        self.title, self.input = input.split('\n', 1)
        if self.title:
            self.title = self.title.strip()
        self.correct = correct
        self.file = file
        self.line = line
        self._setup = setup
        self._teardown = teardown

        self.context = context and context() or Context(Mock(), None)

        self.env = self.context.env = EnvironmentStub()

        from trac.web.href import Href
        req = Mock(href=Href('/'),
                        abs_href=Href('http://www.example.com/'),
                        authname='anonymous')
        if not self.context.req:
            self.context.req = self.req = req
        else:
            self.req = self.context.req

        # -- macros support
        self.env.path = ''
        # -- intertrac support
        self.env.config.set('intertrac', 'trac.title', "Trac's Trac")
        self.env.config.set('intertrac', 'trac.url',
                            "http://trac.edgewall.org")
        self.env.config.set('intertrac', 't', 'trac')

        # TODO: remove the following lines in order to discover
        #       all the places were we should use the req.href
        #       instead of env.href
        self.env.href = self.req.href
        self.env.abs_href = self.req.abs_href

    def setUp(self):
        if self._setup:
            self._setup(self)

    def tearDown(self):
        if self._teardown:
            self._teardown(self)

    def test(self):
        """Testing WikiFormatter"""
        out = StringIO.StringIO()
        formatter = self.formatter()
        formatter.format(self.input, out)
        v = out.getvalue().replace('\r','')
        try:
            self.assertEquals(self.correct, v)
        except AssertionError, e:
            msg = to_unicode(e)
            import re
            match = re.match(r"u?'(.*)' != u?'(.*)'", msg)
            if match:
                sep = '-' * 15
                msg = '\n%s expected:\n%s\n%s actual:\n%s\n%s\n' \
                      % (sep, match.group(1), sep, match.group(2), sep)
# Tip: sometimes, 'expected' and 'actual' differ only by whitespace,
#      then replace the above line by those two:
#                      % (sep, match.group(1).replace(' ', '.'),
#                         sep, match.group(2).replace(' ', '.'), sep)
                msg = msg.replace(r'\n', '\n')
            raise AssertionError( # See below for details
                '%s\n\n%s:%s: "%s" (%s flavor)' \
                % (msg, self.file, self.line, self.title, formatter.flavor))

    def formatter(self):
        return Formatter(self.context)

    def shortDescription(self):
        return 'Test ' + self.title


class OneLinerTestCase(WikiTestCase):
    def formatter(self):
        return OneLinerFormatter(self.context)


def suite(data=None, setup=None, file=__file__, teardown=None, context=None):
    suite = unittest.TestSuite()
    if not data:
        file = os.path.join(os.path.split(file)[0], 'wiki-tests.txt')
        data = open(file, 'r').read().decode('utf-8')
    tests = data.split('=' * 30)
    next_line = 1
    line = 0
    for test in tests:
        if line != next_line:
            line = next_line
        if not test or test == '\n':
            continue
        next_line += len(test.split('\n')) - 1
        blocks = test.split('-' * 30 + '\n')
        if len(blocks) != 3:
            continue
        input, page, oneliner = blocks
        tc = WikiTestCase(input, page, file, line, setup, teardown, context)
        suite.addTest(tc)
        if oneliner:
            tc = OneLinerTestCase(input, oneliner[:-1], file, line,
                                  setup, teardown, context)
            suite.addTest(tc)
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
