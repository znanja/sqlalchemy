# objectstore.py
# Copyright (C) 2005 Michael Bayer mike_mp@zzzcomputing.com
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.


"""maintains all currently loaded objects in memory,
using the "identity map" pattern.  Also provides a "unit of work" object which tracks changes
to objects so that they may be properly persisted within a transactional scope."""

import thread
import sqlalchemy.util as util
import sqlalchemy.attributes as attributes
import weakref
import string

def get_id_key(ident, class_, table):
    """returns an identity-map key for use in storing/retrieving an item from the identity map, given
    a tuple of the object's primary key values.
    
    ident - a tuple of primary key values corresponding to the object to be stored.  these values
    should be in the same order as the primary keys of the table
    class_ - a reference to the object's class
    table - a Table object where the object's primary fields are stored.
    selectable - a Selectable object which represents all the object's column-based fields.  this Selectable
    may be synonymous with the table argument or can be a larger construct containing that table.
    return value: a tuple object which is used as an identity key.
    """
    return (class_, table, tuple(ident))
def get_row_key(row, class_, table, primary_keys):
    """returns an identity-map key for use in storing/retrieving an item from the identity map, given
    a result set row.
    
    row - a sqlalchemy.dbengine.RowProxy instance or other map corresponding result-set column
    names to their values within a row.
    class_ - a reference to the object's class
    table - a Table object where the object's primary fields are stored.
    selectable - a Selectable object which represents all the object's column-based fields.  this Selectable
    may be synonymous with the table argument or can be a larger construct containing that table.
    return value: a tuple object which is used as an identity key.
    """
    return (class_, table, tuple([row[column.label] for column in primary_keys]))

def mapper(*args, **params):
    import sqlalchemy.mapper
    return sqlalchemy.mapper.mapper(*args, **params)
    
def commit(*obj):
    uow().commit(*obj)
    
def clear():
    uow.set(UnitOfWork())

def delete(*obj):
    uw = uow()
    for o in obj:
        uw.register_deleted(o)
    
def has_key(key):
    return uow().identity_map.has_key(key)

class UOWSmartProperty(attributes.SmartProperty):
    def attribute_registry(self):
        return uow().attributes
    
class UOWListElement(attributes.ListElement):
    def __init__(self, obj, key, data=None, deleteremoved=False):
        attributes.ListElement.__init__(self, obj, key, data=data)
        self.deleteremoved = deleteremoved
    def list_value_changed(self, obj, key, item, listval, isdelete):
        uow().modified_lists.append(self)
        if isdelete and self.deleteremoved:
            uow().register_deleted(item)
    def append(self, item, _mapper_nohistory = False):
        if _mapper_nohistory:
            self.append_nohistory(item)
        else:
            attributes.ListElement.append(self, item)
            
class UOWAttributeManager(attributes.AttributeManager):
    def __init__(self, uow):
        attributes.AttributeManager.__init__(self)
        self.uow = uow
        
    def value_changed(self, obj, key, value):
        if hasattr(obj, '_instance_key'):
            self.uow.register_dirty(obj)
        else:
            self.uow.register_new(obj)

    def create_prop(self, key, uselist, **kwargs):
        return UOWSmartProperty(self).property(key, uselist, **kwargs)

    def create_list(self, obj, key, list_, **kwargs):
        return UOWListElement(obj, key, list_, **kwargs)
        
