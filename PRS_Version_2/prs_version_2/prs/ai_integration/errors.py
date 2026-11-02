"""Provider failures distinguished from patient-record errors."""


class ProviderError(Exception):
    """Base error at the optional AI boundary."""


class ProviderUnavailableError(ProviderError):
    """The configured model could not be reached or completed no response."""


class InvalidPredictionError(ProviderError):
    """The provider returned a malformed or unsupported prediction."""
