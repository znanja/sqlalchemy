# types.py
# Copyright (C) 2005,2006 Michael Bayer mike_mp@zzzcomputing.com
#
# This module is part of SQLAlchemy and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

__all__ = [ 'TypeEngine', 'TypeDecorator', 'NullTypeEngine',
            'INT', 'CHAR', 'VARCHAR', 'TEXT', 'FLOAT', 'DECIMAL', 
            'TIMESTAMP', 'DATETIME', 'CLOB', 'BLOB', 'BOOLEAN', 'String', 'Integer', 'Smallinteger',
            'Numeric', 'Float', 'DateTime', 'Date', 'Time', 'Binary', 'Boolean', 'Unicode', 'PickleType', 'NULLTYPE',
        'SMALLINT', 'DATE', 'TIME'
            ]

import sqlalchemy.util as util
try:
    import cPickle as pickle
except:
    import pickle

class AbstractType(object):
    def _get_impl_dict(self):
        try:
            return self._impl_dict
        except AttributeError:
            self._impl_dict = {}
            return self._impl_dict
    impl_dict = property(_get_impl_dict)
    def get_constructor_args(self):
        return {}
    def adapt_args(self):
        return self

class TypeEngine(AbstractType):
    def __init__(self, *args, **params):
        pass
    def engine_impl(self, engine):
        try:
            return self.impl_dict[engine]
        except:
            return self.impl_dict.setdefault(engine, engine.type_descriptor(self))
    def get_col_spec(self):
        raise NotImplementedError()
    def convert_bind_param(self, value, engine):
        return value
    def convert_result_value(self, value, engine):
        return value

class TypeDecorator(AbstractType):
    def __init__(self, *args, **params):
        pass
    def engine_impl(self, engine):
        try:
            return self.impl_dict[engine]
        except:
            typedesc = engine.type_descriptor(self.impl)
            tt = self.__class__(**self.get_constructor_args())
            tt.impl = typedesc
            self.impl_dict[engine] = tt
            return tt
    def get_col_spec(self):
        return self.impl.get_col_spec()
    def convert_bind_param(self, value, engine):
        return self.impl.convert_bind_param(value, engine)
    def convert_result_value(self, value, engine):
        return self.impl.convert_result_value(value, engine)
        
def to_instance(typeobj):
    if typeobj is None:
        return NULLTYPE
    elif isinstance(typeobj, type):
        return typeobj()
    else:
        return typeobj
def adapt_type(typeobj, colspecs):
    if isinstance(typeobj, type):
        typeobj = typeobj()
    t2 = typeobj.adapt_args()
    for t in t2.__class__.__mro__[0:-1]:
        try:
            impltype = colspecs[t]
            break
        except KeyError:
            pass
    else:
        # couldnt adapt...raise exception ?
        return typeobj
    return impltype(**t2.get_constructor_args())
    
class NullTypeEngine(TypeEngine):
    def get_col_spec(self):
        raise NotImplementedError()
    def convert_bind_param(self, value, engine):
        return value
    def convert_result_value(self, value, engine):
        return value

    
class String(TypeEngine):
    def __init__(self, length = None):
        self.length = length
    def get_constructor_args(self):
        return {'length':self.length}
    def convert_bind_param(self, value, engine):
        if not engine.convert_unicode or value is None or not isinstance(value, unicode):
            return value
        else:
            return value.encode(engine.encoding)
    def convert_result_value(self, value, engine):
        if not engine.convert_unicode or value is None or isinstance(value, unicode):
            return value
        else:
            return value.decode(engine.encoding)
    def adapt_args(self):
        if self.length is None:
            return TEXT()
        else:
            return self
            
class Unicode(TypeDecorator):
    impl = String
    def convert_bind_param(self, value, engine):
         if value is not None and isinstance(value, unicode):
              return value.encode(engine.encoding)
         else:
              return value
    def convert_result_value(self, value, engine):
         if value is not None and not isinstance(value, unicode):
             return value.decode(engine.encoding)
         else:
             return value
              
class Integer(TypeEngine):
    """integer datatype"""
    pass
    
class SmallInteger(Integer):
    """ smallint datatype """
    pass
Smallinteger = SmallInteger
  
class Numeric(TypeEngine):
    def __init__(self, precision = 10, length = 2):
        self.precision = precision
        self.length = length
    def get_constructor_args(self):
        return {'precision':self.precision, 'length':self.length}

class Float(Numeric):
    def __init__(self, precision = 10):
        self.precision = precision
    def get_constructor_args(self):
        return {'precision':self.precision}

class DateTime(TypeEngine):
    pass

class Date(TypeEngine):
    pass

class Time(TypeEngine):
    pass

class Binary(TypeEngine):
    def __init__(self, length=None):
        self.length = length
    def convert_bind_param(self, value, engine):
        return engine.dbapi().Binary(value)
    def convert_result_value(self, value, engine):
        return value
    def get_constructor_args(self):
        return {'length':self.length}

class PickleType(TypeDecorator):
      def __init__(self, protocol=pickle.HIGHEST_PROTOCOL):
           """allows the pickle protocol to be specified"""
           self.protocol = protocol
           self.impl = Binary()
      def convert_result_value(self, value, engine):
          if value is None:
              return None
          buf = self.impl.convert_result_value(value, engine)
          return pickle.loads(str(buf))
      def convert_bind_param(self, value, engine):
          if value is None:
              return None
          return self.impl.convert_bind_param(pickle.dumps(value, self.protocol), engine)
      def get_constructor_args(self):
            return {}

class Boolean(TypeEngine):
    pass

class FLOAT(Float):pass
class TEXT(String):pass
class DECIMAL(Numeric):pass
class INT(Integer):pass
INTEGER = INT
class SMALLINT(Smallinteger):pass
class TIMESTAMP(DateTime): pass
class DATETIME(DateTime): pass
class DATE(Date): pass
class TIME(Time): pass
class CLOB(String): pass
class VARCHAR(String): pass
class CHAR(String):pass
class BLOB(Binary): pass
class BOOLEAN(Boolean): pass

NULLTYPE = NullTypeEngine()
