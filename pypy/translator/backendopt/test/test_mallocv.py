import py
from pypy.translator.backendopt.mallocv import MallocVirtualizer
from pypy.translator.backendopt.inline import inline_function
from pypy.translator.backendopt.all import backend_optimizations
from pypy.translator.translator import TranslationContext, graphof
from pypy.translator import simplify
from pypy.objspace.flow.model import checkgraph, flatten, Block, mkentrymap
from pypy.objspace.flow.model import summary
from pypy.rpython.llinterp import LLInterpreter
from pypy.rpython.lltypesystem import lltype, llmemory
from pypy.rpython.ootypesystem import ootype
from pypy.rlib import objectmodel
from pypy.conftest import option

class BaseMallocRemovalTest(object):
    type_system = None
    MallocRemover = None

    def _skip_oo(self, msg):
        if self.type_system == 'ootype':
            py.test.skip(msg)

    def check_malloc_removed(cls, graph):
        #remover = cls.MallocRemover()
        checkgraph(graph)
        count = 0
        for node in flatten(graph):
            if isinstance(node, Block):
                for op in node.operations:
                    if op.opname == 'malloc': #cls.MallocRemover.MALLOC_OP:
                        S = op.args[0].value
                        #if not remover.union_wrapper(S):   # union wrappers are fine
                        count += 1
        assert count == 0   # number of mallocs left
    check_malloc_removed = classmethod(check_malloc_removed)

    def check(self, fn, signature, args, expected_result, must_be_removed=True):
        t = TranslationContext()
        t.buildannotator().build_types(fn, signature)
        t.buildrtyper(type_system=self.type_system).specialize()
        graph = graphof(t, fn)
        if option.view:
            t.view()
        # to detect missing keepalives and broken intermediate graphs,
        # we do the loop ourselves instead of calling remove_simple_mallocs()
        maxiter = 100
        mallocv = MallocVirtualizer(t.graphs, verbose=True)
        while True:
            progress = mallocv.remove_mallocs_once()
            #simplify.transform_dead_op_vars_in_blocks(list(graph.iterblocks()))
            if progress and option.view:
                t.view()
            if expected_result is not Ellipsis:
                interp = LLInterpreter(t.rtyper)
                res = interp.eval_graph(graph, args)
                assert res == expected_result
            if not progress:
                break
        if must_be_removed:
            self.check_malloc_removed(graph)
        return graph

    def test_fn1(self):
        def fn1(x, y):
            if x > 0:
                t = x+y, x-y
            else:
                t = x-y, x+y
            s, d = t
            return s*d
        graph = self.check(fn1, [int, int], [15, 10], 125)
        insns = summary(graph)
        assert insns['int_mul'] == 1

    def test_aliasing1(self):
        A = lltype.GcStruct('A', ('x', lltype.Signed))
        def fn1(x):
            a1 = lltype.malloc(A)
            a1.x = 123
            if x > 0:
                a2 = a1
            else:
                a2 = lltype.malloc(A)
                a2.x = 456
            a1.x += 1
            return a2.x
        self.check(fn1, [int], [3], 124)
        self.check(fn1, [int], [-3], 456)

    def test_direct_call(self):
        def g(t):
            a, b = t
            return a * b
        def f(x):
            return g((x+1, x-1))
        graph = self.check(f, [int], [10], 99)

    def test_direct_call_mutable_simple(self):
        A = lltype.GcStruct('A', ('x', lltype.Signed))
        def g(a):
            a.x += 1
        def f(x):
            a = lltype.malloc(A)
            a.x = x
            g(a)
            return a.x
        graph = self.check(f, [int], [41], 42)
        insns = summary(graph)
        assert insns.get('direct_call', 0) == 0     # no more call, inlined

    def test_direct_call_mutable_retval(self):
        A = lltype.GcStruct('A', ('x', lltype.Signed))
        def g(a):
            a.x += 1
            return a.x * 100
        def f(x):
            a = lltype.malloc(A)
            a.x = x
            y = g(a)
            return a.x + y
        graph = self.check(f, [int], [41], 4242)
        insns = summary(graph)
        assert insns.get('direct_call', 0) == 0     # no more call, inlined

    def test_direct_call_mutable_ret_virtual(self):
        A = lltype.GcStruct('A', ('x', lltype.Signed))
        def g(a):
            a.x += 1
            return a
        def f(x):
            a = lltype.malloc(A)
            a.x = x
            b = g(a)
            return a.x + b.x
        graph = self.check(f, [int], [41], 84)
        insns = summary(graph)
        assert insns.get('direct_call', 0) == 0     # no more call, inlined

    def test_direct_call_mutable_lastref(self):
        A = lltype.GcStruct('A', ('x', lltype.Signed))
        def g(a):
            a.x *= 10
            return a.x
        def f(x):
            a = lltype.malloc(A)
            a.x = x
            y = g(a)
            return x - y
        graph = self.check(f, [int], [5], -45)
        insns = summary(graph)
        assert insns.get('direct_call', 0) == 1     # not inlined

    def test_fn2(self):
        py.test.skip("redo me")
        class T:
            pass
        def fn2(x, y):
            t = T()
            t.x = x
            t.y = y
            if x > 0:
                return t.x + t.y
            else:
                return t.x - t.y
        self.check(fn2, [int, int], [-6, 7], -13)

    def test_fn3(self):
        py.test.skip("redo me")
        def fn3(x):
            a, ((b, c), d, e) = x+1, ((x+2, x+3), x+4, x+5)
            return a+b+c+d+e
        self.check(fn3, [int], [10], 65)

    def test_fn4(self):
        py.test.skip("redo me")
        class A:
            pass
        class B(A):
            pass
        def fn4(i):
            a = A()
            b = B()
            a.b = b
            b.i = i
            return a.b.i
        self.check(fn4, [int], [42], 42)

    def test_fn5(self):
        py.test.skip("redo me")
        class A:
            attr = 666
        class B(A):
            attr = 42
        def fn5():
            b = B()
            return b.attr
        self.check(fn5, [], [], 42)

    def test_aliasing(self):
        py.test.skip("redo me")
        class A:
            pass
        def fn6(n):
            a1 = A()
            a1.x = 5
            a2 = A()
            a2.x = 6
            if n > 0:
                a = a1
            else:
                a = a2
            a.x = 12
            return a1.x
        self.check(fn6, [int], [1], 12, must_be_removed=False)



