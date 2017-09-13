import os

from manager_rest.config import instance

from . import logger, acfy
from .commands import agents, cluster, context, ldap, ssl


@acfy.group(name='acfy')
@acfy.options.verbose(expose_value=True)
@acfy.options.version
def _acfy(verbose):
    logger.set_global_verbosity_level(verbose)
    # TODO figure out a better way to pass this config path
    os.environ['MANAGER_REST_CONFIG_PATH'] = '/opt/manager/cloudify-rest.conf'
    try:
        instance.load_configuration()
    except IOError:
        pass


def _register_commands():
    _acfy.add_command(agents.agents)
    _acfy.add_command(cluster.cluster)
    _acfy.add_command(context.context)
    _acfy.add_command(ldap.ldap)
    _acfy.add_command(ssl.ssl)

_register_commands()
logger.configure_loggers()


if __name__ == '__main__':
    _acfy()