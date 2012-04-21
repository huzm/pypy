import py
from pypy.translator.stm.test.support import CompiledSTMTests
from pypy.translator.stm.test import targetdemo


class TestSTMTranslated(CompiledSTMTests):

    def test_hello_world(self):
        t, cbuilder = self.compile(targetdemo.entry_point)
        data, dataerr = cbuilder.cmdexec('4 5000', err=True)
        assert 'done sleeping.' in dataerr
        assert 'check ok!' in data

    def test_bug1(self):
        from pypy.rlib import rstm, rgc
        from pypy.module.transaction import threadintf
        #
        class State:
            pass
        state = State()
        #
        def _foo(_, retry_counter):
            rgc.collect(0)
        def _run_thread():
            rstm.descriptor_init()
            rstm.perform_transaction(_foo, X, None)
            threadintf.release(state.ll_unfinished_lock)
            rstm.descriptor_done()
        #
        class X:
            def __init__(self, count):
                self.count = count
        def g():
            x = X(1000)
            rstm.enter_transactional_mode()
            threadintf.start_new_thread(_run_thread)
            threadintf.acquire(state.ll_unfinished_lock, True)
            rstm.leave_transactional_mode()
            return x
        def entry_point(argv):
            state.ll_unfinished_lock = threadintf.allocate_lock()
            x = X(len(argv))
            y = g()
            print '<', x.count, y.count, '>'
            return 0
        #
        t, cbuilder = self.compile(entry_point, backendopt=True)
        data = cbuilder.cmdexec('a b c d')
        assert '< 5 1000 >' in data, "got: %r" % (data,)