# interfaces.py
# Copyright (C) 2005, 2006, 2007, 2008, 2009, 2010 Michael Bayer
# mike_mp@zzzcomputing.com
#
# This module is part of SQLAlchemy and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

"""

Contains various base classes used throughout the ORM.

Defines the now deprecated ORM extension classes as well
as ORM internals.

Other than the deprecated extensions, this module and the
classes within should be considered mostly private.

"""

from itertools import chain

import sqlalchemy.exceptions as sa_exc
from sqlalchemy import log, util, event
from sqlalchemy.sql import expression

class_mapper = None
collections = None

__all__ = (
    'AttributeExtension',
    'EXT_CONTINUE',
    'EXT_STOP',
    'ExtensionOption',
    'InstrumentationManager',
    'LoaderStrategy',
    'MapperExtension',
    'MapperOption',
    'MapperProperty',
    'PropComparator',
    'PropertyOption',
    'SessionExtension',
    'StrategizedOption',
    'StrategizedProperty',
    'build_path',
    )

EXT_CONTINUE = util.symbol('EXT_CONTINUE')
EXT_STOP = util.symbol('EXT_STOP')

ONETOMANY = util.symbol('ONETOMANY')
MANYTOONE = util.symbol('MANYTOONE')
MANYTOMANY = util.symbol('MANYTOMANY')

from deprecated_interfaces import AttributeExtension, SessionExtension, \
    MapperExtension


class MapperProperty(object):
    """Manage the relationship of a ``Mapper`` to a single class
    attribute, as well as that attribute as it appears on individual
    instances of the class, including attribute instrumentation,
    attribute access, loading behavior, and dependency calculations.
    """

    cascade = ()
    """The set of 'cascade' attribute names.
    
    This collection is checked before the 'cascade_iterator' method is called.
    
    """

    get_col_value = None
    """Optional method which converts an attribute value into a per-column
    value::
    
        def get_col_value(self, column, value):
            ...
            
    Basically used by CompositeProperty.
    
    The mapper checks this attribute for non-None to reduce callcounts.
    
    """

    def setup(self, context, entity, path, adapter, **kwargs):
        """Called by Query for the purposes of constructing a SQL statement.

        Each MapperProperty associated with the target mapper processes the
        statement referenced by the query context, adding columns and/or
        criterion as appropriate.
        """

        pass

    def create_row_processor(self, selectcontext, path, mapper, row, adapter):
        """Return a 3-tuple consisting of three row processing functions.
        
        """

        raise NotImplementedError()

    def cascade_iterator(self, type_, state, visited_instances=None,
                            halt_on=None):
        """Iterate through instances related to the given instance for
        a particular 'cascade', starting with this MapperProperty.
        
        Return an iterator3-tuples (instance, mapper, state).
        
        Note that the 'cascade' collection on this MapperProperty is
        checked first for the given type before cascade_iterator is called.

        See PropertyLoader for the related instance implementation.
        """

        return iter(())

    def set_parent(self, parent, init):
        self.parent = parent

    def instrument_class(self, mapper):
        raise NotImplementedError()

    _compile_started = False
    _compile_finished = False
    
    def init(self):
        """Called after all mappers are created to assemble
        relationships between mappers and perform other post-mapper-creation
        initialization steps.

        """
        self._compile_started = True
        self.do_init()
        self._compile_finished = True

    @property
    def class_attribute(self):
        """Return the class-bound descriptor corresponding to this
        MapperProperty."""

        return getattr(self.parent.class_, self.key)

    def do_init(self):
        """Perform subclass-specific initialization post-mapper-creation
        steps.
        
        This is a template method called by the ``MapperProperty``
        object's init() method.
        
        """

        pass

    def post_instrument_class(self, mapper):
        """Perform instrumentation adjustments that need to occur
        after init() has completed.

        """
        pass

    def per_property_preprocessors(self, uow):
        pass

    def is_primary(self):
        """Return True if this ``MapperProperty``'s mapper is the
        primary mapper for its class.

        This flag is used to indicate that the ``MapperProperty`` can
        define attribute instrumentation for the class at the class
        level (as opposed to the individual instance level).
        """

        return not self.parent.non_primary

    def merge(self, session, source_state, source_dict, dest_state,
                dest_dict, load, _recursive):
        """Merge the attribute represented by this ``MapperProperty``
        from source to destination object"""

        raise NotImplementedError()

    def compare(self, operator, value):
        """Return a compare operation for the columns represented by
        this ``MapperProperty`` to the given value, which may be a
        column value or an instance.  'operator' is an operator from
        the operators module, or from sql.Comparator.

        By default uses the PropComparator attached to this MapperProperty
        under the attribute name "comparator".
        """

        return operator(self.comparator, value)

