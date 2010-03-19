from sqlalchemy.connectors import Connector
from sqlalchemy.util import asbool

import sys
import re
import urllib
import decimal
from sqlalchemy import processors, types as sqltypes

class PyODBCNumeric(sqltypes.Numeric):
    """Turns Decimals with adjusted() < -6 into floats."""
    
    def bind_processor(self, dialect):
        super_process = super(PyODBCNumeric, self).bind_processor(dialect)
        
        def process(value):
            if self.asdecimal and \
                    isinstance(value, decimal.Decimal) and \
                    value.adjusted() < -6:
                return processors.to_float(value)
            elif super_process:
                return super_process(value)
            else:
                return value
        return process

    # This method turns the adjusted into a string.
    # not sure if this has advantages over the simple float
    # approach above.
#    def bind_processor(self, dialect):
#        def process(value):
#            if isinstance(value, decimal.Decimal):
#                if value.adjusted() < 0:
#                    result = "%s0.%s%s" % (
#                            (value < 0 and '-' or ''),
#                            '0' * (abs(value.adjusted()) - 1),
#                            "".join([str(nint) for nint in value._int]))
#
#                else:
#                    if 'E' in str(value):
#                        result = "%s%s%s" % (
#                                (value < 0 and '-' or ''),
#                                "".join([str(s) for s in value._int]),
#                                "0" * (value.adjusted() - (len(value._int)-1)))
#                    else:
#                        if (len(value._int) - 1) > value.adjusted():
#                            result = "%s%s.%s" % (
#                                    (value < 0 and '-' or ''),
#                                    "".join([str(s) for s in value._int][0:value.adjusted() + 1]),
#                                    "".join([str(s) for s in value._int][value.adjusted() + 1:]))
#                        else:
#                            result = "%s%s" % (
#                                    (value < 0 and '-' or ''),
#                                    "".join([str(s) for s in value._int][0:value.adjusted() + 1]))
#                return result
#
#            else:
#                return value
#        return process

class PyODBCConnector(Connector):
    driver='pyodbc'

    supports_sane_multi_rowcount = False
    # PyODBC unicode is broken on UCS-4 builds
    supports_unicode = sys.maxunicode == 65535
    supports_unicode_statements = supports_unicode
    supports_native_decimal = True
    default_paramstyle = 'named'
    
    # for non-DSN connections, this should
    # hold the desired driver name
    pyodbc_driver_name = None
    
    # will be set to True after initialize()
    # if the freetds.so is detected
    freetds = False
    
    @classmethod
    def dbapi(cls):
        return __import__('pyodbc')

    def create_connect_args(self, url):
        opts = url.translate_connect_args(username='user')
        opts.update(url.query)
        
        keys = opts
        query = url.query

        connect_args = {}
        for param in ('ansi', 'unicode_results', 'autocommit'):
            if param in keys:
                connect_args[param] = asbool(keys.pop(param))

        if 'odbc_connect' in keys:
            connectors = [urllib.unquote_plus(keys.pop('odbc_connect'))]
        else:
            dsn_connection = 'dsn' in keys or ('host' in keys and 'database' not in keys)
            if dsn_connection:
                connectors= ['dsn=%s' % (keys.pop('host', '') or keys.pop('dsn', ''))]
            else:
                port = ''
                if 'port' in keys and not 'port' in query:
                    port = ',%d' % int(keys.pop('port'))

                connectors = ["DRIVER={%s}" % keys.pop('driver', self.pyodbc_driver_name),
                              'Server=%s%s' % (keys.pop('host', ''), port),
                              'Database=%s' % keys.pop('database', '') ]

            user = keys.pop("user", None)
            if user:
                connectors.append("UID=%s" % user)
                connectors.append("PWD=%s" % keys.pop('password', ''))
            else:
                connectors.append("Trusted_Connection=Yes")

            # if set to 'Yes', the ODBC layer will try to automagically convert 
            # textual data from your database encoding to your client encoding 
            # This should obviously be set to 'No' if you query a cp1253 encoded 
            # database from a latin1 client... 
            if 'odbc_autotranslate' in keys:
                connectors.append("AutoTranslate=%s" % keys.pop("odbc_autotranslate"))

            connectors.extend(['%s=%s' % (k,v) for k,v in keys.iteritems()])
        return [[";".join (connectors)], connect_args]
        
    def is_disconnect(self, e):
        if isinstance(e, self.dbapi.ProgrammingError):
            return "The cursor's connection has been closed." in str(e) or \
                            'Attempt to use a closed connection.' in str(e)
        elif isinstance(e, self.dbapi.Error):
            return '[08S01]' in str(e)
        else:
            return False

    def initialize(self, connection):
        # determine FreeTDS first.   can't issue SQL easily
        # without getting unicode_statements/binds set up.
        
        pyodbc = self.dbapi

        dbapi_con = connection.connection

        self.freetds = bool(re.match(r".*libtdsodbc.*\.so",  dbapi_con.getinfo(pyodbc.SQL_DRIVER_NAME)))

        # the "Py2K only" part here is theoretical.
        # have not tried pyodbc + python3.1 yet.
        # Py2K
        self.supports_unicode_statements = not self.freetds
        self.supports_unicode_binds = not self.freetds
        # end Py2K
        
        # run other initialization which asks for user name, etc.
        super(PyODBCConnector, self).initialize(connection)

    def _get_server_version_info(self, connection):
        dbapi_con = connection.connection
        version = []
        r = re.compile('[.\-]')
        for n in r.split(dbapi_con.getinfo(self.dbapi.SQL_DBMS_VER)):
            try:
                version.append(int(n))
            except ValueError:
                version.append(n)
        return tuple(version)
