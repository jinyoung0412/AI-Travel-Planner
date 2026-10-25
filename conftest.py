"""Install offline isolation before collecting any project test modules."""
from scripts.offline_environment import install

install()

pytest_plugins = ['scripts.offline_pytest']
