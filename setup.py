from setuptools import Extension, setup


lapq_extension = Extension(
    "lapq._lapq",
    sources=[
        "python/lapq/_lapq.c",
        "src/lapq.c",
        "src/skiplist.c",
        "src/handles.c",
        "src/stats.c",
    ],
    include_dirs=["include", "src"],
    extra_compile_args=["-std=c99"],
)


setup(ext_modules=[lapq_extension])
