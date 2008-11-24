# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2008 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

"""Utilities for text translation with gettext."""

from functools import partial
import re
import sys 
try:
    import threading
except ImportError:
    import dummy_threading as threading

import pkg_resources

from genshi.builder import tag


__all__ = ['gettext', 'ngettext', 'gettext_noop', 'ngettext_noop', 
           'tgettext', 'tgettext_noop', 'tngettext', 'tngettext_noop']


def dgettext_noop(domain, string, **kwargs):
    return kwargs and string % kwargs or string
gettext_noop = partial(dgettext_noop, None)
N_ = gettext_noop

def dngettext_noop(domain, singular, plural, num, **kwargs):
    string = (plural, singular)[num == 1]
    kwargs.setdefault('num', num)
    return string % kwargs
ngettext_noop = partial(dngettext_noop, None)

_param_re = re.compile(r"%\((\w+)\)(?:s|[\d]*d|\d*.?\d*[fg])")
def _tag_kwargs(trans, kwargs):
    trans_elts = _param_re.split(trans)
    for i in xrange(1, len(trans_elts), 2):
        trans_elts[i] = kwargs.get(trans_elts[i], '???')
    return tag(*trans_elts)

def dtgettext_noop(domain, string, **kwargs):
    return kwargs and _tag_kwargs(string, kwargs) or string
tgettext_noop = partial(dtgettext_noop, None)

def dtngettext_noop(domain, singular, plural, num, **kwargs):
    string = (plural, singular)[num == 1]
    kwargs.setdefault('num', num)
    return _tag_kwargs(string, kwargs)
tngettext_noop = partial(dtngettext_noop, None)

def add_domain(domain, env_path, locale_dir):
    pass

def domain_functions(domain, *symbols):
    _functions = {
      'gettext': gettext_noop,
      '_': gettext_noop,
      'N_': gettext_noop,
      'ngettext': ngettext_noop,
      'tgettext': tgettext_noop,
      'tag_': tgettext_noop,
      'tngettext': tngettext_noop,
      'add_domain': add_domain,
      }
    return [_functions[s] for s in symbols]