class PropComparator(expression.ColumnOperators):
    """Defines comparison operations for MapperProperty objects.

    User-defined subclasses of :class:`.PropComparator` may be created. The
    built-in Python comparison and math operator methods, such as
    ``__eq__()``, ``__lt__()``, ``__add__()``, can be overridden to provide
    new operator behaivor. The custom :class:`.PropComparator` is passed to
    the mapper property via the ``comparator_factory`` argument. In each case,
    the appropriate subclass of :class:`.PropComparator` should be used::
    
        from sqlalchemy.orm.properties import \\
                                ColumnProperty,\\
                                CompositeProperty,\\
                                RelationshipProperty

        class MyColumnComparator(ColumnProperty.Comparator):
            pass
        
        class MyCompositeComparator(CompositeProperty.Comparator):
            pass
            
        class MyRelationshipComparator(RelationshipProperty.Comparator):
            pass
    
    """

    def __init__(self, prop, mapper, adapter=None):
        self.prop = self.property = prop
        self.mapper = mapper
        self.adapter = adapter

    def __clause_element__(self):
        raise NotImplementedError("%r" % self)

    def adapted(self, adapter):
        """Return a copy of this PropComparator which will use the given
        adaption function on the local side of generated expressions.
        
        """

        return self.__class__(self.prop, self.mapper, adapter)

    @staticmethod
    def any_op(a, b, **kwargs):
        return a.any(b, **kwargs)

    @staticmethod
    def has_op(a, b, **kwargs):
        return a.has(b, **kwargs)

    @staticmethod
    def of_type_op(a, class_):
        return a.of_type(class_)

    def of_type(self, class_):
        """Redefine this object in terms of a polymorphic subclass.

        Returns a new PropComparator from which further criterion can be
        evaluated.

        e.g.::

            query.join(Company.employees.of_type(Engineer)).\\
               filter(Engineer.name=='foo')

        \class_
            a class or mapper indicating that criterion will be against
            this specific subclass.


        """

        return self.operate(PropComparator.of_type_op, class_)

    def any(self, criterion=None, **kwargs):
        """Return true if this collection contains any member that meets the
        given criterion.

        criterion
          an optional ClauseElement formulated against the member class' table
          or attributes.

        \**kwargs
          key/value pairs corresponding to member class attribute names which
          will be compared via equality to the corresponding values.
        """

        return self.operate(PropComparator.any_op, criterion, **kwargs)

    def has(self, criterion=None, **kwargs):
        """Return true if this element references a member which meets the
        given criterion.

        criterion
          an optional ClauseElement formulated against the member class' table
          or attributes.

        \**kwargs
          key/value pairs corresponding to member class attribute names which
          will be compared via equality to the corresponding values.
        """

        return self.operate(PropComparator.has_op, criterion, **kwargs)


class StrategizedProperty(MapperProperty):
    """A MapperProperty which uses selectable strategies to affect
    loading behavior.

    There is a single strategy selected by default.  Alternate
    strategies can be selected at Query time through the usage of
    ``StrategizedOption`` objects via the Query.options() method.
    
    """
    
    def _get_context_strategy(self, context, path):
        cls = context.attributes.get(('loaderstrategy',
                _reduce_path(path)), None)
        if cls:
            try:
                return self.__all_strategies[cls]
            except KeyError:
                return self.__init_strategy(cls)
        else:
            return self.strategy

    def _get_strategy(self, cls):
        try:
            return self.__all_strategies[cls]
        except KeyError:
            return self.__init_strategy(cls)

    def __init_strategy(self, cls):
        self.__all_strategies[cls] = strategy = cls(self)
        strategy.init()
        return strategy

    def setup(self, context, entity, path, adapter, **kwargs):
        self._get_context_strategy(context, path + (self.key,)).\
                    setup_query(context, entity, path, adapter, **kwargs)

    def create_row_processor(self, context, path, mapper, row, adapter):
        return self._get_context_strategy(context, path + (self.key,)).\
                    create_row_processor(context, path, mapper, row, adapter)

    def do_init(self):
        self.__all_strategies = {}
        self.strategy = self.__init_strategy(self.strategy_class)

    def post_instrument_class(self, mapper):
        if self.is_primary() and \
            not mapper.class_manager._attr_has_impl(self.key):
            self.strategy.init_class_attribute(mapper)
        
def build_path(entity, key, prev=None):
    if prev:
        return prev + (entity, key)
    else:
        return (entity, key)

def serialize_path(path):
    if path is None:
        return None
    
    return zip(
        [m.class_ for m in [path[i] for i in range(0, len(path), 2)]], 
        [path[i] for i in range(1, len(path), 2)] + [None]
    )

