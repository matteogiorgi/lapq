from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext


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
)


class LapqBuildExt(build_ext):
    def build_extensions(self):
        if self.compiler.compiler_type != "msvc":
            for extension in self.extensions:
                extension.extra_compile_args = [*extension.extra_compile_args, "-std=c99"]
        super().build_extensions()


setup(ext_modules=[lapq_extension], cmdclass={"build_ext": LapqBuildExt})