try:
    from babel.support import LazyProxy, Translations
    from gettext import NullTranslations

    class TranslationsProxy(object):
        """Delegate Translations calls to the currently active Translations.

        If there's none, wrap those calls in LazyProxy objects.
        """

        def __init__(self):
            self._current = threading.local()
            self._null_translations = NullTranslations()
            self._plugin_domains = {}
            self._plugin_domains_lock = threading.RLock()

        # Public API

        def add_domain(self, domain, env_path, locales_dir):
            self._plugin_domains_lock.acquire()
            try:
                if env_path not in self._plugin_domains:
                    self._plugin_domains[env_path] = []
                self._plugin_domains[env_path].append((domain, locales_dir))
            finally:
                self._plugin_domains_lock.release()

        def activate(self, locale, env_path=None):
            locale_dir = pkg_resources.resource_filename(__name__, '../locale')
            t = Translations.load(locale_dir, locale)
            if env_path:
                self._plugin_domains_lock.acquire()
                try:
                    domains = list(self._plugin_domains.get(env_path, []))
                finally:
                    self._plugin_domains_lock.release()
                for domain, dirname in domains:
                    t.add(Translations.load(dirname, locale, domain))
            self._current.translations = t
         
        def deactivate(self):
            del self._current.translations
    
        @property
        def active(self):
            return getattr(self._current, 'translations', 
                           self._null_translations)

        @property
        def isactive(self):
            return hasattr(self._current, 'translations')

        # Delegated methods

        def __getattr__(self, name):
            return getattr(self.active, name)

        def gettext(self, string, **kwargs):
            def _gettext():
                trans = self.active.ugettext(string)
                return kwargs and trans % kwargs or trans
            if not self.isactive:
                return LazyProxy(_gettext)
            return _gettext()

        def dgettext(self, domain, string, **kwargs):
            def _dgettext():
                trans = self.active.dugettext(domain, string)
                return kwargs and trans % kwargs or trans
            if not self.isactive:
                return LazyProxy(_dgettext)
            return _dgettext()

        def ngettext(self, singular, plural, num, **kwargs):
            kwargs = kwargs.copy()
            kwargs.setdefault('num', num)
            def _ngettext():
                trans = self.active.ungettext(singular, plural, num)
                return trans % kwargs
            if not self.isactive:
                return LazyProxy(_ngettext)
            return _ngettext()

        def dngettext(self, domain, singular, plural, num, **kwargs):
            kwargs = kwargs.copy()
            kwargs.setdefault('num', num)
            def _dngettext():
                trans = self.active.dungettext(domain, singular, plural, num)
                return trans % kwargs
            if not self.isactive:
                return LazyProxy(_dngettext)
            return _dngettext()

        def tgettext(self, string, **kwargs):
            def _tgettext():
                trans = self.active.ugettext(string)
                return kwargs and _tag_kwargs(trans, kwargs) or trans
            if not self.isactive:
                return LazyProxy(_tgettext)
            return _tgettext()

        def dtgettext(self, domain, string, **kwargs):
            def _dtgettext():
                trans = self.active.dugettext(domain, string)
                return kwargs and _tag_kwargs(trans, kwargs) or trans
            if not self.isactive:
                return LazyProxy(_dtgettext)
            return _dtgettext()

        def tngettext(self, singular, plural, num, **kwargs):
            kwargs = kwargs.copy()
            kwargs.setdefault('num', num)
            def _tngettext():
                trans = self.active.ungettext(singular, plural, num)
                return _tag_kwargs(trans, kwargs)
            if not self.isactive:
                return LazyProxy(_tngettext)
            return _tngettext()

        def dtngettext(self, domain, singular, plural, num, **kwargs):
            kwargs = kwargs.copy()
            def _dtngettext():
                trans = self.active.dungettext(domain, singular, plural, num)
                if '%(num)' in trans:
                    kwargs.update(num=num)
                return kwargs and _tag_kwargs(trans, kwargs) or trans
            if not self.isactive:
                return LazyProxy(_dtngettext)
            return _dtngettext()

    
    translations = TranslationsProxy()

    def domain_functions(domain, *symbols):
        _functions = {
          'gettext': translations.dgettext,
          '_': translations.dgettext,
          'ngettext': translations.dngettext,
          'tgettext': translations.dtgettext,
          'tag_': translations.dtgettext,
          'tngettext': translations.dtngettext,
          'add_domain': translations.add_domain,
          }
        def wrapdomain(symbol):
            if symbol == 'N_':
                return gettext_noop
            return lambda *args, **kw: _functions[symbol](domain, *args, **kw)
        return [wrapdomain(s) for s in symbols]

    gettext = translations.gettext 
    _ = gettext 
    dgettext = translations.dgettext 
    ngettext = translations.ngettext 
    dngettext = translations.dngettext 
    tgettext = translations.tgettext 
    tag_ = tgettext 
    dtgettext = translations.dtgettext 
    tngettext = translations.tngettext 
    dtngettext = translations.dtngettext 
    
    def deactivate():
        translations.deactivate()

    def activate(locale, env_path=None):
        translations.activate(locale, env_path)

    def add_domain(domain, env_path, locale_dir):
        translations.add_domain(domain, env_path, locale_dir)

    def get_translations():
        return translations

    def get_available_locales():
        """Return a list of locale identifiers of the locales for which
        translations are available.
        """
        return [dirname for dirname
                in pkg_resources.resource_listdir(__name__, '../locale')
                if '.' not in dirname]

except ImportError: # fall back on 0.11 behavior, i18n functions are no-ops
    gettext = _ = gettext_noop
    dgettext = dgettext_noop
    ngettext = ngettext_noop
    dngettext = dngettext_noop
    tgettext = tag_ = tgettext_noop
    dtgettext = dtgettext_noop
    tngettext = tngettext_noop
    dtngettext = dtngettext_noop

    def activate(locale, env_path=None):
        pass

    def deactivate():
        pass

    def get_translations():
        return []

    def get_available_locales():
        return []
