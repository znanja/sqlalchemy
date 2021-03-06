
from sqlalchemy.testing import eq_, assert_raises, \
    assert_raises_message, is_
from sqlalchemy.ext import declarative as decl
from sqlalchemy import exc
import sqlalchemy as sa
from sqlalchemy import testing
from sqlalchemy import MetaData, Integer, String, ForeignKey, \
    ForeignKeyConstraint, Index
from sqlalchemy.testing.schema import Table, Column
from sqlalchemy.orm import relationship, create_session, class_mapper, \
    joinedload, configure_mappers, backref, clear_mappers, \
    polymorphic_union, deferred, column_property, composite,\
    Session
from sqlalchemy.testing import eq_
from sqlalchemy.util import classproperty
from sqlalchemy.ext.declarative import declared_attr, AbstractConcreteBase, \
            ConcreteBase, has_inherited_table
from sqlalchemy.testing import fixtures

Base = None

class DeclarativeTestBase(fixtures.TestBase, testing.AssertsExecutionResults):
    def setup(self):
        global Base
        Base = decl.declarative_base(testing.db)

    def teardown(self):
        Session.close_all()
        clear_mappers()
        Base.metadata.drop_all()

class DeclarativeInheritanceTest(DeclarativeTestBase):

    def test_we_must_copy_mapper_args(self):

        class Person(Base):

            __tablename__ = 'people'
            id = Column(Integer, primary_key=True)
            discriminator = Column('type', String(50))
            __mapper_args__ = {'polymorphic_on': discriminator,
                               'polymorphic_identity': 'person'}

        class Engineer(Person):

            primary_language = Column(String(50))

        assert 'inherits' not in Person.__mapper_args__
        assert class_mapper(Engineer).polymorphic_identity is None
        assert class_mapper(Engineer).polymorphic_on is Person.__table__.c.type

    def test_we_must_only_copy_column_mapper_args(self):

        class Person(Base):

            __tablename__ = 'people'
            id = Column(Integer, primary_key=True)
            a=Column(Integer)
            b=Column(Integer)
            c=Column(Integer)
            d=Column(Integer)
            discriminator = Column('type', String(50))
            __mapper_args__ = {'polymorphic_on': discriminator,
                               'polymorphic_identity': 'person',
                               'version_id_col': 'a',
                               'column_prefix': 'bar',
                               'include_properties': ['id', 'a', 'b'],
                               }
        assert class_mapper(Person).version_id_col == 'a'
        assert class_mapper(Person).include_properties == set(['id', 'a', 'b'])


    def test_custom_join_condition(self):

        class Foo(Base):

            __tablename__ = 'foo'
            id = Column('id', Integer, primary_key=True)

        class Bar(Foo):

            __tablename__ = 'bar'
            id = Column('id', Integer, primary_key=True)
            foo_id = Column('foo_id', Integer)
            __mapper_args__ = {'inherit_condition': foo_id == Foo.id}

        # compile succeeds because inherit_condition is honored

        configure_mappers()

    def test_joined(self):

        class Company(Base, fixtures.ComparableEntity):

            __tablename__ = 'companies'
            id = Column('id', Integer, primary_key=True,
                        test_needs_autoincrement=True)
            name = Column('name', String(50))
            employees = relationship('Person')

        class Person(Base, fixtures.ComparableEntity):

            __tablename__ = 'people'
            id = Column('id', Integer, primary_key=True,
                        test_needs_autoincrement=True)
            company_id = Column('company_id', Integer,
                                ForeignKey('companies.id'))
            name = Column('name', String(50))
            discriminator = Column('type', String(50))
            __mapper_args__ = {'polymorphic_on': discriminator}

        class Engineer(Person):

            __tablename__ = 'engineers'
            __mapper_args__ = {'polymorphic_identity': 'engineer'}
            id = Column('id', Integer, ForeignKey('people.id'),
                        primary_key=True)
            primary_language = Column('primary_language', String(50))

        class Manager(Person):

            __tablename__ = 'managers'
            __mapper_args__ = {'polymorphic_identity': 'manager'}
            id = Column('id', Integer, ForeignKey('people.id'),
                        primary_key=True)
            golf_swing = Column('golf_swing', String(50))

        Base.metadata.create_all()
        sess = create_session()
        c1 = Company(name='MegaCorp, Inc.',
                     employees=[Engineer(name='dilbert',
                     primary_language='java'), Engineer(name='wally',
                     primary_language='c++'), Manager(name='dogbert',
                     golf_swing='fore!')])
        c2 = Company(name='Elbonia, Inc.',
                     employees=[Engineer(name='vlad',
                     primary_language='cobol')])
        sess.add(c1)
        sess.add(c2)
        sess.flush()
        sess.expunge_all()
        eq_(sess.query(Company).filter(Company.employees.of_type(Engineer).
            any(Engineer.primary_language
            == 'cobol')).first(), c2)

        # ensure that the Manager mapper was compiled with the Manager id
        # column as higher priority. this ensures that "Manager.id"
        # is appropriately treated as the "id" column in the "manager"
        # table (reversed from 0.6's behavior.)

        assert Manager.id.property.columns == [Manager.__table__.c.id, Person.__table__.c.id]

        # assert that the "id" column is available without a second
        # load. as of 0.7, the ColumnProperty tests all columns
        # in it's list to see which is present in the row.

        sess.expunge_all()

        def go():
            assert sess.query(Manager).filter(Manager.name == 'dogbert'
                    ).one().id
        self.assert_sql_count(testing.db, go, 1)
        sess.expunge_all()

        def go():
            assert sess.query(Person).filter(Manager.name == 'dogbert'
                    ).one().id

        self.assert_sql_count(testing.db, go, 1)

    def test_add_subcol_after_the_fact(self):

        class Person(Base, fixtures.ComparableEntity):

            __tablename__ = 'people'
            id = Column('id', Integer, primary_key=True,
                        test_needs_autoincrement=True)
            name = Column('name', String(50))
            discriminator = Column('type', String(50))
            __mapper_args__ = {'polymorphic_on': discriminator}

        class Engineer(Person):

            __tablename__ = 'engineers'
            __mapper_args__ = {'polymorphic_identity': 'engineer'}
            id = Column('id', Integer, ForeignKey('people.id'),
                        primary_key=True)

        Engineer.primary_language = Column('primary_language',
                String(50))
        Base.metadata.create_all()
        sess = create_session()
        e1 = Engineer(primary_language='java', name='dilbert')
        sess.add(e1)
        sess.flush()
        sess.expunge_all()
        eq_(sess.query(Person).first(), Engineer(primary_language='java'
            , name='dilbert'))

    def test_add_parentcol_after_the_fact(self):

        class Person(Base, fixtures.ComparableEntity):

            __tablename__ = 'people'
            id = Column('id', Integer, primary_key=True,
                        test_needs_autoincrement=True)
            discriminator = Column('type', String(50))
            __mapper_args__ = {'polymorphic_on': discriminator}

        class Engineer(Person):

            __tablename__ = 'engineers'
            __mapper_args__ = {'polymorphic_identity': 'engineer'}
            primary_language = Column(String(50))
            id = Column('id', Integer, ForeignKey('people.id'),
                        primary_key=True)

        Person.name = Column('name', String(50))
        Base.metadata.create_all()
        sess = create_session()
        e1 = Engineer(primary_language='java', name='dilbert')
        sess.add(e1)
        sess.flush()
        sess.expunge_all()
        eq_(sess.query(Person).first(),
            Engineer(primary_language='java', name='dilbert'))

    def test_add_sub_parentcol_after_the_fact(self):

        class Person(Base, fixtures.ComparableEntity):

            __tablename__ = 'people'
            id = Column('id', Integer, primary_key=True,
                        test_needs_autoincrement=True)
            discriminator = Column('type', String(50))
            __mapper_args__ = {'polymorphic_on': discriminator}

        class Engineer(Person):

            __tablename__ = 'engineers'
            __mapper_args__ = {'polymorphic_identity': 'engineer'}
            primary_language = Column(String(50))
            id = Column('id', Integer, ForeignKey('people.id'),
                        primary_key=True)

        class Admin(Engineer):

            __tablename__ = 'admins'
            __mapper_args__ = {'polymorphic_identity': 'admin'}
            workstation = Column(String(50))
            id = Column('id', Integer, ForeignKey('engineers.id'),
                        primary_key=True)

        Person.name = Column('name', String(50))
        Base.metadata.create_all()
        sess = create_session()
        e1 = Admin(primary_language='java', name='dilbert',
                   workstation='foo')
        sess.add(e1)
        sess.flush()
        sess.expunge_all()
        eq_(sess.query(Person).first(), Admin(primary_language='java',
            name='dilbert', workstation='foo'))

    def test_subclass_mixin(self):

        class Person(Base, fixtures.ComparableEntity):

            __tablename__ = 'people'
            id = Column('id', Integer, primary_key=True)
            name = Column('name', String(50))
            discriminator = Column('type', String(50))
            __mapper_args__ = {'polymorphic_on': discriminator}

        class MyMixin(object):

            pass

        class Engineer(MyMixin, Person):

            __tablename__ = 'engineers'
            __mapper_args__ = {'polymorphic_identity': 'engineer'}
            id = Column('id', Integer, ForeignKey('people.id'),
                        primary_key=True)
            primary_language = Column('primary_language', String(50))

        assert class_mapper(Engineer).inherits is class_mapper(Person)

    def test_with_undefined_foreignkey(self):

        class Parent(Base):

            __tablename__ = 'parent'
            id = Column('id', Integer, primary_key=True)
            tp = Column('type', String(50))
            __mapper_args__ = dict(polymorphic_on=tp)

        class Child1(Parent):

            __tablename__ = 'child1'
            id = Column('id', Integer, ForeignKey('parent.id'),
                        primary_key=True)
            related_child2 = Column('c2', Integer,
                                    ForeignKey('child2.id'))
            __mapper_args__ = dict(polymorphic_identity='child1')

        # no exception is raised by the ForeignKey to "child2" even
        # though child2 doesn't exist yet

        class Child2(Parent):

            __tablename__ = 'child2'
            id = Column('id', Integer, ForeignKey('parent.id'),
                        primary_key=True)
            related_child1 = Column('c1', Integer)
            __mapper_args__ = dict(polymorphic_identity='child2')

        sa.orm.configure_mappers()  # no exceptions here

    def test_foreign_keys_with_col(self):
        """Test that foreign keys that reference a literal 'id' subclass
        'id' attribute behave intuitively.

        See [ticket:1892].

        """

        class Booking(Base):
            __tablename__ = 'booking'
            id = Column(Integer, primary_key=True)

        class PlanBooking(Booking):
            __tablename__ = 'plan_booking'
            id = Column(Integer, ForeignKey(Booking.id),
                            primary_key=True)

        # referencing PlanBooking.id gives us the column
        # on plan_booking, not booking
        class FeatureBooking(Booking):
            __tablename__ = 'feature_booking'
            id = Column(Integer, ForeignKey(Booking.id),
                                        primary_key=True)
            plan_booking_id = Column(Integer,
                                ForeignKey(PlanBooking.id))

            plan_booking = relationship(PlanBooking,
                        backref='feature_bookings')

        assert FeatureBooking.__table__.c.plan_booking_id.\
                    references(PlanBooking.__table__.c.id)

        assert FeatureBooking.__table__.c.id.\
                    references(Booking.__table__.c.id)


    def test_single_colsonbase(self):
        """test single inheritance where all the columns are on the base
        class."""

        class Company(Base, fixtures.ComparableEntity):

            __tablename__ = 'companies'
            id = Column('id', Integer, primary_key=True,
                        test_needs_autoincrement=True)
            name = Column('name', String(50))
            employees = relationship('Person')

        class Person(Base, fixtures.ComparableEntity):

            __tablename__ = 'people'
            id = Column('id', Integer, primary_key=True,
                        test_needs_autoincrement=True)
            company_id = Column('company_id', Integer,
                                ForeignKey('companies.id'))
            name = Column('name', String(50))
            discriminator = Column('type', String(50))
            primary_language = Column('primary_language', String(50))
            golf_swing = Column('golf_swing', String(50))
            __mapper_args__ = {'polymorphic_on': discriminator}

        class Engineer(Person):

            __mapper_args__ = {'polymorphic_identity': 'engineer'}

        class Manager(Person):

            __mapper_args__ = {'polymorphic_identity': 'manager'}

        Base.metadata.create_all()
        sess = create_session()
        c1 = Company(name='MegaCorp, Inc.',
                     employees=[Engineer(name='dilbert',
                     primary_language='java'), Engineer(name='wally',
                     primary_language='c++'), Manager(name='dogbert',
                     golf_swing='fore!')])
        c2 = Company(name='Elbonia, Inc.',
                     employees=[Engineer(name='vlad',
                     primary_language='cobol')])
        sess.add(c1)
        sess.add(c2)
        sess.flush()
        sess.expunge_all()
        eq_(sess.query(Person).filter(Engineer.primary_language
            == 'cobol').first(), Engineer(name='vlad'))
        eq_(sess.query(Company).filter(Company.employees.of_type(Engineer).
            any(Engineer.primary_language
            == 'cobol')).first(), c2)

    def test_single_colsonsub(self):
        """test single inheritance where the columns are local to their
        class.

        this is a newer usage.

        """

        class Company(Base, fixtures.ComparableEntity):

            __tablename__ = 'companies'
            id = Column('id', Integer, primary_key=True,
                        test_needs_autoincrement=True)
            name = Column('name', String(50))
            employees = relationship('Person')

        class Person(Base, fixtures.ComparableEntity):

            __tablename__ = 'people'
            id = Column(Integer, primary_key=True,
                        test_needs_autoincrement=True)
            company_id = Column(Integer, ForeignKey('companies.id'))
            name = Column(String(50))
            discriminator = Column('type', String(50))
            __mapper_args__ = {'polymorphic_on': discriminator}

        class Engineer(Person):

            __mapper_args__ = {'polymorphic_identity': 'engineer'}
            primary_language = Column(String(50))

        class Manager(Person):

            __mapper_args__ = {'polymorphic_identity': 'manager'}
            golf_swing = Column(String(50))

        # we have here a situation that is somewhat unique. the Person
        # class is mapped to the "people" table, but it was mapped when
        # the table did not include the "primary_language" or
        # "golf_swing" columns.  declarative will also manipulate the
        # exclude_properties collection so that sibling classes don't
        # cross-pollinate.

        assert Person.__table__.c.company_id is not None
        assert Person.__table__.c.golf_swing is not None
        assert Person.__table__.c.primary_language is not None
        assert Engineer.primary_language is not None
        assert Manager.golf_swing is not None
        assert not hasattr(Person, 'primary_language')
        assert not hasattr(Person, 'golf_swing')
        assert not hasattr(Engineer, 'golf_swing')
        assert not hasattr(Manager, 'primary_language')
        Base.metadata.create_all()
        sess = create_session()
        e1 = Engineer(name='dilbert', primary_language='java')
        e2 = Engineer(name='wally', primary_language='c++')
        m1 = Manager(name='dogbert', golf_swing='fore!')
        c1 = Company(name='MegaCorp, Inc.', employees=[e1, e2, m1])
        e3 = Engineer(name='vlad', primary_language='cobol')
        c2 = Company(name='Elbonia, Inc.', employees=[e3])
        sess.add(c1)
        sess.add(c2)
        sess.flush()
        sess.expunge_all()
        eq_(sess.query(Person).filter(Engineer.primary_language
            == 'cobol').first(), Engineer(name='vlad'))
        eq_(sess.query(Company).filter(Company.employees.of_type(Engineer).
            any(Engineer.primary_language
            == 'cobol')).first(), c2)
        eq_(sess.query(Engineer).filter_by(primary_language='cobol'
            ).one(), Engineer(name='vlad', primary_language='cobol'))

    @testing.skip_if(lambda: testing.against('oracle'),
                    "Test has an empty insert in it at the moment")
    def test_columns_single_inheritance_conflict_resolution(self):
        """Test that a declared_attr can return the existing column and it will
        be ignored.  this allows conditional columns to be added.

        See [ticket:2472].

        """
        class Person(Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)

        class Engineer(Person):
            """single table inheritance"""

            @declared_attr
            def target_id(cls):
                return cls.__table__.c.get('target_id',
                       Column(Integer, ForeignKey('other.id'))
                    )
            @declared_attr
            def target(cls):
                return relationship("Other")

        class Manager(Person):
            """single table inheritance"""

            @declared_attr
            def target_id(cls):
                return cls.__table__.c.get('target_id',
                        Column(Integer, ForeignKey('other.id'))
                    )
            @declared_attr
            def target(cls):
                return relationship("Other")

        class Other(Base):
            __tablename__ = 'other'
            id = Column(Integer, primary_key=True)

        is_(
            Engineer.target_id.property.columns[0],
            Person.__table__.c.target_id
        )
        is_(
            Manager.target_id.property.columns[0],
            Person.__table__.c.target_id
        )
        # do a brief round trip on this
        Base.metadata.create_all()
        session = Session()
        o1, o2 = Other(), Other()
        session.add_all([
            Engineer(target=o1),
            Manager(target=o2),
            Manager(target=o1)
            ])
        session.commit()
        eq_(session.query(Engineer).first().target, o1)


    def test_joined_from_single(self):

        class Company(Base, fixtures.ComparableEntity):

            __tablename__ = 'companies'
            id = Column('id', Integer, primary_key=True,
                        test_needs_autoincrement=True)
            name = Column('name', String(50))
            employees = relationship('Person')

        class Person(Base, fixtures.ComparableEntity):

            __tablename__ = 'people'
            id = Column(Integer, primary_key=True,
                        test_needs_autoincrement=True)
            company_id = Column(Integer, ForeignKey('companies.id'))
            name = Column(String(50))
            discriminator = Column('type', String(50))
            __mapper_args__ = {'polymorphic_on': discriminator}

        class Manager(Person):

            __mapper_args__ = {'polymorphic_identity': 'manager'}
            golf_swing = Column(String(50))

        class Engineer(Person):

            __tablename__ = 'engineers'
            __mapper_args__ = {'polymorphic_identity': 'engineer'}
            id = Column(Integer, ForeignKey('people.id'),
                        primary_key=True)
            primary_language = Column(String(50))

        assert Person.__table__.c.golf_swing is not None
        assert not Person.__table__.c.has_key('primary_language')
        assert Engineer.__table__.c.primary_language is not None
        assert Engineer.primary_language is not None
        assert Manager.golf_swing is not None
        assert not hasattr(Person, 'primary_language')
        assert not hasattr(Person, 'golf_swing')
        assert not hasattr(Engineer, 'golf_swing')
        assert not hasattr(Manager, 'primary_language')
        Base.metadata.create_all()
        sess = create_session()
        e1 = Engineer(name='dilbert', primary_language='java')
        e2 = Engineer(name='wally', primary_language='c++')
        m1 = Manager(name='dogbert', golf_swing='fore!')
        c1 = Company(name='MegaCorp, Inc.', employees=[e1, e2, m1])
        e3 = Engineer(name='vlad', primary_language='cobol')
        c2 = Company(name='Elbonia, Inc.', employees=[e3])
        sess.add(c1)
        sess.add(c2)
        sess.flush()
        sess.expunge_all()
        eq_(sess.query(Person).with_polymorphic(Engineer).
            filter(Engineer.primary_language
            == 'cobol').first(), Engineer(name='vlad'))
        eq_(sess.query(Company).filter(Company.employees.of_type(Engineer).
            any(Engineer.primary_language
            == 'cobol')).first(), c2)
        eq_(sess.query(Engineer).filter_by(primary_language='cobol'
            ).one(), Engineer(name='vlad', primary_language='cobol'))

    def test_single_from_joined_colsonsub(self):
        class Person(Base, fixtures.ComparableEntity):

            __tablename__ = 'people'
            id = Column(Integer, primary_key=True,
                        test_needs_autoincrement=True)
            name = Column(String(50))
            discriminator = Column('type', String(50))
            __mapper_args__ = {'polymorphic_on': discriminator}

        class Manager(Person):
            __tablename__ = 'manager'
            __mapper_args__ = {'polymorphic_identity': 'manager'}
            id = Column(Integer, ForeignKey('people.id'), primary_key=True)
            golf_swing = Column(String(50))

        class Boss(Manager):
            boss_name = Column(String(50))

        is_(
            Boss.__mapper__.column_attrs['boss_name'].columns[0],
            Manager.__table__.c.boss_name
        )

    def test_polymorphic_on_converted_from_inst(self):
        class A(Base):
            __tablename__ = 'A'
            id = Column(Integer, primary_key=True)
            discriminator = Column(String)

            @declared_attr
            def __mapper_args__(cls):
                return {
                    'polymorphic_identity': cls.__name__,
                    'polymorphic_on': cls.discriminator
                }

        class B(A):
            pass
        is_(B.__mapper__.polymorphic_on, A.__table__.c.discriminator)

    def test_add_deferred(self):

        class Person(Base, fixtures.ComparableEntity):

            __tablename__ = 'people'
            id = Column('id', Integer, primary_key=True,
                        test_needs_autoincrement=True)

        Person.name = deferred(Column(String(10)))
        Base.metadata.create_all()
        sess = create_session()
        p = Person(name='ratbert')
        sess.add(p)
        sess.flush()
        sess.expunge_all()
        eq_(sess.query(Person).all(), [Person(name='ratbert')])
        sess.expunge_all()
        person = sess.query(Person).filter(Person.name == 'ratbert'
                ).one()
        assert 'name' not in person.__dict__

    def test_single_fksonsub(self):
        """test single inheritance with a foreign key-holding column on
        a subclass.

        """

        class Person(Base, fixtures.ComparableEntity):

            __tablename__ = 'people'
            id = Column(Integer, primary_key=True,
                        test_needs_autoincrement=True)
            name = Column(String(50))
            discriminator = Column('type', String(50))
            __mapper_args__ = {'polymorphic_on': discriminator}

        class Engineer(Person):

            __mapper_args__ = {'polymorphic_identity': 'engineer'}
            primary_language_id = Column(Integer,
                    ForeignKey('languages.id'))
            primary_language = relationship('Language')

        class Language(Base, fixtures.ComparableEntity):

            __tablename__ = 'languages'
            id = Column(Integer, primary_key=True,
                        test_needs_autoincrement=True)
            name = Column(String(50))

        assert not hasattr(Person, 'primary_language_id')
        Base.metadata.create_all()
        sess = create_session()
        java, cpp, cobol = Language(name='java'), Language(name='cpp'), \
            Language(name='cobol')
        e1 = Engineer(name='dilbert', primary_language=java)
        e2 = Engineer(name='wally', primary_language=cpp)
        e3 = Engineer(name='vlad', primary_language=cobol)
        sess.add_all([e1, e2, e3])
        sess.flush()
        sess.expunge_all()
        eq_(sess.query(Person).filter(Engineer.primary_language.has(
            Language.name
            == 'cobol')).first(), Engineer(name='vlad',
            primary_language=Language(name='cobol')))
        eq_(sess.query(Engineer).filter(Engineer.primary_language.has(
            Language.name
            == 'cobol')).one(), Engineer(name='vlad',
            primary_language=Language(name='cobol')))
        eq_(sess.query(Person).join(Engineer.primary_language).order_by(
            Language.name).all(),
            [Engineer(name='vlad',
            primary_language=Language(name='cobol')),
            Engineer(name='wally', primary_language=Language(name='cpp'
            )), Engineer(name='dilbert',
            primary_language=Language(name='java'))])

    def test_single_three_levels(self):

        class Person(Base, fixtures.ComparableEntity):

            __tablename__ = 'people'
            id = Column(Integer, primary_key=True)
            name = Column(String(50))
            discriminator = Column('type', String(50))
            __mapper_args__ = {'polymorphic_on': discriminator}

        class Engineer(Person):

            __mapper_args__ = {'polymorphic_identity': 'engineer'}
            primary_language = Column(String(50))

        class JuniorEngineer(Engineer):

            __mapper_args__ = \
                {'polymorphic_identity': 'junior_engineer'}
            nerf_gun = Column(String(50))

        class Manager(Person):

            __mapper_args__ = {'polymorphic_identity': 'manager'}
            golf_swing = Column(String(50))

        assert JuniorEngineer.nerf_gun
        assert JuniorEngineer.primary_language
        assert JuniorEngineer.name
        assert Manager.golf_swing
        assert Engineer.primary_language
        assert not hasattr(Engineer, 'golf_swing')
        assert not hasattr(Engineer, 'nerf_gun')
        assert not hasattr(Manager, 'nerf_gun')
        assert not hasattr(Manager, 'primary_language')

    def test_single_detects_conflict(self):

        class Person(Base):

            __tablename__ = 'people'
            id = Column(Integer, primary_key=True)
            name = Column(String(50))
            discriminator = Column('type', String(50))
            __mapper_args__ = {'polymorphic_on': discriminator}

        class Engineer(Person):

            __mapper_args__ = {'polymorphic_identity': 'engineer'}
            primary_language = Column(String(50))

        # test sibling col conflict

        def go():

            class Manager(Person):

                __mapper_args__ = {'polymorphic_identity': 'manager'}
                golf_swing = Column(String(50))
                primary_language = Column(String(50))

        assert_raises(sa.exc.ArgumentError, go)

        # test parent col conflict

        def go():

            class Salesman(Person):

                __mapper_args__ = {'polymorphic_identity': 'manager'}
                name = Column(String(50))

        assert_raises(sa.exc.ArgumentError, go)

    def test_single_no_special_cols(self):

        class Person(Base, fixtures.ComparableEntity):

            __tablename__ = 'people'
            id = Column('id', Integer, primary_key=True)
            name = Column('name', String(50))
            discriminator = Column('type', String(50))
            __mapper_args__ = {'polymorphic_on': discriminator}

        def go():

            class Engineer(Person):

                __mapper_args__ = {'polymorphic_identity': 'engineer'}
                primary_language = Column('primary_language',
                        String(50))
                foo_bar = Column(Integer, primary_key=True)

        assert_raises_message(sa.exc.ArgumentError, 'place primary key'
                              , go)

    def test_single_no_table_args(self):

        class Person(Base, fixtures.ComparableEntity):

            __tablename__ = 'people'
            id = Column('id', Integer, primary_key=True)
            name = Column('name', String(50))
            discriminator = Column('type', String(50))
            __mapper_args__ = {'polymorphic_on': discriminator}

        def go():

            class Engineer(Person):

                __mapper_args__ = {'polymorphic_identity': 'engineer'}
                primary_language = Column('primary_language',
                        String(50))

                # this should be on the Person class, as this is single
                # table inheritance, which is why we test that this
                # throws an exception!

                __table_args__ = {'mysql_engine': 'InnoDB'}

        assert_raises_message(sa.exc.ArgumentError,
                              'place __table_args__', go)

    @testing.emits_warning("This declarative")
    def test_dupe_name_in_hierarchy(self):
        class A(Base):
           __tablename__ = "a"
           id = Column( Integer, primary_key=True)
        a_1 = A
        class A(a_1):
           __tablename__ = 'b'

           id = Column(Integer(),ForeignKey(a_1.id), primary_key = True)

        assert A.__mapper__.inherits is a_1.__mapper__


