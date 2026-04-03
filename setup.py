from setuptools import setup

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="py-wechat-ilink",
    version="0.1.0",
    description="通过ClawBot的ilink接口实现WX SDK",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="luojiaaoo",
    author_email="675925864@qq.com",
    url="https://github.com/luojiaaoo/py-wechat-ilink",
    project_urls={
        "Bug Tracker": "https://github.com/luojiaaoo/py-wechat-ilink/issues",
    },
    packages=["py_wechat_ilink"],
    python_requires=">=3.9",
    install_requires=[
        "pycryptodome>=3.23.0",
    ],
)