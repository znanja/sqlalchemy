from testbase import PersistTest
import unittest, sys, os
from sqlalchemy.mapper import *
import sqlalchemy.objectstore as objectstore

#ECHO = True
ECHO = False
execfile("test/tables.py")
db.echo = True

class User(object):
    def __init__(self):
        self.user_id = None
    def __rrepr__(self):
        return (
"""
objid: %d
User ID: %s
User Name: %s
email address ?: %s
Addresses: %s
Orders: %s
Open Orders %s
Closed Orderss %s
------------------
""" % tuple([id(self), self.user_id, repr(self.user_name), repr(getattr(self, 'email_address', None))] + [repr(getattr(self, attr, None)) for attr in ('addresses', 'orders', 'orders_open', 'orders_closed')])
)

class Address(object):
    def __rrepr__(self):
        return "Address: " + repr(getattr(self, 'address_id', None)) + " " + repr(getattr(self, 'user_id', None)) + " " + repr(self.email_address)

class Order(object):
    def __repr__(self):
        return "Order: " + repr(self.description) + " " + repr(self.isopen) + " " + repr(getattr(self, 'items', None))

class Item(object):
    def __repr__(self):
        return "Item: " + repr(self.item_name) + " " +repr(getattr(self, 'keywords', None))
    
class Keyword(object):
    def __repr__(self):
        return "Keyword: %s/%s" % (repr(getattr(self, 'keyword_id', None)),repr(self.name))

class AssertMixin(PersistTest):
    def assert_result(self, result, class_, *objects):
        print repr(result)
        self.assert_list(result, class_, objects)
    def assert_list(self, result, class_, list):
        for i in range(0, len(list)):
            self.assert_row(class_, result[i], list[i])
    def assert_row(self, class_, rowobj, desc):
        self.assert_(rowobj.__class__ is class_, "item class is not " + repr(class_))
        for key, value in desc.iteritems():
            if isinstance(value, tuple):
                self.assert_list(getattr(rowobj, key), value[0], value[1])
            else:
                self.assert_(getattr(rowobj, key) == value, "attribute %s value %s does not match %s" % (key, getattr(rowobj, key), value))
        
class MapperTest(AssertMixin):
    
    def setUp(self):
        pass
        #globalidentity().clear()

    def testget(self):
        m = mapper(User, users, scope = "thread")
        self.assert_(m.get(19) is None)
        u = m.get(7)
        u2 = m.get(7)
        self.assert_(u is u2)
        objectstore.clear("thread")
        u2 = m.get(7)
        self.assert_(u is not u2)

    def testload(self):
        """tests loading rows with a mapper and producing object instances"""
        m = mapper(User, users)
        l = m.select()
        self.assert_result(l, User, {'user_id' : 7}, {'user_id' : 8}, {'user_id' : 9})
        l = m.select(users.c.user_name.endswith('ed'))
        self.assert_result(l, User, {'user_id' : 8}, {'user_id' : 9})

    def testmultitable(self):
        usersaddresses = sql.join(users, addresses, users.c.user_id == addresses.c.user_id)
        m = mapper(User, usersaddresses, table = users)
        l = m.select()
        print repr(l)

    def testeageroptions(self):
        """tests that a lazy relation can be upgraded to an eager relation via the options method"""
        m = mapper(User, users, properties = dict(
            addresses = relation(Address, addresses, lazy = True)
        ))
        l = m.options(eagerload('addresses')).select()
        self.assert_result(l, User,
            {'user_id' : 7, 'addresses' : (Address, [{'address_id' : 1}])},
            {'user_id' : 8, 'addresses' : (Address, [{'address_id' : 2}, {'address_id' : 3}])},
            {'user_id' : 9, 'addresses' : (Address, [])}
            )

    def testlazyoptions(self):
        """tests that an eager relation can be upgraded to a lazy relation via the options method"""
        m = mapper(User, users, properties = dict(
            addresses = relation(Address, addresses, lazy = False)
        ))
        l = m.options(lazyload('addresses')).select()
        self.assert_result(l, User,
            {'user_id' : 7, 'addresses' : (Address, [{'address_id' : 1}])},
            {'user_id' : 8, 'addresses' : (Address, [{'address_id' : 2}, {'address_id' : 3}])},
            {'user_id' : 9, 'addresses' : (Address, [])}
            )
    