class OverlapColPrecedenceTest(DeclarativeTestBase):
    """test #1892 cases when declarative does column precedence."""

    def _run_test(self, Engineer, e_id, p_id):
        p_table = Base.metadata.tables['person']
        e_table = Base.metadata.tables['engineer']
        assert Engineer.id.property.columns[0] is e_table.c[e_id]
        assert Engineer.id.property.columns[1] is p_table.c[p_id]

    def test_basic(self):
        class Person(Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)

        class Engineer(Person):
            __tablename__ = 'engineer'
            id = Column(Integer, ForeignKey('person.id'), primary_key=True)

        self._run_test(Engineer, "id", "id")

    def test_alt_name_base(self):
        class Person(Base):
            __tablename__ = 'person'
            id = Column("pid", Integer, primary_key=True)

        class Engineer(Person):
            __tablename__ = 'engineer'
            id = Column(Integer, ForeignKey('person.pid'), primary_key=True)

        self._run_test(Engineer, "id", "pid")

    def test_alt_name_sub(self):
        class Person(Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)

        class Engineer(Person):
            __tablename__ = 'engineer'
            id = Column("eid", Integer, ForeignKey('person.id'), primary_key=True)

        self._run_test(Engineer, "eid", "id")

    def test_alt_name_both(self):
        class Person(Base):
            __tablename__ = 'person'
            id = Column("pid", Integer, primary_key=True)

        class Engineer(Person):
            __tablename__ = 'engineer'
            id = Column("eid", Integer, ForeignKey('person.pid'), primary_key=True)

        self._run_test(Engineer, "eid", "pid")