class TestLLTypeMallocRemoval(BaseMallocRemovalTest):
    type_system = 'lltype'
    #MallocRemover = LLTypeMallocRemover

    def test_with_keepalive(self):
        py.test.skip("redo me")
        from pypy.rlib.objectmodel import keepalive_until_here
        def fn1(x, y):
            if x > 0:
                t = x+y, x-y
            else:
                t = x-y, x+y
            s, d = t
            keepalive_until_here(t)
            return s*d
        self.check(fn1, [int, int], [15, 10], 125)

    def test_dont_remove_with__del__(self):
        py.test.skip("redo me")
        import os
        delcalls = [0]
        class A(object):
            nextid = 0
            def __init__(self):
                self.id = self.nextid
                self.nextid += 1

            def __del__(self):
                delcalls[0] += 1
                os.write(1, "__del__\n")

        def f(x=int):
            a = A()
            i = 0
            while i < x:
                a = A()
                os.write(1, str(delcalls[0]) + "\n")
                i += 1
            return 1
        t = TranslationContext()
        t.buildannotator().build_types(f, [int])
        t.buildrtyper().specialize()
        graph = graphof(t, f)
        backend_optimizations(t)
        op = graph.startblock.exits[0].target.exits[1].target.operations[0]
        assert op.opname == "malloc"

    def test_add_keepalives(self):
        py.test.skip("redo me")
        class A:
            pass
        SMALL = lltype.Struct('SMALL', ('x', lltype.Signed))
        BIG = lltype.GcStruct('BIG', ('z', lltype.Signed), ('s', SMALL))
        def fn7(i):
            big = lltype.malloc(BIG)
            a = A()
            a.big = big
            a.small = big.s
            a.small.x = 0
            while i > 0:
                a.small.x += i
                i -= 1
            return a.small.x
        self.check(fn7, [int], [10], 55, must_be_removed=False)

    def test_getsubstruct(self):
        py.test.skip("redo me")
        py.test.skip("fails because of the interior structure changes")
        SMALL = lltype.Struct('SMALL', ('x', lltype.Signed))
        BIG = lltype.GcStruct('BIG', ('z', lltype.Signed), ('s', SMALL))

        def fn(n1, n2):
            b = lltype.malloc(BIG)
            b.z = n1
            b.s.x = n2
            return b.z - b.s.x

        self.check(fn, [int, int], [100, 58], 42)

    def test_fixedsizearray(self):
        py.test.skip("redo me")
        py.test.skip("fails because of the interior structure changes")
        A = lltype.FixedSizeArray(lltype.Signed, 3)
        S = lltype.GcStruct('S', ('a', A))

        def fn(n1, n2):
            s = lltype.malloc(S)
            a = s.a
            a[0] = n1
            a[2] = n2
            return a[0]-a[2]

        self.check(fn, [int, int], [100, 42], 58)

    def test_wrapper_cannot_be_removed(self):
        py.test.skip("redo me")
        SMALL = lltype.OpaqueType('SMALL')
        BIG = lltype.GcStruct('BIG', ('z', lltype.Signed), ('s', SMALL))

        def g(small):
            return -1
        def fn():
            b = lltype.malloc(BIG)
            g(b.s)

        self.check(fn, [], [], None, must_be_removed=False)

    def test_direct_fieldptr(self):
        py.test.skip("redo me")
        S = lltype.GcStruct('S', ('x', lltype.Signed))

        def fn():
            s = lltype.malloc(S)
            s.x = 11
            p = lltype.direct_fieldptr(s, 'x')
            return p[0]

        self.check(fn, [], [], 11)

    def test_direct_fieldptr_2(self):
        py.test.skip("redo me")
        T = lltype.GcStruct('T', ('z', lltype.Signed))
        S = lltype.GcStruct('S', ('t', T),
                                 ('x', lltype.Signed),
                                 ('y', lltype.Signed))
        def fn():
            s = lltype.malloc(S)
            s.x = 10
            s.t.z = 1
            px = lltype.direct_fieldptr(s, 'x')
            py = lltype.direct_fieldptr(s, 'y')
            pz = lltype.direct_fieldptr(s.t, 'z')
            py[0] = 31
            return px[0] + s.y + pz[0]

        self.check(fn, [], [], 42)

    def test_getarraysubstruct(self):
        py.test.skip("redo me")
        py.test.skip("fails because of the interior structure changes")
        U = lltype.Struct('U', ('n', lltype.Signed))
        for length in [1, 2]:
            S = lltype.GcStruct('S', ('a', lltype.FixedSizeArray(U, length)))
            for index in range(length):

                def fn():
                    s = lltype.malloc(S)
                    s.a[index].n = 12
                    return s.a[index].n
                self.check(fn, [], [], 12)

    def test_ptr_nonzero(self):
        py.test.skip("redo me")
        S = lltype.GcStruct('S')
        def fn():
            s = lltype.malloc(S)
            return bool(s)
        self.check(fn, [], [], True)

    def test_substruct_not_accessed(self):
        py.test.skip("redo me")
        SMALL = lltype.Struct('SMALL', ('x', lltype.Signed))
        BIG = lltype.GcStruct('BIG', ('z', lltype.Signed), ('s', SMALL))
        def fn():
            x = lltype.malloc(BIG)
            while x.z < 10:    # makes several blocks
                x.z += 3
            return x.z
        self.check(fn, [], [], 12)

    def test_union(self):
        py.test.skip("redo me")
        py.test.skip("fails because of the interior structure changes")
        UNION = lltype.Struct('UNION', ('a', lltype.Signed), ('b', lltype.Signed),
                              hints = {'union': True})
        BIG = lltype.GcStruct('BIG', ('u1', UNION), ('u2', UNION))
        def fn():
            x = lltype.malloc(BIG)
            x.u1.a = 3
            x.u2.b = 6
            return x.u1.b * x.u2.a
        self.check(fn, [], [], Ellipsis)

    def test_keep_all_keepalives(self):
        py.test.skip("redo me")
        SIZE = llmemory.sizeof(lltype.Signed)
        PARRAY = lltype.Ptr(lltype.FixedSizeArray(lltype.Signed, 1))
        class A:
            def __init__(self):
                self.addr = llmemory.raw_malloc(SIZE)
            def __del__(self):
                llmemory.raw_free(self.addr)
        class B:
            pass
        def myfunc():
            b = B()
            b.keep = A()
            b.data = llmemory.cast_adr_to_ptr(b.keep.addr, PARRAY)
            b.data[0] = 42
            ptr = b.data
            # normally 'b' could go away as early as here, which would free
            # the memory held by the instance of A in b.keep...
            res = ptr[0]
            # ...so we explicitly keep 'b' alive until here
            objectmodel.keepalive_until_here(b)
            return res
        graph = self.check(myfunc, [], [], 42,
                           must_be_removed=False)    # 'A' instance left

        # there is a getarrayitem near the end of the graph of myfunc.
        # However, the memory it accesses must still be protected by the
        # following keepalive, even after malloc removal
        entrymap = mkentrymap(graph)
        [link] = entrymap[graph.returnblock]
        assert link.prevblock.operations[-1].opname == 'keepalive'

    def test_nested_struct(self):
        py.test.skip("redo me")
        S = lltype.GcStruct("S", ('x', lltype.Signed))
        T = lltype.GcStruct("T", ('s', S))
        def f(x):
            t = lltype.malloc(T)
            s = t.s
            if x:
                s.x = x
            return t.s.x + s.x
        graph = self.check(f, [int], [42], 2 * 42)

    def test_interior_ptr(self):
        py.test.skip("redo me")
        py.test.skip("fails")
        S = lltype.Struct("S", ('x', lltype.Signed))
        T = lltype.GcStruct("T", ('s', S))
        def f(x):
            t = lltype.malloc(T)
            t.s.x = x
            return t.s.x
        graph = self.check(f, [int], [42], 42)

    def test_interior_ptr_with_index(self):
        py.test.skip("redo me")
        S = lltype.Struct("S", ('x', lltype.Signed))
        T = lltype.GcArray(S)
        def f(x):
            t = lltype.malloc(T, 1)
            t[0].x = x
            return t[0].x
        graph = self.check(f, [int], [42], 42)

    def test_interior_ptr_with_field_and_index(self):
        py.test.skip("redo me")
        S = lltype.Struct("S", ('x', lltype.Signed))
        T = lltype.GcStruct("T", ('items', lltype.Array(S)))
        def f(x):
            t = lltype.malloc(T, 1)
            t.items[0].x = x
            return t.items[0].x
        graph = self.check(f, [int], [42], 42)

    def test_interior_ptr_with_index_and_field(self):
        py.test.skip("redo me")
        S = lltype.Struct("S", ('x', lltype.Signed))
        T = lltype.Struct("T", ('s', S))
        U = lltype.GcArray(T)
        def f(x):
            u = lltype.malloc(U, 1)
            u[0].s.x = x
            return u[0].s.x
        graph = self.check(f, [int], [42], 42)


class DISABLED_TestOOTypeMallocRemoval(BaseMallocRemovalTest):
    type_system = 'ootype'
    #MallocRemover = OOTypeMallocRemover

    def test_oononnull(self):
        FOO = ootype.Instance('Foo', ootype.ROOT)
        def fn():
            s = ootype.new(FOO)
            return bool(s)
        self.check(fn, [], [], True)

    def test_classattr_as_defaults(self):
        class Bar:
            foo = 41
        
        def fn():
            x = Bar()
            x.foo += 1
            return x.foo
        self.check(fn, [], [], 42)

    def test_fn5(self):
        # don't test this in ootype because the class attribute access
        # is turned into an oosend which prevents malloc removal to
        # work unless we inline first. See test_classattr in
        # test_inline.py
        pass
