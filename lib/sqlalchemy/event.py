"""
The event system handles all events throughout the :mod:`sqlalchemy`
and :mod:`sqlalchemy.orm` packages.


"""

from sqlalchemy import util

def listen(fn, identifier, target, *args, **kw):
    """Listen for events, passing to fn."""

    # rationale - the events on ClassManager, Session, and Mapper
    # will need to accept mapped classes directly as targets and know 
    # what to do
    
    for evt_cls in _registrars[identifier]:
        for tgt in evt_cls.accept_with(target):
            
            tgt.dispatch.events.listen(fn, identifier, tgt, *args, **kw)
            break
    
class _DispatchMeta(type):
    def __init__(cls, classname, bases, dict_):
        
        dispatch_base = getattr(cls, 'dispatch', Dispatch)
        cls.dispatch = dispatch_cls = type("%sDispatch" % classname, (dispatch_base, ), {})
        dispatch_cls.events = cls
        for k in dict_:
            if k.startswith('on_'):
                setattr(dispatch_cls, k, EventDescriptor(dict_[k]))
                _registrars[k].append(cls)
        return type.__init__(cls, classname, bases, dict_)

_registrars = util.defaultdict(list)

class Dispatch(object):

    def __init__(self, parent_cls):
        self.parent_cls = parent_cls
    
    @property
    def descriptors(self):
        return (getattr(self, k) for k in dir(self) if k.startswith("on_"))
        
    def update(self, other):
        """Populate from the listeners in another :class:`Events` object."""

        for ls in other.descriptors:
            getattr(self, ls.name).listeners.extend(ls.listeners)


class Events(object):
    __metaclass__ = _DispatchMeta
    
    @classmethod
    def accept_with(cls, target):
        # Mapper, ClassManager, Session override this to
        # also accept classes, scoped_sessions, sessionmakers, etc.
        if hasattr(target, 'dispatch') and (
                    isinstance(target.dispatch, cls.dispatch) or \
                    isinstance(target.dispatch, type) and \
                    issubclass(target.dispatch, cls.dispatch)
                ):
            return [target]
        else:
            return []

    @classmethod
    def listen(cls, fn, identifier, target):
        getattr(target.dispatch, identifier).append(fn, target)
        


class _ExecEvent(object):
    _exec_once = False
    
    def exec_once(self, *args, **kw):
        """Execute this event, but only if it has not been
        executed already for this collection."""
        
        if not self._exec_once:
            self(*args, **kw)
            self._exec_once = True
    
    def exec_until_return(self, *args, **kw):
        """Execute listeners for this event until
        one returns a non-None value.
        
        Returns the value, or None.
        """
        
        if self:
            for fn in self:
                r = fn(*args, **kw)
                if r is not None:
                    return r
        return None
        
    def __call__(self, *args, **kw):
        """Execute this event."""
        
        if self:
            for fn in self:
                fn(*args, **kw)
    
class EventDescriptor(object):
    """Represent an event type associated with a :class:`Events` class
    as well as class-level listeners.
    
    """
    def __init__(self, fn):
        self.__name__ = fn.__name__
        self.__doc__ = fn.__doc__
        self._clslevel = util.defaultdict(list)
    
    def append(self, obj, target):
        assert isinstance(target, type), \
                "Class-level Event targets must be classes."
        for cls in [target] + target.__subclasses__():
            self._clslevel[cls].append(obj)
    
    def __get__(self, obj, cls):
        if obj is None:
            return self
        obj.__dict__[self.__name__] = result = Listeners(self, obj.parent_cls)
        return result

class Listeners(_ExecEvent):
    """Represent a collection of listeners linked
    to an instance of :class:`Events`."""
    
    def __init__(self, parent, target_cls):
        self.parent_listeners = parent._clslevel[target_cls]
        self.name = parent.__name__
        self.listeners = []
    
    # I'm not entirely thrilled about the overhead here,
    # but this allows class-level listeners to be added
    # at any point.
    
    def __len__(self):
        return len(self.parent_listeners + self.listeners)
        
    def __iter__(self):
        return iter(self.parent_listeners + self.listeners)
    
    def __getitem__(self, index):
        return (self.parent_listeners + self.listeners)[index]
        
    def __nonzero__(self):
        return bool(self.listeners or self.parent_listeners)
        
    def append(self, obj, target):
        if obj not in self.listeners:
            self.listeners.append(obj)

class dispatcher(object):
    def __init__(self, events):
        self.dispatch_cls = events.dispatch
        
    def __get__(self, obj, cls):
        if obj is None:
            return self.dispatch_cls
        obj.__dict__['dispatch'] = disp = self.dispatch_cls(cls)
        return disp
