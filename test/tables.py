
from sqlalchemy.sql import *
from sqlalchemy.schema import *
from sqlalchemy.mapper import *
import os

DBTYPE = 'sqlite_memory'

if DBTYPE == 'sqlite_memory':
    import sqlalchemy.databases.sqlite as sqllite
    db = sqllite.engine(':memory:', {}, echo = False)
elif DBTYPE == 'sqlite_file':
    import sqlalchemy.databases.sqlite as sqllite
    if os.access('querytest.db', os.F_OK):
        os.remove('querytest.db')
    db = sqllite.engine('querytest.db', opts = {}, echo = True)
elif DBTYPE == 'postgres':
    pass

users = Table('users', db,
    Column('user_id', INT, primary_key = True),
    Column('user_name', VARCHAR(20)),
)

addresses = Table('email_addresses', db,
    Column('address_id', INT, primary_key = True),
    Column('user_id', INT),
    Column('email_address', VARCHAR(20)),
)

orders = Table('orders', db,
    Column('order_id', INT, primary_key = True),
    Column('user_id', INT),
    Column('description', VARCHAR(50)),
    Column('isopen', INT)
)

orderitems = Table('items', db,
    Column('item_id', INT, primary_key = True),
    Column('order_id', INT),
    Column('item_name', VARCHAR(50))
)

keywords = Table('keywords', db,
    Column('keyword_id', INT, primary_key = True),
    Column('name', VARCHAR(50))
)

itemkeywords = Table('itemkeywords', db,
    Column('item_id', INT),
    Column('keyword_id', INT)
)

users.build()
users.insert().execute(
    dict(user_id = 7, user_name = 'jack'),
    dict(user_id = 8, user_name = 'ed'),
    dict(user_id = 9, user_name = 'fred')
)

addresses.build()
addresses.insert().execute(
    dict(address_id = 1, user_id = 7, email_address = "jack@bean.com"),
    dict(address_id = 2, user_id = 8, email_address = "ed@wood.com"),
    dict(address_id = 3, user_id = 8, email_address = "ed@lala.com")
)

orders.build()
orders.insert().execute(
    dict(order_id = 1, user_id = 7, description = 'order 1', isopen=0),
    dict(order_id = 2, user_id = 9, description = 'order 2', isopen=0),
    dict(order_id = 3, user_id = 7, description = 'order 3', isopen=1),
    dict(order_id = 4, user_id = 9, description = 'order 4', isopen=1),
    dict(order_id = 5, user_id = 7, description = 'order 5', isopen=0)
)

orderitems.build()
orderitems.insert().execute(
    dict(item_id=1, order_id=2, item_name='item 1'),
    dict(item_id=3, order_id=3, item_name='item 3'),
    dict(item_id=2, order_id=2, item_name='item 2'),
    dict(item_id=5, order_id=3, item_name='item 5'),
    dict(item_id=4, order_id=3, item_name='item 4')
)

keywords.build()
keywords.insert().execute(
    dict(keyword_id=1, name='blue'),
    dict(keyword_id=2, name='red'),
    dict(keyword_id=3, name='green'),
    dict(keyword_id=4, name='big'),
    dict(keyword_id=5, name='small'),
    dict(keyword_id=6, name='round'),
    dict(keyword_id=7, name='square')
)

itemkeywords.build()
itemkeywords.insert().execute(
    dict(keyword_id=2, item_id=1),
    dict(keyword_id=2, item_id=2),
    dict(keyword_id=4, item_id=1),
    dict(keyword_id=6, item_id=1),
    dict(keyword_id=7, item_id=2),
    dict(keyword_id=6, item_id=3),
    dict(keyword_id=3, item_id=3),
    dict(keyword_id=5, item_id=2),
    dict(keyword_id=4, item_id=3)
)
db.connection().commit()
