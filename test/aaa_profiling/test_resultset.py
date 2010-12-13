from sqlalchemy import *
from test.lib import *
NUM_FIELDS = 10
NUM_RECORDS = 1000


class ResultSetTest(TestBase, AssertsExecutionResults):

    __only_on__ = 'sqlite'

    @classmethod
    def setup_class(cls):
        global t, t2, metadata
        metadata = MetaData(testing.db)
        t = Table('table', metadata, *[Column('field%d' % fnum, String)
                  for fnum in range(NUM_FIELDS)])
        t2 = Table('table2', metadata, *[Column('field%d' % fnum,
                   Unicode) for fnum in range(NUM_FIELDS)])

    def setup(self):
        metadata.create_all()
        t.insert().execute([dict(('field%d' % fnum, u'value%d' % fnum)
                           for fnum in range(NUM_FIELDS)) for r_num in
                           range(NUM_RECORDS)])
        t2.insert().execute([dict(('field%d' % fnum, u'value%d' % fnum)
                            for fnum in range(NUM_FIELDS)) for r_num in
                            range(NUM_RECORDS)])

    def teardown(self):
        metadata.drop_all()

    @profiling.function_call_count(14416, versions={'2.4': 13214,
                                   '2.6+cextension': 410, '2.7+cextension':401})
    def test_string(self):
        [tuple(row) for row in t.select().execute().fetchall()]

    # sqlite3 returns native unicode.  so shouldn't be an increase here.

    @profiling.function_call_count(14396, versions={'2.4': 13214,
                                   '2.6+cextension': 409, 
                                   '2.7+cextension':409})
    def test_unicode(self):
        [tuple(row) for row in t2.select().execute().fetchall()]

class ExecutionTest(TestBase):
    __only_on__ = 'sqlite'
    
    def test_minimal_connection_execute(self):
        # create an engine without any instrumentation.
        e = create_engine('sqlite://')
        c = e.connect()
        # ensure initial connect activities complete
        c.execute("select 1")
        
        @profiling.function_call_count(36, versions={'2.6':35, '2.5':35, 
                                                    '2.4':21, '3':34}, 
                                            variance=.10)
        def go():
            c.execute("select 1")
        go()

    def test_minimal_engine_execute(self):
        # create an engine without any instrumentation.
        e = create_engine('sqlite://')
        # ensure initial connect activities complete
        e.execute("select 1")

        @profiling.function_call_count(59, versions={'2.4':41, '2.5':58, 
                                                    '2.6':58, '3':57}, 
                                            variance=.05)
        def go():
            e.execute("select 1")
        go()

