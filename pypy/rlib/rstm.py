import threading
from pypy.rlib.objectmodel import specialize, we_are_translated
from pypy.rlib.objectmodel import keepalive_until_here
from pypy.rlib.debug import ll_assert
from pypy.rpython.lltypesystem import lltype, llmemory, rffi, rclass
from pypy.rpython.lltypesystem.lloperation import llop
from pypy.rpython.annlowlevel import (cast_base_ptr_to_instance,
                                      cast_instance_to_base_ptr,
                                      llhelper)
from pypy.translator.stm.stmgcintf import StmOperations

_global_lock = threading.RLock()

@specialize.memo()
def _get_stm_callback(func, argcls):
    def _stm_callback(llarg, retry_counter):
        llop.stm_start_transaction(lltype.Void)
        if we_are_translated():
            llarg = rffi.cast(rclass.OBJECTPTR, llarg)
            arg = cast_base_ptr_to_instance(argcls, llarg)
        else:
            arg = lltype.TLS.stm_callback_arg
        try:
            res = func(arg, retry_counter)
            ll_assert(res is None, "stm_callback should return None")
        finally:
            llop.stm_commit_transaction(lltype.Void)
        return lltype.nullptr(rffi.VOIDP.TO)
    return _stm_callback

@specialize.arg(0, 1)
def perform_transaction(func, argcls, arg):
    ll_assert(arg is None or isinstance(arg, argcls),
              "perform_transaction: wrong class")
    if we_are_translated():
        llarg = cast_instance_to_base_ptr(arg)
        llarg = rffi.cast(rffi.VOIDP, llarg)
        adr_of_top = llop.gc_adr_of_root_stack_top(llmemory.Address)
    else:
        # only for tests: we want (1) to test the calls to the C library,
        # but also (2) to work with multiple Python threads, so we acquire
        # and release some custom GIL here --- even though it doesn't make
        # sense from an STM point of view :-/
        _global_lock.acquire()
        lltype.TLS.stm_callback_arg = arg
        llarg = lltype.nullptr(rffi.VOIDP.TO)
        adr_of_top = llmemory.NULL
    #
    callback = _get_stm_callback(func, argcls)
    llcallback = llhelper(StmOperations.CALLBACK_TX, callback)
    StmOperations.perform_transaction(llcallback, llarg, adr_of_top)
    keepalive_until_here(arg)
    if not we_are_translated():
        _global_lock.release()

def enter_transactional_mode():
    llop.stm_enter_transactional_mode(lltype.Void)

def leave_transactional_mode():
    llop.stm_leave_transactional_mode(lltype.Void)

def descriptor_init():
    if not we_are_translated(): _global_lock.acquire()
    llop.stm_descriptor_init(lltype.Void)
    if not we_are_translated(): _global_lock.release()

def descriptor_done():
    if not we_are_translated(): _global_lock.acquire()
    llop.stm_descriptor_done(lltype.Void)
    if not we_are_translated(): _global_lock.release()

def _debug_get_state():
    if not we_are_translated(): _global_lock.acquire()
    res = StmOperations._debug_get_state()
    if not we_are_translated(): _global_lock.release()
    return res

def thread_id():
    return StmOperations.thread_id()