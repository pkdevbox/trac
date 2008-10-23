#!/usr/bin/python
"""better_twill is a small wrapper around twill to set some sane defaults and
monkey-patch some better versions of some of twill's methods.
It also handles twill's absense.
"""

import os
from os.path import abspath, dirname, join
import sys
from pkg_resources import parse_version as pv
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

# On OSX lxml needs to be imported before twill to avoid Resolver issues
# somehow caused by the mac specific 'ic' module
try:
    from lxml import etree
except ImportError:
    pass

try:
    import twill
except ImportError:
    twill = None

# When twill tries to connect to a site before the site is up, it raises an
# exception.  In 0.9b1, it's urlib2.URLError, but in -latest, it's
# _mechanize_dist._mechanize.BrowserStateError.
try:
    from _mechanize_dist._mechanize import BrowserStateError as ConnectError
except ImportError:
    from urllib2 import URLError as ConnectError


if twill:
    # We want Trac to generate valid html, and therefore want to test against
    # the html as generated by Trac.  "tidy" tries to clean up broken html, and
    # is responsible for one difficult to track down testcase failure (for
    # #5497).  Therefore we turn it off here.
    twill.commands.config('use_tidy', '0')

    # We use a transparent proxy to access the global browser object through
    # twill.get_browser(), as the browser can be destroyed by browser_reset()
    # (see #7472).
    class _BrowserProxy(object):
        def __getattribute__(self, name):
            return getattr(twill.get_browser(), name)
        
        def __setattr(self, name, value):
            setattr(twill.get_browser(), name, value)
            
    # setup short names to reduce typing
    # This twill browser (and the tc commands that use it) are essentially
    # global, and not tied to our test fixture.
    tc = twill.commands
    b = _BrowserProxy()

    # Setup XHTML validation for all retrieved pages
    try:
        from lxml import etree
    except ImportError:
        print "SKIP: validation of XHTML output in functional tests " \
              "(no lxml installed)"
        etree = None

    if etree and pv(etree.__version__) < pv('2.0.0'):
        # 2.0.7 and 2.1.x are known to work.
        print "SKIP: validation of XHTML output in functional tests " \
              "(lxml < 2.0, api incompatibility)"
        etree = None

    if etree:
        class _Resolver(etree.Resolver):
            base_dir = dirname(abspath(__file__))

            def resolve(self, system_url, public_id, context):
                return self.resolve_filename(join(self.base_dir,
                                                  system_url.split("/")[-1]),
                                             context)

        _parser = etree.XMLParser(dtd_validation=True)
        _parser.resolvers.add(_Resolver())
        etree.set_default_parser(_parser)

        def _format_error_log(data, log):
            msg = []
            for entry in log:
                context = data.splitlines()[max(0, entry.line - 5):
                                            entry.line + 6]
                msg.append("\n# %s\n# URL: %s\n# Line %d, column %d\n\n%s\n"
                    % (entry.message, entry.filename, 
                       entry.line, entry.column,
                       "\n".join([each.decode('utf-8') for each in context])))
            return "\n".join(msg).encode('ascii', 'xmlcharrefreplace')

        def _validate_xhtml(func_name, *args, **kwargs):
            page = b.get_html()
            if "xhtml1-strict.dtd" not in page:
                return
            etree.clear_error_log()
            try:
                doc = etree.parse(StringIO(page), base_url=b.get_url())
            except etree.XMLSyntaxError, e:
                raise twill.errors.TwillAssertionError(
                    _format_error_log(page, e.error_log))

        b._post_load_hooks.append(_validate_xhtml)

    # When we can't find something we expected, or find something we didn't
    # expect, it helps the debugging effort to have a copy of the html to
    # analyze.
    def twill_write_html():
        """Write the current html to a file.  Name the file based on the
        current testcase.
        """
        frame = sys._getframe()
        while frame:
            if frame.f_code.co_name in ('runTest', 'setUp', 'tearDown'):
                testcase = frame.f_locals['self']
                testname = testcase.__class__.__name__
                tracdir = testcase._testenv.tracdir
                break
            frame = frame.f_back
        else:
            # We didn't find a testcase in the stack, so we have no clue what's
            # going on.
            raise Exception("No testcase was found on the stack.  This was "
                "really not expected, and I don't know how to handle it.")

        filename = os.path.join(tracdir, 'log', "%s.html" % testname)
        html_file = open(filename, 'w')
        html_file.write(b.get_html())
        html_file.close()

        return filename

    # Twill isn't as helpful with errors as I'd like it to be, so we replace
    # the formvalue function.  This would be better done as a patch to Twill.
    def better_formvalue(form, field, value, fv=tc.formvalue):
        try:
            fv(form, field, value)
        except (twill.errors.TwillAssertionError,
                twill.utils.ClientForm.ItemNotFoundError), e:
            filename = twill_write_html()
            args = e.args + (filename,)
            raise twill.errors.TwillAssertionError(*args)
    tc.formvalue = better_formvalue

    # Twill's formfile function leaves a filehandle open which prevents the
    # file from being deleted on Windows.  Since we would just assume use a
    # StringIO object in the first place, allow the file-like object to be
    # provided directly.
    def better_formfile(formname, fieldname, filename, content_type=None,
                        fp=None):
        if not fp:
            filename = filename.replace('/', os.path.sep)
            temp_fp = open(filename, 'rb')
            data = temp_fp.read()
            temp_fp.close()
            fp = StringIO(data)

        form = b.get_form(formname)
        control = b.get_form_field(form, fieldname)

        if not control.is_of_kind('file'):
            raise twill.errors.TwillException('ERROR: field is not a file '
                                              'upload field!')

        b.clicked(form, control)
        control.add_file(fp, content_type, filename)
    tc.formfile = better_formfile

    # Twill's tc.find() does not provide any guidance on what we got instead of
    # what was expected.
    def better_find(what, flags='', tcfind=tc.find):
        try:
            tcfind(what, flags)
        except twill.errors.TwillAssertionError, e:
            filename = twill_write_html()
            args = e.args + (filename,)
            raise twill.errors.TwillAssertionError(*args)
    tc.find = better_find
    def better_notfind(what, flags='', tcnotfind=tc.notfind):
        try:
            tcnotfind(what, flags)
        except twill.errors.TwillAssertionError, e:
            filename = twill_write_html()
            args = e.args + (filename,)
            raise twill.errors.TwillAssertionError(*args)
    tc.notfind = better_notfind
else:
    b = tc = None
