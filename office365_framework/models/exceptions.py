# See LICENSE file for full copyright and licensing details.
import logging

_logger = logging.getLogger(__name__)


class ParameterError(Exception):
    def __init__(self, msg, status_code=None):
        self.status_code = status_code
        
        _logger.error('AzureAD Provided parameters for request were incorrect: %s' % msg)

        super(ParameterError, self).__init__(msg)


class ScopeError(Exception):
    def __init__(self, msg, status_code=None):
        self.status_code = status_code
    
        _logger.error('AzureAD Permission scope was insufficient: %s' % msg)

        super(ScopeError, self).__init__(msg)


class ServerError(Exception):
    def __init__(self, msg, status_code=None):
        self.status_code = status_code
    
        _logger.error('AzureAD Server returned with an error: %s' % msg)

        super(ServerError, self).__init__(msg)


class ThrottleError(Exception):
    def __init__(self, msg, status_code=None):
        self.status_code = status_code
    
        _logger.warning('AzureAD User has reached throttle limit: %s' % msg)

        super(ThrottleError, self).__init__(msg)


class AlreadyExistsError(Exception):
    def __init__(self, msg, status_code=None):
        self.status_code = status_code
    
        _logger.warning('AzureAD User already has item: %s' % msg)

        super(AlreadyExistsError, self).__init__(msg)


class NotFoundError(Exception):
    def __init__(self, msg, status_code=None):
        self.status_code = status_code
    
        _logger.warning('AzureAD Requested item was not found: 404')

        super(NotFoundError, self).__init__(msg)


class ItemGoneError(Exception):
    def __init__(self, msg, status_code=None):
        self.status_code = status_code
    
        _logger.warning('AzureAD Requested item was gone: 404')

        super(ItemGoneError, self).__init__(msg)


class AuthenticationError(Exception):
    def __init__(self, msg, status_code=None):
        self.status_code = status_code
    
        _logger.warning('AzureAD User is not correctly logged in: %s' % msg)

        super(AuthenticationError, self).__init__(msg)
