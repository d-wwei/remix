from setuptools import find_packages, setup


setup(
    name="remix",
    version="0.1.0",
    description="Artifact remix system that integrates Skill-SE-Kit",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
)