class UnitOfWork(object):
    def __init__(self, parent = None, is_begun = False):
        self.is_begun = is_begun
        if parent is not None:
            self.identity_map = parent.identity_map
        else:
            self.identity_map = {}
        self.attributes = UOWAttributeManager(self)
        self.new = util.HashSet(ordered = True)
        self.dirty = util.HashSet()
        self.modified_lists = util.HashSet()
        # the delete list is ordered mostly so the unit tests can predict the argument list ordering.
        # TODO: need stronger unit test fixtures....
        self.deleted = util.HashSet(ordered = True)
        self.parent = parent

    def get(self, class_, *id):
        return sqlalchemy.mapper.object_mapper(class_).get(*id)

    def _get(self, key):
        return self.identity_map[key]
        
    def _put(self, key, obj):
        self.identity_map[key] = obj

    def has_key(self, key):
        return self.identity_map.has_key(key)
        
    def _remove_deleted(self, obj):
        if hasattr(obj, "_instance_key"):
            del self.identity_map[obj._instance_key]
        del self.deleted[obj]
        self.attributes.remove(obj)
        
    def update(self, obj):
        """called to add an object to this UnitOfWork as though it were loaded from the DB, but is
        actually coming from somewhere else, like a web session or similar."""
        self._put(obj._instance_key, obj)
        self.register_dirty(obj)
        
    def register_attribute(self, class_, key, uselist, **kwargs):
        self.attributes.register_attribute(class_, key, uselist, **kwargs)

    def register_callable(self, obj, key, func, uselist, **kwargs):
        self.attributes.set_callable(obj, key, func, uselist, **kwargs)
        
    def register_clean(self, obj):
        try:
            del self.dirty[obj]
        except KeyError:
            pass
        try:
            del self.new[obj]
        except KeyError:
            pass
        self._put(obj._instance_key, obj)
        
    def register_new(self, obj):
        self.new.append(obj)
        
    def register_dirty(self, obj):
        self.dirty.append(obj)
            
    def is_dirty(self, obj):
        if not self.dirty.contains(obj):
            return False
        else:
            return True
        
    def register_deleted(self, obj):
        self.deleted.append(obj)  
        mapper = object_mapper(obj)
        # TODO: should the cascading delete dependency thing
        # happen wtihin PropertyLoader.process_dependencies ?
        mapper.register_deleted(obj, self)

    # TODO: tie in register_new/register_dirty with table transaction begins ?
    def begin(self):
        u = UnitOfWork(self, True)
        uow.set(u)
        
    def commit(self, *objects):
        commit_context = UOWTransaction(self)

        if len(objects):
            for obj in objects:
                if self.deleted.contains(obj):
                    commit_context.register_object(obj, isdelete=True)
                elif self.new.contains(obj) or self.dirty.contains(obj):
                    commit_context.register_object(obj)
        else:
            for obj in [n for n in self.new] + [d for d in self.dirty]:
                if self.deleted.contains(obj):
                    continue
                commit_context.register_object(obj)
            for item in self.modified_lists:
                obj = item.obj
                if self.deleted.contains(obj):
                    continue
                commit_context.register_object(obj, listonly = True)
                for o in item.added_items() + item.deleted_items():
                    if self.deleted.contains(o):
                        continue
                    commit_context.register_object(o, listonly=True)
            for obj in self.deleted:
                commit_context.register_object(obj, isdelete=True)
                
        engines = util.HashSet()
        for mapper in commit_context.mappers:
            for e in mapper.engines:
                engines.append(e)
                
        for e in engines:
            e.begin()
        try:
            commit_context.execute()
        except:
            for e in engines:
                e.rollback()
            if self.parent:
                self.rollback()
            raise
        for e in engines:
            e.commit()
            
        commit_context.post_exec()
        self.attributes.commit()
        
        if self.parent:
            uow.set(self.parent)

    def rollback_object(self, obj):
        self.attributes.rollback(obj)

    def rollback(self):
        if not self.is_begun:
            raise "UOW transaction is not begun"
        self.attributes.rollback()
        uow.set(self.parent)
            
class UOWTransaction(object):
    def __init__(self, uow):
        self.uow = uow

        #  unique list of all the mappers we come across
        self.mappers = util.HashSet()
        self.dependencies = {}
        self.tasks = {}
        self.saved_objects = util.HashSet()
        self.saved_lists = util.HashSet()
        self.deleted_objects = util.HashSet()
        self.deleted_lists = util.HashSet()

    def register_object(self, obj, isdelete = False, listonly = False):
        """adds an object to this UOWTransaction to be updated in the database.
        'isdelete' indicates whether the object is to be deleted or saved (update/inserted).
        'listonly', indicates that only this object's dependency relationships should be 
        refreshed/updated to reflect a recent save/upcoming delete operation, but not a full
        save/delete operation on the object itself, unless an additional save/delete registration 
        is entered for the object."""
        mapper = object_mapper(obj)
        self.mappers.append(mapper)
        task = self.get_task_by_mapper(mapper)
        task.append(obj, listonly, isdelete=isdelete)

    def get_task_by_mapper(self, mapper):
        try:
            return self.tasks[mapper]
        except KeyError:
            return self.tasks.setdefault(mapper, UOWTask(mapper))
            
    def register_dependency(self, mapper, dependency):
        self.dependencies[(mapper, dependency)] = True

    def register_processor(self, mapper, isdelete, processor, mapperfrom, isdeletefrom):
        task = self.get_task_by_mapper(mapper)
        targettask = self.get_task_by_mapper(mapperfrom)
        task.dependencies.append((processor, targettask, isdeletefrom))

    def register_saved_object(self, obj):
        self.saved_objects.append(obj)

    def register_saved_list(self, listobj):
        self.saved_lists.append(listobj)

    def register_deleted_list(self, listobj):
        self.deleted_lists.append(listobj)
        
    def register_deleted_object(self, obj):
        self.deleted_objects.append(obj)
        
    def execute(self):
        for task in self.tasks.values():
            task.mapper.register_dependencies(self)

        head = self._sort_dependencies()
        print "Task dump:\n" + head.dump()
        head.execute(self)
            
    def post_exec(self):
        """after an execute/commit is completed, all of the objects and lists that have
        been committed are updated in the parent UnitOfWork object to mark them as clean."""
        for obj in self.saved_objects:
            mapper = object_mapper(obj)
            obj._instance_key = mapper.instance_key(obj)
            self.uow.register_clean(obj)

        for obj in self.saved_lists:
            try:
                del self.uow.modified_lists[obj]
            except KeyError:
                pass

        for obj in self.deleted_objects:
            self.uow._remove_deleted(obj)
        
        for obj in self.deleted_lists:
            try:
                del self.uow.modified_lists[obj]
            except KeyError:
                pass

    def _sort_dependencies(self):
        """creates a hierarchical tree of dependent tasks.  the root node is returned.
        when the root node is executed, it also executes its child tasks recursively."""
        bymapper = {}
        
        def sort_hier(node):
            if node is None:
                return None
            task = bymapper.get(node.item, None)
            if task is not None:
                if node.circular:
                    task.circular = task._sort_circular_dependencies(self)
                    task.iscircular = True
            for child in node.children:
                t = sort_hier(child)
                if t is not None:
                    task.childtasks.append(t)
            return task
            
        mappers = util.HashSet()
        for task in self.tasks.values():
            mappers.append(task.mapper)
            bymapper[task.mapper] = task
    
        head = util.DependencySorter(self.dependencies, mappers).sort()
        task = sort_hier(head)
        return task