from test.orm.test_events import _RemoveListeners
class ConcreteInhTest(_RemoveListeners, DeclarativeTestBase):
    def _roundtrip(self, Employee, Manager, Engineer, Boss,
                            polymorphic=True, explicit_type=False):
        Base.metadata.create_all()
        sess = create_session()
        e1 = Engineer(name='dilbert', primary_language='java')
        e2 = Engineer(name='wally', primary_language='c++')
        m1 = Manager(name='dogbert', golf_swing='fore!')
        e3 = Engineer(name='vlad', primary_language='cobol')
        b1 = Boss(name="pointy haired")

        if polymorphic:
            for obj in [e1, e2, m1, e3, b1]:
                if explicit_type:
                    eq_(obj.type, obj.__mapper__.polymorphic_identity)
                else:
                    assert_raises_message(
                        AttributeError,
                        "does not implement attribute .?'type' "
                            "at the instance level.",
                        getattr, obj, "type"
                    )
        else:
            assert "type" not in Engineer.__dict__
            assert "type" not in Manager.__dict__
            assert "type" not in Boss.__dict__

        sess.add_all([e1, e2, m1, e3, b1])
        sess.flush()
        sess.expunge_all()
        if polymorphic:
            eq_(sess.query(Employee).order_by(Employee.name).all(),
                [Engineer(name='dilbert'), Manager(name='dogbert'),
                Boss(name='pointy haired'), Engineer(name='vlad'), Engineer(name='wally')])
        else:
            eq_(sess.query(Engineer).order_by(Engineer.name).all(),
                [Engineer(name='dilbert'), Engineer(name='vlad'),
                Engineer(name='wally')])
            eq_(sess.query(Manager).all(), [Manager(name='dogbert')])
            eq_(sess.query(Boss).all(), [Boss(name='pointy haired')])


    def test_explicit(self):
        engineers = Table('engineers', Base.metadata, Column('id',
                          Integer, primary_key=True,
                          test_needs_autoincrement=True), Column('name'
                          , String(50)), Column('primary_language',
                          String(50)))
        managers = Table('managers', Base.metadata,
                    Column('id',Integer, primary_key=True, test_needs_autoincrement=True),
                    Column('name', String(50)),
                    Column('golf_swing', String(50))
                )
        boss = Table('boss', Base.metadata,
                    Column('id',Integer, primary_key=True, test_needs_autoincrement=True),
                    Column('name', String(50)),
                    Column('golf_swing', String(50))
                )
        punion = polymorphic_union({
                                'engineer': engineers,
                                'manager' : managers,
                                'boss': boss}, 'type', 'punion')

        class Employee(Base, fixtures.ComparableEntity):

            __table__ = punion
            __mapper_args__ = {'polymorphic_on': punion.c.type}

        class Engineer(Employee):

            __table__ = engineers
            __mapper_args__ = {'polymorphic_identity': 'engineer',
                               'concrete': True}

        class Manager(Employee):

            __table__ = managers
            __mapper_args__ = {'polymorphic_identity': 'manager',
                               'concrete': True}

        class Boss(Manager):
            __table__ = boss
            __mapper_args__ = {'polymorphic_identity': 'boss',
                               'concrete': True}

        self._roundtrip(Employee, Manager, Engineer, Boss)

    def test_concrete_inline_non_polymorphic(self):
        """test the example from the declarative docs."""

        class Employee(Base, fixtures.ComparableEntity):

            __tablename__ = 'people'
            id = Column(Integer, primary_key=True,
                        test_needs_autoincrement=True)
            name = Column(String(50))

        class Engineer(Employee):

            __tablename__ = 'engineers'
            __mapper_args__ = {'concrete': True}
            id = Column(Integer, primary_key=True,
                        test_needs_autoincrement=True)
            primary_language = Column(String(50))
            name = Column(String(50))

        class Manager(Employee):

            __tablename__ = 'manager'
            __mapper_args__ = {'concrete': True}
            id = Column(Integer, primary_key=True,
                        test_needs_autoincrement=True)
            golf_swing = Column(String(50))
            name = Column(String(50))

        class Boss(Manager):
            __tablename__ = 'boss'
            __mapper_args__ = {'concrete': True}
            id = Column(Integer, primary_key=True,
                        test_needs_autoincrement=True)
            golf_swing = Column(String(50))
            name = Column(String(50))

        self._roundtrip(Employee, Manager, Engineer, Boss, polymorphic=False)

    def test_abstract_concrete_extension(self):
        class Employee(AbstractConcreteBase, Base, fixtures.ComparableEntity):
            pass

        class Manager(Employee):
            __tablename__ = 'manager'
            employee_id = Column(Integer, primary_key=True,
                                    test_needs_autoincrement=True)
            name = Column(String(50))
            golf_swing = Column(String(40))
            __mapper_args__ = {
                            'polymorphic_identity':'manager',
                            'concrete':True}

        class Boss(Manager):
            __tablename__ = 'boss'
            employee_id = Column(Integer, primary_key=True,
                                    test_needs_autoincrement=True)
            name = Column(String(50))
            golf_swing = Column(String(40))
            __mapper_args__ = {
                            'polymorphic_identity':'boss',
                            'concrete':True}

        class Engineer(Employee):
            __tablename__ = 'engineer'
            employee_id = Column(Integer, primary_key=True,
                                    test_needs_autoincrement=True)
            name = Column(String(50))
            primary_language = Column(String(40))
            __mapper_args__ = {'polymorphic_identity':'engineer',
                            'concrete':True}

        self._roundtrip(Employee, Manager, Engineer, Boss)

    def test_concrete_extension(self):
        class Employee(ConcreteBase, Base, fixtures.ComparableEntity):
            __tablename__ = 'employee'
            employee_id = Column(Integer, primary_key=True,
                                test_needs_autoincrement=True)
            name = Column(String(50))
            __mapper_args__ = {
                            'polymorphic_identity':'employee',
                            'concrete':True}
        class Manager(Employee):
            __tablename__ = 'manager'
            employee_id = Column(Integer, primary_key=True,
                            test_needs_autoincrement=True)
            name = Column(String(50))
            golf_swing = Column(String(40))
            __mapper_args__ = {
                            'polymorphic_identity':'manager',
                            'concrete':True}

        class Boss(Manager):
            __tablename__ = 'boss'
            employee_id = Column(Integer, primary_key=True,
                                    test_needs_autoincrement=True)
            name = Column(String(50))
            golf_swing = Column(String(40))
            __mapper_args__ = {
                            'polymorphic_identity':'boss',
                            'concrete':True}

        class Engineer(Employee):
            __tablename__ = 'engineer'
            employee_id = Column(Integer, primary_key=True,
                            test_needs_autoincrement=True)
            name = Column(String(50))
            primary_language = Column(String(40))
            __mapper_args__ = {'polymorphic_identity':'engineer',
                            'concrete':True}
        self._roundtrip(Employee, Manager, Engineer, Boss)


    def test_has_inherited_table_doesnt_consider_base(self):
        class A(Base):
            __tablename__ = 'a'
            id = Column(Integer, primary_key=True)

        assert not has_inherited_table(A)

        class B(A):
            __tablename__ = 'b'
            id = Column(Integer, ForeignKey('a.id'), primary_key=True)

        assert has_inherited_table(B)

    def test_has_inherited_table_in_mapper_args(self):
        class Test(Base):
            __tablename__ = 'test'
            id = Column(Integer, primary_key=True)
            type = Column(String(20))

            @declared_attr
            def __mapper_args__(cls):
                if not has_inherited_table(cls):
                    ret = {
                        'polymorphic_identity': 'default',
                        'polymorphic_on': cls.type,
                        }
                else:
                    ret = {'polymorphic_identity': cls.__name__}
                return ret

        class PolyTest(Test):
            __tablename__ = 'poly_test'
            id = Column(Integer, ForeignKey(Test.id), primary_key=True)

        configure_mappers()

        assert Test.__mapper__.polymorphic_on is Test.__table__.c.type
        assert PolyTest.__mapper__.polymorphic_on is Test.__table__.c.type

    def test_ok_to_override_type_from_abstract(self):
        class Employee(AbstractConcreteBase, Base, fixtures.ComparableEntity):
            pass

        class Manager(Employee):
            __tablename__ = 'manager'
            employee_id = Column(Integer, primary_key=True,
                                    test_needs_autoincrement=True)
            name = Column(String(50))
            golf_swing = Column(String(40))

            @property
            def type(self):
                return "manager"

            __mapper_args__ = {
                            'polymorphic_identity': "manager",
                            'concrete':True}

        class Boss(Manager):
            __tablename__ = 'boss'
            employee_id = Column(Integer, primary_key=True,
                                    test_needs_autoincrement=True)
            name = Column(String(50))
            golf_swing = Column(String(40))

            @property
            def type(self):
                return "boss"

            __mapper_args__ = {
                            'polymorphic_identity': "boss",
                            'concrete':True}

        class Engineer(Employee):
            __tablename__ = 'engineer'
            employee_id = Column(Integer, primary_key=True,
                            test_needs_autoincrement=True)
            name = Column(String(50))
            primary_language = Column(String(40))

            @property
            def type(self):
                return "engineer"
            __mapper_args__ = {'polymorphic_identity': "engineer",
                            'concrete':True}
        self._roundtrip(Employee, Manager, Engineer, Boss, explicit_type=True)
