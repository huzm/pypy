import autopath
from pypy.tool import test
from pypy.tool.udir import udir
from pypy.translator.test.buildcl import make_cl_func

class GenCLTestCase(test.IntTestCase):

    def setUp(self):
        import os
        cl = os.getenv("PYPY_CL")
        if cl:
            self.cl = cl
        else:
            raise test.TestSkip
    def cl_func(self, func):
        return make_cl_func(func, self.cl, udir)

    #___________________________________
    def if_then_else(cond, x, y):
        if cond:
            return x
        else:
            return y
    def test_if_bool(self):
        cl_if = self.cl_func(self.if_then_else)
        self.assertEquals(cl_if(True, 50, 100), 50)
        self.assertEquals(cl_if(False, 50, 100), 100)
    def test_if_int(self):
        cl_if = self.cl_func(self.if_then_else)
        self.assertEquals(cl_if(0, 50, 100), 100)
        self.assertEquals(cl_if(1, 50, 100), 50)

    #___________________________________
    def my_gcd(a, b):
        r = a % b
        while r:
            a = b
            b = r
            r = a % b
        return b
    def test_gcd(self):
        cl_gcd = self.cl_func(self.my_gcd)
        self.assertEquals(cl_gcd(96, 64), 32)

    #___________________________________
    def is_perfect_number(n):
        div = 1
        sum = 0
        while div < n:
            if n % div == 0:
                sum += div
            div += 1
        return n == sum
    def test_is_perfect(self): # pun intended
        cl_perfect = self.cl_func(self.is_perfect_number)
        self.assertEquals(cl_perfect(24), False)
        self.assertEquals(cl_perfect(28), True)

    #___________________________________
    def my_bool(x):
        return not not x
    def test_bool(self):
        cl_bool = self.cl_func(self.my_bool)
        self.assertEquals(cl_bool(0), False)
        self.assertEquals(cl_bool(42), True)
        self.assertEquals(cl_bool(True), True)

    #___________________________________
    def two_plus_two():
        array = [0] * 3
        array[0] = 2
        array[1] = 2
        array[2] = array[0] + array[1]
        return array[2]
    def test_array(self):
        cl_four = self.cl_func(self.two_plus_two)
        self.assertEquals(cl_four(), 4)

    #___________________________________
    def sieve_of_eratosthenes():
        # This one is from:
        # The Great Computer Language Shootout
        flags = [True] * (8192+1)
        count = 0
        i = 2
        while i <= 8192:
            if flags[i]:
                k = i + i
                while k <= 8192:
                    flags[k] = False
                    k = k + i
                count = count + 1
            i = i + 1
        return count
    def test_sieve(self):
        cl_sieve = self.cl_func(self.sieve_of_eratosthenes)
        self.assertEquals(cl_sieve(), 1028)

if __name__ == '__main__':
    test.main()
