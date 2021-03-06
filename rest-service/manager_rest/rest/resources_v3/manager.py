#########
# Copyright (c) 2016 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#  * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  * See the License for the specific language governing permissions and
#  * limitations under the License.

from flask import current_app, request

from manager_rest import config
from manager_rest.security import SecuredResource
from manager_rest.security.authorization import authorize
from manager_rest.storage import models, get_storage_manager
from manager_rest.storage.models_states import AvailabilityState
from manager_rest.manager_exceptions import (BadParametersError,
                                             MethodNotAllowedError,
                                             UnauthorizedError)
from manager_rest.constants import (FILE_SERVER_BLUEPRINTS_FOLDER,
                                    FILE_SERVER_UPLOADED_BLUEPRINTS_FOLDER,
                                    FILE_SERVER_DEPLOYMENTS_FOLDER)

from .. import rest_decorators, rest_utils
from ...security.authentication import authenticator
from ..responses_v3 import BaseResponse, ResourceID

try:
    from cloudify_premium import LdapResponse
except ImportError:
    LdapResponse = BaseResponse


class FileServerAuth(SecuredResource):
    @staticmethod
    def _verify_tenant(uri):
        tenanted_resources = [
            FILE_SERVER_BLUEPRINTS_FOLDER,
            FILE_SERVER_UPLOADED_BLUEPRINTS_FOLDER,
            FILE_SERVER_DEPLOYMENTS_FOLDER
        ]
        tenanted_resources = [r.strip('/') for r in tenanted_resources]
        uri = uri.strip('/')

        # if it's global blueprint - no need or tenant verification
        if FileServerAuth._is_global_blueprint(uri):
            return

        # verifying that the only tenant that can be accessed is the one in
        # the header
        for resource in tenanted_resources:
            if uri.startswith(resource):
                uri = uri.replace(resource, '', 1).strip('/')
                uri_tenant, _ = uri.split('/', 1)
                authenticator.authenticate(request)

                @authorize('file_server_auth', uri_tenant)
                def _authorize():
                    pass

                _authorize()

    @staticmethod
    def _is_global_blueprint(uri):
        try:
            resource, tenant, resource_id, _ = uri.split('/')
        except Exception:
            # in case of different format of file server uri
            return False
        if resource not in [FILE_SERVER_UPLOADED_BLUEPRINTS_FOLDER,
                            FILE_SERVER_BLUEPRINTS_FOLDER]:
            return False
        blueprint = get_storage_manager().get(models.Blueprint,
                                              resource_id)
        return blueprint.resource_availability == AvailabilityState.GLOBAL

    @rest_decorators.exceptions_handled
    @rest_decorators.marshal_with(ResourceID)
    def get(self, **_):
        """
        Verify that the user is allowed to access requested resource.

        The user cannot access tenants except the one in the request's header.
        """
        uri = request.headers.get('X-Original-Uri')
        self._verify_tenant(uri)

        # verified successfully
        return {}


class LdapAuthentication(SecuredResource):
    @rest_decorators.exceptions_handled
    @authorize('ldap_set')
    @rest_decorators.marshal_with(LdapResponse)
    def post(self):
        ldap_config = self._validate_set_ldap_request()

        from cloudify_premium.authentication.ldap_authentication \
            import LdapAuthentication

        # update current configuration
        for key, value in ldap_config.iteritems():
            setattr(config.instance, key, value)

        # assert LDAP configuration is valid.
        auth = LdapAuthentication()
        auth.configure_ldap()
        try:
            auth.authenticate_user(ldap_config.get('ldap_username'),
                                   ldap_config.get('ldap_password'))
        except UnauthorizedError:
            # reload previous configuration.
            config.instance.load_configuration()
            raise BadParametersError(
                'Failed setting LDAP authenticator: Invalid parameters '
                'provided.')

        config.reset(config.instance, write=True)

        # Restart the rest service so that each the LDAP configuration
        # be loaded to all flask processes.
        rest_utils.set_restart_task()

        ldap_config.pop('ldap_password')
        return ldap_config

    @staticmethod
    def _only_admin_in_manager():
        """
        True if no users other than the admin user exists.
        :return:
        """
        users = get_storage_manager().list(models.User)
        return len(users) == 1

    def _validate_set_ldap_request(self):
        if not self._only_admin_in_manager():
            raise MethodNotAllowedError('LDAP Configuration may be set only on'
                                        ' a clean manager.')
        if not current_app.premium_enabled:
            raise MethodNotAllowedError('LDAP is only supported in the '
                                        'Cloudify premium edition.')
        ldap_config = rest_utils.get_json_and_verify_params({
            'ldap_server',
            'ldap_username',
            'ldap_password',
            'ldap_domain',
            'ldap_is_active_directory',
            'ldap_dn_extra'
        })
        return ldap_config
