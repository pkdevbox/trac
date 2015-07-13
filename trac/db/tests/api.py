# -*- coding: utf-8 -*-

import os
import unittest

from trac.db.api import DatabaseManager, _parse_db_str, get_column_names, \
                        with_transaction
from trac.db.schema import Column, Table
from trac.test import EnvironmentStub, Mock
from trac.util.concurrency import ThreadLocal


class Connection(object):
    
    committed = False
    rolledback = False
    
    def commit(self):
        self.committed = True
    
    def rollback(self):
        self.rolledback = True


class Error(Exception):
    pass


class MockDatabaseManager(object):
    def __init__(self):
        self._transaction_local = ThreadLocal(db=None)
        
class MinimalEnv(object):
    def __init__(self, db=None):
        self.db = db
        self.components = {DatabaseManager: MockDatabaseManager()}
    def get_db_cnx(self):
        if self.db is Connection:
            return Connection()
        return self.db


class WithTransactionTest(unittest.TestCase):

    def test_successful_transaction(self):
        db = Connection()
        env = MinimalEnv(db)
        @with_transaction(env)
        def do_transaction(db):
            self.assertTrue(not db.committed and not db.rolledback)
        self.assertTrue(db.committed and not db.rolledback)
        
    def test_failed_transaction(self):
        db = Connection()
        env = MinimalEnv(db)
        try:
            @with_transaction(env)
            def do_transaction(db):
                self.assertTrue(not db.committed and not db.rolledback)
                raise Error()
            self.fail()
        except Error:
            pass
        self.assertTrue(not db.committed and db.rolledback)
        
    def test_implicit_nesting_success(self):
        env = MinimalEnv(Connection)
        dbs = [None, None]
        @with_transaction(env)
        def level0(db):
            dbs[0] = db
            @with_transaction(env)
            def level1(db):
                dbs[1] = db
                self.assertTrue(not db.committed and not db.rolledback)
            self.assertTrue(not db.committed and not db.rolledback)
        self.assertTrue(dbs[0] is not None)
        self.assertTrue(dbs[0] is dbs[1])
        self.assertTrue(dbs[0].committed and not dbs[0].rolledback)

    def test_implicit_nesting_failure(self):
        env = MinimalEnv(Connection)
        dbs = [None, None]
        try:
            @with_transaction(env)
            def level0(db):
                dbs[0] = db
                try:
                    @with_transaction(env)
                    def level1(db):
                        dbs[1] = db
                        self.assertTrue(not db.committed and not db.rolledback)
                        raise Error()
                    self.fail()
                except Error:
                    self.assertTrue(not db.committed and not db.rolledback)
                    raise
            self.fail()
        except Error:
            pass
        self.assertTrue(dbs[0] is not None)
        self.assertTrue(dbs[0] is dbs[1])
        self.assertTrue(not dbs[0].committed and dbs[0].rolledback)

    def test_explicit_success(self):
        db = Connection()
        env = MinimalEnv(None)
        @with_transaction(env, db)
        def do_transaction(idb):
            self.assertTrue(idb is db)
            self.assertTrue(not db.committed and not db.rolledback)
        self.assertTrue(not db.committed and not db.rolledback)

    def test_explicit_failure(self):
        db = Connection()
        env = MinimalEnv(None)
        try:
            @with_transaction(env, db)
            def do_transaction(idb):
                self.assertTrue(idb is db)
                self.assertTrue(not db.committed and not db.rolledback)
                raise Error()
            self.fail()
        except Error:
            pass
        self.assertTrue(not db.committed and not db.rolledback)

    def test_implicit_in_explicit_success(self):
        db = Connection()
        env = MinimalEnv(Connection)
        dbs = [None, None]
        @with_transaction(env, db)
        def level0(db):
            dbs[0] = db
            @with_transaction(env)
            def level1(db):
                dbs[1] = db
                self.assertTrue(not db.committed and not db.rolledback)
            self.assertTrue(not db.committed and not db.rolledback)
        self.assertTrue(dbs[0] is not None)
        self.assertTrue(dbs[0] is dbs[1])
        self.assertTrue(not dbs[0].committed and not dbs[0].rolledback)

    def test_implicit_in_explicit_failure(self):
        db = Connection()
        env = MinimalEnv(Connection)
        dbs = [None, None]
        try:
            @with_transaction(env, db)
            def level0(db):
                dbs[0] = db
                @with_transaction(env)
                def level1(db):
                    dbs[1] = db
                    self.assertTrue(not db.committed and not db.rolledback)
                    raise Error()
                self.fail()
            self.fail()
        except Error:
            pass
        self.assertTrue(dbs[0] is not None)
        self.assertTrue(dbs[0] is dbs[1])
        self.assertTrue(not dbs[0].committed and not dbs[0].rolledback)

    def test_explicit_in_implicit_success(self):
        db = Connection()
        env = MinimalEnv(Connection)
        dbs = [None, None]
        @with_transaction(env)
        def level0(db):
            dbs[0] = db
            @with_transaction(env, db)
            def level1(db):
                dbs[1] = db
                self.assertTrue(not db.committed and not db.rolledback)
            self.assertTrue(not db.committed and not db.rolledback)
        self.assertTrue(dbs[0] is not None)
        self.assertTrue(dbs[0] is dbs[1])
        self.assertTrue(dbs[0].committed and not dbs[0].rolledback)

    def test_explicit_in_implicit_failure(self):
        db = Connection()
        env = MinimalEnv(Connection)
        dbs = [None, None]
        try:
            @with_transaction(env)
            def level0(db):
                dbs[0] = db
                @with_transaction(env, db)
                def level1(db):
                    dbs[1] = db
                    self.assertTrue(not db.committed and not db.rolledback)
                    raise Error()
                self.fail()
            self.fail()
        except Error:
            pass
        self.assertTrue(dbs[0] is not None)
        self.assertTrue(dbs[0] is dbs[1])
        self.assertTrue(not dbs[0].committed and dbs[0].rolledback)

    def test_invalid_nesting(self):
        env = MinimalEnv(Connection)
        try:
            @with_transaction(env)
            def level0(db):
                @with_transaction(env, Connection())
                def level1(db):
                    raise Error()
                raise Error()
            raise Error()
        except AssertionError:
            pass



