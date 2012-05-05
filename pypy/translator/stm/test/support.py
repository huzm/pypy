"""CompiledSTMTests, a support class for translated tests with STM"""

from pypy.translator.c.test.test_standalone import StandaloneTests


class CompiledSTMTests(StandaloneTests):
    gc = "stmgc"

    def compile(self, entry_point, **kwds):
        from pypy.config.pypyoption import get_pypy_config
        self.config = get_pypy_config(translating=True)
        self.config.translation.stm = True
        self.config.translation.gc = self.gc
        #
        # Prevent the RaiseAnalyzer from just emitting "WARNING: Unknown
        # operation".  We want instead it to crash.
        from pypy.translator.backendopt.canraise import RaiseAnalyzer
        RaiseAnalyzer.fail_on_unknown_operation = True
        try:
            res = StandaloneTests.compile(self, entry_point, debug=True,
                                          **kwds)
        finally:
            RaiseAnalyzer.fail_on_unknown_operation = False
        return res