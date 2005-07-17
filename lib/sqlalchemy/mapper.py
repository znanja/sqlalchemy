"""
# create a mapper from a class and table object
usermapper = Mapper(User, users)


# get primary key
usermapper.get(10)

userlist = usermapper.select(usermapper.table.user_id == 10)

userlist = usermapper.select(
        and_(usermapper.table.user_name == 'fred', usermapper.table.user_id == 12)
    )

userlist = usermapper.select("user_id =12 and foo=bar", from_obj=["foo"])

usermapper = Mapper(
    User, 
    users, 
    properties = {
        'addresses' : Relation(addressmapper, lazy = False),
        'permissions' : Relation(permissions, 
        
                # one or the other
                associationtable = userpermissions, 
                criterion = and_(users.user_id == userpermissions.user_id, userpermissions.permission_id=permissions.permission_id), 
                lazy = True),
        '*' : [users, userinfo]
    },
    )

addressmapper = Mapper(Address, addresses, properties = {
    'street': addresses.address_1,
})
"""

import sqlalchemy.sql as sql
import sqlalchemy.schema as schema

class Mapper(object):
    def __init__(self, class_, table, properties = None, identitymap = None):
        self.class_ = class_
        self.table = table
        
        self.props = {}
        
        for column in table.columns:
            self.props[column.key] = ColumnProperty(column)

        if properties is not None:
            for key, value in properties.iteritems():
                self.props[key] = value
                
        if identitymap is not None:
            self.identitymap = identitymap
        else:
            self.identitymap = _global_identitymap
            
    def instances(self, cursor):
        result = []
        cursor = ResultProxy(cursor)
        localmap = IdentityMap()
        while True:
            row = cursor.fetchone()
            if row is None:
                break
                
            identitykey = localmap.get_key(row, self.class_, self.table)
            if not localmap.map.has_key(identitykey):
                instance = self._create(row, identitykey, localmap)
                result.append(instance)
            else:
                for key, prop in self.props.iteritems():
                    prop.execute(instance, key, row, identitykey, localmap, True)
                
        return result
        
    def get(self, id):
        """returns an instance of the object based on the given ID."""
        pass
        
    def select(self, arg = None, **params):
        """selects instances of the object from the database.  
        
        arg can be any ClauseElement, which will form the criterion with which to
        load the objects.
        
        For more advanced usage, arg can also be a Select statement object, which
        will be executed and its resulting rowset used to build new object instances.  
        in this case, the developer must insure that an adequate set of columns exists in the 
        rowset with which to build new object instances."""
        if arg is not None and isinstance(arg, sql.Select):
            return self._select_statement(arg, **params)
        else:
            return self._select_whereclause(arg, **params)
        
    def save(self, object):
        pass
        
    def delete(self, whereclause = None, **params):
        pass


    def _select_whereclause(self, whereclause = None, **params):
        statement = sql.select([self.table], whereclause)
        for key, value in self.props.iteritems():
            value.setup(key, self.table, statement) 
        return self._select_statement(statement, **params)
    
    def _select_statement(self, statement, **params):
        statement.use_labels = True
        return self.instances(statement.execute(**params))

    def _identity_key(self, row):
        return self.identitymap.get_key(row, self.class_, self.table)

    def _create(self, row, identitykey, localmap):
        instance = self.class_()
        for column in self.table.primary_keys:
            if row[column.label] is None:
                return None
        for key, prop in self.props.iteritems():
            prop.execute(instance, key, row, identitykey, localmap, False)
        self.identitymap.map[identitykey] = instance
        localmap.map[identitykey] = instance
        return instance


class MapperProperty:
    def execute(self, instance, key, row, isduplicate):
        raise NotImplementedError()
    def setup(self, key, primarytable, statement):
        pass

class ColumnProperty(MapperProperty):
    def __init__(self, column):
        self.column = column
        
    def execute(self, instance, key, row, identitykey, localmap, isduplicate):
        if not isduplicate:
            setattr(instance, key, row[self.column.label])

class EagerLoader(MapperProperty):
    def __init__(self, mapper, whereclause):
        self.mapper = mapper
        self.whereclause = whereclause
        
    def setup(self, key, primarytable, statement):
        targettable = self.mapper.table
        if hasattr(statement, '_outerjoin'):
            statement._outerjoin = sql.outerjoin(statement._outerjoin, targettable, self.whereclause)
        else:
            statement._outerjoin = sql.outerjoin(primarytable, targettable, self.whereclause)
        statement.append_from(statement._outerjoin)
        statement.append_column(targettable)
        
    def execute(self, instance, key, row, identitykey, localmap, isduplicate):
        try:
            list = getattr(instance, key)
        except AttributeError:
            list = []
            setattr(instance, key, list)
        
        identitykey = self.mapper._identity_key(row)
        if not localmap.has_key(identitykey):
            subinstance = self.mapper._create(row, identitykey, localmap)
            list.append(subinstance)

class ResultProxy:
    def __init__(self, cursor):
        self.cursor = cursor
        metadata = cursor.description
        self.props = {}
        i = 0
        for item in metadata:
            self.props[item[0]] = i
            self.props[i] = i
            i+=1

    def fetchone(self):
        row = self.cursor.fetchone()
        print "row: " + repr(row)
        if row is not None:
            return RowProxy(self, row)
        else:
            return None
        
class RowProxy:
    def __init__(self, parent, row):
        self.parent = parent
        self.row = row
    def __getitem__(self, key):
        return self.row[self.parent.props[key]]
        
class IdentityMap(object):
    def __init__(self):
        self.map = {}
        self.keystereotypes = {}
    
    def has_key(self, key):
        return self.map.has_key(key)
        
    def get_key(self, row, class_, table):
        return (class_, table.id, tuple([row[column.label] for column in table.primary_keys]))
        
    def get(self, row, class_, table, key = None):
        """given a database row, a class to be instantiated, and a table corresponding 
        to the row, returns a corrseponding object instance, if any, from the identity
        map.  the primary keys specified in the table will be used to indicate which
        columns from the row form the effective key of the instance."""
        
        if key is None:
            key = self.get_key(row, class_, table)

        return self.map[key]
            
    
    
_global_identitymap = IdentityMap()