class ParseConnectionStringTestCase(unittest.TestCase):

    def test_sqlite_relative(self):
        # Default syntax for specifying DB path relative to the environment
        # directory
        self.assertEqual(('sqlite', {'path': 'db/trac.db'}),
                         _parse_db_str('sqlite:db/trac.db'))

    def test_sqlite_absolute(self):
        # Standard syntax
        self.assertEqual(('sqlite', {'path': '/var/db/trac.db'}),
                         _parse_db_str('sqlite:///var/db/trac.db'))
        # Legacy syntax
        self.assertEqual(('sqlite', {'path': '/var/db/trac.db'}),
                         _parse_db_str('sqlite:/var/db/trac.db'))

    def test_sqlite_with_timeout_param(self):
        # In-memory database
        self.assertEqual(('sqlite', {'path': 'db/trac.db',
                                     'params': {'timeout': '10000'}}),
                         _parse_db_str('sqlite:db/trac.db?timeout=10000'))

    def test_sqlite_windows_path(self):
        # In-memory database
        os_name = os.name
        try:
            os.name = 'nt'
            self.assertEqual(('sqlite', {'path': 'C:/project/db/trac.db'}),
                             _parse_db_str('sqlite:C|/project/db/trac.db'))
        finally:
            os.name = os_name

    def test_postgres_simple(self):
        self.assertEqual(('postgres', {'host': 'localhost', 'path': '/trac'}),
                         _parse_db_str('postgres://localhost/trac'))

    def test_postgres_with_port(self):
        self.assertEqual(('postgres', {'host': 'localhost', 'port': 9431,
                                       'path': '/trac'}),
                         _parse_db_str('postgres://localhost:9431/trac'))

    def test_postgres_with_creds(self):
        self.assertEqual(('postgres', {'user': 'john', 'password': 'letmein',
                                       'host': 'localhost', 'port': 9431,
                                       'path': '/trac'}),
                 _parse_db_str('postgres://john:letmein@localhost:9431/trac'))

    def test_postgres_with_quoted_password(self):
        self.assertEqual(('postgres', {'user': 'john', 'password': ':@/',
                                       'host': 'localhost', 'path': '/trac'}),
                     _parse_db_str('postgres://john:%3a%40%2f@localhost/trac'))

    def test_mysql_simple(self):
        self.assertEqual(('mysql', {'host': 'localhost', 'path': '/trac'}),
                     _parse_db_str('mysql://localhost/trac'))

    def test_mysql_with_creds(self):
        self.assertEqual(('mysql', {'user': 'john', 'password': 'letmein',
                                    'host': 'localhost', 'port': 3306,
                                    'path': '/trac'}),
                     _parse_db_str('mysql://john:letmein@localhost:3306/trac'))


class StringsTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()

    def tearDown(self):
        self.env.reset_db()

    def test_insert_unicode(self):
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute('INSERT INTO system (name,value) VALUES (%s,%s)',
                       ('test-unicode', u'ünicöde'))
        db.commit()
        cursor = db.cursor()
        cursor.execute("SELECT value FROM system WHERE name='test-unicode'")
        self.assertEqual([(u'ünicöde',)], cursor.fetchall())

    def test_insert_empty(self):
        from trac.util.text import empty
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute('INSERT INTO system (name,value) VALUES (%s,%s)',
                       ('test-empty', empty))
        db.commit()
        cursor = db.cursor()
        cursor.execute("SELECT value FROM system WHERE name='test-empty'")
        self.assertEqual([(u'',)], cursor.fetchall())

    def test_insert_markup(self):
        from genshi.core import Markup
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute('INSERT INTO system (name,value) VALUES (%s,%s)',
                       ('test-markup', Markup(u'<em>märkup</em>')))
        db.commit()
        cursor = db.cursor()
        cursor.execute("SELECT value FROM system WHERE name='test-markup'")
        self.assertEqual([(u'<em>märkup</em>',)], cursor.fetchall())

    def test_quote(self):
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute('SELECT 1 AS %s' % \
                       db.quote(r'alpha\`\"\'\\beta``gamma""delta'))
        self.assertEqual(r'alpha\`\"\'\\beta``gamma""delta',
                         get_column_names(cursor)[0])

    def test_quoted_id_with_percent(self):
        db = self.env.get_read_db()
        name = """%?`%s"%'%%"""

        def test(db, logging=False):
            cursor = db.cursor()
            if logging:
                cursor.log = self.env.log

            cursor.execute('SELECT 1 AS ' + db.quote(name))
            self.assertEqual(name, get_column_names(cursor)[0])
            cursor.execute('SELECT %s AS ' + db.quote(name), (42,))
            self.assertEqual(name, get_column_names(cursor)[0])
            cursor.executemany("UPDATE system SET value=%s WHERE "
                               "1=(SELECT 0 AS " + db.quote(name) + ")",
                               [])
            cursor.executemany("UPDATE system SET value=%s WHERE "
                               "1=(SELECT 0 AS " + db.quote(name) + ")",
                               [('42',), ('43',)])

        test(db)
        test(db, logging=True)

    def test_prefix_match_case_sensitive(self):
        @self.env.with_transaction()
        def do_insert(db):
            cursor = db.cursor()
            cursor.executemany("INSERT INTO system (name,value) VALUES (%s,1)",
                               [('blahblah',), ('BlahBlah',), ('BLAHBLAH',),
                                (u'BlähBlah',), (u'BlahBläh',)])

        db = self.env.get_read_db()
        cursor = db.cursor()
        cursor.execute("SELECT name FROM system WHERE name %s" %
                       db.prefix_match(),
                       (db.prefix_match_value('Blah'),))
        names = sorted(name for name, in cursor)
        self.assertEqual('BlahBlah', names[0])
        self.assertEqual(u'BlahBläh', names[1])
        self.assertEqual(2, len(names))

    def test_prefix_match_metachars(self):
        def do_query(prefix):
            db = self.env.get_read_db()
            cursor = db.cursor()
            cursor.execute("SELECT name FROM system WHERE name %s "
                           "ORDER BY name" % db.prefix_match(),
                           (db.prefix_match_value(prefix),))
            return [name for name, in cursor]

        @self.env.with_transaction()
        def do_insert(db):
            values = ['foo*bar', 'foo*bar!', 'foo?bar', 'foo?bar!',
                      'foo[bar', 'foo[bar!', 'foo]bar', 'foo]bar!',
                      'foo%bar', 'foo%bar!', 'foo_bar', 'foo_bar!',
                      'foo/bar', 'foo/bar!', 'fo*ob?ar[fo]ob%ar_fo/obar']
            cursor = db.cursor()
            cursor.executemany("INSERT INTO system (name,value) VALUES (%s,1)",
                               [(value,) for value in values])

        self.assertEqual(['foo*bar', 'foo*bar!'], do_query('foo*'))
        self.assertEqual(['foo?bar', 'foo?bar!'], do_query('foo?'))
        self.assertEqual(['foo[bar', 'foo[bar!'], do_query('foo['))
        self.assertEqual(['foo]bar', 'foo]bar!'], do_query('foo]'))
        self.assertEqual(['foo%bar', 'foo%bar!'], do_query('foo%'))
        self.assertEqual(['foo_bar', 'foo_bar!'], do_query('foo_'))
        self.assertEqual(['foo/bar', 'foo/bar!'], do_query('foo/'))
        self.assertEqual(['fo*ob?ar[fo]ob%ar_fo/obar'], do_query('fo*'))
        self.assertEqual(['fo*ob?ar[fo]ob%ar_fo/obar'],
                         do_query('fo*ob?ar[fo]ob%ar_fo/obar'))


