# -*- coding: utf-8 -*-

import unittest

from trac.util.text import expandtabs, javascript_quote, to_unicode


class ToUnicodeTestCase(unittest.TestCase):

    def test_explicit_charset(self):
        uc = to_unicode('\xc3\xa7', 'utf-8')
        assert isinstance(uc, unicode)
        self.assertEquals(u'\xe7', uc)

    def test_explicit_charset_with_replace(self):
        uc = to_unicode('\xc3', 'utf-8')
        assert isinstance(uc, unicode)
        self.assertEquals(u'\ufffd', uc)

    def test_implicit_charset(self):
        uc = to_unicode('\xc3\xa7')
        assert isinstance(uc, unicode)
        self.assertEquals(u'\xe7', uc)

    def test_from_exception_using_unicode_args(self):
        u = u'\uB144'
        try:
            raise ValueError, '%s is not a number.' % u
        except ValueError, e:
            self.assertEquals(u'\uB144 is not a number.', to_unicode(e))

    def test_from_exception_using_str_args(self):
        u = u'Das Ger\xe4t oder die Ressource ist belegt'
        try:
            raise ValueError, u.encode('utf-8')
        except ValueError, e:
            self.assertEquals(u, to_unicode(e))


class ExpandtabsTestCase(unittest.TestCase):
    def test_empty(self):
        x = expandtabs('', ignoring='\0')
        self.assertEquals('', x)
    def test_ingoring(self):
        x = expandtabs('\0\t', ignoring='\0')
        self.assertEquals('\0        ', x)
    def test_tabstops(self):
        self.assertEquals('        ', expandtabs('       \t'))
        self.assertEquals('                ', expandtabs('\t\t'))


class JavascriptQuoteTestCase(unittest.TestCase):
    def test_quoting(self):
        self.assertEqual(r'Quote \" in text',
                         javascript_quote('Quote " in text'))
        self.assertEqual(r'\\\"\b\f\n\r\t\'',
                         javascript_quote('\\"\b\f\n\r\t\''))
        self.assertEqual(r'\u0002\u001e',
                         javascript_quote('\x02\x1e'))


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ToUnicodeTestCase, 'test'))
    suite.addTest(unittest.makeSuite(ExpandtabsTestCase, 'test'))
    suite.addTest(unittest.makeSuite(JavascriptQuoteTestCase, 'test'))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