def deserialize_path(path):
    if path is None:
        return None

    global class_mapper
    if class_mapper is None:
        from sqlalchemy.orm import class_mapper
    
    p = tuple(chain(*[(class_mapper(cls), key) for cls, key in path]))
    if p and p[-1] is None:
        p = p[0:-1]
    return p

class MapperOption(object):
    """Describe a modification to a Query."""

    propagate_to_loaders = False
    """if True, indicate this option should be carried along 
    Query object generated by scalar or object lazy loaders.
    """
    
    def process_query(self, query):
        pass

    def process_query_conditionally(self, query):
        """same as process_query(), except that this option may not
        apply to the given query.
        
        Used when secondary loaders resend existing options to a new
        Query."""

        self.process_query(query)

class PropertyOption(MapperOption):
    """A MapperOption that is applied to a property off the mapper or
    one of its child mappers, identified by a dot-separated key. """

    def __init__(self, key, mapper=None):
        self.key = key
        self.mapper = mapper

    def process_query(self, query):
        self._process(query, True)

    def process_query_conditionally(self, query):
        self._process(query, False)

    def _process(self, query, raiseerr):
        paths, mappers = self._get_paths(query, raiseerr)
        if paths:
            self.process_query_property(query, paths, mappers)

    def process_query_property(self, query, paths, mappers):
        pass

    def __getstate__(self):
        d = self.__dict__.copy()
        d['key'] = ret = []
        for token in util.to_list(self.key):
            if isinstance(token, PropComparator):
                ret.append((token.mapper.class_, token.key))
            else:
                ret.append(token)
        return d

    def __setstate__(self, state):
        ret = []
        for key in state['key']:
            if isinstance(key, tuple):
                cls, propkey = key
                ret.append(getattr(cls, propkey))
            else:
                ret.append(key)
        state['key'] = tuple(ret)
        self.__dict__ = state

    def _find_entity( self, query, mapper, raiseerr):
        from sqlalchemy.orm.util import _class_to_mapper, \
            _is_aliased_class
        if _is_aliased_class(mapper):
            searchfor = mapper
            isa = False
        else:
            searchfor = _class_to_mapper(mapper)
            isa = True
        for ent in query._mapper_entities:
            if searchfor is ent.path_entity or isa \
                and searchfor.common_parent(ent.path_entity):
                return ent
        else:
            if raiseerr:
                raise sa_exc.ArgumentError("Can't find entity %s in "
                        "Query.  Current list: %r" % (searchfor,
                        [str(m.path_entity) for m in query._entities]))
            else:
                return None

    def _get_paths(self, query, raiseerr):
        path = None
        entity = None
        l = []
        mappers = []

        # _current_path implies we're in a secondary load with an
        # existing path

        current_path = list(query._current_path)
        tokens = []
        for key in util.to_list(self.key):
            if isinstance(key, basestring):
                tokens += key.split('.')
            else:
                tokens += [key]
        for token in tokens:
            if isinstance(token, basestring):
                if not entity:
                    if current_path:
                        if current_path[1] == token:
                            current_path = current_path[2:]
                            continue
                    entity = query._entity_zero()
                    path_element = entity.path_entity
                    mapper = entity.mapper
                mappers.append(mapper)
                if mapper.has_property(token):
                    prop = mapper.get_property(token)
                else:
                    prop = None
                key = token
            elif isinstance(token, PropComparator):
                prop = token.property
                if not entity:
                    if current_path:
                        if current_path[0:2] == [token.parententity,
                                prop.key]:
                            current_path = current_path[2:]
                            continue
                    entity = self._find_entity(query,
                            token.parententity, raiseerr)
                    if not entity:
                        return [], []
                    path_element = entity.path_entity
                    mapper = entity.mapper
                mappers.append(prop.parent)
                key = prop.key
            else:
                raise sa_exc.ArgumentError('mapper option expects '
                        'string key or list of attributes')
            if prop is None:
                return [], []
            path = build_path(path_element, prop.key, path)
            l.append(path)
            if getattr(token, '_of_type', None):
                path_element = mapper = token._of_type
            else:
                path_element = mapper = getattr(prop, 'mapper', None)
            if path_element:
                path_element = path_element

        if current_path:
            return [], []
        return l, mappers



class StrategizedOption(PropertyOption):
    """A MapperOption that affects which LoaderStrategy will be used
    for an operation by a StrategizedProperty.
    """

    is_chained = False

    def process_query_property(self, query, paths, mappers):

        # _get_context_strategy may receive the path in terms of a base
        # mapper - e.g.  options(eagerload_all(Company.employees,
        # Engineer.machines)) in the polymorphic tests leads to
        # "(Person, 'machines')" in the path due to the mechanics of how
        # the eager strategy builds up the path

        if self.is_chained:
            for path in paths:
                query._attributes[('loaderstrategy',
                                  _reduce_path(path))] = \
                    self.get_strategy_class()
        else:
            query._attributes[('loaderstrategy',
                              _reduce_path(paths[-1]))] = \
                self.get_strategy_class()

    def get_strategy_class(self):
        raise NotImplementedError()

