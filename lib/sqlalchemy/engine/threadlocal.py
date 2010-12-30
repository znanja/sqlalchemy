"""Provides a thread-local transactional wrapper around the root Engine class.

The ``threadlocal`` module is invoked when using the ``strategy="threadlocal"`` flag
with :func:`~sqlalchemy.engine.create_engine`.  This module is semi-private and is 
invoked automatically when the threadlocal engine strategy is used.
"""

from sqlalchemy import util, event, events
from sqlalchemy.engine import base
import weakref

class TLConnection(base.Connection):
    def __init__(self, *arg, **kw):
        super(TLConnection, self).__init__(*arg, **kw)
        self.__opencount = 0
    
    def _increment_connect(self):
        self.__opencount += 1
        return self
    
    def close(self):
        if self.__opencount == 1:
            base.Connection.close(self)
        self.__opencount -= 1

    def _force_close(self):
        self.__opencount = 0
        base.Connection.close(self)

class TLEvents(events.EngineEvents):
    @classmethod
    def _listen(cls, target, identifier, fn):
        if target.TLConnection is TLConnection:
            target.TLConnection = base._listener_connection_cls(
                                        TLConnection, 
                                        target.dispatch)
        events.EngineEvents._listen(target, identifier, fn)

class TLEngine(base.Engine):
    """An Engine that includes support for thread-local managed transactions."""

    TLConnection = TLConnection

    def __init__(self, *args, **kwargs):
        super(TLEngine, self).__init__(*args, **kwargs)
        self._connections = util.threading.local()

    dispatch = event.dispatcher(TLEvents)
    
    def contextual_connect(self, **kw):
        if not hasattr(self._connections, 'conn'):
            connection = None
        else:
            connection = self._connections.conn()
        
        if connection is None or connection.closed:
            # guards against pool-level reapers, if desired.
            # or not connection.connection.is_valid:
            connection = self.TLConnection(self, self.pool.connect(), **kw)
            self._connections.conn = conn = weakref.ref(connection)
        
        return connection._increment_connect()
    
    def begin_twophase(self, xid=None):
        if not hasattr(self._connections, 'trans'):
            self._connections.trans = []
        self._connections.trans.append(self.contextual_connect().begin_twophase(xid=xid))

    def begin_nested(self):
        if not hasattr(self._connections, 'trans'):
            self._connections.trans = []
        self._connections.trans.append(self.contextual_connect().begin_nested())
        
    def begin(self):
        if not hasattr(self._connections, 'trans'):
            self._connections.trans = []
        self._connections.trans.append(self.contextual_connect().begin())
        
    def prepare(self):
        if not hasattr(self._connections, 'trans') or \
            not self._connections.trans:
            return
        self._connections.trans[-1].prepare()
        
    def commit(self):
        if not hasattr(self._connections, 'trans') or \
            not self._connections.trans:
            return
        trans = self._connections.trans.pop(-1)
        trans.commit()
        
    def rollback(self):
        if not hasattr(self._connections, 'trans') or \
            not self._connections.trans:
            return
        trans = self._connections.trans.pop(-1)
        trans.rollback()
        
    def dispose(self):
        self._connections = util.threading.local()
        super(TLEngine, self).dispose()
        
    @property
    def closed(self):
        return not hasattr(self._connections, 'conn') or \
                self._connections.conn() is None or \
                self._connections.conn().closed
        
    def close(self):
        if not self.closed:
            self.contextual_connect().close()
            connection = self._connections.conn()
            connection._force_close()
            del self._connections.conn
            self._connections.trans = []
        
    def __repr__(self):
        return 'TLEngine(%s)' % str(self.url)
