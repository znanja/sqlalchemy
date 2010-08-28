"""
The event system handles all events throughout the :mod:`sqlalchemy`
and :mod:`sqlalchemy.orm` packages.


"""

from sqlalchemy import util
import inspect

def listen(fn, identifier, target, *args, **kw):
    """Listen for events, passing to fn.
    
    Event listener functions are in a consistent format::
        
        def listen(event_name, args):
            # ...
            
    Where ``event_name`` is the string name, the same 
    as ``identifier``, and ``args`` is a dict containing
    an entry for each argument.  The names match those 
    of the event declaration.
    
    """

    for evt_cls in _registrars[identifier]:
        for tgt in evt_cls.accept_with(target):
            fn = _create_wrapper(evt_cls, fn, identifier)
            tgt.dispatch.listen(fn, identifier, tgt, *args, **kw)
            break

def _create_wrapper(evt_cls, fn, identifier):
    argspec = inspect.getargspec(getattr(evt_cls, identifier))
    arg, varargs, keywords, defaults = argspec
    def go(*args, **kw):
        # here we are coercing the *arg, **kw to a single 
        # dictionary.
        
        # TODO: defaults
        if keywords:
            kw = {keywords:kw}
        for n, v in zip(arg[1:], args):
            kw[n] = v
        if varargs:
            kw[varargs] = arg[len(args)+1:]
        
        fn(identifier, kw)
        
        # then here, we ask the Events subclass to interpret
        # the dictionary back to what it wants for a return.
        
        return evt_cls.unwrap(identifier, kw)
        
    return util.update_wrapper(go, fn)
    
def listen_raw(fn, identifier, target, *args, **kw):
    """Listen for events, accepting an event function that's "raw".
    Only the exact arguments are received in order.
    
    This is used by SQLA internals simply to reduce the overhead
    of creating an event dictionary for each event call.
    
    """

    # rationale - the events on ClassManager, Session, and Mapper
    # will need to accept mapped classes directly as targets and know 
    # what to do
    
    for evt_cls in _registrars[identifier]:
        for tgt in evt_cls.accept_with(target):
            tgt.dispatch.listen(fn, identifier, tgt, *args, **kw)
            break
    
_registrars = util.defaultdict(list)

class _Dispatch(object):
    """Mirror the event listening definitions of an Events class with 
    listener collections.
    
    """
    
    def __init__(self, parent_cls):
        self.parent_cls = parent_cls
    
    @property
    def descriptors(self):
        return (getattr(self, k) for k in dir(self) if k.startswith("on_"))
        
    def update(self, other):
        """Populate from the listeners in another :class:`Events` object."""

        for ls in other.descriptors:
            getattr(self, ls.name).listeners.extend(ls.listeners)

class _EventMeta(type):
    """Intercept new Event subclasses and create 
    associated _Dispatch classes."""
    
    def __init__(cls, classname, bases, dict_):
        _create_dispatcher_class(cls, classname, bases, dict_)
        return type.__init__(cls, classname, bases, dict_)
        
def _create_dispatcher_class(cls, classname, bases, dict_):
    # there's all kinds of ways to do this,
    # i.e. make a Dispatch class that shares the 'listen' method
    # of the Event class, this is the straight monkeypatch.
    dispatch_base = getattr(cls, 'dispatch', _Dispatch)
    cls.dispatch = dispatch_cls = type("%sDispatch" % classname, 
                                        (dispatch_base, ), {})
    dispatch_cls.listen = cls.listen

    for k in dict_:
        if k.startswith('on_'):
            setattr(dispatch_cls, k, _DispatchDescriptor(dict_[k]))
            _registrars[k].append(cls)

class Events(object):
    """Define event listening functions for a particular target type."""
    
    
    __metaclass__ = _EventMeta
    
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

    @classmethod
    def unwrap(cls, identifier, event):
        return None
    
class _DispatchDescriptor(object):
    """Class-level attributes on _Dispatch classes."""
    
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
        obj.__dict__[self.__name__] = result = \
                            _ListenerCollection(self, obj.parent_cls)
        return result

class _ListenerCollection(object):
    """Represent a collection of listeners linked
    to an instance of _Dispatch.
    
    """

    _exec_once = False
    
    def __init__(self, parent, target_cls):
        self.parent_listeners = parent._clslevel[target_cls]
        self.name = parent.__name__
        self.listeners = []

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
    """Descriptor used by target classes to 
    deliver the _Dispatch class at the class level
    and produce new _Dispatch instances for target
    instances.
    
    """
    def __init__(self, events):
        self.dispatch_cls = events.dispatch
        
        
    def __get__(self, obj, cls):
        if obj is None:
            return self.dispatch_cls
        obj.__dict__['dispatch'] = disp = self.dispatch_cls(cls)
        return disp