class UOWTaskElement(object):
    def __init__(self, obj):
        self.obj = obj
        self.listonly = True
        self.childtask = None
        self.isdelete = False
    def __repr__(self):
        return "UOWTaskElement/%d: %s/%d %s" % (id(self), self.obj.__class__.__name__, id(self.obj), (self.listonly and 'listonly' or (self.isdelete and 'delete' or 'save')) )
        
class UOWTask(object):
    def __init__(self, mapper):
        self.mapper = mapper
        self.objects = util.OrderedDict()
        self.dependencies = []
        self.iscircular = False
        self.circular = None
        self.childtasks = []
        
    def append(self, obj, listonly = False, childtask = None, isdelete = False):
        """appends an object to this task, to be either saved or deleted
        depending on the 'isdelete' attribute of this UOWTask.  'listonly' indicates
        that the object should only be processed as a dependency and not actually saved/deleted.
        if the object already exists with a 'listonly' flag of False, it is kept as is.
        'childtask' is used internally when creating a hierarchical list of self-referential
        tasks, to assign dependent operations at the per-object instead of per-task level."""
        try:
            rec = self.objects[obj]
        except KeyError:
            rec = UOWTaskElement(obj)
            self.objects[obj] = rec
        if not listonly:
            rec.listonly = False
        if childtask:
            rec.childtask = childtask
        if isdelete:
            rec.isdelete = True
        
    def execute(self, trans, isdelete = False):
        """executes this UOWTask.  saves objects to be saved, processes all dependencies
        that have been registered, and deletes objects to be deleted.  If the UOWTask
        has been marked as "circular", performs a circular dependency sort which creates 
        a subtree of UOWTasks which are then executed hierarchically."""
        if self.circular is not None:
            self.circular.execute(trans)
            return
        
        saved_obj_list = self.saved_objects()
        deleted_obj_list = self.deleted_objects()
        self.mapper.save_obj(saved_obj_list, trans)
        for dep in self.dependencies:
            (processor, targettask, isdelete) = dep
            if isdelete:
                continue
            processor.process_dependencies(targettask, targettask.saved_objects(includelistonly=True), trans, delete = False)
        for obj in self.saved_objects(includelistonly=True):
            childtask = self.objects[obj].childtask
            if childtask is not None:
                childtask.execute(trans)
        for dep in self.dependencies:
            (processor, targettask, isdelete) = dep
            if not isdelete:
                continue
            processor.process_dependencies(targettask, targettask.deleted_objects(includelistonly=True), trans, delete = True)
        for child in self.childtasks:
            child.execute(trans)
        for obj in self.deleted_objects(includelistonly=True):
            childtask = self.objects[obj].childtask
            if childtask is not None:
                childtask.execute(trans)
        self.mapper.delete_obj(deleted_obj_list, trans)

    def saved_objects(self, includelistonly=False):
        if not includelistonly:
            return [o for o, rec in self.objects.iteritems() if not rec.listonly and not rec.isdelete]
        else:
            return [o for o, rec in self.objects.iteritems() if not rec.isdelete]
    def deleted_objects(self, includelistonly=False):
        if not includelistonly:
            return [o for o, rec in self.objects.iteritems() if not rec.listonly and rec.isdelete]
        else:
            return [o for o, rec in self.objects.iteritems() if rec.isdelete]
            
    def _sort_circular_dependencies(self, trans):
        """for a single task, creates a hierarchical tree of "subtasks" which associate
        specific dependency actions with individual objects.  This is used for a
        "circular" task, or a task where elements
        of its object list contain dependencies on each other."""
        
        allobjects = self.objects.keys()
        tuples = []
        
        objecttotask = {}
        def get_task(obj):
            try:
                return objecttotask[obj]
            except KeyError:
                t = UOWTask(self.mapper)
                objecttotask[obj] = t
                return t

        dependencies = {}
        def get_dependency_task(obj, processor, isdelete):
            try:
                dp = dependencies[obj]
            except KeyError:
                dp = {}
                dependencies[obj] = dp
            try:
                l = dp[(processor, isdelete)]
            except KeyError:
                l = UOWTask(None)
                dp[(processor, isdelete)] = l
            return l
            
        for obj in allobjects:
            parenttask = get_task(obj)
            # TODO: we are doing this dependency sort which uses a lot of the 
            # concepts in mapper.PropertyLoader's more coarse-grained version.
            # should consolidate the concept of "childlist/added/deleted/unchanged" "left/right"
            # in one place
            for dep in self.dependencies:
                (processor, targettask, isdelete) = dep
                childlist = processor.get_object_dependencies(obj, trans, passive = True)
                #childlist = childlist.unchanged_items() + childlist.deleted_items() + childlist.added_items()
                if isdelete:
                    childlist = childlist.unchanged_items() + childlist.deleted_items()
                else:
                    #childlist = childlist.added_items() + childlist.deleted_items()
                    childlist = childlist.added_items()
                for o in childlist:
                    if not self.objects.has_key(o):
                        continue
                    whosdep = processor.whose_dependent_on_who(obj, o, trans)
                    if whosdep is not None:
                        tuples.append(whosdep)
                        if whosdep[0] is obj:
                            get_dependency_task(whosdep[0], processor, isdelete).append(whosdep[0], isdelete=isdelete)
                        else:
                            get_dependency_task(whosdep[0], processor, isdelete).append(whosdep[1], isdelete=isdelete)
        
        head = util.DependencySorter(tuples, allobjects).sort()
        if head is None:
            return None
        
        def make_task_tree(node, parenttask):
            parenttask.append(node.item, self.objects[node.item].listonly, objecttotask[node.item], isdelete=self.objects[node.item].isdelete)
            if dependencies.has_key(node.item):
                for tup, deptask in dependencies[node.item].iteritems():
                    (processor, isdelete) = tup
                    parenttask.dependencies.append((processor, deptask, isdelete))
            t = get_task(node.item)
            for n in node.children:
                t2 = make_task_tree(n, t)
            return t
            
        t = UOWTask(self.mapper)
        make_task_tree(head, t)
        return t

    def dump(self, depth=0):
        indent = "  " * depth
        s = "\n" + indent + repr(self)
        s += "\n" + indent + "  Save Elements:"
        for o in self.objects.values():
            if o.listonly or o.isdelete:
                continue
            s += "\n     " + indent + repr(o)
            if o.childtask is not None:
                s += "\n" + indent + "  Circular Child Task:"
                s += "\n" + o.childtask.dump(depth + 2)
        s += "\n" + indent + "  Dependencies:"
        for dt in self.dependencies:
            s += "\n    " + indent + repr(dt[0].key) + "/" + (dt[2] and 'items to be deleted' or 'saved items')
            if dt[2]:
                val = [t for t in dt[1].objects.values() if t.isdelete]
            else:
                val = [t for t in dt[1].objects.values() if not t.isdelete]
            for o in val:
                s += "\n      " + indent + repr(o)
        s += "\n" + indent + "  Child Tasks:"
        for t in self.childtasks:
            s += t.dump(depth + 2)
        s += "\n" + indent + "  Circular Task:"
        if self.circular is not None:
            s += self.circular.dump(depth + 2)
        else:
            s += "None"
        s += "\n" + indent + "  Delete Elements:"
        for o in self.objects.values():
            if o.listonly or not o.isdelete:
                continue
            s += "\n     " + indent + repr(o)
            if o.childtask is not None:
                s += "\n" + indent + "  Circular Child Task:"
                s += "\n" + o.childtask.dump(depth + 2)
        return s

    def __repr__(self):
        return ("UOWTask/%d Table: '%s'" % (id(self), self.mapper and self.mapper.primarytable.name or '(none)'))
        

                    
uow = util.ScopedRegistry(lambda: UnitOfWork(), "thread")


def object_mapper(obj):
    import sqlalchemy.mapper
    return sqlalchemy.mapper.object_mapper(obj)