class LazyTest(AssertMixin):
    def setUp(self):
        #globalidentity().clear()
        pass

    def testbasic(self):
        """tests a basic one-to-many lazy load"""
        m = mapper(User, users, properties = dict(
            addresses = relation(Address, addresses, lazy = True)
        ))
        l = m.select(users.c.user_id == 7)
        self.assert_result(l, User,
            {'user_id' : 7, 'addresses' : (Address, [{'address_id' : 1}])},
            )

    def testonetoone(self):
        m = mapper(User, users, properties = dict(
            address = relation(Address, addresses, lazy = True, uselist = False)
        ))
        l = m.select(users.c.user_id == 7)
        print repr(l)
        print repr(l[0].address)

        # test 'backwards'
        m = mapper(Address, addresses, properties = dict(
            user = relation(User, users, primaryjoin = users.c.user_id == addresses.c.user_id, lazy = True, uselist = False)
        ))
        l = m.select(addresses.c.address_id == 1)
        print repr(l)
        print repr(l[0].user)

    def testmanytomany(self):
        """tests a many-to-many lazy load"""
        items = orderitems

        m = mapper(Item, items, properties = dict(
                keywords = relation(Keyword, keywords, itemkeywords, lazy = True),
            ))
        l = m.select()
        self.assert_result(l, Item, 
            {'item_id' : 1, 'keywords' : (Keyword, [{'keyword_id' : 2}, {'keyword_id' : 4}, {'keyword_id' : 6}])},
            {'item_id' : 2, 'keywords' : (Keyword, [{'keyword_id' : 2}, {'keyword_id' : 5}, {'keyword_id' : 7}])},
            {'item_id' : 3, 'keywords' : (Keyword, [{'keyword_id' : 3}, {'keyword_id' : 4}, {'keyword_id' : 6}])},
            {'item_id' : 4, 'keywords' : (Keyword, [])},
            {'item_id' : 5, 'keywords' : (Keyword, [])}
        )

        l = m.select(and_(keywords.c.name == 'red', keywords.c.keyword_id == itemkeywords.c.keyword_id, items.c.item_id==itemkeywords.c.item_id))
        self.assert_result(l, Item, 
            {'item_id' : 1, 'keywords' : (Keyword, [{'keyword_id' : 2}, {'keyword_id' : 4}, {'keyword_id' : 6}])},
            {'item_id' : 2, 'keywords' : (Keyword, [{'keyword_id' : 2}, {'keyword_id' : 5}, {'keyword_id' : 7}])},
        )

