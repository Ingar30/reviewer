"""Bundle canonical CLI resources at build time; never maintain runtime copies."""
from pathlib import Path
import sys

from setuptools import setup
from setuptools.command.build_py import build_py

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
from build_cli_package import cli_payload


class BuildWithRuntime(build_py):
    def run(self):
        super().run()
        destination = Path(self.build_lib) / "economics_paper_reviewer" / "runtime"
        for relative, content in cli_payload(Path(__file__).resolve().parent).items():
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)


setup(cmdclass={"build_py": BuildWithRuntime})