class ConnectionTestCase(unittest.TestCase):
    def setUp(self):
        self.env = EnvironmentStub()
        self.db = self.env.get_db_cnx()
        self.tables = [
            Table('HOURS', key='ID')[
                Column('ID', auto_increment=True),
                Column('AUTHOR')],
            Table('blog', key='bid')[
                Column('bid', auto_increment=True),
                Column('author')
            ]
        ]
        self._drop_tables(self.tables)
        self._create_tables(self.tables)

    def tearDown(self):
        self._drop_tables(self.tables)
        self.env.reset_db()

    def _create_tables(self, tables):
        @self.env.with_transaction()
        def do_create(db):
            connector = DatabaseManager(self.env).get_connector()[0]
            cursor = self.db.cursor()
            for table in tables:
                for sql in connector.to_sql(table):
                    cursor.execute(sql)

    def _drop_tables(self, tables):
        @self.env.with_transaction()
        def do_drop(db):
            for table in tables:
                self.db.drop_table(table.name)

    def test_get_last_id(self):
        c = self.db.cursor()
        q = "INSERT INTO report (author) VALUES ('anonymous')"
        c.execute(q)
        # Row ID correct before...
        id1 = self.db.get_last_id(c, 'report')
        self.assertNotEqual(0, id1)
        self.db.commit()
        c.execute(q)
        self.db.commit()
        # ... and after commit()
        id2 = self.db.get_last_id(c, 'report')
        self.assertEqual(id1 + 1, id2)

    def test_update_sequence_default_column(self):
        cursor = self.db.cursor()
        cursor.execute("""
            INSERT INTO report (id, author) VALUES (42, 'anonymous')
            """)
        self.db.commit()
        self.db.update_sequence(cursor, 'report', 'id')
        self.db.commit()
        cursor.execute("INSERT INTO report (author) VALUES ('next-id')")
        self.db.commit()
        cursor.execute("SELECT id FROM report WHERE author='next-id'")
        self.assertEqual(43, cursor.fetchall()[0][0])

    def test_update_sequence_nondefault_column(self):
        db = self.db
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO blog (bid, author) VALUES (42, 'anonymous')")
        db.commit()

        db.update_sequence(cursor, 'blog', 'bid')
        db.commit()
        cursor.execute("INSERT INTO blog (author) VALUES ('next-id')")
        db.commit()

        cursor.execute("SELECT bid FROM blog WHERE author='next-id'")
        self.assertEqual(43, cursor.fetchall()[0][0])

    def test_identifiers_need_quoting(self):
        """Test for regression described in comment:4:ticket:11512."""
        db = self.db
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO %s (%s, %s) VALUES (42, 'anonymous')"
            % (db.quote('HOURS'), db.quote('ID'), db.quote('AUTHOR')))
        db.commit()
        db.update_sequence(cursor, 'HOURS', 'ID')
        db.commit()

        cursor.execute(
            "INSERT INTO %s (%s) VALUES ('next-id')"
            % (db.quote('HOURS'), db.quote('AUTHOR')))
        db.commit()
        last_id = db.get_last_id(cursor, 'HOURS', 'ID')

        self.assertEqual(43, last_id)


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ParseConnectionStringTestCase, 'test'))
    suite.addTest(unittest.makeSuite(StringsTestCase, 'test'))
    suite.addTest(unittest.makeSuite(ConnectionTestCase, 'test'))
    suite.addTest(unittest.makeSuite(WithTransactionTest, 'test'))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