class EagerTest(AssertMixin):
    
    def setUp(self):
        #globalidentity().clear()
        pass

    def testbasic(self):
        """tests a basic one-to-many eager load"""
        
        m = mapper(Address, addresses)
        
        m = mapper(User, users, properties = dict(
            #addresses = relation(Address, addresses, lazy = False),
            addresses = relation(m, lazy = False),
        ))
        l = m.select()
        print repr(l)

    def testonetoone(self):
        m = mapper(User, users, properties = dict(
            address = relation(Address, addresses, lazy = False, uselist = False)
        ))
        l = m.select(users.c.user_id == 7)
        print repr(l)
        print repr(l[0].address)

        # test 'backwards'
        m = mapper(Address, addresses, properties = dict(
            user = relation(User, users, primaryjoin = addresses.c.user_id == users.c.user_id, lazy = False, uselist = False)
        ))
        l = m.select(addresses.c.address_id == 1)
        print repr(l)
        print repr(l[0].user)

    def testwithrepeat(self):
        """tests a one-to-many eager load where we also query on joined criterion, where the joined
        criterion is using the same tables that are used within the eager load.  the mapper must insure that the 
        criterion doesnt interfere with the eager load criterion."""
        m = mapper(User, users, properties = dict(
            addresses = relation(Address, addresses, primaryjoin = users.c.user_id==addresses.c.user_id, lazy = False)
        ))
        l = m.select(and_(addresses.c.email_address == 'ed@lala.com', addresses.c.user_id==users.c.user_id))
        print repr(l)

    def testcompile(self):
        """tests deferred operation of a pre-compiled mapper statement"""
        m = mapper(User, users, properties = dict(
            addresses = relation(Address, addresses, lazy = False)
        ))
        s = m.compile(and_(addresses.c.email_address == bindparam('emailad'), addresses.c.user_id==users.c.user_id))
        c = s.compile()
        print "\n" + str(c) + repr(c.get_params())
        
        l = m.instances(s.execute(emailad = 'jack@bean.com'))
        print repr(l)
        
    def testmulti(self):
        """tests eager loading with two relations simultaneously"""
        m = mapper(User, users, properties = dict(
            addresses = relation(Address, addresses, primaryjoin = users.c.user_id==addresses.c.user_id, lazy = False),
            orders = relation(Order, orders, lazy = False),
        ))
        l = m.select()
        print repr(l)

    def testdouble(self):
        """tests eager loading with two relations simulatneously, from the same table.  you
        have to use aliases for this less frequent type of operation."""
        openorders = alias(orders, 'openorders')
        closedorders = alias(orders, 'closedorders')
        m = mapper(User, users, properties = dict(
            orders_open = relation(Order, openorders, primaryjoin = and_(openorders.c.isopen == 1, users.c.user_id==openorders.c.user_id), lazy = False),
            orders_closed = relation(Order, closedorders, primaryjoin = and_(closedorders.c.isopen == 0, users.c.user_id==closedorders.c.user_id), lazy = False)
        ))
        l = m.select()
        print repr(l)

    def testnested(self):
        """tests eager loading, where one of the eager loaded items also eager loads its own 
        child items."""
        ordermapper = mapper(Order, orders, properties = dict(
                items = relation(Item, orderitems, lazy = False)
            ))

        m = mapper(User, users, properties = dict(
            addresses = relation(Address, addresses, lazy = False),
            orders = relation(ordermapper, primaryjoin = users.c.user_id==orders.c.user_id, lazy = False),
        ))
        l = m.select()
        print repr(l)
    
    def testmanytomany(self):
        items = orderitems
        
        m = mapper(Item, items, properties = dict(
                keywords = relation(Keyword, keywords, itemkeywords, lazy = False),
            ))
        l = m.select()
        self.assert_result(l, Item, 
            {'item_id' : 1, 'keywords' : (Keyword, [{'keyword_id' : 2}, {'keyword_id' : 4}, {'keyword_id' : 6}])},
            {'item_id' : 2, 'keywords' : (Keyword, [{'keyword_id' : 2}, {'keyword_id' : 7}, {'keyword_id' : 5}])},
            {'item_id' : 3, 'keywords' : (Keyword, [{'keyword_id' : 6}, {'keyword_id' : 3}, {'keyword_id' : 4}])},
            {'item_id' : 4, 'keywords' : (Keyword, [])},
            {'item_id' : 5, 'keywords' : (Keyword, [])}
        )
        
        l = m.select(and_(keywords.c.name == 'red', keywords.c.keyword_id == itemkeywords.c.keyword_id, items.c.item_id==itemkeywords.c.item_id))
        self.assert_result(l, Item, 
            {'item_id' : 1, 'keywords' : (Keyword, [{'keyword_id' : 2}, {'keyword_id' : 4}, {'keyword_id' : 6}])},
            {'item_id' : 2, 'keywords' : (Keyword, [{'keyword_id' : 2}, {'keyword_id' : 7}, {'keyword_id' : 5}])},
        )
    
    def testoneandmany(self):
        items = orderitems

        m = mapper(Item, items, 
        properties = dict(
                keywords = relation(Keyword, keywords, itemkeywords, lazy = False),
            ))

        m = mapper(Order, orders, properties = dict(
                items = relation(m, lazy = False)
            ))
        l = m.select("orders.order_id in (1,2,3)")
        #l = m.select()
        print repr(l)

