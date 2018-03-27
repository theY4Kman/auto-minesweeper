def apply_method_filter(iterable, **filters):
    """Filter iterables by return values of methods specified by **filters

    >>> class Base:
    ...     def __repr__(self): return self.__class__.__name__
    ...
    >>> class Foo(Base):
    ...     def is_foo(self): return True
    ...     def is_bar(self): return False
    ...
    >>> class Bar(Base):
    ...     def is_foo(self): return False
    ...     def is_bar(self): return True
    ...
    >>> iterable = [Foo(), Foo(), Bar()]
    >>> apply_method_filter(iterable, is_foo=True)
    [Foo, Foo]
    >>> apply_method_filter(iterable, is_bar=False)
    [Foo, Foo]
    >>> apply_method_filter(iterable, is_bar=True)
    [Bar]
    >>> apply_method_filter(iterable, is_foo=True, is_bar=True)
    []

    """
    def is_valid(o):
        for method, expected in filters.items():
            if getattr(o, method)() != expected:
                return False
        else:
            return True
    return [o for o in iterable if is_valid(o)]
