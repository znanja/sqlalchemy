"""
Illustrates how to attach events to all instrumented attributes
and listen for change events.

"""

from sqlalchemy import event, orm

def configure_listener(class_, key, inst):
    def append(instance, value, initiator):
        instance.receive_change_event("append", key, value, None)

    def remove(instance, value, initiator):
        instance.receive_change_event("remove", key, value, None)

    def set_(instance, value, oldvalue, initiator):
        instance.receive_change_event("set", key, value, oldvalue)

    event.listen(append, 'on_append', inst)
    event.listen(remove, 'on_remove', inst)
    event.listen(set_, 'on_set', inst)


if __name__ == '__main__':

    from sqlalchemy import Column, Integer, String, ForeignKey
    from sqlalchemy.orm import relationship
    from sqlalchemy.ext.declarative import declarative_base

    class Base(object):
        
        def receive_change_event(self, verb, key, value, oldvalue):
            s = "Value '%s' %s on attribute '%s', " % (value, verb, key)
            if oldvalue:
                s += "which replaced the value '%s', " % oldvalue
            s += "on object %s" % self
            print s
            
    Base = declarative_base(cls=Base)

    event.listen(configure_listener, 'on_attribute_instrument', Base)

    class MyMappedClass(Base):
        __tablename__ = "mytable"
    
        id = Column(Integer, primary_key=True)
        data = Column(String(50))
        related_id = Column(Integer, ForeignKey("related.id"))
        related = relationship("Related", backref="mapped")

        def __str__(self):
            return "MyMappedClass(data=%r)" % self.data
            
    class Related(Base):
        __tablename__ = "related"

        id = Column(Integer, primary_key=True)
        data = Column(String(50))

        def __str__(self):
            return "Related(data=%r)" % self.data
    
    # classes are instrumented.  Demonstrate the events !
    
    m1 = MyMappedClass(data='m1', related=Related(data='r1'))
    m1.data = 'm1mod'
    m1.related.mapped.append(MyMappedClass(data='m2'))
    del m1.data
    
    