class SaveTest(AssertMixin):

    def testbasic(self):
        # save two users
        u = User()
        u.user_name = 'savetester'
        u2 = User()
        u2.user_name = 'savetester2'
        m = mapper(User, users)

        objectstore.uow().commit()
        return
        
        m.save(u)
        m.save(u2)

        # assert the first one retreives the same from the identity map
        nu = m.get(u.user_id)
        self.assert_(u is nu)

        # clear out the identity map, so next get forces a SELECT
        objectstore.clear()

        # check it again, identity should be different but ids the same
        nu = m.get(u.user_id)
        self.assert_(u is not nu and u.user_id == nu.user_id and nu.user_name == 'savetester')

        # change first users name and save
        u.user_name = 'modifiedname'
        m.save(u)

        # select both
        userlist = m.select(users.c.user_id.in_(u.user_id, u2.user_id))
        # making a slight assumption here about the IN clause mechanics with regards to ordering
        self.assert_(u.user_id == userlist[0].user_id and userlist[0].user_name == 'modifiedname')
        self.assert_(u2.user_id == userlist[1].user_id and userlist[1].user_name == 'savetester2')

    def testmultitable(self):
        """tests a save of an object where each instance spans two tables. also tests
        redefinition of the keynames for the column properties."""
        usersaddresses = sql.join(users, addresses, users.c.user_id == addresses.c.user_id)
        m = mapper(User, usersaddresses, table = users,  
            properties = dict(
                email = ColumnProperty(addresses.c.email_address), 
                foo_id = ColumnProperty(users.c.user_id, addresses.c.user_id)
                )
            )
            
        u = User()
        u.user_name = 'multitester'
        u.email = 'multi@test.org'


        m.save(u)

        usertable = engine.ResultProxy(users.select(users.c.user_id.in_(u.foo_id)).execute()).fetchall()
        self.assert_(usertable[0].row == (u.foo_id, 'multitester'))
        addresstable = engine.ResultProxy(addresses.select(addresses.c.address_id.in_(4)).execute()).fetchall()
        self.assert_(addresstable[0].row == (u.address_id, u.foo_id, 'multi@test.org'))

        u.email = 'lala@hey.com'
        u.user_name = 'imnew'
        m.save(u)
        usertable = engine.ResultProxy(users.select(users.c.user_id.in_(u.foo_id)).execute()).fetchall()
        self.assert_(usertable[0].row == (u.foo_id, 'imnew'))
        addresstable = engine.ResultProxy(addresses.select(addresses.c.address_id.in_(u.address_id)).execute()).fetchall()
        self.assert_(addresstable[0].row == (u.address_id, u.foo_id, 'lala@hey.com'))

        u = m.select(users.c.user_id==u.foo_id)[0]
        print repr(u.__dict__)

    def testonetoone(self):
        m = mapper(User, users, properties = dict(
            address = relation(Address, addresses, lazy = True, uselist = False)
        ))
        u = User()
        u.user_name = 'one2onetester'
        u.address = Address()
        u.address.email_address = 'myonlyaddress@foo.com'
        m.save(u)
        u.user_name = 'imnew'
        m.save(u)
        u.address.email_address = 'imnew@foo.com'
        m.save(u)
        m.save(u)

    def testbackwardsonetoone(self):
        # test 'backwards'
        m = mapper(Address, addresses, properties = dict(
            user = relation(User, users, foreignkey = addresses.c.user_id, primaryjoin = users.c.user_id == addresses.c.user_id, lazy = True, uselist = False)
        ))
        data = [
            {'user_name' : 'thesub' , 'email_address' : 'bar@foo.com'},
            {'user_name' : 'assdkfj' , 'email_address' : 'thesdf@asdf.com'},
            {'user_name' : 'n4knd' , 'email_address' : 'asf3@bar.org'},
            {'user_name' : 'v88f4' , 'email_address' : 'adsd5@llala.net'},
            {'user_name' : 'asdf8d' , 'email_address' : 'theater@foo.com'}
        ]
        objects = []
        for elem in data:
            a = Address()
            a.email_address = elem['email_address']
            a.user = User()
            a.user.user_name = elem['user_name']
            objects.append(a)
            
        objectstore.uow().commit()

        objects[2].email_address = 'imnew@foo.bar'
        objects[3].user = User()
        objects[3].user.user_name = 'imnewlyadded'
        
        objectstore.uow().commit()
        return
        m.save(a)
        l = sql.select([users, addresses], sql.and_(users.c.user_id==addresses.c.address_id, addresses.c.address_id==a.address_id)).execute()
        r = engine.ResultProxy(l)
        print repr(r.fetchone().row)
        
    def testonetomany(self):
        """test basic save of one to many."""
        m = mapper(User, users, properties = dict(
            addresses = relation(Address, addresses, lazy = True)
        ))
        u = User()
        u.user_name = 'one2manytester'
        u.addresses = []
        a = Address()
        a.email_address = 'one2many@test.org'
        u.addresses.append(a)
        a2 = Address()
        a2.email_address = 'lala@test.org'
        u.addresses.append(a2)

        objectstore.uow().commit()
        return

        m.save(u)
        usertable = engine.ResultProxy(users.select(users.c.user_id.in_(u.user_id)).execute()).fetchall()
        self.assert_(usertable[0].row == (u.user_id, 'one2manytester'))
        addresstable = engine.ResultProxy(addresses.select(addresses.c.address_id.in_(a.address_id, a2.address_id)).execute()).fetchall()
        self.assert_(addresstable[0].row == (a.address_id, u.user_id, 'one2many@test.org'))
        self.assert_(addresstable[1].row == (a2.address_id, u.user_id, 'lala@test.org'))

        userid = u.user_id
        addressid = a2.address_id
        
        a2.email_address = 'somethingnew@foo.com'
        m.save(u)
        addresstable = engine.ResultProxy(addresses.select(addresses.c.address_id == addressid).execute()).fetchall()
        self.assert_(addresstable[0].row == (addressid, userid, 'somethingnew@foo.com'))
        self.assert_(u.user_id == userid and a2.address_id == addressid)

    def testalias(self):
        """tests that an alias of a table can be used in a mapper. 
        the mapper has to locate the original table and columns to keep it all straight."""
        ualias = Alias(users, 'ualias')
        m = mapper(User, ualias)
        u = User()
        u.user_name = 'testalias'
        m.save(u)
        
        u2 = m.select(ualias.c.user_id == u.user_id)[0]
        self.assert_(u2 is u)

    def testremove(self):
        m = mapper(User, users, properties = dict(
            addresses = relation(Address, addresses, lazy = True)
        ))
        u = User()
        u.user_name = 'one2manytester'
        u.addresses = []
        a = Address()
        a.email_address = 'one2many@test.org'
        u.addresses.append(a)
        a2 = Address()
        a2.email_address = 'lala@test.org'
        u.addresses.append(a2)
        m.save(u)
        addresstable = engine.ResultProxy(addresses.select(addresses.c.address_id.in_(a.address_id, a2.address_id)).execute()).fetchall()
        print repr(addresstable[0].row)
        self.assert_(addresstable[0].row == (a.address_id, u.user_id, 'one2many@test.org'))
        self.assert_(addresstable[1].row == (a2.address_id, u.user_id, 'lala@test.org'))
        del u.addresses[1]
        m.save(u)
        addresstable = engine.ResultProxy(addresses.select(addresses.c.address_id.in_(a.address_id, a2.address_id)).execute()).fetchall()
        print repr(addresstable)
        self.assert_(addresstable[0].row == (a.address_id, u.user_id, 'one2many@test.org'))
        self.assert_(addresstable[1].row == (a2.address_id, None, 'lala@test.org'))

    def testmanytomany(self):
        items = orderitems

        m = mapper(Item, items, properties = dict(
                keywords = relation(Keyword, keywords, itemkeywords, lazy = False),
            ), echo = True)

        keywordmapper = mapper(Keyword, keywords)

        data = [Item,
            {'item_name': 'item1', 'keywords' : (Keyword,[{'name': 'green'}, {'name': 'purple'},{'name': 'big'},{'name': 'round'}])},
            {'item_name': 'item2', 'keywords' : (Keyword,[{'name':'blue'}, {'name':'small'}, {'name':'imnew'},{'name':'round'}])},
            {'item_name': 'item3', 'keywords' : (Keyword,[])},
            {'item_name': 'item4', 'keywords' : (Keyword,[{'name':'blue'},{'name':'big'}])},
            {'item_name': 'item5', 'keywords' : (Keyword,[{'name':'green'},{'name':'big'},{'name':'exacting'}])},
            {'item_name': 'item6', 'keywords' : (Keyword,[{'name':'red'},{'name':'small'},{'name':'round'}])},
        ]
        objects = []
        for elem in data[1:]:
            item = Item()
            objects.append(item)
            item.item_name = elem['item_name']
            item.keywords = []
            if len(elem['keywords'][1]):
                klist = keywordmapper.select(keywords.c.name.in_(*[e['name'] for e in elem['keywords'][1]]))
            else:
                klist = []
            khash = {}
            for k in klist:
                khash[k.name] = k
            for kname in [e['name'] for e in elem['keywords'][1]]:
                try:
                    k = khash[kname]
                except KeyError:
                    k = Keyword()
                    k.name = kname
                item.keywords.append(k)

        objectstore.uow().commit()
        print "OK!"
        l = m.select(items.c.item_name.in_(*[e['item_name'] for e in data[1:]]))
        self.assert_result(l, data)
        print "OK!"

        objects[4].item_name = 'item4updated'
        k = Keyword()
        k.name = 'yellow'
        objects[5].keywords.append(k)
        
        objectstore.uow().commit()
        print "OK!"
        objects[2].keywords.append(k)
        print "added: " + repr(objects[2].keywords.added_items())
        objectstore.uow().commit()
        
if __name__ == "__main__":
    unittest.main()
