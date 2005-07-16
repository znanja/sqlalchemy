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

class Mapper:
    def __init__(self, class_, table, properties, identitymap = None):
        self.class_ = class_
        self.table = table
        self.properties = properties
        if identitymap is not None:
            self.identitymap = identitymap
        else:
            self.identitymap = _global_identitymap

    def instance(self, row):
        pass

    def get(self, id):
        """returns an instance of the object based on the given ID."""
        pass
        
    def _select_whereclause(self, whereclause, **params):
        # make select statement

        
        return self._select_statement(statement, **params)

    
    def _select_statement(self, statement, **params):
        pass

    def select(self, arg, **params):
        """selects instances of the object from the database.  
        
        arg can be any ClauseElement, which will form the criterion with which to
        load the objects.
        
        For more advanced usage, arg can also be a Select statement object, which
        will be executed and its resulting rowset used to build new object instances.  
        in this case, the developer must insure that an adequate set of columns exists in the 
        rowset with which to build new object instances."""
        if isinstance(arg, sql.Select):
            return self._select_statement(arg, **params)
        else:
            return self._select_whereclause(arg, **params)
        
    def save(self, object):
        pass
        
    def delete(self, whereclause = None, **params):
        pass
        
        
class IdentityMap:
    def __init__(self):
        self.map = {}
        
    def get(self, row, class_, table):
        """given a database row, a class to be instantiated, and a table corresponding 
        to the row, returns a corrseponding object instance, if any, from the identity
        map.  the primary keys specified in the table will be used to indicate which
        columns from the row form the effective key of the instance."""
        pass
        
    def put(self, instance, table):
        """puts this object instance, corresponding to a row from the given table, into 
        the identity map.  the primary keys specified in the table will be used to 
        indicate which properties of the instance form the effective key of the instance."""
        
        pass
    
    
_global_identitymap = IdentityMap()