def _reduce_path(path):
    """Convert a (mapper, path) path to use base mappers.
    
    This is used to allow more open ended selection of loader strategies, i.e.
    Mapper -> prop1 -> Subclass -> prop2, where Subclass is a sub-mapper
    of the mapper referened by Mapper.prop1.
    
    """
    return tuple([i % 2 != 0 and 
                    path[i] or 
                    getattr(path[i], 'base_mapper', path[i]) 
                    for i in xrange(len(path))])

class LoaderStrategy(object):
    """Describe the loading behavior of a StrategizedProperty object.

    The ``LoaderStrategy`` interacts with the querying process in three
    ways:

    * it controls the configuration of the ``InstrumentedAttribute``
      placed on a class to handle the behavior of the attribute.  this
      may involve setting up class-level callable functions to fire
      off a select operation when the attribute is first accessed
      (i.e. a lazy load)

    * it processes the ``QueryContext`` at statement construction time,
      where it can modify the SQL statement that is being produced.
      simple column attributes may add their represented column to the
      list of selected columns, *eager loading* properties may add
      ``LEFT OUTER JOIN`` clauses to the statement.

    * it processes the ``SelectionContext`` at row-processing time.  This
      includes straight population of attributes corresponding to rows,
      setting instance-level lazyloader callables on newly
      constructed instances, and appending child items to scalar/collection
      attributes in response to eagerly-loaded relations.
    """

    def __init__(self, parent):
        self.parent_property = parent
        self.is_class_level = False
        self.parent = self.parent_property.parent
        self.key = self.parent_property.key

    def init(self):
        raise NotImplementedError("LoaderStrategy")

    def init_class_attribute(self, mapper):
        pass

    def setup_query(self, context, entity, path, adapter, **kwargs):
        pass

    def create_row_processor(self, selectcontext, path, mapper, 
                                row, adapter):
        """Return row processing functions which fulfill the contract
        specified by MapperProperty.create_row_processor.
        
        StrategizedProperty delegates its create_row_processor method
        directly to this method. """

        raise NotImplementedError()

    def __str__(self):
        return str(self.parent_property)

    def debug_callable(self, fn, logger, announcement, logfn):
        if announcement:
            logger.debug(announcement)
        if logfn:
            def call(*args, **kwargs):
                logger.debug(logfn(*args, **kwargs))
                return fn(*args, **kwargs)
            return call
        else:
            return fn

class InstrumentationManager(object):
    """User-defined class instrumentation extension.
    
    :class:`.InstrumentationManager` can be subclassed in order
    to change
    how class instrumentation proceeds. This class exists for
    the purposes of integration with other object management
    frameworks which would like to entirely modify the
    instrumentation methodology of the ORM, and is not intended
    for regular usage.  For interception of class instrumentation
    events, see :class:`.InstrumentationEvents`.
    
    For an example of :class:`.InstrumentationManager`, see the
    example :ref:`examples_instrumentation`.
    
    The API for this class should be considered as semi-stable,
    and may change slightly with new releases.
    
    """

    # r4361 added a mandatory (cls) constructor to this interface.
    # given that, perhaps class_ should be dropped from all of these
    # signatures.

    def __init__(self, class_):
        pass

    def manage(self, class_, manager):
        setattr(class_, '_default_class_manager', manager)

    def dispose(self, class_, manager):
        delattr(class_, '_default_class_manager')

    def manager_getter(self, class_):
        def get(cls):
            return cls._default_class_manager
        return get

    def instrument_attribute(self, class_, key, inst):
        pass

    def post_configure_attribute(self, class_, key, inst):
        pass

    def install_descriptor(self, class_, key, inst):
        setattr(class_, key, inst)

    def uninstall_descriptor(self, class_, key):
        delattr(class_, key)

    def install_member(self, class_, key, implementation):
        setattr(class_, key, implementation)

    def uninstall_member(self, class_, key):
        delattr(class_, key)

    def instrument_collection_class(self, class_, key, collection_class):
        global collections
        if collections is None:
            from sqlalchemy.orm import collections
        return collections.prepare_instrumentation(collection_class)

    def get_instance_dict(self, class_, instance):
        return instance.__dict__

    def initialize_instance_dict(self, class_, instance):
        pass

    def install_state(self, class_, instance, state):
        setattr(instance, '_default_state', state)

    def remove_state(self, class_, instance):
        delattr(instance, '_default_state', state)

    def state_getter(self, class_):
        return lambda instance: getattr(instance, '_default_state')

    def dict_getter(self, class_):
        return lambda inst: self.get_instance_dict(class_, inst)
        